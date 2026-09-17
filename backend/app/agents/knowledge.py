from __future__ import annotations

import re
from typing import Any

from app.agents.base import Agent, AgentContext, AgentResult


_STOP = {
    "the","and","for","with","that","this","from","have","has","was","were",
    "into","then","than","them","they","their","there","which","while","when",
    "you","your","yours","our","ours","are","not","but","also","been","being",
    "will","would","could","should","must","may","can","using","use","used",
    "very","much","many","some","any","all","one","two","three","first","second",
    "over","under","above","below","between","across","after","before","during",
    "about","against","along","although","among","around","because","without",
    "within","upon","per","via","etc","its","it's","yet","so","just",
}

_METRIC = re.compile(
    r"\b(?:(?:reduced|increased|improved|cut|grew|shipped|handled|processed|delivered)\s+)?"
    r"(?:by\s+|to\s+|~|about\s+)?"
    r"(?:\$|£|€)?\d[\d,\.]*\s*"
    r"(?:%|percent|k|K|m|M|b|B|ms|s|sec|seconds|minutes|hours|users|requests|req/s|rps|qps|tps)\b",
    re.IGNORECASE,
)

_YEARS = re.compile(r"\b(19|20)\d{2}\b")

# Very common tech/skill tokens — deliberately narrow so we don't hallucinate.
_TECH = {
    "aws","gcp","azure","kubernetes","k8s","docker","terraform","ansible",
    "postgres","postgresql","mysql","mongodb","redis","kafka","rabbitmq",
    "python","javascript","typescript","java","golang","go","rust","c++","c#","ruby",
    "django","flask","fastapi","react","nextjs","next.js","node","node.js","spring",
    "graphql","rest","grpc","oauth","jwt","saml",
    "ci","cd","ci/cd","github","gitlab","jenkins","circleci",
    "s3","ec2","lambda","dynamodb","rds","cloudfront","iam","vpc","sqs","sns",
    "prometheus","grafana","opentelemetry","otel","datadog",
    "linux","bash","nginx","haproxy","envoy","istio",
    "hadoop","spark","airflow","snowflake","bigquery","redshift","dbt",
    "pandas","numpy","pytorch","tensorflow","scikit-learn","huggingface",
    "elasticsearch","opensearch","pgvector","llm","rag","embedding","vector",
    "iac","microservices","serverless","event-driven",
    "networking","security","observability","monitoring","logging",
    "sre","devops","backend","frontend","full-stack","mobile","ios","android",
}

_ROLE_HINT = re.compile(
    r"\b("
    r"cloud engineer|software engineer|backend engineer|frontend engineer|"
    r"full[- ]stack engineer|data engineer|ml engineer|machine learning engineer|"
    r"site reliability engineer|sre|devops engineer|security engineer|"
    r"platform engineer|solutions architect|solution architect|engineering manager|"
    r"product manager|technical program manager|tpm|founder|cto|cio|ceo"
    r")\b",
    re.IGNORECASE,
)

_SKILL_HINT = re.compile(
    r"\b(experience with|proficient in|skilled in|hands[- ]on with|built|designed|"
    r"led|owned|migrated|scaled|deployed|optimi[sz]ed|automated|architected)\b",
    re.IGNORECASE,
)


def _tokens(text: str) -> list[str]:
    return [
        t.lower()
        for t in re.findall(r"[A-Za-z][A-Za-z0-9\+\-#\.]+", text)
        if len(t) > 2 and t.lower() not in _STOP
    ]


def _extract_from_chunk(text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for m in _METRIC.finditer(text):
        span = m.group(0).strip()
        items.append({"kind": "metric", "label": span[:200], "confidence": 0.7})

    for m in _ROLE_HINT.finditer(text):
        items.append(
            {"kind": "role", "label": m.group(1).lower().strip(), "confidence": 0.85}
        )

    lowered = text.lower()
    seen_tech = set()
    for tech in _TECH:
        if tech in seen_tech:
            continue
        pattern = r"(?<![A-Za-z0-9])" + re.escape(tech) + r"(?![A-Za-z0-9])"
        if re.search(pattern, lowered):
            items.append({"kind": "technology", "label": tech, "confidence": 0.9})
            seen_tech.add(tech)

    for m in _SKILL_HINT.finditer(text):
        start = m.end()
        window = text[start:start + 140].strip().rstrip(".;\n")
        snippet = " ".join(window.split())
        if not snippet:
            continue
        # First noun-ish clause up to 90 chars.
        snippet = snippet.split(".")[0]
        snippet = snippet.split(",")[0][:120]
        if len(snippet) < 4:
            continue
        items.append(
            {
                "kind": "skill",
                "label": f"{m.group(1).lower()} {snippet}"[:200],
                "confidence": 0.55,
            }
        )

    for m in _YEARS.finditer(text):
        items.append(
            {"kind": "fact", "label": f"date reference {m.group(0)}", "confidence": 0.3}
        )

    return items


class KnowledgeExtractionAgent(Agent):
    """§12 Knowledge Extraction Agent.

    Deterministic-first: pure heuristics over chunk text so the demo works with
    the mock provider. When an LLM provider is present the caller can pass an
    already-enriched list through `tools["prepend"]` and this agent will merge.
    """

    name = "knowledge"
    description = "Extract concepts, skills, technologies, metrics from chunks."

    async def execute(self, context: AgentContext, tools: dict[str, Any]) -> AgentResult:
        chunks: list[dict[str, Any]] = tools.get("chunks", [])
        preloaded: list[dict[str, Any]] = tools.get("prepend", [])

        extracted: list[dict[str, Any]] = list(preloaded)
        for chunk in chunks:
            items = _extract_from_chunk(chunk["text"])
            for item in items:
                item["source_document_id"] = chunk.get("document_id")
                item["source_chunk_ordinal"] = chunk.get("ordinal")
                extracted.append(item)

        # Deduplicate by (kind, normalised label). Keep highest confidence.
        merged: dict[tuple[str, str], dict[str, Any]] = {}
        for item in extracted:
            key = (item["kind"], item["label"].lower().strip())
            existing = merged.get(key)
            if existing is None or item["confidence"] > existing["confidence"]:
                merged[key] = item

        kinds_count: dict[str, int] = {}
        for item in merged.values():
            kinds_count[item["kind"]] = kinds_count.get(item["kind"], 0) + 1

        return AgentResult(
            agent=self.name,
            status="success",
            confidence=1.0 if merged else 0.0,
            result={
                "items": list(merged.values()),
                "kinds": kinds_count,
                "raw_count": len(extracted),
            },
        )
