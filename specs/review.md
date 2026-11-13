> Written on 2026-11-13, after the implementation skeleton (commit `519f83b`) and after the first version of the spec (commit `1e9ac7e`).

# Spec review by a context-free agent

Method: a reviewer agent with no access to the conversation, the code, the README or the git history read only `specs/spec.md`, `specs/plan.md`, `specs/tasks.md` and `evals/dataset.jsonl` at commit `1e9ac7e`, and answered four questions (`prompts/02_peixinho.md`). Only the findings it marked as blocking were applied; no scope was added.

## 1. Verdict

NOT READY. Most important correction asked: "decide in `spec.md` which agent owns non-Getnet questions and `web_search`, and which of those questions are declined, then make RF07, RF18, D19, the classifier classes (G12) and rows S2, S7, A6 say the same thing; today RF07 and RF15 cannot both pass."

The reviewer explained the message flow back correctly from the three files (masking, injection check, the four routing steps, the agents, handoff on any error, output mask), and confirmed that section 4 of the spec matches `evals/dataset.jsonl` row by row for the 30 ids.

## 2. Findings and what was done

| # | Finding | Severity | Resolution |
|---|---|---|---|
| a | RF07 puts web search in the knowledge agent; section 4, D19 and the dataset require the `general` agent. The spec named the conflict (G01) and did not say which side is normative. | blocking | RF07 now states the normative split: `knowledge` answers only from retrieved passages, `general` owns web search, weather and exchange rates; S2, S7, H3, H4 are its acceptance criteria. The deviation from the statement's wording stays recorded as G01. |
| b | RF18 declines irrelevant requests, yet A6 also accepted `["general"]`, and nothing defined which non-Getnet questions are answered and which are declined. The four-class classifier could never answer "out of scope" (G12). | blocking | RF18 now defines the boundary (harmless facts are `general`; jokes, recipes, homework, coding, creative writing and unsafe requests are declined). A6 accepts only `["out_of_scope"]`, in the spec and in the dataset. The classifier gains an `out_of_scope` class (G12). |
| c | The Jev step had no endpoint, request or response format in the specs, and the default differed: unset `ROUTER_FALLBACK` means `llm`, `.env.example` sets `jev`. | blocking | Spec section 6 "Contracts" describes the request, the two questions, the answer and both defaults, and what happens when Jev fails. |
| d | Response fields, tool signatures, the user-data schema and the rule patterns were absent, so the specs could not be implemented alone. | blocking | Spec section 6 lists the ten response fields, the eight tool signatures, the keys of `data/merchants.json` and where the contract of the two rules lives. |
| e | Route `["error"]` and a handoff without `ticket_id` were not in the vocabulary; a tool error did not hand off (G14); a ticket opened by the model was not specified. | minor | Vocabulary updated; G14 closed in code by commit `f9ce408`; section 6 states that a model-opened ticket does not set `handoff`. |
| f | S5 accepted three routes although rule 2 always yields `support` then `knowledge`; S8 accepts two routes. | not blocking | S5 now requires exactly `["support","knowledge"]` with both tools, in the spec and in the dataset. S8 is unchanged: whether `knowledge` is added there is left to the router. |

## 3. Gaps closed in code after the review

Each commit cites the requirement or gap it closes.

| Gap | Requirement | Commit | What changed |
|---|---|---|---|
| G14 (tool failure) | RF21, D18 | `f9ce408` | A tool loop without an answer, or a run where every tool call failed, becomes a handoff. Tool results enter the prompt as data. |
| G19 | RF14 | `8b98c42` | Language by word count for Portuguese and English; A1b gets its refusal in Portuguese. |
| G10 (report) | RNF08 | `00d490c` | `evals/run.py` writes the stored report format and runs cases in parallel. |
| found by G14 | RF08 | `9a674bd` | A rate-limited external API is tried again before the tool fails (S2). |
| G12 | RF18 | `7d087c4`, `cac01eb` | The classifier has a fifth class, `out_of_scope`; a joke or a request to attack a card machine is declined instead of reaching an agent or opening a ticket. |

After these commits: 120 tests pass and `make eval-cli` gives 29 of 30 (`evals/report_claude_cli.json`); H6 still ends in a handoff after the knowledge step (G09).
