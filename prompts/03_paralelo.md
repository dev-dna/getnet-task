Leia CLAUDE.md e specs/tasks.md. Feche as tarefas; não reescreva o que já passa nos testes.

Lance 3 sub-agentes em paralelo. Cada um recebe CLAUDE.md, specs/ e os arquivos da sua lista, termina quando o critério de pronto passar e faz um commit por tarefa ("Txx: descrição").

Sub-agente A (infra): T01–T04
- Conferir schemas.py, llm.py e api.py contra specs/spec.md.
- `LLM_PROVIDER=fake pytest tests/test_packaging.py tests/test_orchestrator.py -q` verde.
- `docker compose build` sem erro. Não tocar em agents.py nem orchestrator.py.

Sub-agente B (conhecimento): T05–T07
- `python scripts/ingest.py`. Para cada fonte com ERR ou VAZIO em data/sources.txt: abrir a URL, corrigir ou remover a linha. Critério: pelo menos 15 trechos e pelo menos uma fonte para cada assunto dos cenários S1, S4, S5, S6, S9 e S10.
- Proibido escrever trecho de cabeça. Se um assunto não tiver fonte, registrar em specs/plan.md como lacuna: a resposta certa do sistema nesse caso é o handoff.
- `pytest tests/test_retriever.py -q` verde. Para cada S acima, imprimir os 3 primeiros trechos de `retriever.retrieve(pergunta)` e conferir que o assunto bate.
- `python scripts/smoke_tools.py` com clima e câmbio respondendo; se o formato da resposta for outro, corrigir a leitura em tools.py.

Sub-agente C (suporte, guardrails, classificador): T08–T11
- `python scripts/gen_router_data.py && python scripts/train_router.py`. Critério: acerto quando decide sozinho ≥ 94% e decide sozinho em ≥ 45% das frases, na validação por molde. Abaixo disso: acrescentar moldes novos; não mexer na forma de separar treino e teste.
- `pytest tests/test_router_clf.py tests/test_guardrails.py tests/test_tools.py -q` verde.
- `python scripts/smoke_jev.py` respondendo OK; se o formato da resposta for outro, corrigir a leitura em jev.decide(). `pytest tests/test_jev.py -q` verde.
- Copiar a tabela limiar × cobertura × acerto e a matriz de confusão para specs/plan.md, seção "Avaliação do roteador".

Quando os três terminarem: `make test` completo e um relatório de 5 linhas: o que passou, o que foi cortado, quais fontes entraram na base e o que falta para rodar `make eval` com o modelo real.
