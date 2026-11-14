"""Chama o Jev de verdade uma vez e mostra a resposta crua. Rodar antes da sessão para confirmar chave, endereço e formato."""
import json
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app import jev, llm  # noqa: E402,F401  (importar llm lê o .env)

msg = sys.argv[1] if len(sys.argv) > 1 else "Minha maquininha não conecta na internet, o que eu faço?"
key = os.getenv("JEV_API_KEY") or os.getenv("OPENROUTER_API_KEY")
if not key:
    sys.exit("Falta OPENROUTER_API_KEY (ou JEV_API_KEY) no .env")
print("endereço:", jev.URL, "| modelo:", jev.MODEL)
r = httpx.post(jev.URL, timeout=20, headers={"Authorization": f"Bearer {key}"},
               json={"model": jev.MODEL, "state": msg, "questions": jev.QUESTIONS})
print("HTTP", r.status_code)
print(json.dumps(r.json(), ensure_ascii=False, indent=2)[:1500])
r.raise_for_status()
d = jev.decide(msg)
print("\nlido pelo nosso código:", d)
assert d["label"] in jev.LABELS, "o campo 'choice' não veio como esperado: ajustar jev.decide()"
assert d["probabilities"], "o campo 'probabilities' não veio como objeto: ajustar jev.decide()"
print("plano:", jev.route(msg))
print("OK")
