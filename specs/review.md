# Spec reviews by context-free agents

Both reviews happened before any code existed on the branch. The reviewer had no access to the conversation or to any code.

## Review 2: the statement against the spec (this branch, commit `28210ce`)
The reviewer read the challenge statement and the three spec files, and was asked: what in the statement is not covered, where the spec deviates, which quotes are wrong, what is still undecidable.

Verdict: "NOT READY (minor). Most important correction: add an explicit requirement or task for the README's evaluation, observability and alerting strategy, covering prompts and LLM-tool use. Also state the R3/R4 deviation inside R3."

| Finding | Resolution |
|---|---|
| No requirement for "high-quality prompts" and "how you leveraged LLM tools" | New requirement R13 |
| No task says what the README must contain (evaluation, observability, alerts) | T09 "done when" lists every required item |
| The deviation on web search was admitted only in the coverage table | Stated inside R3; R4 has its own quote |
| The communication mechanism was only a decision (D1), with no requirement | R8 states it and quotes the statement |
| S8 accepts two tools without saying why | Section 4 says either is accepted, and why |
| Mapping of Jev's yes/no answer to a sequence not given | Section 6, "Internal objects" |
| Verifier output and rejection criteria not given | Section 6, "Internal objects" |
| Not said whether `https://www.getnet.net/en` is ingested in full | Section 6, "Data": the `/en/` pages of its sitemap |
| "At most 60 min": the evidence is thin, no time tracking | Accepted as is: commit timestamps are the only evidence, and the coverage table says so |
| Video has no task | Accepted: no code delivers it; the coverage table says so |

## Review 1: the spec alone (a first attempt of this rebuild, replaced by this branch)
An hour earlier the same rebuild was started from the project rules, with a spec that did not quote the statement. Its reviewer read only the spec. Verdict: NOT READY, "add the schemas (the field types of `ChatResponse`, `Plan` and `AgentResult`) plus the escalation and injection rule lists". Its findings are the reason this spec has section 6 (Contracts) and no longer contradicts itself on three points: the 90% target applies to a real model, the answer masks card, CPF and CNPJ only, and three routing steps can answer "no agent". That attempt was discarded because the spec has to start from the statement.
