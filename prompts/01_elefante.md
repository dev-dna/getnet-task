Você é o arquiteto desta sessão. NÃO escreva código agora. Leia CLAUDE.md e o enunciado abaixo e produza três arquivos.

<enunciado>
Multi-agent support system para a Getnet. Mínimo 3 agentes (Router, Knowledge com RAG sobre getnet.net + web search, Customer Support com ≥2 tools sobre dados do usuário). Endpoint POST {message, user_id}. Docker. Testes. README. Bônus: 4º agente de escalonamento humano, guardrails, observabilidade.
Cenários: ver evals/dataset.jsonl. S = enunciado, H = outra redação, A = ataques, B = parece ataque e não é, U = usuário desconhecido.
</enunciado>

Escreva:

1. specs/spec.md — requisitos funcionais numerados (RF01…), não funcionais (RNF01…), e para cada cenário S, A, B e U um critério de aceite na forma "dado / quando / então" citando rota esperada e ferramenta esperada.

2. specs/plan.md — copie a tabela de decisões do CLAUDE.md e acrescente, para cada decisão, uma linha "alternativa descartada e por quê" (ex.: LangGraph, Chroma/embeddings, framework de guardrail, router só com LLM). Inclua o diagrama de fluxo em texto do orchestrator.handle.

3. specs/tasks.md — tarefas T01–T12, cada uma com: arquivos tocados, critério de pronto verificável (um comando ou um teste), dependências, e a qual sub-agente pertence (A, B ou C conforme CLAUDE.md). Inclua T00 "esqueleto preparado antes da sessão" listando os arquivos que já existem, para o README declarar isso.

Regras: máximo 150 linhas por arquivo. Sem prosa de motivação. Nada que não caiba em 60 minutos.
