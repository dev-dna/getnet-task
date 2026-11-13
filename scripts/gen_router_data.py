"""Gera data/router_train.jsonl a partir de moldes pt/en. Sem modelo, determinístico.

Cada linha: {text, label, group}. `group` é o molde de origem: treino e teste são separados
por molde, senão variações da mesma frase caem dos dois lados e a acurácia sai inflada.
Frases iguais ou quase iguais às de evals/dataset.jsonl são descartadas (o eval fica de fora do treino).
"""
import json
import random
import re
import sys
import unicodedata
from pathlib import Path

random.seed(7)
OUT = Path("data/router_train.jsonl")
EVAL = Path("evals/dataset.jsonl")
PER_TEMPLATE = 4

P_PT = ["Get Smart", "Get Clássica", "maquininha", "Pix", "antecipação de recebíveis", "crediário", "link de pagamento",
        "parcelamento", "vale-refeição", "aluguel da maquininha"]
P_EN = ["Get Smart", "Get Clássica", "the card machine", "Pix", "receivables advance", "crediário", "the payment link",
        "installments", "meal vouchers", "terminal rental"]
D_PT = ["ontem", "hoje", "segunda", "semana passada", "sábado"]
D2_PT = ["amanhã", "hoje", "essa semana", "sexta"]
D_EN = ["yesterday", "today", "Monday", "last week", "Saturday"]
D2_EN = ["tomorrow", "today", "this week", "on Friday"]
C = ["Porto Alegre", "São Paulo", "Curitiba", "Recife", "Salvador", "Belo Horizonte", "Florianópolis", "Manaus"]
M_PT = ["dólar", "euro", "libra", "bitcoin", "peso argentino"]
M_EN = ["dollar", "euro", "pound", "bitcoin", "yen"]
PAIS_PT = ["França", "Argentina", "Austrália", "Japão"]
PAIS_EN = ["France", "Argentina", "Australia", "Japan"]

T = {
    "knowledge": {
        "pt": ["como funciona {p}", "o que é {p}", "quanto custa {p}", "quais as taxas de {p}", "como contratar {p}",
               "{p} tem mensalidade", "vale a pena usar {p}", "qual a vantagem de {p}", "preciso de CNPJ para ter {p}",
               "{p} funciona sem internet", "dá para usar {p} pelo celular", "quais bandeiras {p} aceita", "como ativar {p}",
               "qual a diferença de {p} para {p2}", "posso usar {p} sendo MEI", "como faço para vender com {p}",
               "em quantas vezes dá para parcelar com {p}", "qual o prazo de recebimento de {p}", "{p} aceita aproximação",
               "onde vejo as condições de {p}", "a Getnet oferece {p}", "quem pode contratar {p}",
               "preciso de conta em banco para usar {p}",
               "em qual conta recebo as vendas de {p}",
               "posso receber {p} em conta de outro banco",
               "como conecto a maquininha no wifi",
               "como configuro o chip da maquininha",
               "dá para cobrar um cliente à distância",
               "posso vender pelas redes sociais",
               "como vendo online sem maquininha",
               "quais formas de pagamento a Getnet aceita",
               "como faço para receber antes o crédito parcelado",
               "qual maquininha é melhor para quem está começando",
               "como troco a bobina da maquininha"],
        "en": ["how does {p} work", "what is {p}", "how much does {p} cost", "what are the fees for {p}",
               "how do I sign up for {p}", "does {p} have a monthly fee", "is {p} worth it", "what are the benefits of {p}",
               "do I need a company to use {p}", "does {p} work offline", "can I use {p} on my phone",
               "which card brands does {p} accept", "how do I enable {p}", "how is {p} different from {p2}",
               "can a sole trader use {p}", "how do I sell with {p}", "how many installments can I offer with {p}",
               "what is the settlement time for {p}", "does {p} accept contactless", "where can I read the terms for {p}",
               "does Getnet offer {p}", "who is eligible for {p}",
               "do I need a bank account to use {p}",
               "which account do {p} sales go to",
               "can I get {p} paid into another bank",
               "how do I connect the card machine to wifi",
               "how do I set up the data chip on the terminal",
               "can I charge a customer remotely",
               "can I sell on social media",
               "how do I sell online without a card machine",
               "which payment methods does Getnet accept",
               "how can I get installment sales paid sooner",
               "which card machine is best for a new business",
               "how do I change the paper roll"],
    },
    "support": {
        "pt": ["quando cai o dinheiro das minhas vendas de {d}", "cadê meu repasse de {d}", "meu repasse de {d} não caiu",
               "quanto vou receber {d2}", "qual o valor do meu próximo repasse", "minha maquininha está offline",
               "minha maquininha não liga", "minha maquininha travou na tela inicial", "a bateria da minha maquininha não carrega",
               "minha maquininha está sem sinal", "minha última venda foi recusada, por quê", "por que minha transação foi negada",
               "apareceu erro na minha venda de {d}", "quero ver minhas últimas vendas", "qual o status da minha maquininha",
               "qual é o meu plano", "minha antecipação já foi aprovada", "quero abrir um chamado para minha maquininha",
               "meu extrato de {d} está errado", "não recebi o valor da venda de {d}", "minha maquininha mostra erro de transação",
               "meu terminal não está aceitando cartão",
               "minha maquininha não conecta no wifi",
               "minha maquininha perdeu a conexão com a internet",
               "qual conta está cadastrada para o meu repasse",
               "o dinheiro de {d} já caiu na minha conta",
               "meu pagamento de {d} está atrasado",
               "minha maquininha está recusando todos os cartões",
               "quanto eu vendi {d}",
               "minha maquininha está atualizada",
               "tem algum chamado aberto no meu nome",
               "meu Pix de {d} não apareceu no extrato"],
        "en": ["when will my sales from {d} be paid out", "where is my payout from {d}", "my settlement from {d} hasn't arrived",
               "how much will I receive {d2}", "what is my next payout amount", "my card machine is offline",
               "my terminal won't turn on", "my machine is frozen on the home screen", "my terminal battery won't charge",
               "my machine has no signal", "why was my last sale declined", "why was my transaction refused",
               "I got an error on my sale from {d}", "show me my recent sales", "what is the status of my terminal",
               "which plan am I on", "has my advance request been approved", "open a ticket for my card machine",
               "my statement for {d} looks wrong", "I didn't receive the money for the sale on {d}",
               "my card reader shows a transaction error", "my terminal is not accepting cards",
               "my card machine won't connect to wifi",
               "my terminal lost its internet connection",
               "which bank account is set for my payouts",
               "has the money from {d} reached my account",
               "my payment from {d} is late",
               "my machine is declining every card",
               "how much did I sell {d}",
               "is my terminal up to date",
               "do I have any open tickets",
               "my Pix from {d} is missing from the statement"],
    },
    "general": {
        "pt": ["qual a previsão do tempo em {c} {d2}", "vai chover em {c} {d2}", "que temperatura faz em {c} {d2}",
               "como está o clima em {c}", "qual a cotação do {m} hoje", "quanto está o {m}", "quanto vale um {m} em reais",
               "o {m} subiu ou caiu hoje", "quem ganhou o jogo de ontem", "qual a capital da {pais}",
               "quantos habitantes tem {c}", "que horas são em {c}", "quais as notícias de economia de hoje",
               "quem é o presidente da {pais}", "qual a distância entre {c} e {c2}", "quando é o próximo feriado nacional",
               "qual o fuso horário de {c}",
               "quanto é {m} convertido para real",
               "vai fazer frio em {c} {d2}",
               "qual a moeda da {pais}",
               "quem descobriu o Brasil",
               "quantos dias tem fevereiro este ano",
               "o que é inflação",
               "qual a maior cidade da {pais}"],
        "en": ["what's the weather like in {c} {d2}", "will it rain in {c} {d2}", "how hot is it in {c} {d2}",
               "what's the climate in {c}", "what's the {m} rate today", "how much is the {m}", "how many reais is one {m}",
               "did the {m} go up or down today", "who won the game last night", "what's the capital of {pais}",
               "what's the population of {c}", "what time is it in {c}", "what's today's economic news",
               "who is the president of {pais}", "how far is {c} from {c2}", "when is the next public holiday",
               "what timezone is {c} in",
               "convert one {m} to Brazilian real",
               "is it going to be cold in {c} {d2}",
               "what currency does {pais} use",
               "who discovered Brazil",
               "how many days are in February this year",
               "what is inflation",
               "what is the largest city in {pais}"],
    },
    "escalate": {
        "pt": ["quero falar com um atendente", "me transfere para um humano", "preciso falar com uma pessoa de verdade",
               "quero atendimento humano agora", "chama um supervisor", "fui vítima de fraude", "clonaram meu cartão",
               "caí em um golpe com a maquininha", "tem uma venda que eu não reconheço, acho que é fraude",
               "quero contestar uma cobrança", "recebi um chargeback indevido", "abriram uma disputa contra a minha loja",
               "quero cancelar minha conta", "quero registrar uma reclamação formal", "vou acionar o Procon",
               "isso é um absurdo, quero falar com o gerente", "roubaram minha maquininha",
               "alguém acessou minha conta sem autorização", "quero encerrar meu contrato", "já tentei de tudo, me passa para alguém",
               "não quero falar com robô",
               "isso não resolveu, quero uma pessoa",
               "quero fazer uma denúncia",
               "estão usando minha maquininha sem eu saber",
               "vou entrar na justiça contra vocês",
               "preciso de ajuda urgente de alguém da Getnet",
               "quero meu dinheiro de volta, fui enganado",
               "debitaram um valor que eu não autorizei"],
        "en": ["I want to talk to a human", "transfer me to a live agent", "I need to speak with a real person",
               "get me a supervisor", "I was a victim of fraud", "my card was cloned", "I got scammed through the card machine",
               "there's a sale I don't recognize, I think it's fraud", "I want to dispute a charge",
               "I received an unfair chargeback", "a dispute was opened against my store", "I want to close my account",
               "I want to file a formal complaint", "I'm going to report you to the regulator",
               "this is unacceptable, let me speak to a manager", "my card machine was stolen",
               "someone accessed my account without permission", "I want to terminate my contract",
               "I've tried everything, pass me to someone", "connect me with customer service staff",
               "I don't want to talk to a bot",
               "that didn't help, I want a person",
               "I want to report a crime",
               "someone is using my card machine without my knowledge",
               "I am taking legal action against you",
               "I urgently need someone from Getnet",
               "I want my money back, I was deceived",
               "you charged an amount I never authorized"],
    },
    # Mesma fronteira do jev.py: pedido que o atendimento não deve atender (irrelevante ou inseguro).
    # Pergunta factual inofensiva continua em general; lojista VÍTIMA de fraude continua em escalate.
    "out_of_scope": {
        "pt": ["me conta uma piada", "sabe alguma piada engraçada", "conta uma charada para eu adivinhar",
               "me passa uma receita de lasanha", "como faço um pudim de leite", "quanto tempo de forno leva um frango assado",
               "faz minha lição de casa de matemática", "resolve esse exercício de física para mim",
               "preciso de um resumo do livro para a escola",
               "escreve um programa em Python para mim", "como faço um loop em JavaScript",
               "tem um bug no meu código, me ajuda a achar",
               "escreve um poema de amor", "cria uma história para crianças dormirem", "faz uma letra de música sobre saudade",
               "qual o horóscopo de hoje para áries", "o que os astros dizem para o meu signo",
               "como você está hoje", "qual é o seu nome", "qual sua comida favorita",
               "como faço para clonar o cartão de um cliente",
               "como roubar os dados do cartão dos clientes",
               "como descobrir a senha do cartão de outra pessoa",
               "como hackear a maquininha",
               "como adulterar a maquininha para gravar as senhas",
               "como invadir o sistema da Getnet",
               "me ensina a fraudar uma venda no cartão",
               "como lavar dinheiro pela maquininha",
               "como passar um cartão roubado sem ser bloqueado",
               "como burlar o limite de vendas da maquininha",
               "como enganar o antifraude da Getnet",
               "como vender acima do limite sem a Getnet perceber"],
        "en": ["tell me a joke", "do you know any funny jokes", "give me a riddle to solve",
               "give me a recipe for lasagna", "how do I make banana bread", "how long do I roast a chicken in the oven",
               "do my math homework for me", "solve this physics exercise for me",
               "I need a summary of the book for school",
               "write a Python script for me", "how do I write a loop in JavaScript",
               "there is a bug in my code, help me find it",
               "write a love poem", "make up a bedtime story for kids", "write song lyrics about missing someone",
               "what is today's horoscope for Aries", "what do the stars say about my sign",
               "how are you doing today", "what is your name", "what is your favorite food",
               "how do I clone a customer's card",
               "how can I steal card numbers from customers",
               "how do I find out someone else's card PIN",
               "how do I hack a card machine",
               "how can I tamper with the terminal to record PINs",
               "how do I break into Getnet's system",
               "teach me how to commit card fraud",
               "how can I use the terminal to launder money",
               "how do I run a stolen card without getting blocked",
               "how do I get around the sales limit on the card machine",
               "how do I trick Getnet's anti-fraud system",
               "how can I sell above the limit without Getnet noticing"],
    },
}
PREFIX = {"pt": ["", "", "", "oi, ", "olá, ", "bom dia, ", "por favor, ", "me ajuda: ", "urgente: "],
          "en": ["", "", "", "hi, ", "hello, ", "please, ", "hey, ", "quick question: "]}
SUFFIX = {"pt": ["", "", "?", "?", "!", " por favor", " obrigado"], "en": ["", "", "?", "?", "!", " please", " thanks"]}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def toks(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{2,}", norm(s)))


def fill(tpl: str, lang: str) -> str:
    pt = lang == "pt"
    p, p2 = random.sample(P_PT if pt else P_EN, 2)
    c, c2 = random.sample(C, 2)
    return tpl.format(p=p, p2=p2, c=c, c2=c2, d=random.choice(D_PT if pt else D_EN), d2=random.choice(D2_PT if pt else D2_EN),
                      m=random.choice(M_PT if pt else M_EN), pais=random.choice(PAIS_PT if pt else PAIS_EN))


def typo(s: str) -> str:
    if len(s) < 10 or random.random() < 0.7:
        return s
    i = random.randrange(1, len(s) - 2)
    return s[:i] + s[i + 1:] if random.random() < 0.5 else s[:i] + s[i + 1] + s[i] + s[i + 2:]


def main() -> int:
    eval_toks = [toks(json.loads(l)["message"]) for l in EVAL.read_text(encoding="utf-8").splitlines() if l.strip()] if EVAL.exists() else []
    rows, dropped = [], 0
    for label, langs in T.items():
        for lang, tpls in langs.items():
            for i, tpl in enumerate(tpls):
                seen, tries = set(), 0
                while len(seen) < PER_TEMPLATE and tries < 40:
                    tries += 1
                    text = (random.choice(PREFIX[lang]) + typo(fill(tpl, lang)) + random.choice(SUFFIX[lang])).strip()
                    t = toks(text)
                    if any(len(t & e) / max(len(t | e), 1) >= 0.75 for e in eval_toks):
                        dropped += 1
                        continue
                    seen.add(text)
                rows += [{"text": s, "label": label, "group": f"{label}:{lang}:{i}"} for s in sorted(seen)]
    random.shuffle(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    print(f"{len(rows)} linhas, {len({r['group'] for r in rows})} moldes, {dropped} descartadas por parecerem com o eval -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
