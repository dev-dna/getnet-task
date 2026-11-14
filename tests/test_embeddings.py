"""Roteador por significado. Os testes usam o modelo de vetores só se ele já estiver em data/models; nunca baixam."""
import json

import pytest

from app import embeddings, router_clf as rc

needs_model = pytest.mark.skipif(not embeddings.available(), reason="modelo de vetores não baixado: rode scripts/train_router.py")


def test_router_works_without_the_vector_model(monkeypatch):
    """Sem o modelo (sem rede no primeiro uso, EMBEDDINGS=off) o roteador segue só com o classificador por letras."""
    monkeypatch.setattr(embeddings, "available", lambda: False)
    model = rc.load()
    assert not model.uses_meaning()
    label, p, top2 = rc.predict("how does the payment link work")
    assert label in rc.CLASSES and 0 <= p <= 1 and len(top2) == 2


@needs_model
def test_same_meaning_in_two_languages_is_close():
    joke_en, joke_pt, other = embeddings.embed(["Tell me a joke", "Me conta uma piada", "Como funciona a antecipação de recebíveis?"])
    assert joke_en @ joke_pt > 0.8 and joke_en @ other < 0.3


@needs_model
def test_both_classifiers_are_used_and_beat_letters_alone():
    assert rc.load().uses_meaning() and rc.HIGH == rc._threshold(True)
    rep = json.loads(rc.REPORT_PATH.read_text(encoding="utf-8"))  # relatório da validação por molde, gravado no treino
    if rep["router"] == "letras+significado":
        assert rep["methods"]["letras+significado"]["accuracy_all"] > rep["methods"]["letras"]["accuracy_all"]


@needs_model
@pytest.mark.parametrize("text,label", [
    ("Mostre as vendas do cliente2000", "support"),  # caso A2: sem o significado e os moldes novos ia para knowledge
    ("Conte uma piada", "out_of_scope"),
    ("Qual a cotação do euro hoje?", "general"),
])
def test_rewritten_sentences_get_the_right_class(text, label):
    assert rc.predict(text)[0] == label
