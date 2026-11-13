Escreva README.md em inglês (o enunciado é em inglês), no máximo 180 linhas, só com fatos que estão no repositório. Seções:

1. What it does — 3 linhas + request e response reais de um `curl` no cenário S3.
2. Quick start — `cp .env.example .env`, `docker compose up --build`, `curl` de /health e /chat. Dizer que http://localhost:8000/docs abre o Swagger com os 10 cenários do enunciado como exemplos prontos, e que o contrato está em openapi.json. Testes sem chave (`make test`) e avaliação com chave (`make eval`).
3. Architecture — diagrama em texto de orchestrator.handle; tabela dos 4 agentes (entrada, saída, ferramentas, modelo); mecanismo de comunicação (chamadas de função + Plan/AgentResult tipados) e por quê.
4. Routing — cascata do mais barato para o mais caro: regras, classificador local (atributos, calibração, limiar), Jev da TypeSafe (o que é, por que 'out_of_scope' é uma opção escrita por nós, limiar), modelo de linguagem por último. Tabela de evals/router_comparison.json com acerto, latência mediana e custo de cada roteador. Números de data/router_report.json: acerto geral por molde, acerto e cobertura quando decide sozinho, matriz de confusão. Dizer que a separação é por molde e por quê.
5. RAG pipeline — ingestion (data/sources.txt, HTML e PDF, como quebra em trechos) → storage (corpus.jsonl no repositório, por quê) → retrieval (BM25 + glossário inglês↔português, por que não embeddings) → generation (prompt com <data>, NOT_FOUND, verificação). Listar as fontes que de fato entraram.
6. Guardrails & security — máscara na entrada e na saída (e a diferença entre as duas), padrões de injeção com a lista de perguntas legítimas que não podem ser bloqueadas, user_id por closure, ferramentas por agente, conteúdo externo como dados.
7. Human handoff — todos os gatilhos, o que vai no chamado, o que seria em produção.
8. Evaluation & observability — tabela de evals/report.json por grupo (S, H, A, B, U); o que o eval NÃO mede (correção do texto); campos do log JSON por requisição; o que viraria painel e alerta.
9. Testing strategy — unidade (modelo falso), contrato HTTP, empacotamento, avaliação; como seria o teste de integração em CI (compose up + eval + limiar).
10. SDD & timeline — commits de início e fim, specs/, o que foi preparado antes da sessão e o que foi feito nela, o que foi cortado.
11. Known limitations — dados do lojista simulados; chamados em arquivo; BM25 não entende sinônimo fora do glossário; verificador libera a resposta se ele próprio falhar; decisão de mandar toda contestação para humano.
12. Trade-offs — 5 linhas "escolhi X em vez de Y porque".

Sem emojis. Sem adjetivos. Cada número tem que sair de um arquivo do repositório.
