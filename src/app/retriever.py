"""Busca por palavras (BM25) sobre data/corpus.jsonl. Cada linha: {id, url, title, lang, text}.

BM25 só casa palavras iguais, então pergunta em inglês não acha página em português.
O glossário abaixo acrescenta à consulta os termos equivalentes; é a alternativa simples a embeddings.
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
    "receivables advance": "antecipacao recebiveis", "advance": "antecipacao", "paid earlier": "antecipacao",
    "installment": "parcelas parcelamento parcelar", "payment link": "link de pagamento", "card machine": "maquininha",
    "terminal": "maquininha", "bank account": "conta bancaria", "fee": "taxa taxas", "decline": "recusada negada",
    "connect": "conexao conectar wifi internet", "difference": "diferenca", "sell": "vender vendas", "receive": "receber",
    "antecipacao": "receivables advance", "maquininha": "card machine terminal", "parcela": "installments",
    "link de pagamento": "payment link", "taxa": "fees",
}
_index = None
_docs: list[dict] = []
_placeholder = False


def tokenize(t: str) -> list[str]:
    return re.findall(r"[a-z0-9]{2,}", normalize(t))


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


def retrieve(query: str, k: int = 5, lang: str | None = None) -> list[dict]:
    """Devolve até k trechos com alguma palavra em comum; os do idioma da pergunta vêm primeiro."""
    index, docs = load()
    scores = index.get_scores(tokenize(expand(query)))
    order = [i for i in sorted(range(len(docs)), key=lambda i: -scores[i]) if scores[i] > 0]
    if order:  # corta trecho que só encostou numa palavra: fica quem tem ao menos 35% da pontuação do melhor
        order = [i for i in order if scores[i] >= 0.35 * scores[order[0]]]
    if lang:
        order = [i for i in order if docs[i].get("lang") == lang] + [i for i in order if docs[i].get("lang") != lang]
    return [dict(docs[i], score=round(float(scores[i]), 2)) for i in order[:k]]
