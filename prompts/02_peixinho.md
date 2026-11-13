Abra um sub-agente SEM acesso a esta conversa. Ele deve ler apenas specs/spec.md, specs/plan.md, specs/tasks.md e evals/dataset.jsonl e responder, em no máximo 20 linhas:

1. Explique de volta, em 5 linhas, como uma mensagem percorre o sistema do POST até a resposta.
2. Liste até 5 ambiguidades ou contradições que impediriam um engenheiro de implementar sem perguntar.
3. Para cada cenário S1–S10, diga se a rota e a ferramenta esperadas estão inequívocas (sim/não + motivo em 1 linha).
4. Veredito: PRONTO PARA IMPLEMENTAR ou NÃO PRONTO, com a 1 correção mais importante.

Depois, aplique nas specs apenas as correções que o sub-agente apontou como bloqueantes. Não adicione escopo.
