"""Vetores de significado (embeddings) de frases em português e inglês. Roda no processador, sem chave e sem serviço externo.

Quem usa: o roteador (classificador por significado, em router_clf.py) e a busca na base (retriever.py), para que
sinônimos e outra redação da mesma pergunta sejam entendidos sem lista manual de palavras.

Modelo: paraphrase-multilingual-MiniLM-L12-v2, pela biblioteca fastembed (ONNX). O arquivo (uns 240 MB) fica em
data/models, fora do git; é baixado na primeira vez e no `docker build`.
Se a biblioteca ou o modelo não estiverem disponíveis, available() devolve False e quem chama segue só por palavras.
"""
import logging
import os
import threading
from pathlib import Path

import numpy as np

MODEL_NAME = os.getenv("EMBED_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
CACHE = Path(os.getenv("EMBED_CACHE", "data/models"))
# auto: usa o modelo e baixa se faltar | cached: usa só se já estiver baixado (testes, sem rede) | off: nunca usa
MODE = os.getenv("EMBEDDINGS", "auto")

log = logging.getLogger("embeddings")
_lock = threading.Lock()
_model = None
_failed = False


def _load():
    global _model, _failed
    with _lock:
        if _model is not None or _failed or MODE == "off":
            return _model
        try:
            from fastembed import TextEmbedding
            try:
                _model = TextEmbedding(MODEL_NAME, cache_dir=str(CACHE), local_files_only=True)
            except Exception:
                if MODE == "cached":
                    raise
                _model = TextEmbedding(MODEL_NAME, cache_dir=str(CACHE))  # primeira vez: baixa o modelo
        except Exception as e:  # noqa: BLE001  # sem biblioteca, sem rede ou sem o arquivo: o sistema segue sem vetores
            _failed = True
            log.warning("vetores de significado indisponíveis (%s): roteador e busca seguem só por palavras", type(e).__name__)
        return _model


def available() -> bool:
    return _load() is not None


def embed(texts: list[str]) -> np.ndarray:
    """Uma linha por texto, com norma 1: o produto interno de duas linhas é a similaridade de cosseno entre os textos."""
    v = np.array(list(_load().embed(list(texts))), dtype=np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)
