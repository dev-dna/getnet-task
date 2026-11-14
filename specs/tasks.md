# Tasks

In order. One commit per task. "Done when" is the command that must pass before the commit.

| Task | Files | Done when |
|---|---|---|
| T01 contracts and guardrails | `src/app/__init__.py`, `schemas.py`, `guardrails.py`, `tests/test_guardrails.py` | `pytest tests/test_guardrails.py` |
| T02 model gateway | `src/app/llm.py`, `tests/test_llm_cli.py` | `pytest tests/test_llm_cli.py` |
| T03 knowledge base and retriever | `scripts/ingest.py`, `data/sources.txt`, `data/corpus.jsonl`, `data/corpus_seed.jsonl`, `src/app/retriever.py`, `tests/test_retriever.py` | `pytest tests/test_retriever.py` |
| T04 tools | `src/app/tools.py`, `data/merchants.json`, `tests/test_tools.py` | `pytest tests/test_tools.py` |
| T05 route classifier | `src/app/embeddings.py`, `router_clf.py`, `scripts/gen_router_data.py`, `scripts/train_router.py`, `data/router_train.jsonl`, `data/router_report.json`, `evals/dataset.jsonl`, `evals/variations.jsonl`, `tests/conftest.py`, `tests/test_router_clf.py`, `tests/test_embeddings.py` | `pytest tests/test_router_clf.py tests/test_embeddings.py` |
| T06 agents, routing cascade, orchestrator and API | `src/app/agents.py`, `jev.py`, `orchestrator.py`, `api.py`, `openapi.json`, `scripts/export_openapi.py`, `scripts/serve.py`, `scripts/jev_label.py`, `scripts/smoke_*.py`, `tests/test_orchestrator.py`, `test_jev.py`, `test_tool_failure.py`, `test_openapi.py` | `pytest tests/test_orchestrator.py tests/test_jev.py tests/test_tool_failure.py tests/test_openapi.py` |
| T07 evaluation runner | `evals/run.py`, `compare_routers.py`, stored reports | `python evals/run.py` runs to the end with the fake model (plumbing only); the 90% target of R10 is measured with a real model by `python evals/run.py --cli` |
| T08 packaging | `requirements.txt`, `requirements.lock`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `Makefile`, `pyproject.toml`, `tests/test_packaging.py` | `pytest tests/test_packaging.py`, then the whole suite |
| T09 README | `README.md`, `docs/architecture.md` | the README has: how to build, configure and run, and how to run the tests; the architecture, the design choices and the message workflow; the RAG pipeline (ingestion, storage, retrieval, generation); how the LLM tools are used; the evaluation and observability strategy, with the dashboards and alerts that would be built; the testing strategy including integration testing; known limitations; what this session is. Every command in it exists in the repository |

The evaluation datasets come in with T05, before the classifier: its tests check that no evaluation sentence is in the training data, so the acceptance data has to exist first.
