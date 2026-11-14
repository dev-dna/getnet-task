"""Treino com o Jev como professor (opcional): o Jev rotula mensagens sem rótulo e o classificador local aprende com elas.

Para que serve: o classificador local foi treinado com frases geradas por moldes. Com mensagens de verdade, sem rótulo,
o Jev dá a rota e a probabilidade; as que ele rotula com confiança entram no treino. Depois disso o classificador
decide sozinho mais mensagens, e o Jev e o modelo de linguagem (pagos por chamada) são chamados menos.

Uso:
    python scripts/jev_label.py mensagens.txt             # uma mensagem por linha -> data/router_train_jev.jsonl
    python scripts/jev_label.py mensagens.txt --min 0.9   # só rótulos com probabilidade >= 0.9 (padrão 0.8)
    python scripts/train_router.py                        # treina com os moldes + as mensagens rotuladas pelo Jev

Precisa de OPENROUTER_API_KEY (ou JEV_API_KEY) no .env. Nunca foi rodado com chave real: o formato da chamada foi
conferido com a referência oficial e este arquivo tem teste com resposta simulada (tests/test_jev.py).
"""
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app import guardrails, jev, llm, router_clf  # noqa: E402,F401  (importar llm lê o .env)
from gen_router_data import toks  # noqa: E402

EVAL_FILES = (Path("evals/dataset.jsonl"), Path("evals/variations.jsonl"))


def _eval_tokens() -> list[set[str]]:
    return [toks(json.loads(l)["message"]) for f in EVAL_FILES if f.exists() for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]


def label(messages: list[str], min_p: float = 0.8, decide=None) -> tuple[list[dict], dict]:
    """Devolve (linhas de treino, contagem). Só entra no treino o que o Jev rotulou com probabilidade >= min_p.
    O texto é mascarado antes de sair da máquina; ataque e frase parecida com as da avaliação ficam de fora."""
    decide = decide or jev.decide
    eval_toks, seen, rows = _eval_tokens(), set(), []
    stats = {"kept": 0, "low_confidence": 0, "like_eval": 0, "injection": 0, "duplicate": 0, "errors": 0, "cost_usd": 0.0}
    for raw in messages:
        text = guardrails.mask(raw.strip())
        if not text:
            continue
        t = toks(text)
        if text in seen:
            stats["duplicate"] += 1
        elif guardrails.detect_injection(text):
            stats["injection"] += 1
        elif any(len(t & e) / max(len(t | e), 1) >= 0.75 for e in eval_toks):
            stats["like_eval"] += 1  # a avaliação fica fora do treino, como nas frases geradas por molde
        else:
            seen.add(text)
            try:
                d = decide(text)
            except Exception:  # noqa: BLE001  # uma falha do Jev não derruba o lote
                stats["errors"] += 1
                continue
            stats["cost_usd"] += d.get("cost_usd", 0.0)
            if d["label"] in router_clf.CLASSES and d["p"] >= min_p:
                # cada mensagem é o próprio grupo: na validação por molde ela nunca fica em treino e teste ao mesmo tempo
                rows.append({"text": text, "label": d["label"], "group": "jev:" + hashlib.sha1(text.encode()).hexdigest()[:10],
                             "p": round(d["p"], 3), "source": "jev"})
                stats["kept"] += 1
            else:
                stats["low_confidence"] += 1
    return rows, stats


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    if not (os.getenv("JEV_API_KEY") or os.getenv("OPENROUTER_API_KEY")):
        sys.exit("Falta OPENROUTER_API_KEY (ou JEV_API_KEY) no .env: o Jev é chamado pela API do OpenRouter.")
    min_p = float(sys.argv[sys.argv.index("--min") + 1]) if "--min" in sys.argv else 0.8
    messages = Path(args[0]).read_text(encoding="utf-8").splitlines()
    rows, stats = label(messages, min_p)
    out = router_clf.JEV_TRAIN_PATH
    old = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines() if l.strip()] if out.exists() else []
    merged = {r["text"]: r for r in old + rows}
    if not merged:
        sys.exit(f"Nenhuma mensagem rotulada com probabilidade >= {min_p}: {stats}. Nada foi gravado.")
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in merged.values()), encoding="utf-8")
    print(f"{len(messages)} mensagens lidas | {stats}")
    print(f"{len(merged)} mensagens rotuladas pelo Jev em {out}. Agora: python scripts/train_router.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
