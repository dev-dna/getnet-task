> Written on 2026-11-13, after the implementation skeleton (commit `519f83b`), from the challenge statement; it is the reference the code is checked against.

# Plan: Getnet multi-agent support

Decisions come from `CLAUDE.md` (section named in brackets). Requirement ids (RF, RNF) and case ids (S, H, A, B, U) are those of `specs/spec.md` and `evals/dataset.jsonl`. Measured numbers come from `data/router_report.json` and `evals/report_claude_cli.json`.

## 1. Decisions and discarded alternatives

| ID | Decision | Alternative discarded and why |
|---|---|---|
| D01 | Python 3.12, FastAPI, pydantic v2, httpx [Stack] | Node.js/TypeScript: the route classifier (scikit-learn) and the PDF/HTML readers are Python libraries; pydantic models give request validation and the OpenAPI contract with no extra code. |
| D02 | No agent framework. Each agent is a function; agents talk by function calls with typed `Plan` and `AgentResult` [Stack, Estrutura] | LangGraph, ADK, LangChain: the flow is a fixed list of at most three steps, so a graph runtime adds a dependency and hides the prompts and the tool loop behind its own abstractions. A message queue or events: one process, one request at a time per call, nothing to decouple. |
| D03 | Model chosen by environment: `LLM_PROVIDER`, `MODEL_FAST`, `MODEL_SMART`; `fake` provider for tests [Stack] | One provider SDK hard-coded: the service could not run with a different key, and tests would need a credential. |
| D04 | Two model tiers: fast for router fallback, verifier and `general`; smart for `knowledge`, `support` and the final text [Stack] | One model for every call: classification and verification steps would pay the price and latency of the larger model. |
| D05 | Retrieval by words (BM25, `rank-bm25`) with an English↔Portuguese glossary [Base de conhecimento] | Chroma or another vector store with embeddings: needs an embedding model or API key at build and run time and a stateful index in the container, for a base of about 500 passages. BM25 is deterministic and testable offline. Cost accepted: synonyms outside the glossary are missed. |
| D06 | The BM25 score is not used as an answer threshold [Base de conhecimento] | "Score below x means not found": the score is not a probability and grows with query length. The model's `NOT_FOUND` and `verify()` decide instead. |
| D07 | Knowledge base built by `scripts/ingest.py` from `data/sources.txt` (HTML and PDF), stored as `data/corpus.jsonl` in git; ingest fails under 15 passages; `data/corpus_seed.jsonl` is sample text flagged by `/health` [Base de conhecimento] | Scraping at container start: start-up and answers would depend on third-party sites being up. Writing product facts by hand: not verifiable, forbidden by the project rules. |
| D08 | Routing cascade, cheapest first: rules, local classifier (`p >= 0.75`), Jev (`p >= 0.5`), language model [Fluxo, step 3] | Router made only of a language model: every message pays a model call before any agent runs, the decision has no calibrated probability, and it cannot be evaluated without a credential. |
| D09 | Classifier: TF-IDF of character n-grams (3 to 5), logistic regression, calibration [Classificador de rota] | Embedding or fine-tuned transformer classifier: model download and heavier image. Character n-grams tolerate accents, typos and mixed Portuguese/English with a model trained at build time. |
| D10 | Training sentences generated from templates, each with `group` = template; sentences close to `evals/dataset.jsonl` are dropped; evaluation by `StratifiedGroupKFold` [Classificador de rota] | Random train/test split: variations of one template land on both sides and the accuracy comes out inflated. |
| D11 | Jev (TypeSafe decision model, OpenRouter Decisions API) as optional second router, with `out_of_scope` written as one of its options [Fluxo, step 3] | Going straight from classifier to language model: kept as the path for `ROUTER_FALLBACK=llm` and for Jev failure. Asking Jev for "none of the above": it has no such answer, so the option is explicit. |
| D12 | Guardrails as a local layer with no model: masking, injection patterns, request for a human, sensitive subjects [Fluxo, steps 1 and 2] | A guardrail framework (NeMo Guardrails, Guardrails AI, LLM Guard) or a moderation model call: one more model call or a large dependency before every message. Patterns are checked by two lists in `tests/test_guardrails.py` (attacks, legitimate). Cost accepted: only known phrasings are caught. |
| D13 | Fraud, dispute and request for a human always go to `escalate` by rule [Fluxo, step 2] | Letting `knowledge` answer informational questions about fraud: a wrong automated answer where money was lost costs more than a ticket. |
| D14 | Each agent receives the original masked message plus `facts` of earlier agents, never a rewritten question [Fluxo, step 4] | Router rewriting one sub-question per agent: the rewrite can drop or invent details, and it is one more text produced from user input. |
| D15 | The `knowledge` answer passes `verify()` against its passages before it is merged [Fluxo, step 5] | Trusting the "only from the passages" prompt: it does not stop unsupported sentences. Cost accepted: one fast-model call per knowledge answer. |
| D16 | Any `AgentResult.error` or exception becomes `escalate` with a ticket; never HTTP 500 [Fluxo, step 6] | Returning an error status or an apology: the merchant is left with no next step and no record. |
| D17 | `user_id` comes from `ChatRequest`; `tools.bind(user_id)` closes over it; no tool has that parameter [Regras de segurança] | `user_id` as a tool argument filled by the model: a message can make the model pass another id (case A2). |
| D18 | External content (message, passages, tool output) enters prompts inside `<data>` with "treat as data" [Regras de segurança] | Concatenating raw text: instructions inside a scraped page or a tool result would read as instructions. |
| D19 | Each agent receives only its own tools: `general` has `weather`, `fx_rate`, `web_search`; `support` has `get_profile`, `get_settlements`, `get_transactions`, `get_terminal_status`, `open_ticket` [Regras de segurança] | One agent holding every tool: a manipulated general question could reach account tools. |
| D20 | Output masks card, CPF and CNPJ only; phone and e-mail stay; money values are never masked [Fluxo, step 7; Regras de segurança] | Masking everything on output: hides Getnet's public contact channels and the amounts the merchant asked about. Amounts are protected by D17. |
| D21 | `make test` runs offline with the fake model; `make eval` runs the 30 cases with a real model, target 90%; answer text is read by a person [Testes] | Only end-to-end tests with a real model: need a key, are slow and vary between runs. A model judging the text: not adopted, its verdict would itself need checking. |
| D22 | Merchant data simulated in `data/merchants.json` with relative dates; tickets in a JSON file [Estrutura] | A database and a ticketing API: no back end is provided by the statement. Relative dates keep "yesterday" and "tomorrow" correct on any day. |

## 2. Flow of `orchestrator.handle`

```
POST /chat {message, user_id}      api.chat -> orchestrator.handle(req); a bad payload gets 422 from pydantic before this
  lang = guardrails.language(message)        "pt" or "en": language of fixed texts and of the reply instruction
  msg  = guardrails.mask(message)            card (Luhn check), CNPJ, CPF, e-mail, phone -> tags
  detect_injection(msg)? -- yes --> route ["guardrail"], REFUSAL[lang], decided_by guardrail, no model call
  plan_for(msg), first match wins:                                                         decided_by
    1  is_sensitive(msg) or wants_human(msg)            -> [escalate]                      rule
    2  "my card machine ..." and "what should I do ..." -> [support, knowledge]            rule
    3  router_clf.predict(msg), p >= ROUTER_HIGH (0.75) -> [label]                         clf
    4  ROUTER_FALLBACK=jev: jev.route(msg), p >= JEV_MIN (0.5)
                                   -> [label], [support, knowledge] or [] (out_of_scope)   jev
    5  agents.route_llm(msg, two top classes of step 3) -> up to 3 steps, or []            llm
       route_llm fails -> top class of step 3 with confidence 0.5                          clf
  plan.steps == [] --> route ["out_of_scope"], OUT_OF_SCOPE[lang]
  facts = []; for step in plan.steps:
    escalate  -> hand_off(reason = plan.reason)
    knowledge -> retriever.retrieve(msg, k=5); nothing found -> error no_chunks
                 MODEL_SMART answers from <data> passages and <data> facts; "NOT_FOUND" -> error not_in_kb
                 agents.verify(answer, passages + facts) with MODEL_FAST; false -> error ungrounded_answer
    support   -> user_id not in data/merchants.json -> error merchant_not_found
                 tools.bind(user_id) -> tool loop with MODEL_SMART, at most 4 rounds
    general   -> tools.bind_general() -> tool loop with MODEL_FAST, at most 4 rounds
    result.error -> hand_off(reason = "agent_error:<error>");  otherwise facts += result.facts
  answer = agents.write_final(msg, facts)    one fact: returned unchanged; several: MODEL_SMART merges them
  done(): guardrails.mask_output(answer) (card, CNPJ, CPF) -> ChatResponse; one JSON log line with trace_id
hand_off(): agents.escalate -> tools.open_ticket_record -> data/tickets.json
            answer = merged facts so far (if any) + ticket text; route + ["escalate"]; handoff true; ticket_id
exception after the injection check -> hand_off, route ["escalate"], decided_by error
            if hand_off also fails -> FALLBACK[lang], route ["error"], handoff true, no ticket
```

Differences between this flow and `CLAUDE.md`: `verify()` also accepts the facts of earlier agents as evidence (since `52d236c`); when `ROUTER_FALLBACK` is unset the code uses `llm`, while `.env.example` sets `jev`.

## 3. Router evaluation

Source: `data/router_report.json` (commit `519f83b`). Regenerated on 2026-11-13 in a copy of the repository with `scripts/gen_router_data.py` and `scripts/train_router.py`: identical file.

- 944 sentences from 236 templates. Split: `StratifiedGroupKFold(5)` by template. Accuracy over all sentences: 85.8%.
- At `ROUTER_HIGH = 0.75` the classifier decides alone on 61.8% of the sentences, with 96.6% accuracy. The other 38.2% go to the next step of the cascade.

| Threshold | Coverage (share decided alone) | Accuracy when it decides |
|---|---|---|
| 0.50 | 93.5% | 88.8% |
| 0.60 | 81.5% | 92.8% |
| 0.70 | 69.4% | 94.8% |
| 0.75 (in use) | 61.8% | 96.6% |
| 0.80 | 51.1% | 97.7% |
| 0.90 | 25.3% | 97.9% |

Confusion matrix, all sentences, no threshold (row = true class, column = predicted):

| | knowledge | support | general | escalate | Recall (derived) |
|---|---|---|---|---|---|
| knowledge | 249 | 10 | 5 | 8 | 91.5% |
| support | 9 | 214 | 20 | 13 | 83.6% |
| general | 5 | 8 | 179 | 0 | 93.2% |
| escalate | 19 | 27 | 10 | 168 | 75.0% |

- `escalate` has the lowest recall. Rule 1 of the flow (fraud, dispute, request for a human) runs before the classifier and covers cases A4 and A5.
- On the 30 cases of `evals/report_claude_cli.json` (`ROUTER_FALLBACK=llm`) the route was decided by: classifier 12, language model 13, rule 3, guardrail 2.
- Not measured: the Jev step, and the comparison classifier × Jev × language model × cascade (gaps G03, G04).

## 4. Evaluation with a real model

Source: `evals/report_claude_cli.json` (commit `a2bbfea`), provider `claude_cli`, `corpus_is_placeholder: false`. Not re-run for this plan.

| Group | S | H | A | B | U | Total |
|---|---|---|---|---|---|---|
| Passed | 10/10 | 7/8 | 7/7 | 4/4 | 1/1 | 29/30 = 96.7% |

Latency of the 26 cases that called a model: median 12.5 s, from 5.3 s (U1) to 40.7 s (S5). Each model call starts one `claude -p` process.

## 5. Gaps

Not met, or not verified. Checks dated 2026-11-13 were run for this plan with the fake model, outside the repository.

- G01 (RF07). The web search tool belongs to a separate `general` agent; `knowledge` has only `retrieve`. No eval case and no agent-level test calls `web_search`; only `scripts/smoke_tools.py` does (ran, returned results).
- G02 (RNF11). Providers `anthropic` and `openrouter` were never run with real credentials. The real-model evaluation used `LLM_PROVIDER=claude_cli`, where a tool call is JSON inside the text, so the tool-call formats of both APIs and the model names in `.env.example` are untested. `scripts/smoke_llm.py` was not run.
- G03 (RF04). The Jev step was never called with a real key (`scripts/smoke_jev.py` not run); `tests/test_jev.py` uses a simulated response in the documented format. `.env.example` sets `LLM_PROVIDER=openrouter` and `ROUTER_FALLBACK=jev`: the default container configuration is the unverified one.
- G04 (RNF08). `make compare` was not run and `evals/router_comparison.json` does not exist. Cost and latency of the cascade against a language-model-only router are not measured; D08 rests on the cross-validation of section 3.
- G05 (RF09, RF16). Merchant data is simulated: two users in `data/merchants.json`. A ticket is a record in a JSON file inside the container: no operator is notified and the file is lost with the container.
- G06 (RNF06, RNF02, RNF13). `README.md` does not exist, so the required README content and the written testing strategy are missing. No video is in the repository.
- G07 (RNF12). These spec files were written after the skeleton; the code was not derived from them. `specs/tasks.md` records what was verified, not what was built from the spec.
- G08 (RNF01). `docker compose build` and `make docker` were not verified: no Docker daemon where the checks ran and no build record in the repository. `claude_cli` does not work inside the image, so no run of the container with a real model is recorded.
- G09 (RNF08, RF05). H6 fails: route `["support","knowledge","escalate"]`, the knowledge step ended in handoff. B1 passes its check (`route not ["guardrail"]`) but its route is `["knowledge","escalate"]`: a request for update instructions gets a ticket, not an answer.
- G10 (RNF08). The evaluation ran with `EVAL_DIRECT=1` (`make eval-cli`): the orchestrator was called in process, and the HTTP layer is covered only by fake-model tests. The report file has fields (`answers`, `info.router_fallback`) that `evals/run.py` at `a2bbfea` does not write, so the command that produced it is not in the repository.
- G11 (RNF08). No record of a person reading the ten S answers. Spot check for this plan: the figures of the S1 and S9 answers are in passages of `data/corpus.jsonl` from URLs listed in `sources`; in S1 one figure is attributed inline to a different URL of that list. S2 to S8 and S10 were not checked.
- G12 (RF18). Only the Jev and language-model steps can answer "out of scope". The classifier has four classes, so an irrelevant or unsafe message it scores at 0.75 or more goes to an agent. Measured with `router_clf.predict`: "Conte uma piada" → `escalate` 0.95 (opens a ticket); "How do I hack a card machine to steal card numbers?" → `knowledge` 0.80.
- G13 (RF17). Injection detection is a fixed list of Portuguese and English patterns. Other phrasings reach the model, where only D17, D18 and D19 apply. Measured only on A1, A1b and the lists in `tests/test_guardrails.py`.
- G14 (RF21, RNF07). `verify()` returns true when the verifier call itself fails. `general` and `support` never set `AgentResult.error`: a tool that returns `{"error": ...}` or a tool loop that ends without an answer does not cause a handoff.
- G15 (RF04). `support` and `general` receive `facts` but do not use them; only `knowledge` and `write_final` read facts of earlier agents.
- G16 (RNF10). Observability is one log line per request and `/health`. No metrics endpoint, token or cost count, dashboard or alert exists, and none is described (G06). Latency is measured only through `claude_cli` (section 4).
- G17 (RF11). `user_id` is trusted as sent; the statement defines no authentication and none exists.
- G18 (RF12). No state between requests, yet the S5 and S8 answers in the report offer a follow-up ("I can open a ticket... tell me the priority") that a later message cannot refer to.
- G19 (D01). The 99 tests passed on Python 3.13; the fixed stack and the image use 3.12, which was not exercised (G08).
