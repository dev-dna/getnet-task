"""Chama de verdade as APIs externas (clima, câmbio, busca) e mostra a resposta. Rodar no seu computador antes da sessão."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app import tools  # noqa: E402

ok = True
for name, out in (("weather", tools.weather("Porto Alegre", "tomorrow")),
                  ("fx_rate", tools.fx_rate("EUR-BRL")),
                  ("web_search", tools.web_search("capital da Austrália"))):
    bad = "error" in out
    ok &= not bad or name == "web_search"  # busca web é opcional (primeiro item da lista de cortes)
    print(f"{'ERRO' if bad else 'ok  '} {name}: {json.dumps(out, ensure_ascii=False)[:300]}")
print("\nOK" if ok else "\nFALHOU: clima ou câmbio não respondeu. Veja a mensagem de erro acima.")
sys.exit(0 if ok else 1)
