# Evaluation

Authoritative source: `AGENT.md` §26–28, §39–40, §61, §63.

## Principles

- Never return a single unexplained score. Every evaluation carries per-dimension scores + evidence + confidence.
- Prefer "I don't have enough evidence" over confident fabrication (§39).
- Readiness (§27) is derived, deterministic where practical, and documented. It is **not** an LLM prompt asking "how ready 0–100?".

## Default scoring profile (§26)

| Dimension    | Weight |
|--------------|--------|
| Accuracy     | 30%    |
| Completeness | 20%    |
| Relevance    | 15%    |
| Conciseness  | 10%    |
| Evidence     | 10%    |
| Communication| 10%    |
| Response Time| 5%     |

Weights re-balance by session mode (technical interview, pitch, etc. — §26).

## Readiness formula (TBD — must be written before Evaluator agent lands)

Inputs to consider (§27): topic mastery, recency, difficulty, consistency, weakness severity, pressure handling, response quality, coverage.

Track this decision here.

## Consensus (§40)

Reserved for mock interviews, pitch simulations, Final Boss, and important readiness snapshots. Do not run consensus on every flashcard.

## Eval dataset (§63)

Planned at `backend/tests/evals/`:
- `interview_questions.json`
- `expected_scores.json`
- `retrieval_cases.json`
- `prompt_injection_cases.json`
- `contradiction_cases.json`
