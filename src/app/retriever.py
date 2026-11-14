"""Busca por palavras (BM25) sobre data/corpus.jsonl. Cada linha: {id, url, title, lang, text}.

BM25 só casa palavras iguais, então pergunta em inglês não acha página em português.
O glossário abaixo acrescenta à consulta os termos equivalentes; é a alternativa simples a embeddings.

A ordem é só a da pontuação. Os produtos do Brasil (Get Clássica, crediário, antecipação) só existem em páginas em
português e os cenários do enunciado são em inglês: pôr primeiro os trechos no idioma da pergunta escondia a resposta.
Palavras de ligação saem da consulta e do índice; sem isso "what/the/between" casavam com textos longos em inglês.
"""
import json
import logging
import re
from pathlib import Path

from rank_bm25 import BM25Okapi

from .guardrails import normalize

CORPUS_PATH = Path("data/corpus.jsonl")
SEED_PATH = Path("data/corpus_seed.jsonl")
log = logging.getLogger("retriever")

GLOSSARY = {
    "receivables advance": "antecipacao recebiveis", "advance": "antecipacao", "paid earlier": "antecipacao antecipar recebiveis",
    "installment": "parcelas parcelamento parcelar", "payment link": "link de pagamento", "card machine": "maquininha",
    "terminal": "maquininha", "bank account": "conta bancaria", "fee": "taxa taxas", "decline": "recusada negada",
    "connect": "conexao conectar wifi sinal", "conect": "conexao conectar wifi sinal", "internet": "wifi conexao chip",
    "difference": "diferenca", "sell": "vender vendas", "receive": "receber",
    "antecipacao": "receivables advance", "parcela": "installments", "link de pagamento": "payment link", "taxa": "fees",
    # sinônimos que as variações de evals/variations.jsonl mostraram faltar (V5a, V6a, V8c): sem eles a busca não achava a página
    "anticipat": "antecipacao recebiveis", "get online": "conexao conectar wifi sinal", "offline": "conexao conectar wifi sinal",
    "card reader": "maquininha", "refus": "recusada negada erro", "denied": "recusada negada erro", "reject": "recusada negada erro",
    "recus": "recusada negada erro", "negad": "recusada negada erro",
}
STOPWORDS = frozenset("""
a an and are as at be but by can could did do does don for from has have how i if in into is it its me my need not of on or
our should so than that the their there these this to was we what when where which who why will with won would you your
ao aos as com como da das de do dos e ela ele em entre essa esse esta este eu foi ja mais mas me meu meus minha minhas na nas nao
no nos o os ou para pela pelo por pra qual quais quando que se sem ser seu seus sim sua suas tambem tem ter um uma umas uns voce
""".split())
_WIFI = re.compile(r"wi[\s\-‑]fi")  # os manuais escrevem "Wi-Fi"; sem isto vira "wi" + "fi" e não casa com "wifi"
PRODUCTS = ("classica", "smart", "mini", "tap")  # maquininhas Get Clássica, Get Smart, Get Mini e Get Tap
_index = None
_docs: list[dict] = []
_placeholder = False


def tokenize(t: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]{2,}", _WIFI.sub("wifi", normalize(t))) if w not in STOPWORDS]


def expand(query: str) -> str:
    n = normalize(query)
    return query + " " + " ".join(v for k, v in GLOSSARY.items() if k in n)


def load(path: Path | None = None):
    global _index, _docs, _placeholder
    if _index is None:
        p = path or (CORPUS_PATH if CORPUS_PATH.exists() else SEED_PATH)
        _docs = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
        _placeholder = any(d.get("placeholder") for d in _docs)
        if _placeholder:
            log.warning("BASE DE CONHECIMENTO É DE EXEMPLO (%s). Rode scripts/ingest.py antes de entregar.", p)
        _index = BM25Okapi([tokenize(d["title"] + " " + d["text"]) for d in _docs])
    return _index, _docs


def is_placeholder() -> bool:
    load()
    return _placeholder


def _rank(query: str) -> list[tuple[int, float]]:
    """(posição na base, pontuação) do mais para o menos pontuado."""
    index, docs = load()
    scores = index.get_scores(tokenize(expand(query)))
    order = [i for i in sorted(range(len(docs)), key=lambda i: -scores[i]) if scores[i] > 0]
    if order:  # corta trecho que só encostou numa palavra: fica quem tem ao menos 35% da pontuação do melhor
        order = [i for i in order if scores[i] >= 0.35 * scores[order[0]]]
    return [(i, float(scores[i])) for i in order]


def retrieve(query: str, k: int = 5) -> list[dict]:
    """Devolve até k trechos com alguma palavra em comum, do mais para o menos pontuado, em qualquer idioma.

    Pergunta que cita dois ou mais produtos ("Get Clássica ou Get Smart?"): o nome mais raro levava todos os trechos
    e o outro produto ficava sem descrição (S1). Nesse caso há uma busca por produto, intercalada com a da pergunta.
    """
    _, docs = load()
    lists = [_rank(query)]
    named = [p for p in PRODUCTS if p in tokenize(query)]
    if len(named) >= 2:
        for p in named:  # primeiro os trechos cujo título é o produto: são a seção que o descreve
            lists.append(sorted(_rank("get " + p), key=lambda hit: p not in tokenize(docs[hit[0]]["title"])))
        k = max(k, 2 * len(lists))
    seen, out = set(), []
    for pos in range(max(map(len, lists))):
        for ranked in lists:
            if pos < len(ranked) and ranked[pos][0] not in seen:
                seen.add(ranked[pos][0])
                out.append(dict(docs[ranked[pos][0]], score=round(ranked[pos][1], 2)))
    return out[:k]
