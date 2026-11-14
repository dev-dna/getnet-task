import json
import re
from pathlib import Path

import pytest

from app import router_clf as rc
from app.guardrails import normalize

EVAL = [json.loads(l) for l in Path("evals/dataset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


def _toks(s):
    return set(re.findall(r"[a-z0-9]{2,}", normalize(s)))


def test_eval_sentences_are_not_in_training_data():
    train = [_toks(json.loads(l)["text"]) for l in rc.TRAIN_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    for case in EVAL:
        e = _toks(case["message"])
        assert all(len(t & e) / len(t | e) < 0.75 for t in train), case["id"]


def test_grouped_cross_validation_quality():
    X, y, groups = rc._rows(rc.TRAIN_PATH)
    rep = rc.evaluate(X, y, groups)
    assert rep["accuracy_all"] >= 0.80          # frases de moldes nunca vistos
    assert rep["decides_alone"]["accuracy"] >= 0.94  # quando decide sem o modelo
    assert rep["decides_alone"]["share"] >= 0.45


def test_never_confidently_wrong_on_held_out_scenarios():
    """Nos cenários fora do treino, ou o classificador acerta, ou fica abaixo do limiar e o modelo decide."""
    for case in EVAL:
        if case["id"][0] not in "SH":
            continue
        accepted = set(case.get("expected_route", [])) | {a for r in case.get("expected_route_any", []) for a in r}
        label, p, _ = rc.predict(case["message"])
        assert p < rc.HIGH or label in accepted, (case["id"], label, round(p, 2))


def test_predict_shape():
    label, p, top2 = rc.predict("how does the payment link work")
    assert label in rc.CLASSES and 0 <= p <= 1 and len(top2) == 2


def test_startup_training_does_not_run_cross_validation(tmp_path, monkeypatch):
    """Arquivo ausente na subida: treina e grava, sem a avaliação por molde (minutos) e sem tocar no relatório."""
    monkeypatch.setattr(rc, "_clf", None)
    monkeypatch.setattr(rc, "evaluate", lambda *a, **k: pytest.fail("a subida não pode rodar a validação cruzada"))
    before = rc.REPORT_PATH.read_bytes()
    clf = rc.load(tmp_path / "router.joblib")
    assert (tmp_path / "router.joblib").exists() and rc.REPORT_PATH.read_bytes() == before
    assert rc.predict("how does the payment link work", clf)[0] in rc.CLASSES
    assert rc.mode() in ("letras", "letras+significado")
