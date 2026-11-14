# Architecture

Diagrams of what the code does today. Text versions and the reasons behind each choice are in `README.md` (sections 3 and 4) and in `specs/plan.md` (decisions D01 to D22).

## 1. One request, end to end

```mermaid
flowchart TD
    C["Client"] -->|"POST /chat {message, user_id}"| API["api.py (FastAPI)"]
    API --> H["orchestrator.handle"]
    H --> M["guardrails.mask: card, CPF, CNPJ, e-mail, phone"]
    M --> I{"prompt injection?"}
    I -- yes --> REF["fixed refusal, route: guardrail, no model call"]
    I -- no --> P["plan_for: routing cascade (section 2)"]
    P -- "no steps" --> OOS["fixed text, route: out_of_scope"]
    P -- "plan with 1 to 3 steps" --> RUN["run the steps in order; each agent gets the original masked message and the facts of earlier agents"]
    RUN --> K["knowledge: BM25 over data/corpus.jsonl; if the base has no answer, web search on the official sites; answer only from that evidence"]
    RUN --> S["support: tools bound to the user_id of the request"]
    RUN --> G["general: weather, fx_rate, web_search"]
    K --> V{"verify: every fact in the chunks?"}
    V -- yes --> W["write_final: one fact as is, several merged"]
    S --> W
    G --> W
    V -- "no, or NOT_FOUND" --> E["escalate: ticket, handoff = true"]
    S -- "unknown user, tool failure" --> E
    G -- "tool failure" --> E
    P -- "escalate" --> E
    H -. "any exception" .-> E
    W --> MO["mask_output: card, CPF, CNPJ"]
    MO --> R["ChatResponse and one JSON log line with trace_id"]
    E --> R
    REF --> R
    OOS --> R
```

## 2. Routing cascade, cheapest step first

```mermaid
flowchart LR
    MSG["masked message"] --> R1{"rules"}
    R1 -- "fraud, dispute, request for a person" --> ESC["escalate"]
    R1 -- "my machine ... what should I do" --> SK["support, then knowledge"]
    R1 -- "no match" --> CLF{"local classifier (letters + meaning), p >= 0.7?"}
    CLF -- yes --> C1["its class: one agent, or out_of_scope"]
    CLF -- no --> JEV{"Jev, p >= 0.5? (only with ROUTER_FALLBACK=jev)"}
    JEV -- yes --> J1["its choice"]
    JEV -- "no, error or timeout" --> LLM["language-model router: plan of up to 3 steps, or none"]
```

`decided_by` in the response names the step that decided: `rule`, `clf`, `jev` or `llm`.

## 3. Components and what they talk to

| Component | File | Talks to |
|---|---|---|
| HTTP API | `src/app/api.py` | `orchestrator.handle` |
| Orchestrator and router | `src/app/orchestrator.py`, `router_clf.py`, `jev.py` | the agents; Jev over HTTPS (optional) |
| Agents | `src/app/agents.py` | the model gateway, the retriever, the tools |
| Model gateway | `src/app/llm.py` | Anthropic API, OpenRouter, the Claude Code CLI, or the fake model of the tests |
| Retriever | `src/app/retriever.py` | `data/corpus.jsonl`, built offline by `scripts/ingest.py` |
| Tools | `src/app/tools.py` | `data/merchants.json` (simulated), `data/tickets.json`, Open-Meteo, Frankfurter, DuckDuckGo |
| Guardrails | `src/app/guardrails.py` | nothing: regular expressions and word lists |

Everything runs in one process and one container. State on disk: the knowledge base (read-only), the simulated merchants (read-only) and the tickets file.

## 4. Communication between agents, and why there is no queue

The challenge allows direct function calls, an internal message queue or events. This design uses **direct function calls with two typed objects**: the router returns a `Plan` (list of steps, confidence, who decided) and each agent returns an `AgentResult` (facts, sources, evidence, tools called, error). Both are in `src/app/schemas.py`.

Why not a queue or events:
- One request is answered synchronously by at most three agents in sequence. There is no second consumer and nothing to decouple.
- A failure is a field (`AgentResult.error`) that the orchestrator turns into a handoff in the same call. With a queue this would need delivery guarantees, idempotent agents and a trace across hops.
- The whole flow is one function of about 100 lines that a test can run with a fake model.

Where a queue would enter in production:
- **Tickets.** `tools.open_ticket_record` writes a file today; it would publish to the help-desk queue.
- **Ingestion.** `scripts/ingest.py` runs by hand; it would be a scheduled job that publishes a new corpus version.
- **Long or parallel work.** If agents had to run in parallel, or a request had to survive a restart, the steps of a `Plan` would become messages and the agents would become workers.
