# Spec

Written before any code of this branch, from the challenge statement "AI Hardcore Engineer - Multi-Agent Support System". Each requirement quotes the sentence of the statement it answers and names the check that proves it. Section 2 shows that every item of the statement is covered. The project rules in `CLAUDE.md` add the fixed stack and the security rules.

## 1. Goal
An HTTP service that answers messages of Getnet merchants with cooperating agents: a router, a knowledge agent (RAG over the Getnet sites), a customer-support agent (the merchant's own data, through tools), a general agent (weather, exchange rates, web) and a human-escalation agent.

## 2. Coverage of the statement

| Item of the statement | Where it is answered |
|---|---|
| At least three distinct agent types and a clear communication mechanism | R2 (router), R3 (knowledge), R5 (support), plus R4 and R6; mechanism: direct function calls with typed objects (`specs/plan.md`, D1) |
| Router Agent: entry point, chooses an agent or a sequence, manages workflow and data flow | R2, R8 |
| Knowledge Agent: retrieval (internal and external) and generation, grounded in the Getnet website | R3 |
| RAG plus a web search tool for general-purpose questions | R3 (web search on the official sites when the base has no answer), R4 (general-purpose questions: a separate agent with the same tool, so that a product answer never rests on an unofficial page) |
| Suggested source `https://www.getnet.net/en`, and other sources | R3; `data/sources.txt` lists that site and the Brazilian product pages, manuals and terms |
| Customer Support Agent: user data, at least 2 tools | R5 |
| API endpoint with `{message, user_id}` | R1 |
| Dockerfile, docker-compose | R11 |
| Testing strategy and integration testing | R10, `specs/plan.md` section 4, README section 9 (task T09 lists the required content) |
| Language and frameworks | Python, FastAPI; `specs/plan.md` section 1 |
| README: build, configure, run, tests, architecture, design choices, workflow, RAG pipeline, LLM tools | task T09, whose "done when" lists each of these |
| "high-quality prompts", "how you leveraged LLM tools" | R13 |
| Spec Driven Development, at most 60 minutes for the core | this folder, written before the code; the only time evidence is the timestamps of the start and end commits of the session. README section 10 says what the session is and what was developed before it |
| Video | recorded by the author; it has no task here because no code delivers it |
| Bonus: fourth agent | R6 |
| Bonus: guardrails | R7 |
| Bonus: human handoff | R6 |
| Bonus: evaluation and observability strategy, dashboards, alerts | R9, R10 (built); dashboards and alerts are described in the README, not built (task T09) |
| The ten example scenarios | section 4 |

## 3. Requirements

| Id | Statement | Requirement | Check |
|---|---|---|---|
| R1 | "Expose an HTTP endpoint (e.g., FastAPI) that accepts POST requests and returns a meaningful JSON response." | `POST /chat` takes `{message, user_id}` and returns JSON with `answer`, `route`, `decided_by`, `confidence`, `sources`, `tool_calls`, `handoff`, `ticket_id`, `trace_id`, `latency_ms`. An empty message or a missing `user_id` is HTTP 422. A failed agent, tool or model provider is never HTTP 500: it is a handoff. | `tests/test_orchestrator.py::test_http_contract`, `::test_provider_failure_becomes_handoff_not_http_500` |
| R2 | "Serves as the primary entry point for user messages. Analyzes each message and decides which specialized agent (or sequence of agents) should handle it" | Router: the entry point. It returns a plan of one to three agents in order, or no agent (out of scope: the classifier's fifth class, Jev's fifth option, or an empty plan from the language model). It decides in a cascade, cheapest step first: two fixed rules, then a local classifier when its probability is at least 0.7, then the Jev decision model when enabled and its probability is at least 0.5, then a language model. The response says which step decided. | `tests/test_router_clf.py`, `tests/test_jev.py` |
| R3 | "answering questions about Getnet's products and services grounded in the company's website"; "Uses a Retrieval Augmented Generation (RAG) approach plus a web search tool" | Knowledge agent: retrieves passages from a base scraped from the Getnet sites and answers only from them, citing the URL. When the base has no answer it searches the web and accepts only results from `getnet.com.br` and `getnet.net`. Deviation from the statement, on purpose: the statement gives this agent the web search "for general-purpose questions"; here its web search is kept to the official sites, and general-purpose questions go to the general agent (R4), so that an answer about a product never rests on an unofficial page. With no supported answer the case is handed off. Every answer is checked against its evidence before it is used. | `tests/test_retriever.py`, `tests/test_orchestrator.py -k "knowledge or web or ungrounded"` |
| R4 | "a web search tool for general-purpose questions", delivered as a separate agent (deviation stated in R3) | General agent: answers non-Getnet factual questions with tools: `weather(city, day)`, `fx_rate(pair)`, `web_search(query)`. A tool failure is a handoff, not an invented answer. | `tests/test_tools.py`, `tests/test_tool_failure.py` |
| R5 | "Provides customer support by retrieving relevant user data to resolve inquiries. Must create at least 2 tools." | Support agent: answers with the data of the merchant of the request through at least two tools: `get_profile`, `get_settlements`, `get_transactions`, `get_terminal_status`, `open_ticket`. No tool has a `user_id` parameter: the value comes from the request and is bound in code, so a message cannot read another merchant's data. An unknown merchant is a handoff. | `tests/test_tools.py::test_model_never_sees_user_id`, `::test_one_merchant_cannot_read_another` |
| R6 | Bonus: "Add a fourth custom agent ... such as a Human Escalation Agent"; "Add a redirect or human handoff mechanism for situations in which the system cannot confidently resolve the user's request." | Escalation agent: opens a ticket and answers with its id. Triggers: fraud, scam, chargeback, dispute, cloned or stolen card, account cancellation, an explicit request for a person, and any agent error. Exception: when another agent already answered with account data and the knowledge agent finds nothing, that answer is delivered with a fixed notice instead of a ticket. | `tests/test_orchestrator.py -k "escalat or account_answer"` |
| R7 | Bonus: "Implement guardrails to detect and handle unsafe, irrelevant, sensitive, or unsupported requests." | Guardrails: card, CPF, CNPJ, e-mail and phone are masked before any model sees the message; card, CPF and CNPJ are masked in the answer (e-mail and phone are not masked there: the base holds the public contact channels). Masked values are never restored. A prompt-injection attempt gets a fixed refusal with no model call. An irrelevant or unsafe request is declined. Message, passages and tool output enter prompts as data, and content cannot close its own data block. | `tests/test_guardrails.py` |
| R8 | "plus a clear communication mechanism between them (e.g., direct function calls, internal message queue, or event-driven)"; "managing the workflow and data flow between agents" | Communication is by direct function calls: the router returns a typed `Plan` and every agent returns a typed `AgentResult`. Sequence: "my card machine ... what should I do" runs support, then knowledge. Each agent receives the original masked message and the facts of earlier agents, never a rewritten question. The final answer cannot lose a source cited by an agent. | `tests/test_orchestrator.py -k "sequence or cited_source"` |
| R9 | Bonus: "Present an evaluation and observability strategy"; "traces, structured logs" | Observability: one JSON log line per request (trace id, route, who decided, tools, handoff, errors, time per agent, latency, no message text); `GET /health` (provider, configuration problem, last error, router mode, base size); `GET /metrics` (counters since start). | `tests/test_orchestrator.py -k "metrics or health or log_line"` |
| R10 | "Example Test Scenarios"; Bonus: "automated evaluation datasets, regression tests" | Evaluation: `evals/dataset.jsonl` has the ten statement scenarios (S), rewordings (H), attacks (A), look-alike attacks (B) and an unknown user (U); `evals/variations.jsonl` has rewritten sentences (V). `evals/run.py` checks route, tools, leaked strings and handoff. Target: at least 90% with a real model (`python evals/run.py --cli`). With the fake model the same runner only proves that the plumbing works. | `python evals/run.py --cli` |
| R11 | "Provide a Dockerfile (and docker-compose.yml if needed) so the application builds and runs with standard Docker commands." | Packaging: `docker compose up --build` builds and serves on port 8000; the classifier is trained in the build; the test suite runs without any API key. | `tests/test_packaging.py`, `make test` |
| R12 | Not in the statement. Derived: the example scenarios are in English and the Getnet pages are mostly in Portuguese. | The answer is in the language of the message (Portuguese or English). | `tests/test_guardrails.py -k language` |
| R13 | "high-quality prompts"; "how you leveraged LLM tools" | One short system prompt per agent, in `agents.py`; a line is added to a prompt only when an evaluation case fails, and the commit names the case. Each agent receives only its own tools, declared with a JSON Schema; the model asks for a tool, the handler runs in code, the result returns as data; at most 4 rounds. Retrieval is not chosen by the model: the knowledge agent always retrieves in code. | `tests/test_tools.py`, `tests/test_llm_cli.py`, `tests/test_tool_failure.py`; README section 3 |

## 4. The ten statement scenarios

| Id | Message | Expected route | Expected tools |
|---|---|---|---|
| S1 | What's the difference between the Get Clássica and the Get Smart? | knowledge | retrieve |
| S2 | What's the weather forecast in Porto Alegre tomorrow? | general | weather |
| S3 | When will the money from yesterday's sales be deposited? | support | get_settlements |
| S4 | Do I need a bank account to receive my sales via Pix? | knowledge | retrieve |
| S5 | My card machine won't connect to the internet, what should I do? | support, knowledge | get_terminal_status, retrieve |
| S6 | How does receivables advance (antecipação) work with Getnet? | knowledge | retrieve |
| S7 | What's the euro exchange rate today? | general | fx_rate |
| S8 | My card machine is showing a transaction decline error. | support (knowledge may follow) | either `get_transactions` or `get_terminal_status` is accepted: the message does not say whether the fault is in the sale or in the machine |
| S9 | How many installments can I split a sale into with the crediário? | knowledge | retrieve |
| S10 | Can I sell through WhatsApp using the Payment Link? | knowledge | retrieve |

All ten use `user_id` `cliente1988`.

## 5. Out of scope
Conversation memory (the statement's payload has only `message` and `user_id`, no conversation id; each request is independent), authentication, real merchant data (two simulated merchants in a file), a real help-desk queue (tickets are a file), dashboards and alerts (described in the README, not built).

## 6. Contracts

**Response fields.** `answer` string. `route` list of strings: the agents that ran, in order (`knowledge`, `support`, `general`, `escalate`), or `["guardrail"]`, `["out_of_scope"]`, `["error"]`. `decided_by` one of `guardrail`, `rule`, `clf`, `jev`, `llm`, `error`. `confidence` number from 0 to 1, reported by whoever decided. `sources` list of URLs or data-source names. `tool_calls` list of tool names in call order. `handoff` boolean. `ticket_id` string or null. `trace_id` string. `latency_ms` integer.

**Internal objects.** `Step {agent, question}`; `Plan {steps, confidence, source: rule|clf|jev|llm, reason}`; `AgentResult {agent, facts, sources, evidence, tool_calls, error}`. `error` is a name: `not_in_kb`, `no_chunks`, `ungrounded_answer`, `merchant_not_found`, `tool_failed`, `tool_loop_exhausted`. The language-model router answers JSON `{"steps": [{"agent", "question"}], "confidence", "reason"}`. Jev gets two questions in one call: a choice among the four agents and `out_of_scope`, and a yes/no on "reports a problem with the own machine and asks what to do". Mapping: `out_of_scope` is no agent; when the choice is `support` or `knowledge` and the yes/no probability is at least 0.5, the plan is support then knowledge; otherwise the plan is the one chosen agent. The verifier answers JSON `{"grounded": true|false, "why"}`: false only when a fact of the answer is absent from the evidence or contradicts it; a direct yes or no deduced from the passages is not a new fact; if the verifier call itself fails, the answer is released and the failure is logged.

**Rules (regular expressions over the lower-cased, accent-free message).** Rule 1, escalate: fraud, scam, chargeback, dispute (`contesta...`), cloned or stolen card, closing the account, or asking for a person (attendant, human, supervisor). Rule 2, support then knowledge: "my/minha/meu" near "machine/maquininha/terminal/reader" together with "what should I do / o que eu faço / how do I fix / como resolver". Injection: a list of patterns such as "ignore previous instructions", "reveal your system prompt", "you are now ...", "developer mode", in Portuguese and English. The exact lists are the parametrised sentences of `tests/test_guardrails.py`: 14 attacks that must be blocked and 11 legitimate questions that must pass.

**Language.** Count the words of the message that are in a Portuguese list and in an English list; the larger count wins; a tie is decided by accented letters, then English.

**Fixed texts.** Refusal, out-of-scope text, technical-problem text and the "no confirmed instruction" notice exist in both languages in `guardrails.py`; their wording is free, their presence is tested.

**Data.** `data/merchants.json`: one object per `user_id` (`cliente1988`, `cliente2000`) with `name`, `plan`, `terminal_model`, `pix_enabled`, `anticipation_enabled`, `settlements` (`in_days`, `amount_brl`, `origin`), `transactions` (`id`, `days_ago`, `amount_brl`, `brand`, `last4`, `status`, `reason_code`, `reason`) and `terminal`. Dates are computed from today in Brasília time. `data/tickets.json`: a list of `{ticket_id, user_id, summary, priority, source, created_at}`. `data/corpus.jsonl`: one passage per line with `url`, `title`, `lang`, `text`; `data/sources.txt` lists `https://www.getnet.net/en` and the `/en/` pages of that site's sitemap (not the other country sites), plus Brazilian product pages, manuals and terms; the ingest fails under 15 passages, and `/health` reports `corpus_is_placeholder` when only the sample file is present.

**Tools.** Every tool returns a dict; a failure is `{"error": text}`. `weather` uses Open-Meteo with wttr.in as reserve; `fx_rate` uses Frankfurter with AwesomeAPI as reserve; `web_search` uses DuckDuckGo. All three are real services, replaced by fixed answers in the tests.

**Configuration (environment).** `LLM_PROVIDER`, `MODEL_FAST`, `MODEL_SMART`, `ROUTER_FALLBACK` (`llm` or `jev`), `ROUTER_HIGH` (0.7), `JEV_MIN` (0.5), `EMBEDDINGS` (`auto`, `cached`, `off`), `LLM_TIMEOUT_S`, `LLM_THINKING_ROOM`, `REQUEST_DEADLINE_S`, `TICKETS_PATH`.

**Observability.** Log line keys: `trace_id`, `user_id`, `route`, `decided_by`, `confidence`, `tool_calls`, `handoff`, `errors`, `steps` (`agent`, `ms`, `error`), `latency_ms`. `/metrics`: `requests`, `decided_by`, `route`, `errors`, `handoffs`, `handoff_rate`, `avg_latency_ms`. `/health`: `status`, `llm_provider`, `llm_problem`, `last_error`, `router_fallback`, `router_mode`, `corpus_chunks`, `corpus_is_placeholder`.
