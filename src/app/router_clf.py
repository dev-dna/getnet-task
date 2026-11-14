"""Classificador de rota: dois classificadores treinados no projeto, somados pela média das probabilidades.

1. Por letras: TF-IDF de n-gramas de caracteres + regressão logística calibrada. Tolera erro de digitação.
2. Por significado: vetor da frase (embeddings.py) + regressão logística calibrada. Entende sinônimos e outra
   redação da mesma pergunta, em português e inglês.

Na validação por molde a média acerta mais que cada um sozinho (data/router_report.json, campo "methods").
Sem o modelo de vetores (sem rede no primeiro uso, ou EMBEDDINGS=off) fica só o classificador por letras.

A probabilidade decide quem roteia: a partir de HIGH o classificador decide sozinho; abaixo disso o Jev ou o
modelo de linguagem decide. "out_of_scope" é uma classe como as outras (pedido irrelevante ou inseguro):
probabilidade baixa quase sempre é dúvida entre duas rotas válidas, não assunto estranho, então não serve para recusar.
"""
import hashlib
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

from . import embeddings
from .guardrails import normalize

MODEL_PATH = Path("data/router.joblib")
TRAIN_PATH = Path("data/router_train.jsonl")
REPORT_PATH = Path("data/router_report.json")
CLASSES = ["knowledge", "support", "general", "escalate", "out_of_scope"]
FORMAT = 2  # muda quando o conteúdo do .joblib muda: um arquivo de outra versão é refeito
# Limiar escolhido na tabela limiar × cobertura × acerto do relatório, para cada modo.
HIGH_WORDS, HIGH_BOTH = 0.75, 0.7
HIGH = float(os.getenv("ROUTER_HIGH", HIGH_WORDS))  # load() e train() ajustam para o modo em uso

_clf = None


class Router:
    """Os dois classificadores juntos. `meaning` é None quando o modelo de vetores não estava disponível no treino."""

    def __init__(self, words, meaning, signature: str):
        self.words, self.meaning, self.signature, self.format = words, meaning, signature, FORMAT
        self.classes_ = words.classes_

    def uses_meaning(self) -> bool:
        return self.meaning is not None and embeddings.available()

    def predict_proba(self, texts: list[str]) -> np.ndarray:
        proba = self.words.predict_proba(texts)
        if self.uses_meaning():
            proba = (proba + self.meaning.predict_proba(embeddings.embed(texts))) / 2
        return proba


def _threshold(both: bool) -> float:
    return float(os.getenv("ROUTER_HIGH", HIGH_BOTH if both else HIGH_WORDS))


def _rows(path: Path) -> tuple[list[str], list[str], list[str]]:
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [r["text"] for r in rows], [r["label"] for r in rows], [r["group"] for r in rows]


def _signature(path: Path) -> str:
    """Muda quando os dados de treino mudam: um .joblib treinado com outros dados é refeito em vez de reusado."""
    return hashlib.sha1(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:16]


def _splits(y, groups, n: int, seed: int):
    """Dobras que nunca põem o mesmo molde em treino e teste."""
    return list(StratifiedGroupKFold(n_splits=n, shuffle=True, random_state=seed).split(np.zeros(len(y)), y, groups))


def fit(X, y, groups, seed: int = 42):
    """Classificador por letras."""
    pipe = make_pipeline(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True, preprocessor=normalize),
        CalibratedClassifierCV(LogisticRegression(C=4.0, max_iter=3000), cv=_splits(y, groups, 3, seed)),
    )
    return pipe.fit(X, y)


def fit_meaning(E: np.ndarray, y, groups, seed: int = 42):
    """Classificador por significado: mesma regressão logística calibrada, sobre o vetor da frase."""
    return CalibratedClassifierCV(LogisticRegression(C=4.0, max_iter=3000), cv=_splits(y, groups, 3, seed)).fit(E, y)


def _summary(proba: np.ndarray, classes, y, threshold: float) -> dict:
    pred, conf = np.array(classes)[proba.argmax(1)], proba.max(1)
    ok, high = pred == np.array(y), proba.max(1) >= threshold
    table = []
    for t in (0.5, 0.6, 0.7, 0.75, 0.8, 0.9):
        m = conf >= t
        table.append({"threshold": t, "coverage": round(float(m.mean()), 3), "accuracy": round(float(ok[m].mean()), 3) if m.any() else None})
    return {
        "threshold": threshold, "accuracy_all": round(float(ok.mean()), 3),
        "decides_alone": {"share": round(float(high.mean()), 3), "accuracy": round(float(ok[high].mean()), 3) if high.any() else None},
        "goes_to_llm": {"share": round(float(1 - high.mean()), 3)},
        "thresholds": table, "confusion": confusion_matrix(y, pred, labels=CLASSES).tolist(),
    }


def evaluate(X, y, groups, n_splits: int = 5, seed: int = 42) -> dict:
    """Validação cruzada por molde: cada frase é prevista por modelos que nunca viram o molde dela."""
    both = embeddings.available()
    E = embeddings.embed(X) if both else None
    y_arr = np.array(y)
    words, meaning, classes = np.zeros((len(y), len(CLASSES))), np.zeros((len(y), len(CLASSES))), None
    for tr, te in _splits(y, groups, n_splits, seed):
        g_tr = [groups[i] for i in tr]
        clf = fit([X[i] for i in tr], [y[i] for i in tr], g_tr, seed)
        classes = list(clf.classes_)
        words[te] = clf.predict_proba([X[i] for i in te])
        if both:
            meaning[te] = fit_meaning(E[tr], y_arr[tr], g_tr, seed).predict_proba(E[te])
    methods = {"letras": _summary(words, classes, y, _threshold(False))}
    if both:
        methods["significado"] = _summary(meaning, classes, y, _threshold(False))
        methods["letras+significado"] = _summary((words + meaning) / 2, classes, y, _threshold(True))
    active = "letras+significado" if both else "letras"
    return {"n": len(y), "n_templates": len(set(groups)), "split": f"StratifiedGroupKFold({n_splits}) por molde",
            "router": active, "labels": CLASSES, **methods[active],
            "methods": {k: {"accuracy_all": v["accuracy_all"], "threshold": v["threshold"], "decides_alone": v["decides_alone"]}
                        for k, v in methods.items()}}


def _fit_and_save(train_path: Path, out: Path, seed: int = 42) -> bool:
    """Treina com todos os dados e grava o modelo. Devolve True se o classificador por significado entrou."""
    X, y, groups = _rows(train_path)
    both = embeddings.available()
    meaning = fit_meaning(embeddings.embed(X), np.array(y), groups, seed) if both else None
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(Router(fit(X, y, groups, seed), meaning, _signature(train_path)), out)
    return both


def train(train_path: Path = TRAIN_PATH, out: Path = MODEL_PATH, seed: int = 42, write_report: bool = True) -> dict:
    """Treino pedido (scripts/train_router.py): avalia por molde, grava o modelo e o relatório versionado."""
    global HIGH
    X, y, groups = _rows(train_path)
    report = evaluate(X, y, groups, seed=seed)
    both = _fit_and_save(train_path, out, seed)
    if write_report:
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    HIGH = _threshold(both)
    return report


def load(path: Path = MODEL_PATH):
    """Treina na hora se o arquivo faltar, for de outra versão ou de outros dados de treino.
    O .joblib não vai para o git: evita versão incompatível do scikit-learn.
    Aqui só treina (segundos): a validação cruzada e o relatório ficam no treino pedido, fora da subida do app."""
    global _clf, HIGH
    if _clf is None:
        model = None
        if path.exists():
            try:
                model = joblib.load(path)
            except Exception:  # noqa: BLE001  # arquivo de outra versão do scikit-learn ou do projeto
                model = None
        stale = (not isinstance(model, Router) or getattr(model, "format", 0) != FORMAT
                 or model.signature != _signature(TRAIN_PATH) or (model.meaning is None and embeddings.available()))
        if stale:
            _fit_and_save(TRAIN_PATH, path)
            model = joblib.load(path)
        _clf = model
        HIGH = _threshold(_clf.uses_meaning())
    return _clf


def mode() -> str:
    """Quais classificadores estão em uso, com os mesmos nomes de data/router_report.json."""
    return "letras+significado" if load().uses_meaning() else "letras"


def predict(text: str, clf=None) -> tuple[str, float, list[tuple[str, float]]]:
    """Devolve (classe, probabilidade, as 2 classes mais prováveis)."""
    clf = clf or load()
    proba = clf.predict_proba([text])[0]
    ranked = sorted(zip(map(str, clf.classes_), map(float, proba)), key=lambda x: -x[1])
    return ranked[0][0], ranked[0][1], ranked[:2]
