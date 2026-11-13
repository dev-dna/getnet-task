# Comandos da sessão de 60 min (copiar e colar, na ordem)

## Antes do cronômetro (preparo; não é desenvolvimento)
make setup            # instala e cria .env; colocar a chave
make smoke            # modelo responde e chama ferramenta; Jev responde; clima e câmbio respondem
make ingest           # ver quais fontes de data/sources.txt abrem; ajustar o arquivo
make train test       # 65 testes verdes sem chave

## min 0 — terminal
git init && git commit --allow-empty -m "chore: start 60min session"

## min 1 — Claude Code, prompt 1 (ELEFANTE)
Colar prompts/01_elefante.md. Saída: specs/spec.md, specs/plan.md, specs/tasks.md.
git add specs && git commit -m "docs: spec, plan, tasks (SDD)"

## min 10 — prompt 2 (PEIXINHO)
Colar prompts/02_peixinho.md. Aplicar só o que for bloqueante.
git commit -am "docs: spec review by context-free agent"

## min 12 — prompt 3 (PARALELO)
Colar prompts/03_paralelo.md.

## min 38 — integrar e medir
make train ingest test
docker compose up --build -d
curl -s localhost:8000/health        # corpus_is_placeholder tem que ser false
abrir http://localhost:8000/docs      # Swagger: POST /chat → Try it out → Examples → Execute
make eval
make compare          # classificador × Jev × modelo × cascata; gera evals/router_comparison.json
Cada correção: git commit -am "fix(S3): ..."

## min 48 — ler as 10 respostas S
python evals/run.py --answers        # imprime pergunta e resposta dos grupos S e H
O eval não confere o texto. Uma resposta errada com rota certa passa no eval: ler uma por uma.

## min 50 — README
Colar prompts/04_readme.md. git add -A && git commit -m "docs: README"

## min 58
git commit --allow-empty -m "chore: end 60min session"

## Depois do cronômetro — vídeo
make demo-setup                       # uma vez: Playwright + Chromium (ffmpeg precisa estar instalado)
make demo                             # com a API no ar: grava 9 cenários → demo/out/demo.mp4 (uns 5 min)
# grave a sua apresentação narrada (tela + voz) e depois:
python demo/finish.py gravacao.mkv    # volume, formato do YouTube e conferência do limite de 15 min
