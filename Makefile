export PYTHONPATH := src
.PHONY: setup train ingest smoke test run eval compare openapi docker demo-setup demo run-cli eval-cli
# Sem chave de API: usa o Claude Code instalado e logado nesta máquina (não vale dentro do Docker).
run-cli:  ; LLM_PROVIDER=claude_cli ROUTER_FALLBACK=llm uvicorn app.api:app --port 8000
eval-cli: ; LLM_PROVIDER=claude_cli ROUTER_FALLBACK=llm EVAL_DIRECT=1 python evals/run.py --answers
setup:  ; pip install -r requirements.txt && (test -f .env || cp .env.example .env)
train:  ; python scripts/gen_router_data.py && python scripts/train_router.py
ingest: ; python scripts/ingest.py
smoke:  ; python scripts/smoke_llm.py && python scripts/smoke_jev.py && python scripts/smoke_tools.py
test:   ; LLM_PROVIDER=fake pytest -q
run:    ; uvicorn app.api:app --reload --port 8000
eval:   ; python evals/run.py
compare: ; python evals/compare_routers.py
openapi: ; python scripts/export_openapi.py
docker: ; docker compose up --build -d && sleep 10 && curl -s localhost:8000/health
demo-setup: ; pip install -r demo/requirements.txt && playwright install chromium && python .claude/skills/ffmpeg-skill/scripts/_contract.py doctor
demo:   ; python demo/record.py
