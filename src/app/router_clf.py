"""Classificador de rota: TF-IDF de n-gramas de caracteres + regressão logística calibrada.

A probabilidade calibrada decide quem roteia: a partir de HIGH o classificador decide sozinho;
abaixo disso o modelo de linguagem decide (e só ele pode dizer que a mensagem é fora de escopo:
probabilidade baixa aqui quase sempre é dúvida entre duas rotas válidas, não assunto estranho).
"""
import json
import os
from pathlib import Path

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline

from .guardrails import normalize

MODEL_PATH = Path("data/router.joblib")
TRAIN_PATH = Path("data/router_train.jsonl")
REPORT_PATH = Path("data/router_report.json")
CLASSES = ["knowledge", "support", "general", "escalate"]
HIGH = float(os.getenv("ROUTER_HIGH", "0.75"))

_clf = None


def _rows(path: Path) -> tuple[list[str], list[str], list[str]]:
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [r["text"] for r in rows], [r["label"] for r in rows], [r["group"] for r in rows]


def _splits(y, groups, n: int, seed: int):
    """Dobras que nunca põem o mesmo molde em treino e teste."""
    return list(StratifiedGroupKFold(n_splits=n, shuffle=True, random_state=seed).split(np.zeros(len(y)), y, groups))


def fit(X, y, groups, seed: int = 42):
    pipe = make_pipeline(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True, preprocessor=normalize),
        CalibratedClassifierCV(LogisticRegression(C=4.0, max_iter=3000), cv=_splits(y, groups, 3, seed)),
    )
    return pipe.fit(X, y)


def evaluate(X, y, groups, n_splits: int = 5, seed: int = 42) -> dict:
    """Validação cruzada por molde: cada frase é prevista por um modelo que nunca viu o molde dela."""
    pred, conf = [""] * len(y), np.zeros(len(y))
    for tr, te in _splits(y, groups, n_splits, seed):
        clf = fit([X[i] for i in tr], [y[i] for i in tr], [groups[i] for i in tr], seed)
        proba = clf.predict_proba([X[i] for i in te])
        for j, i in enumerate(te):
            k = int(proba[j].argmax())
            pred[i], conf[i] = clf.classes_[k], float(proba[j][k])
    ok = np.array([p == t for p, t in zip(pred, y)])
    table = []
    for t in (0.5, 0.6, 0.7, 0.75, 0.8, 0.9):
        m = conf >= t
        table.append({"threshold": t, "coverage": round(float(m.mean()), 3), "accuracy": round(float(ok[m].mean()), 3) if m.any() else None})
    high = conf >= HIGH
    return {
        "n": len(y), "n_templates": len(set(groups)), "split": f"StratifiedGroupKFold({n_splits}) por molde",
        "accuracy_all": round(float(ok.mean()), 3),
        "decides_alone": {"share": round(float(high.mean()), 3), "accuracy": round(float(ok[high].mean()), 3) if high.any() else None},
        "goes_to_llm": {"share": round(float(1 - high.mean()), 3)},
        "thresholds": table, "labels": CLASSES,
        "confusion": confusion_matrix(y, pred, labels=CLASSES).tolist(),
    }


def train(train_path: Path = TRAIN_PATH, out: Path = MODEL_PATH, seed: int = 42) -> dict:
    X, y, groups = _rows(train_path)
    report = evaluate(X, y, groups, seed=seed)
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(fit(X, y, groups, seed), out)  # modelo final usa todos os dados
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def load(path: Path = MODEL_PATH):
    """Treina na hora se o arquivo não existir (1-2 s). O .joblib não vai para o git: evita versão incompatível do scikit-learn."""
    global _clf
    if _clf is None:
        if not path.exists():
            train(out=path)
        _clf = joblib.load(path)
    return _clf


def predict(text: str, clf=None) -> tuple[str, float, list[tuple[str, float]]]:
    """Devolve (classe, probabilidade, as 2 classes mais prováveis)."""
    clf = clf or load()
    proba = clf.predict_proba([text])[0]
    ranked = sorted(zip(map(str, clf.classes_), map(float, proba)), key=lambda x: -x[1])
    return ranked[0][0], ranked[0][1], ranked[:2]
