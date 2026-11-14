import os
import sys
from pathlib import Path

os.environ["LLM_PROVIDER"] = "fake"  # definido antes de importar app.llm; o .env não sobrescreve
os.environ.setdefault("EMBEDDINGS", "cached")  # os testes nunca baixam o modelo de vetores: usam se já estiver em data/models
ROOT = Path(__file__).resolve().parents[1]
os.environ["TICKETS_PATH"] = str(ROOT / "data" / "tickets_test.json")
sys.path.insert(0, str(ROOT / "src"))
os.chdir(ROOT)

import runpy  # noqa: E402

import pytest  # noqa: E402

from app import router_clf, tools  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def setup_data():
    if not router_clf.TRAIN_PATH.exists():
        runpy.run_path("scripts/gen_router_data.py", run_name="gen")["main"]()
    router_clf.load()
    tools.TICKETS.unlink(missing_ok=True)
    yield
    tools.TICKETS.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def no_real_web_search(monkeypatch):
    """Nenhum teste chama a busca web de verdade: o agente de conhecimento recorre a ela quando a base não responde."""
    monkeypatch.setattr(tools, "web_search", lambda query, k=3: {"results": [], "source": "duckduckgo.com"})


@pytest.fixture
def no_network(monkeypatch):
    """Ferramentas gerais sem internet: devolve resposta fixa no formato que o código espera."""
    monkeypatch.setattr(tools, "weather", lambda city, day="tomorrow": {"city": city, "t_max_c": 25, "source": "open-meteo.com"})
    monkeypatch.setattr(tools, "fx_rate", lambda pair="EUR-BRL": {"pair": pair, "rate": 6.1, "source": "frankfurter.dev"})
    monkeypatch.setattr(tools, "web_search", lambda query, k=3: {"results": [], "source": "duckduckgo.com"})
