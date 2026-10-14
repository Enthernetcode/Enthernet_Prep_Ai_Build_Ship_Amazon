# Evaluation

How the Evaluator Agent scores answers and how the Readiness Engine combines them. Implemented in `backend/app/agents/evaluator.py` and `backend/app/readiness.py`.

## Principles

- Every evaluation carries per-dimension scores + overall + weights, never a single unexplained number.
- Scores are deterministic Python (lexical + structural heuristics). An LLM may wrap them in natural-language rationale, but it does **not** replace them.
- Readiness is a function of mastery, dimension history, difficulty, weakness, and coverage. not a prompt asking "how ready, 0–100?".

## Rubric dimensions (per answer)

Default weights (`_DEFAULT_WEIGHTS` in `evaluator.py`):

| Dimension | Weight |
|---|---|
| Accuracy | 30% |
| Completeness | 20% |
| Relevance | 15% |
| Conciseness | 10% |
| Evidence | 10% |
| Communication | 10% |
| Response Time | 5% |

Mode-specific overrides live in `_MODE_WEIGHTS` (currently `mock_interview`, `final_boss`, `pitch`, `weakness_drill`). Weights are normalised at call time so adding/removing dimensions doesn't break the sum.

Every dimension is a pure function of the answer text, the question topic, the grounding chunk, difficulty, and (when supplied) seconds taken:

- **Accuracy** = `0.25 + 0.75·lexical_overlap(answer, grounding) − 0.3·denial_hits`.
- **Completeness**: target word count scales with difficulty.
- **Relevance**: overlap between answer tokens and topic tokens.
- **Conciseness**: penalises very short / very long answers + common filler words.
- **Evidence**: rewards numbers, percentages, and concrete framing hints.
- **Communication**: average sentence length window + caps-ratio penalty.
- **Response Time**: target seconds scales with difficulty.

Dimensions outside the response shape (`consistency`, `clarity`, `business_impact`) are computed too, so modes that re-weight them (e.g., `pitch`) have the numbers available.

## Optional LLM rationale

When `tools["llm_provider"]` is passed to `EvaluatorAgent.execute` and `.name != "mock"`, the evaluator calls `provider.generate(...)` with a short coach-persona system prompt and returns an additional `rationale` field: 1–2 sentences explaining what the candidate did well and what to tighten.

- Scores are **not** affected. The rationale sits beside them, with a `rationale_source` field (`"none"`, `"openai"`, `"bedrock"`) so clients can tell.
- Silent-fallback: any exception from the provider causes `rationale` to be omitted and `rationale_source` to stay `"none"`. The tool call never fails because of an LLM error.
- Covered by `backend/tests/test_llm_wired_agents.py`.

## Readiness Engine (`app/readiness.py`)

Combines per-user state into a 7-dimension snapshot plus an overall score. All deterministic.

Inputs:

- `competency_mastery`: mastery per competency (0..1), updated on each answer as a running average weighted by attempts.
- `competency_attempts`: attempts per competency (for coverage).
- `recent_dimension_scores`: the last N (default 12) turn evaluations.
- `weakness_severity`: bucket → severity (0..1) from the Weakness Agent.
- `difficulty_history`: list of difficulties the user has been asked at.
- `total_competencies`: denominator for coverage.

Outputs (all 0..1):

| Field | Formula |
|---|---|
| `knowledge` | `0.6·weighted_recent(accuracy) + 0.25·weighted_recent(completeness) + 0.15·mean(mastery)` |
| `communication` | `weighted_recent(communication)` |
| `evidence` | `weighted_recent(evidence)` |
| `conciseness` | `weighted_recent(conciseness)` |
| `pressure` | `weighted_recent(response_time) · (1 − min(1, pressure_severity · 0.5))` |
| `consistency` | `1 − 1.5·stddev(recent accuracy)` |
| `coverage` | `attempted_competencies / total_competencies` |
| `overall` | weighted sum of the above × `difficulty_factor` − `weakness_penalty` |

`weighted_recent` uses exponential recency weighting (`exp(0.35·i)`) so the newest turn weighs most.

`difficulty_factor` = `0.7 + mean(difficulty / 6) · 0.5`, clamped to `[0.3, 1.15]`. Users who answer harder questions correctly earn more.

`weakness_penalty` = up to 15% off the overall when a weakness bucket is above 0.75 severity. Prevents a user from gaming the score by cherry-picking easy competencies.

Baseline (before any turn) uses `baseline_from_coverage`: knowledge from `log10(1 + total_competencies)`, coverage pinned at 0, overall capped at 0.55 so readiness must be earned by performance.

## Consistency with the §26/§27 spec

- Weights match the default rubric.
- The readiness formula is deterministic and the inputs come from the state the agents already maintain. no hidden LLM prompt producing the number.
- `test_readiness_engine.py` locks the behaviour: identical inputs produce identical scores; coverage reflects attempted ratio; weakness penalty lowers overall; baseline is modest without performance.
