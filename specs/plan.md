> Written on 2026-11-13, after the implementation skeleton (commit `519f83b`), from the challenge statement; it is the reference the code is checked against.

# Plan: Getnet multi-agent support

Decisions come from `CLAUDE.md` (section named in brackets). Requirement ids (RF, RNF) and case ids (S, H, A, B, U) are those of `specs/spec.md` and `evals/dataset.jsonl`. Measured numbers come from `data/router_report.json` and `evals/report_claude_cli.json`.

## 1. Decisions and discarded alternatives

| ID | Decision | Alternative discarded and why |
|---|---|---|
| D01 | Python 3.12, FastAPI, pydantic v2, httpx [Stack] | Node.js/TypeScript: the route classifier (scikit-learn) and the PDF/HTML readers are Python libraries; pydantic models give request validation and the OpenAPI contract with no extra code. |
| D02 | No agent framework. Each agent is a function; agents talk by function calls with typed `Plan` and `AgentResult` [Stack, Estrutura] | LangGraph, ADK, LangChain: the flow is a fixed list of at most three steps, so a graph runtime adds a dependency and hides the prompts and the tool loop behind its own abstractions. A message queue or events: one process handles the whole request, so there is nothing to decouple. |
| D03 | Model chosen by environment: `LLM_PROVIDER`, `MODEL_FAST`, `MODEL_SMART`; `fake` provider for tests [Stack] | One provider SDK hard-coded: the service could not run with a different key, and tests would need a credential. |
| D04 | Two model tiers: fast for router fallback, verifier and `general`; smart for `knowledge`, `support` and the final text [Stack] | One model for every call: classification and verification steps would pay the price and latency of the larger model. |
| D05 | Retrieval by words (BM25, `rank-bm25`) with an English↔Portuguese glossary [Base de conhecimento] | Chroma or another vector store with embeddings: needs an embedding model or API key at build and run time and a stateful index in the container, for a base of about 500 passages. BM25 is deterministic and testable offline. Cost accepted: synonyms outside the glossary are missed. A search by meaning with the same embedding model was measured on 2026-11-14 on 28 product questions (script not in the repository): interleaved with BM25 it reached the right page in 27, against 28 for BM25 with the glossary, because the model puts same-language texts closer. Not adopted. |
| D06 | The BM25 score is not used as an answer threshold [Base de conhecimento] | "Score below x means not found": the score is not a probability and grows with query length. The model's `NOT_FOUND` and `verify()` decide instead. |
| D07 | Knowledge base built by `scripts/ingest.py` from `data/sources.txt` (HTML and PDF), stored as `data/corpus.jsonl` in git; ingest fails under 15 passages; `data/corpus_seed.jsonl` is sample text flagged by `/health` [Base de conhecimento] | Scraping at container start: start-up and answers would depend on third-party sites being up. Writing product facts by hand: not verifiable, forbidden by the project rules. |
| D08 | Routing cascade, cheapest first: rules, local classifier (`p >= 0.7`), Jev (`p >= 0.5`), language model [Fluxo, step 3] | Router made only of a language model: every message pays a model call before any agent runs, the decision has no calibrated probability, and it cannot be evaluated without a credential. |
| D09 | Classifier: two calibrated logistic regressions averaged, one on TF-IDF of character n-grams (3 to 5) and one on the sentence embedding of a multilingual model that runs on CPU (`fastembed`, since 2026-11-14) [Classificador de rota] | Letters alone (the first version): 0.858 accuracy against 0.923 for the average on the same folds; it missed synonyms. Cosine similarity to the nearest examples: tested, less accurate than a classifier on the same embeddings. A fine-tuned transformer or an embedding API: heavier image or one more key. Cost accepted: a 240 MB model downloaded at build. |
| D10 | Training sentences generated from templates, each with `group` = template; sentences close to `evals/dataset.jsonl` are dropped; evaluation by `StratifiedGroupKFold` [Classificador de rota] | Random train/test split: variations of one template land on both sides and the accuracy comes out inflated. |
| D11 | Jev (TypeSafe decision model, OpenRouter Decisions API) as optional second router, with `out_of_scope` written as one of its options [Fluxo, step 3] | Going straight from classifier to language model: kept as the path for `ROUTER_FALLBACK=llm` and for Jev failure. Asking Jev for "none of the above": it has no such answer, so the option is explicit. |
| D12 | Guardrails as a local layer with no model: masking, injection patterns, request for a human, sensitive subjects [Fluxo, steps 1 and 2] | A guardrail framework (NeMo Guardrails, Guardrails AI, LLM Guard) or a moderation model call: one more model call or a large dependency before every message. Patterns are checked by two lists in `tests/test_guardrails.py` (attacks, legitimate). Cost accepted: only known phrasings are caught. |
| D13 | Fraud, dispute and request for a human always go to `escalate` by rule [Fluxo, step 2] | Letting `knowledge` answer informational questions about fraud: a wrong automated answer where money was lost costs more than a ticket. |
| D14 | Each agent receives the original masked message plus `facts` of earlier agents, never a rewritten question [Fluxo, step 4] | Router rewriting one sub-question per agent: the rewrite can drop or invent details, and it is one more text produced from user input. |
| D15 | The `knowledge` answer passes `verify()` against its passages before it is merged [Fluxo, step 5] | Trusting the "only from the passages" prompt: it does not stop unsupported sentences. Cost accepted: one fast-model call per knowledge answer. |
| D16 | Any `AgentResult.error` or exception becomes `escalate` with a ticket; never HTTP 500 [Fluxo, step 6]. Exception since 2026-11-14 (H6, V5c, V8c): a `knowledge` error after another agent already produced facts delivers those facts with a fixed notice, without a ticket | Returning an error status or an apology: the merchant is left with no next step and no record. |
| D17 | `user_id` comes from `ChatRequest`; `tools.bind(user_id)` closes over it; no tool has that parameter [Regras de segurança] | `user_id` as a tool argument filled by the model: a message can make the model pass another id (case A2). |
| D18 | External content (message, passages, tool output) enters prompts inside `<data>` with "treat as data" [Regras de segurança] | Concatenating raw text: instructions inside a scraped page or a tool result would read as instructions. |
| D19 | Each agent receives only its own tools: `knowledge` has `retrieve` and, as fallback, `web_search` kept to the official sites (both called in code, since 2026-11-14); `general` has `weather`, `fx_rate`, `web_search`; `support` has `get_profile`, `get_settlements`, `get_transactions`, `get_terminal_status`, `open_ticket` [Regras de segurança] | One agent holding every tool: a manipulated general question could reach account tools. |
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
    3  router_clf.predict(msg), p >= ROUTER_HIGH (0.7)  -> [label] or [] (out_of_scope)    clf
    4  ROUTER_FALLBACK=jev: jev.route(msg), p >= JEV_MIN (0.5)
                                   -> [label], [support, knowledge] or [] (out_of_scope)   jev
    5  agents.route_llm(msg, two top classes of step 3) -> up to 3 steps, or []            llm
       route_llm fails -> top class of step 3 with confidence 0.5; out_of_scope -> []      clf
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

Differences between this flow and `CLAUDE.md`: `verify()` also accepts the facts of earlier agents as evidence (since `52d236c`); when `ROUTER_FALLBACK` is unset the code uses `llm`; `.env.example` also sets `llm` since 2026-11-14 (it set `jev` before; G03).

## 3. Router evaluation

Source: `data/router_report.json`, regenerated on 2026-11-14 with `scripts/gen_router_data.py` and `scripts/train_router.py` after the classifier on meaning was added (D09) and 8 support templates about another account's data (case A2).

- 1320 sentences from 330 templates. Split: `StratifiedGroupKFold(5)` by template.
- Accuracy over all sentences: letters alone 85.8%, meaning alone 91.0%, the average of the two 92.3%.
- At `ROUTER_HIGH = 0.7` the average decides alone on 62.4% of the sentences, with 98.2% accuracy. The other 37.6% go to the next step. Letters alone at 0.75: 51.2% with 98.4%.

| Threshold (average) | Coverage (share decided alone) | Accuracy when it decides |
|---|---|---|
| 0.50 | 92.3% | 95.6% |
| 0.60 | 80.4% | 97.5% |
| 0.70 (in use) | 62.4% | 98.2% |
| 0.75 | 52.9% | 98.9% |
| 0.80 | 41.3% | 99.8% |
| 0.90 | 14.4% | 100.0% |

Confusion matrix of the average, all sentences, no threshold (row = true class, column = predicted):

| | knowledge | support | general | escalate | out_of_scope | Recall (derived) |
|---|---|---|---|---|---|---|
| knowledge | 301 | 5 | 1 | 2 | 11 | 94.1% |
| support | 14 | 261 | 1 | 10 | 2 | 90.6% |
| general | 1 | 1 | 189 | 0 | 1 | 98.4% |
| escalate | 13 | 11 | 0 | 203 | 5 | 87.5% |
| out_of_scope | 22 | 0 | 0 | 1 | 265 | 92.0% |

- `escalate` has the lowest recall. Rule 1 of the flow (fraud, dispute, request for a human) runs before the classifier and covers cases A4 and A5.
- On the 72 test sentences (30 of `evals/dataset.jsonl`, 42 of `evals/variations.jsonl`) no decision the classifier takes alone is wrong.
- Not measured: the Jev step, and the comparison classifier × Jev × language model × cascade (gaps G03, G04).

## 4. Evaluation with a real model

Source: `evals/report_claude_cli.json` and `evals/report_variations_claude_cli.json`, written by `python evals/run.py --cli` on 2026-11-14 with the classifier of D09; provider `claude_cli`, `corpus_is_placeholder: false`. Results vary between runs.

| Group | S | H | A | B | U | Total | V (42 rewritten sentences) |
|---|---|---|---|---|---|---|---|
| Passed | 10/10 | 8/8 | 7/7 | 4/4 | 1/1 | 30/30 | 42/42 |

Route decided on the 30 cases by: classifier 19, language model 6, rule 3, guardrail 2. Latency of the 24 cases that called a model: median 13.7 s, from 8.1 to 41.1 s. Each model call starts one `claude -p` process.

## 5. Gaps

Not met, or not verified. "For this plan" means a check run on 2026-11-13 on the code of `a2bbfea` (later commits change no code), on Python 3.13, with no model credential; scripts that write files ran in a copy of the repository. `README.md` arrived later, in `c08218c`; where it reports a run, the item says so.

Checked and not a gap (RF06): `scripts/ingest.py` was re-run (exit 0, 502 passages, 64 sources). `https://www.getnet.net/` returns 2 passages equal to passages of `https://www.getnet.net/en`, so de-duplication stores them under the `/en` URL.

- G01 (RF07). Resolved in the spec as a normative split after the review (`855d670`): `general` owns non-Getnet facts. Narrowed on 2026-11-14: the knowledge agent now calls `web_search` when the base has no answer and keeps only results from `getnet.com.br` and `getnet.net`, so the Knowledge Agent has both retrieval paths of the statement; general-purpose questions still go to `general`. `tests/test_orchestrator.py` covers the fallback with simulated results (official result answers, unofficial or look-alike domain does not, failure hands off); no eval case exercises the real search, which returned nothing on 2026-11-14; `scripts/smoke_tools.py` got results from it in one run and none in another.
- G02 (RNF11). Half closed on 2026-11-14: the `openrouter` provider ran with a real key (`scripts/smoke_llm.py` passed; `evals/report_openrouter.json` has 23 of 30, the ten statement scenarios passed and every failure was an HTTP 402 of an account without credits). `anthropic` was not run. Text before that date: Providers `anthropic` and `openrouter` were never run with real credentials. The real-model evaluation used `LLM_PROVIDER=claude_cli`, where a tool call is JSON inside the text, so the tool-call formats of both APIs and the model names in `.env.example` are untested. `scripts/smoke_llm.py` was not run.
- G03 (RF04). Closed for the format on 2026-11-14: `scripts/smoke_jev.py` passed against the real endpoint (HTTP 200, the fields `jev.py` reads, 187 ms). Its accuracy is still not measured (G04). Text before that date: The Jev step was never called with a real key (`scripts/smoke_jev.py` not run); `tests/test_jev.py` uses a simulated response in the documented format, checked on 2026-11-14 against the official OpenRouter reference of the Decisions API (a refused question and a response in another shape both fall through to the language-model router). Until 2026-11-14 `.env.example` set `ROUTER_FALLBACK=jev`, so the default container configuration was the unverified one; it now sets `llm` and keeps `jev` as a commented option. `LLM_PROVIDER=openrouter` remains the default and remains unverified (G02).
- G04 (RNF08). `make compare` was not run and `evals/router_comparison.json` does not exist. Cost and latency of the cascade against a language-model-only router are not measured; D08 rests on the cross-validation of section 3.
- G05 (RF09, RF16). Merchant data is simulated: two users in `data/merchants.json`. A ticket is a record in a JSON file inside the container: no operator is notified and the file is lost with the container.
- G06 (RNF13, RNF02). No video is in the repository. `README.md` was added in `c08218c` with the sections RNF06 and RNF02 ask for; its text was not checked line by line against the code for this plan. The integration test in CI is described there, not set up.
- G07 (RNF12). These spec files were written after the skeleton; the code was not derived from them. `specs/tasks.md` records what was verified, not what was built from the spec.
- G08 (RNF01). `docker compose build` was not run for this plan (no Docker daemon). README section 8 reports a build and a run of the container with the fake model and a base image from a registry mirror; no build log is in the repository. `claude_cli` does not work inside the image, so no run of the container with a real model is recorded. The 99 tests were run for this plan on Python 3.13, not on the 3.12 of D01.
- G09 (RNF08, RF05). H6 failed until the search glossary gained entries for inflected and synonymous words ("recusando", "refused", "anticipation", "get online"): the knowledge step found no page and the case ended in handoff. With them, and with the classifier of D09, the stored runs of 2026-11-14 give 30/30 and 41/42 on the rewritten sentences of `evals/variations.jsonl` (earlier runs: 36 and 40). Still open: B1 passes its check (`route not ["guardrail"]`) but ends as `["knowledge","escalate"]`, a ticket instead of an answer; in the variations, one or two cases per run end in handoff after the knowledge step (V5c in the stored run; V4c and V8c in the one before).
- G10 (RNF08). Closed in part by `00d490c`: `evals/run.py` now writes the stored report (`answers`, `info.router_fallback`), so `make eval-cli` reproduces the file. Still open: that path sets `EVAL_DIRECT=1`, the orchestrator is called in process, and the HTTP layer is covered only by fake-model tests and by the container run reported in README section 8.
- G11 (RNF08). No record of a person reading the ten S answers. Spot check for this plan: the figures of the S1 and S9 answers are in passages of `data/corpus.jsonl` from URLs listed in `sources`; in S1 one figure is attributed inline to a different URL of that list. S2 to S8 and S10 were not checked.
- G12 (RF18). Fixed in part on 2026-11-13. Before, only the Jev and language-model steps could answer "out of scope": the classifier had four classes, so "Conte uma piada" went to `escalate` at 0.95 (a ticket) and "How do I hack a card machine to steal card numbers?" to `knowledge` at 0.80. Now the classifier has a fifth class, `out_of_scope`, with 72 templates (jokes, recipes, homework, coding, creative writing, horoscope, small talk; cloning or stealing cards, hacking a card machine, fraud, getting around limits). At 0.75 or more `plan_for` returns a plan with no steps: the fixed out-of-scope text, no agent. `route_llm` returns the same empty plan when the model call fails and `out_of_scope` is the classifier's first guess, or when the model names it as an agent. Measured with `router_clf.predict`: the joke → `out_of_scope` 0.89, the hack sentence → `out_of_scope` 0.84, A6 → `out_of_scope` 0.83; no S or H case is `out_of_scope` at 0.75 or more. Templates paraphrase the two sentences, so they do not measure generalization; section 3 does. Sports results stay in `general`, where a template already had them. 12 `knowledge` and 2 `escalate` templates were added at the boundary (cancel or refund a sale, bank details, password, sales limit, card data; a merchant whose account was hacked): without them such legitimate questions scored `out_of_scope` at 0.60 to 0.74. What remains:
  - Cost. On the 1000 sentences of the four agent classes the classifier decides alone on 50.2% (before: 61.8% of 944), so more messages pay for the next step. The split seed moves the share over all sentences: 46.9% to 51.6% in five seeds (before: 54.3% to 61.8%).
  - Rule 1 runs before the classifier. An unsafe request with one of its words gets a ticket, not a decline: "Como clonar um cartão de crédito?", "How do I commit fraud with a card machine?".
  - The classifier alone declines only what resembles a template. Of 38 hand-written out-of-scope sentences (they guided the templates: not a held-out set) it declines 15; 22 fall below 0.75 and depend on the next step (2 of them stop at rule 1); 1 goes to an agent: "Qual o sentido da vida?" → `general` 0.76.
  - False declines. In the cross-validation 1 of the 1000 agent-class sentences is predicted `out_of_scope` at 0.75 or more (a refund question whose template was held out); none of the 288 `out_of_scope` sentences goes to an agent at 0.75 or more. Of 66 hand-written legitimate sentences the classifier declines none; the highest `out_of_scope` probability is 0.55 ("Esqueci a senha do aplicativo, como recupero?"). When the model call fails, a message whose first guess is `out_of_scope` below 0.75 is declined too.
  - The evaluation with a real model (section 4) was not re-run with the five-class classifier.
  - The injection list is unchanged (G13).
- G13 (RF17). Injection detection is a fixed list of Portuguese and English patterns. Other phrasings reach the model, where only D17, D18 and D19 apply. Measured only on A1, A1b and the lists in `tests/test_guardrails.py`.
- G14 (RF21, RNF07). Second half closed by `f9ce408` and `9a674bd`: a tool loop without an answer, or a run where every tool call failed (after retries on 429 and 5xx), sets `AgentResult.error` in `general` and `support` and becomes a handoff. Still open, accepted: `verify()` returns true when the verifier call itself fails.
- G15 (RF04). `support` and `general` receive `facts` but do not use them; only `knowledge` and `write_final` read facts of earlier agents.
- G16 (RNF10). Observability is one log line per request (with the time of each agent since 2026-11-14), `/health` and, since 2026-11-14, `GET /metrics` with in-memory counters. No token or cost count, dashboard or alert exists; README section 8 describes the dashboards and alerts that would be built. Latency is measured only through `claude_cli` (section 4).
- G17 (RF11). `user_id` is trusted as sent; the statement defines no authentication and none exists.
- G18 (RF12). No state between requests, yet the S5 and S8 answers in the report offer a follow-up (S5: "Just tell me the priority you'd like") that a later message cannot refer to.
- G19 (RF14). Closed by `8b98c42`: language is decided by counting words of a Portuguese and an English list; A1b and "Boa tarde, a bobina acabou" are detected as Portuguese, and all 30 eval messages get their language. Still open: no eval case checks the language of the answer text, and a message with no word of either list defaults to English.
