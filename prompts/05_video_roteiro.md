# Vídeo — roteiro com as falas (alvo 13 min, limite 15)

O enunciado pede que o vídeo mostre três coisas: **seu raciocínio, as decisões de arquitetura e como a orquestração funciona**.
É uma apresentação da solução, não uma leitura do código. Código na tela: só o `orchestrator.py`. Sistema rodando: uns 3 minutos.

Regra: fale só o que é verdade no repositório. Cada número abaixo tem o arquivo de onde saiu; confira antes de gravar.

## Antes de gravar
1. `make setup` e `make test` (161 testes passam).
2. Suba a API com respostas de verdade: `make run-cli` (usa o Claude Code logado na máquina) ou Docker com chave real no `.env`.
3. Abra `http://localhost:8000/docs` e rode um exemplo para aquecer.
4. Leia as 10 respostas do grupo S (`make eval-cli` imprime; também estão em `evals/report_claude_cli.json`, campo `answers`). Só diga "eu li as respostas" se leu.
5. Deixe abertos: terminal com `git log --oneline --reverse`, `specs/review.md`, `src/app/orchestrator.py`, `data/router_report.json`, o Swagger.
6. Ensaie uma vez com cronômetro. Com `make run-cli` cada resposta leva de 10 a 35 segundos: fale enquanto espera.

## 0:00–0:45 — Abertura
"O desafio pede um sistema com pelo menos três agentes que cooperam: um roteador, um agente de conhecimento com busca na base da Getnet e um agente de suporte com ferramentas. Mais uma API, Docker e desenvolvimento guiado por especificação. Vou mostrar como foi feito, como a mensagem percorre o sistema, o sistema rodando e o que ficou de fora."

## 0:45–2:45 — Como foi feito (terminal com `git log --oneline --reverse`, depois `specs/review.md`)
"Vou ser direto sobre o processo. Usei o Claude Code como ferramenta de desenvolvimento, e o histórico mostra cinco etapas."
1. "Um esqueleto que eu já tinha, anterior à especificação. Está no primeiro commit, T00, e declarado no README."
2. "Correções guiadas pela avaliação: cada commit cita o cenário que falhou."
3. "A especificação: 22 requisitos funcionais e 13 não funcionais, cada um ligado a uma frase do enunciado, e uma lista de 19 pontos em que o código não cumpria o enunciado." (`specs/spec.md`, `specs/plan.md`)
4. "Uma revisão por um agente sem nenhum contexto, que leu só a especificação. Ele reprovou: a especificação não decidia quem responde perguntas gerais. Corrigi os quatro pontos bloqueantes." (mostrar `specs/review.md`)
5. "A partir daí, cada mudança de código cita o requisito que fecha. Exemplo: `fix(RF18)`."

"A especificação veio depois do esqueleto, não antes. Se eu começasse hoje, ela seria o primeiro commit."

## 2:45–5:00 — Arquitetura e fluxo (`src/app/orchestrator.py`)
"Toda mensagem entra por uma função só, de umas cem linhas."
- "Primeiro mascaro cartão, CPF, CNPJ, e-mail e telefone, e barro tentativa de manipulação com regras fixas, sem chamar modelo."
- "Depois o roteador devolve um plano: um agente ou uma sequência de agentes."
- "Os agentes rodam em ordem. Cada um recebe a mensagem original e os fatos que os anteriores encontraram."
- "A resposta do agente de conhecimento passa por um verificador, que confere se cada fato está nos trechos usados."
- "Qualquer erro vira chamado para um humano, com protocolo. Nunca erro 500."

"Os agentes se comunicam por chamada de função, trocando dois objetos tipados: o plano do roteador e o resultado de cada agente. Não usei framework de agentes porque o fluxo tem no máximo três passos: assim ele cabe numa função que se lê de cima a baixo e se testa com um modelo falso."

"O enunciado dá ao agente de conhecimento duas buscas: a base e a web. Aqui ele procura primeiro na base raspada. Se a base não responde, ele busca na web, mas só aceita resultado dos sites oficiais da Getnet, e a resposta passa pelo mesmo verificador. Sem resultado oficial, o caso vai para um humano. Clima, câmbio e fatos gerais ficam num agente geral, para uma resposta sobre produto nunca se apoiar em página não oficial."

## 5:00–7:00 — Roteamento em cascata (`data/router_report.json`)
"Rotear é uma decisão, não um texto. Por isso não começo pelo modelo de linguagem: uso uma cascata do mais barato para o mais caro, e cada degrau só entra quando o anterior não tem certeza."
1. "Regras: fraude, contestação e pedido de atendente vão direto para um humano."
2. "Um classificador treinado dentro do projeto, com cinco classes: os quatro agentes e 'fora de escopo'. São dois classificadores com a média das probabilidades: um olha as letras da frase, e tolera erro de digitação; o outro olha o significado, e entende sinônimo e outra redação, em português e inglês. Ele só decide com probabilidade de 0,7 ou mais."
3. "O Jev, um modelo de decisão. Está implementado e testado com respostas simuladas. O formato da chamada e da resposta eu conferi campo a campo com a referência oficial do OpenRouter. Eu não o chamei com chave real, então não afirmo nada sobre o desempenho dele e ele vem desligado por padrão. Se for ligado e falhar, o fluxo segue."
4. "O modelo de linguagem, por último."

"Os números: 1.320 frases de 330 moldes. O classificador acerta 92,3% no geral. Decide sozinho em 62,4% das frases, e nessas acerta 98,2%. Só com o classificador por letras eram 85,8% no geral e 51,2% decididas sozinho: o ganho veio do classificador por significado. Separei treino e teste por molde, porque variações da mesma frase nos dois lados inflam o resultado."

"Um exemplo da especificação guiando o código: ela apontou que o classificador não sabia dizer 'fora de escopo', e 'Conte uma piada' abria chamado humano. O commit `fix(RF18)` criou a quinta classe. O custo na época: ele passou a decidir sozinho em menos mensagens; o classificador por significado recuperou isso depois."

"O campo `decided_by` de cada resposta mostra qual degrau decidiu."

## 7:00–10:00 — Sistema rodando (Swagger, `POST /chat` → Examples)
Em cada resposta, aponte `route`, `decided_by`, `tool_calls` e `sources`.
1. **S3** (quando cai o dinheiro): "Rota suporte. O agente chamou a ferramenta de repasses. Os valores são dados simulados."
2. **S5** (maquininha não conecta): "Dois agentes em sequência, decididos por regra: o suporte vê que a máquina está offline com sinal fraco, e o conhecimento traz o passo a passo dos manuais, com as fontes."
3. **S9** (parcelas no crediário): "Rota conhecimento. A resposta cita o folheto oficial do Crediário."
4. **A1** (ignore as instruções): "Bloqueado pelo filtro, em zero milissegundo, sem chamar modelo."
5. **A4** (quero um atendente): "Passagem para humano, com número de protocolo."
6. Digite **"Conte uma piada"**: "Fora de escopo, decidido pelo classificador. Nenhum agente roda e nenhum chamado é aberto."
7. Se sobrar tempo, **A2** (vendas de outro cliente): "O agente não consegue: as ferramentas só enxergam a conta de quem fez a requisição."

## 10:00–11:30 — Base de conhecimento (`data/sources.txt`)
"São 502 trechos de 64 fontes: os manuais da Get Smart e da Get Clássica, o folheto do Crediário, páginas de ajuda da Getnet do Brasil e o site em inglês. O texto fica no repositório, então o contêiner sobe sem depender do site."

"A busca é por palavras, com um glossário inglês–português, porque os cenários são em inglês e os produtos do Brasil só existem em páginas em português. Não usei vetores: evita um modelo e um serviço a mais. O preço é perder sinônimos fora do glossário."

"O defeito mais útil que eu achei: com a base real, a busca punha primeiro os trechos no idioma da pergunta e escondia a página certa em português. Medi nos seis cenários de produto, corrigi e deixei um teste para cada um."

"Se os trechos não respondem, o agente devolve NOT_FOUND e o caso vai para um humano, em vez de inventar."

## 11:30–12:30 — Segurança e confiabilidade
"O modelo nunca escolhe o `user_id`: ele vem da requisição e fica preso no código das ferramentas. Cada agente só recebe as próprias ferramentas. Tudo que vem de fora, incluindo o resultado das ferramentas, entra no prompt marcado como dado."

"Se uma API externa cai, há novas tentativas; se todas falham, o caso vira chamado, não uma resposta sem dado."

## 12:30–13:30 — Testes e avaliação (`evals/report_claude_cli.json`)
"São 161 testes que rodam sem chave, com um modelo falso que só confere o encanamento. A avaliação tem 30 casos em cinco grupos: os dez do enunciado, as mesmas perguntas com outra redação, ataques, perguntas legítimas que parecem ataque e usuário desconhecido."

"Com modelo real, na execução guardada, passaram 30 de 30; execuções anteriores deram de 28 a 30, porque o resultado varia entre execuções. Num segundo conjunto, com 14 frases reescritas com sinônimos em português e inglês, 42 casos, passaram os 42. Execuções anteriores deram de 39 a 41, por duas causas que a avaliação mostrou e eu corrigi: o verificador, que era uma chamada só ao modelo rápido, reprovava respostas corretas; e uma resposta correta do suporte era trocada por chamado humano quando o conhecimento não achava instrução na base." (`evals/report_variations_claude_cli.json`)

"A avaliação confere rota, ferramenta, vazamento de dados e passagem para humano. Ela não confere se o texto está certo: isso eu li." (só se leu)

## 13:30–14:30 — O que ficou de fora
"O que eu não verifiquei: a avaliação com modelo real rodou pelo Claude Code em linha de comando. Com chave real do OpenRouter eu rodei o provedor e o Jev: os dois responderam, e nos 30 casos por esse caminho passaram 23, com os dez do enunciado certos; os 7 que falharam foram chamadas recusadas pela conta por falta de crédito, e o sistema encaminhou cada uma para um humano, como foi projetado. O provedor da Anthropic direto não foi executado, e a precisão do Jev como roteador não foi medida. A busca web funcionou numa execução e falhou em outras: por isso o caminho da busca web no agente de conhecimento está coberto por testes com resultado simulado, e quando a busca falha o caso vai para um humano."

"Limitações: os dados do lojista são simulados, os chamados ficam num arquivo e não há autenticação."

"O próximo passo já tem o caminho pronto: o script `jev_label.py` usa o Jev como professor. Ele rotula mensagens reais sem rótulo, e o classificador local treina com as que o Jev rotulou com confiança. Assim o classificador, que é gratuito e determinístico, decide cada vez mais mensagens sozinho, e o custo com modelo cai. Isso eu não rodei com chave real."

"Com mais tempo: rodar com chave real e comparar os roteadores, um provedor de busca web estável, interromper uma chamada de modelo em andamento quando o prazo estoura, e a especificação antes do primeiro commit. A busca por significado na base eu medi e não adotei: não achou mais páginas que a busca por palavras."

## Perguntas prováveis na entrevista, e onde está a resposta
- Por que não LangGraph ou outro framework? `specs/plan.md`, decisão D02.
- Por que não vetores? `specs/plan.md`, decisão D05; README, seção 12.
- Como você sabe que o classificador não está inflado? README, seção 4; `data/router_report.json`.
- O que acontece se o provedor do modelo cair? `tests/test_orchestrator.py::test_provider_failure_becomes_handoff_not_http_500`.
- O que a especificação mudou no código? `specs/review.md`, seção 3.
