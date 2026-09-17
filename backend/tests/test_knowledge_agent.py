from __future__ import annotations

import pytest

from app.agents.base import AgentContext
from app.agents.knowledge import KnowledgeExtractionAgent


@pytest.mark.asyncio
async def test_extracts_technologies_and_metrics() -> None:
    chunks = [
        {
            "document_id": "doc-a",
            "ordinal": 0,
            "text": (
                "Cloud Engineer with 5 years of experience. "
                "Built distributed systems on AWS using Kubernetes and Terraform. "
                "Reduced deployment time by 70% by shipping CI/CD on GitHub Actions."
            ),
        },
        {
            "document_id": "doc-b",
            "ordinal": 0,
            "text": (
                "Job description: We seek a Cloud Engineer skilled in AWS, "
                "Kubernetes, and PostgreSQL. Handles 5000 requests/second at p99 "
                "latency under 50ms."
            ),
        },
    ]
    agent = KnowledgeExtractionAgent()
    result = await agent.execute(
        AgentContext(user_id="u", project_id="p"),
        tools={"chunks": chunks},
    )
    assert result.status == "success"
    labels = {(item["kind"], item["label"].lower()) for item in result.result["items"]}
    kinds = result.result["kinds"]

    assert kinds.get("technology", 0) >= 3
    # Dedupe: aws / kubernetes appear in both chunks, should collapse.
    tech_labels = {label for kind, label in labels if kind == "technology"}
    assert "aws" in tech_labels
    assert "kubernetes" in tech_labels
    assert "terraform" in tech_labels
    # Metric extraction picked up the percent value.
    assert kinds.get("metric", 0) >= 1
    # Role hint fired.
    assert kinds.get("role", 0) >= 1


@pytest.mark.asyncio
async def test_deduplicates_across_chunks() -> None:
    chunks = [
        {"document_id": "d1", "ordinal": 0, "text": "AWS everywhere"},
        {"document_id": "d2", "ordinal": 1, "text": "aws AWS aws"},
    ]
    result = await KnowledgeExtractionAgent().execute(
        AgentContext(user_id="u", project_id="p"),
        tools={"chunks": chunks},
    )
    tech_items = [i for i in result.result["items"] if i["kind"] == "technology"]
    aws_items = [i for i in tech_items if i["label"] == "aws"]
    assert len(aws_items) == 1


@pytest.mark.asyncio
async def test_empty_chunks_yields_no_items() -> None:
    result = await KnowledgeExtractionAgent().execute(
        AgentContext(user_id="u", project_id="p"),
        tools={"chunks": []},
    )
    assert result.status == "success"
    assert result.result["items"] == []
    assert result.confidence == 0.0
