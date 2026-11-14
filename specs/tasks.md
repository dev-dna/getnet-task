> Written on 2026-11-13, after the implementation skeleton (commit `519f83b`), from the challenge statement; it is the reference the code is checked against.

# Tasks

The code of every task below already existed in the skeleton commit `519f83b`; no task was built from this spec. "Status" is the result of checking that code against `specs/spec.md` on 2026-11-13. "Commits" names the commit that delivered the files, then the later commits that changed them (`git log`).

- Commands run from the repository root; `tests/conftest.py` forces `LLM_PROVIDER=fake`.
- Checks ran on the code of `a2bbfea` (later commits change no code), on Python 3.13. Full suite, `make test`: 99 passed. Scripts that write files ran in a copy of the repository.
- Sub-agents A (infra), B (knowledge), C (support, guardrails, classifier) are those of `prompts/03_paralelo.md`.
- Counts below are those of that check and are kept as a record. On 2026-11-14 `make test` gives 160 passed in 12 test files (`test_embeddings.py`, `test_llm_cli.py` and `test_tool_failure.py` were added after T00), and the classifier of T10 reports 98.2% when it decides alone and 62.4% decided alone (`data/router_report.json`). Later changes are listed in `README.md` section 10.
- Status: **done** = the criterion was run and passed. **partial** = the offline part passed and the named part was not run or is missing. Gap ids (G01…) are in `specs/plan.md`.

## T00: skeleton prepared before the spec
- Commit `519f83b`: 140 files. 84 are third-party code under `.claude/skills/ffmpeg-skill/` (MIT). The other 56:
- Root: `.dockerignore`, `.env.example`, `.gitignore`, `CLAUDE.md`, `Dockerfile`, `Makefile`, `docker-compose.yml`, `openapi.json`, `pyproject.toml`, `requirements.txt`
- `src/app/`: `__init__.py`, `schemas.py`, `llm.py`, `guardrails.py`, `router_clf.py`, `jev.py`, `retriever.py`, `tools.py`, `agents.py`, `orchestrator.py`, `api.py`
- `scripts/`: `ingest.py`, `gen_router_data.py`, `train_router.py`, `smoke_llm.py`, `smoke_jev.py`, `smoke_tools.py`, `export_openapi.py`
- `data/`: `sources.txt`, `corpus_seed.jsonl`, `merchants.json`, `router_train.jsonl`, `router_report.json`
- `evals/`: `dataset.jsonl`, `run.py`, `compare_routers.py`
- `tests/`: `conftest.py`, `test_guardrails.py`, `test_jev.py`, `test_openapi.py`, `test_orchestrator.py`, `test_packaging.py`, `test_retriever.py`, `test_router_clf.py`, `test_tools.py`, `test_demo_recorder.py`
- `demo/`: `README.md`, `record.py`, `finish.py`, `requirements.txt`; `prompts/`: 6 prompt files
- Added after T00: `data/corpus.jsonl` (`29ed91b`), `tests/test_llm_cli.py` (`8dff569`), `evals/report_claude_cli.json` (`a2bbfea`), `README.md` (`c08218c`), `specs/` (`d2547f5` and later).

## T01: typed contracts (A)
- Files: `src/app/schemas.py`
- Done when: `pytest tests/test_orchestrator.py::test_http_contract -q` passes.
- Depends on: T00. Covers: RF02, RF12, RF13.
- Status: **done**. Commits: `519f83b`; `8dff569` (text of one `Health` field).

## T02: model gateway (A)
- Files: `src/app/llm.py`, `scripts/smoke_llm.py`, `tests/test_llm_cli.py`, `.env.example`
- Done when: `pytest tests/test_llm_cli.py -q` passes, and `python scripts/smoke_llm.py` prints `OK` with a real key for `anthropic` and for `openrouter`.
- Depends on: T00. Covers: RNF11, D03, D04.
- Status: **partial**. The test file passes (4 tests). `scripts/smoke_llm.py` was not run with either provider (G02). Commits: `519f83b`; `8dff569` (`claude_cli` provider).

## T03: HTTP API and contract file (A)
- Files: `src/app/api.py`, `scripts/export_openapi.py`, `openapi.json`
- Done when: `pytest tests/test_openapi.py -q` passes (Swagger page, S1 to S10 as examples, `openapi.json` up to date).
- Depends on: T01, T02. Covers: RF12, RF15, RNF10 (health endpoint).
- Status: **done** (5 tests). Commits: `519f83b`; `8dff569` (one description in `openapi.json`).

## T04: packaging (A)
- Files: `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `Makefile`, `requirements.txt`, `tests/test_packaging.py`
- Done when: `pytest tests/test_packaging.py -q` passes and `docker compose build` ends without error.
- Depends on: T03. Covers: RNF01, RNF11.
- Status: **partial**. The test file passes (7 tests). `docker compose build` was not run in this check; `README.md` section 8 reports a build with the fake model (G08). Commits: `519f83b`; `29ed91b` (one test added), `8dff569` (`Makefile` targets `run-cli`, `eval-cli`).

## T05: ingestion and knowledge base (B)
- Files: `scripts/ingest.py`, `data/sources.txt`, `data/corpus.jsonl`
- Done when: `python scripts/ingest.py` exits 0 with at least 15 passages, and `data/corpus.jsonl` has no row marked `placeholder`.
- Depends on: T00. Covers: RF06, D07.
- Status: **done**. Re-run in a copy: exit 0, 502 passages from 64 sources; one listed page returned no passage. The committed file has 502 passages, 64 URLs, none marked `placeholder`. Commits: `519f83b` (script, source list); `29ed91b` (corpus, source list, sitemap filter).

## T06: retriever (B)
- Files: `src/app/retriever.py`, `tests/test_retriever.py`
- Done when: `pytest tests/test_retriever.py -q` passes; `test_challenge_scenarios_reach_their_source` covers S1, S4, S5, S6, S9, S10.
- Depends on: T05. Covers: RF05, D05, D06.
- Status: **done** (12 tests, against the committed corpus). Commits: `519f83b`; `a435792`, `4aea71a`.

## T07: knowledge agent, verifier, general agent and its tools (B)
- Files: `src/app/agents.py` (`knowledge`, `verify`, `general`), `src/app/tools.py` (`weather`, `fx_rate`, `web_search`), `scripts/smoke_tools.py`
- Done when: `pytest tests/test_orchestrator.py -q -k "knowledge or ungrounded or general"` passes and `python scripts/smoke_tools.py` exits 0.
- Depends on: T02, T06, T08. Covers: RF05, RF08, RF21, D15. RF07 stays unmet by design (G01).
- Status: **done**. 4 tests selected, all pass. `scripts/smoke_tools.py` exited 0 with `weather`, `fx_rate` and `web_search` answering. Commits: `519f83b`; `a435792`, `52d236c`, `a2bbfea` (prompts and verifier).

## T08: guardrails (C)
- Files: `src/app/guardrails.py`, `tests/test_guardrails.py`
- Done when: `pytest tests/test_guardrails.py -q` passes.
- Depends on: T00. Covers: RF17, RF19, RF20, RF22, RNF05 (data block), D12, D18, D20.
- Status: **done** (34 tests). Open findings outside the criterion: G13, G19. Commits: `519f83b`; `d19f92f`.

## T09: support tools, support agent, escalation agent (C)
- Files: `src/app/tools.py` (`bind`, `open_ticket_record`), `src/app/agents.py` (`support`, `escalate`), `data/merchants.json`, `tests/test_tools.py`
- Done when: `pytest tests/test_tools.py -q` passes.
- Depends on: T02, T08. Covers: RF09, RF10, RF11, RF16, D17, D19, D22.
- Status: **done** (7 tests). Data and tickets are simulated (G05). Commits: `519f83b`; `52d236c` (support prompt).

## T10: route classifier (C)
- Files: `scripts/gen_router_data.py`, `scripts/train_router.py`, `src/app/router_clf.py`, `data/router_train.jsonl`, `data/router_report.json`, `tests/test_router_clf.py`
- Done when: `make train` reports, split by template, accuracy when it decides alone of at least 94% and a share decided alone of at least 45%; `pytest tests/test_router_clf.py -q` asserts the same bounds.
- Depends on: T08 (text normalization). Covers: RNF09, D08, D09, D10.
- Status: **done**. Both scripts re-run in a copy: 96.6% and 61.8%, and `data/router_report.json` came out identical to the committed file. 4 tests pass. Commit: `519f83b`.

## T11: Jev router step (C)
- Files: `src/app/jev.py`, `scripts/smoke_jev.py`, `tests/test_jev.py`
- Done when: `pytest tests/test_jev.py -q` passes and `python scripts/smoke_jev.py` prints `OK` with a real key.
- Depends on: T01, T10. Covers: RF04, D11.
- Status: **partial**. The test file passes (9 tests, simulated responses). `scripts/smoke_jev.py` was never run (G03). Commit: `519f83b`.

## T12: orchestration, evaluation, README (integration, after A, B and C; no sub-agent)
- Files: `src/app/orchestrator.py`, `tests/test_orchestrator.py`, `evals/run.py`, `evals/compare_routers.py`, `evals/report_claude_cli.json`, `README.md`
- Done when: `make test` passes; `make eval` exits 0 (at least 90% of the 30 cases with a real model); `make compare` writes `evals/router_comparison.json`; a person has read the ten S answers; `README.md` meets RNF06.
- Depends on: T01 to T11. Covers: RF01, RF03, RF04, RF14, RF15, RF18, RF21, RNF02, RNF06, RNF07, RNF08, RNF10, D13, D14, D16, D21.
- Status: **partial**.
  - Passed: `make test` (99 tests; `tests/test_orchestrator.py` has 11).
  - Recorded, not re-run: 29 of 30 cases in `evals/report_claude_cli.json`, provider `claude_cli` (`make eval-cli`); H6 fails (G09, G10).
  - Not run: `make eval` against the API with `anthropic` or `openrouter` (G02); `make compare` (G04). Not recorded: the reading of the S answers (G11).
  - Delivered, not reviewed against the code here: `README.md` (G06).
  - Commits: `519f83b`; `52d236c` (orchestrator), `a2bbfea` (report), `c08218c` (README).

## Summary
- done: T01, T03, T05, T06, T07, T08, T09, T10.
- partial: T02, T04, T11, T12. What is missing needs a real credential (T02, T11, T12) or a Docker daemon (T04), plus the reading of the S answers and the README review in T12.
- Finishing these tasks does not close G01, G05, G07, G09 and G12 to G19: they are differences between the statement, or the project rules, and the existing design or behavior, outside every done-criterion above. G06 also needs the video.
- After this check: the review of `specs/review.md` (`855d670`) and the gap commits `f9ce408` (G14), `8b98c42` (G19), `00d490c` (G10), `9a674bd` (S2), `7d087c4` and `cac01eb` (G12). The suite has 120 tests at `cac01eb`, and `make eval-cli` gives 29/30 (H6 fails, G09).
