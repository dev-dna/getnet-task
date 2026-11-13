# Vídeo (12 min) — roteiro com as falas

Trocar cada [número] pelo valor do arquivo indicado. Não falar número que não esteja num arquivo do repositório.

## 0:00–1:00 — O que foi pedido
"O desafio pede três agentes que cooperam, uma API, Docker, e desenvolvimento guiado por especificação em 60 minutos. Vou mostrar primeiro o histórico, depois o fluxo, depois os números."

## 1:00–3:00 — Histórico (terminal)
`git log --date=format:%H:%M --format='%ad %s'`
"Aqui começa a sessão e aqui termina. A especificação entra antes do código. Cada commit fecha uma tarefa do tasks.md. O que eu trouxe pronto de antes está listado na tarefa T00 e no README."

## 3:00–5:00 — Fluxo (orchestrator.py aberto)
"A mensagem passa por cinco etapas. Primeiro, mascaro CPF e cartão e bloqueio tentativa de manipulação com regras fixas, sem gastar modelo. Depois decido a rota. Depois os agentes rodam, cada um só com as ferramentas dele. A resposta do agente de conhecimento é verificada contra os trechos que ele usou. Qualquer falha vira chamado para humano, nunca erro 500."

## 5:00–7:30 — Roteamento em cascata (a parte mais importante)
"Rotear é uma decisão, não um texto. Então eu não começo pelo modelo de linguagem. Uso uma cascata do mais barato para o mais caro, e cada degrau só entra quando o anterior não tem certeza."

1. "Regras: fraude e pedido de humano vão direto para o atendente."
2. "Classificador local, treinado por mim: custo zero, um milissegundo. Ele só decide quando a probabilidade passa de 0,75."
3. "Jev, da TypeSafe: um modelo que só decide, não escreve. Devolve a opção e a probabilidade de cada uma. Entra nos casos em que o classificador ficou em dúvida."
4. "Modelo de linguagem: último recurso, quando o Jev também não tem certeza ou está fora do ar."

Mostrar `data/router_report.json`:
"Meu primeiro número era 98,7% e estava errado: frases quase iguais caíam no treino e no teste. Separando por molde, o classificador acerta [accuracy_all]. Mas quando ele decide sozinho acerta [decides_alone.accuracy], e isso cobre [decides_alone.share] das mensagens."

Mostrar `evals/router_comparison.json` (saída de `make compare`):
"Nas mesmas [n] mensagens, que não estão no treino: classificador [x], Jev [y], modelo de linguagem [z], cascata [w]. Latência mediana e custo de cada um estão na tabela. São poucos casos; serve para escolher o padrão, não é prova estatística."

"Limitação que eu encontrei: o Jev não tem resposta 'nenhuma das opções'. Por isso 'fora de escopo' é uma opção escrita por mim. E a documentação não fala de português, então eu medi."

## 7:30–9:30 — Rodando (terminal, ou tocar demo/out/demo.mp4 e narrar por cima)
`docker compose up -d && python evals/run.py`
Comentar: S3 (suporte chama a ferramenta de repasses), S5 (sequência suporte → conhecimento), A1 (ataque bloqueado sem modelo), B1 (parece ataque e passa), A2 (não dá para ver dados de outro lojista), A4 (humano com protocolo).
"Olhem o campo decided_by em cada resposta: ele diz qual degrau da cascata decidiu."

## 9:30–10:30 — Base de conhecimento
"As fontes estão em data/sources.txt: páginas e PDFs oficiais. Busca por palavras com um glossário inglês–português. Escolhi não usar vetores para caber no tempo; está nos próximos passos. Se a base não tem a resposta, o agente devolve NOT_FOUND e o caso vai para humano em vez de inventar."

## 10:30–11:15 — Segurança
"O modelo nunca escolhe o user_id: ele vem da requisição e fica preso no código das ferramentas. Tudo que vem de fora entra no prompt marcado como dado."

## 11:15–12:00 — O que ficou de fora
"O eval confere rota, ferramenta e vazamento; a correção do texto eu li à mão. Dados do lojista são simulados. Com mais uma semana: vetores na busca, limiares calibrados com conversas reais e chamados numa fila."
