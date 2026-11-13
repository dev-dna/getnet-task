import re

import pytest

from app import retriever
from app.guardrails import normalize

# Cenários de produto do enunciado: o que os 5 trechos entregues ao agente de Conhecimento precisam conter.
# Só vale com a base real (data/corpus.jsonl, feita por scripts/ingest.py); a base de exemplo não tem esses textos.
SCENARIOS = [
    ("S1", "What's the difference between the Get Clássica and the Get Smart?", [r"classica", r"get smart"]),
    ("S4", "Do I need a bank account to receive my sales via Pix?", [r"pix.{0,200}conta|conta.{0,200}pix"]),
    ("S5", "My card machine won't connect to the internet, what should I do?", [r"configur\w+ o wifi|erro de conexao|problema de conexao|conecte-se"]),
    ("S6", "How does receivables advance (antecipação) work with Getnet?", [r"antecipacao"]),
    ("S9", "How many installments can I split a sale into with the crediário?", [r"crediario.{0,400}parcel|parcel.{0,400}crediario"]),
    ("S10", "Can I sell through WhatsApp using the Payment Link?", [r"whatsapp"]),
]


def test_retrieve_finds_topic():
    chunks = retriever.retrieve("preciso de conta bancária para receber Pix")
    assert chunks and "pix" in (chunks[0]["title"] + chunks[0]["text"]).lower()


def test_english_question_reaches_portuguese_page():
    """Sem o glossário, 'receivables advance' não tem palavra em comum com a página em português."""
    pt_only = [c for c in retriever.retrieve("how does receivables advance work", k=10) if c["lang"] == "pt"]
    assert any("antecipa" in c["text"].lower() for c in pt_only)


def test_linking_words_and_wifi_spelling():
    assert retriever.tokenize("What is the Wi-Fi of the Get Smart?") == ["wifi", "get", "smart"]


def test_nonsense_returns_nothing():
    assert retriever.retrieve("xyzzy qwfp zxcv") == []


def test_sample_corpus_is_flagged():
    if not retriever.CORPUS_PATH.exists():
        assert retriever.is_placeholder()


@pytest.mark.parametrize("case_id,question,must_find", SCENARIOS, ids=[s[0] for s in SCENARIOS])
def test_challenge_scenarios_reach_their_source(case_id, question, must_find):
    if retriever.is_placeholder():
        pytest.skip("base de exemplo: rode scripts/ingest.py")
    top = [re.sub(r"wi[\s\-‑]fi", "wifi", normalize(c["title"] + " " + c["text"])) for c in retriever.retrieve(question, k=5)]
    for pattern in must_find:
        assert any(re.search(pattern, t, re.S) for t in top), (case_id, pattern)
