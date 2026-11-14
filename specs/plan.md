# Plan

How the spec is built. One process, one container, no agent framework.

## 1. Components

| File | Role | Requirement |
|---|---|---|
| `src/app/schemas.py` | Typed contracts: `ChatRequest`, `ChatResponse`, `Plan`, `Step`, `AgentResult`, `Health`, `Metrics` | R1 |
| `src/app/guardrails.py` | Masks, injection patterns, language, fixed texts, data blocks | R7, R12 |
| `src/app/llm.py` | The only door to a model. Providers by `LLM_PROVIDER`: `anthropic`, `openrouter`, `claude_cli` (no key), `fake` (tests) | R11 |
| `src/app/retriever.py` | BM25 over `data/corpus.jsonl`, built offline by `scripts/ingest.py` from `data/sources.txt` | R3 |
| `src/app/tools.py` | General tools and merchant tools bound to the `user_id`; ticket file | R4, R5, R6 |
| `src/app/embeddings.py`, `router_clf.py` | Local route classifier: letters (TF-IDF) and meaning (sentence vector), probabilities averaged | R2 |
| `src/app/jev.py` | Optional second router (Jev decision model) | R2 |
| `src/app/agents.py` | The agents as functions that return `AgentResult`; LLM router; verifier; final writer | R3 to R6, R8 |
| `src/app/orchestrator.py` | `handle(req)`: the whole flow in one function | R1, R2, R6, R8, R9 |
| `src/app/api.py` | FastAPI: `/chat`, `/health`, `/metrics`, Swagger with the scenarios as examples | R1, R9 |
| `evals/` | Datasets and runner | R10 |

## 2. Flow of one request
1. Mask the message (card, CPF, CNPJ, e-mail, phone). Injection detected: fixed refusal, no model call.
2. Plan: rule (escalate; or support then knowledge) → classifier → Jev (optional) → language model. The last three can also answer "no agent" (out of scope): fixed out-of-scope text.
3. Run the agents in order. Each gets the original masked message and the facts so far.
4. A knowledge answer is verified against its evidence: fast model first; if it rejects, the main model checks; discarded only when both reject.
5. Any agent error or exception: escalate with a ticket (see R6 for the one exception).
6. One fact: returned as is. Several: joined by a model; if the joined text loses a cited URL, the facts are returned whole.
7. Mask the answer, log one JSON line, count metrics.

## 3. Decisions

| Id | Decision | Alternative not taken, and why |
|---|---|---|
| D1 | Direct function calls with typed `Plan` and `AgentResult` | A queue or an agent framework: one synchronous request with at most three steps has nothing to decouple, and a failure is a field the orchestrator turns into a handoff |
| D2 | Routing cascade, cheapest first | One LLM router for everything: slower and paid on every message |
| D3 | Classifier trained on generated sentences, validated by template group | Random split: variations of one sentence fall in train and test and inflate the number |
| D4 | BM25 with a small English-Portuguese glossary | Vector search: measured on this base, it found no more pages |
| D5 | The knowledge agent answers only from evidence with a URL, and a second check verifies it | Trusting the model's memory about products and fees |
| D6 | `user_id` bound in code, absent from every tool schema | Passing it as a tool argument: a message could ask for another account |
| D7 | Handoff on doubt | An answer with a caveat: an unsupported statement about money is worse than a ticket |
| D8 | The corpus is committed | Scraping at start-up: the container would depend on the Getnet sites being reachable |
| D9 | Output limit leaves room for the model's reasoning, and a cut answer is an error | A tight limit: reasoning counts in it and the answer is delivered cut |

## 4. Test practice
Every task ships with its test file, and its tests pass before the commit. Tests need no key: `LLM_PROVIDER=fake` checks the plumbing; quality with a real model is the evaluation of R10.
