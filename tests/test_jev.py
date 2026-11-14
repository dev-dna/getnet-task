"""O Jev de verdade só é chamado por scripts/smoke_jev.py. Aqui a resposta é simulada no formato lido na documentação."""
import httpx
import pytest

from app import agents, jev, orchestrator
from app.schemas import Plan, Step

UNSURE = "Do I need a bank account to receive my sales via Pix?"  # frase em que o classificador (simulado abaixo) fica em dúvida


class _Resp:
    def __init__(self, body, status=200):
        self._b, self.status_code = body, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("erro", request=None, response=None)

    def json(self):
        return self._b


def _answer(choice, p, both=0.1):
    probs = {k: (p if k == choice else (1 - p) / 4) for k in jev.LABELS}
    return {"answers": {"route": {"type": "choice", "choice": choice, "probabilities": probs, "confidence": p},
                        "both": {"type": "noul", "noul": both}},
            "usage": {"input_tokens": 300, "output_tokens": 0, "cost": 0.0000126}}


@pytest.fixture
def jev_says(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "teste")
    sent = {}

    def install(body, status=200):
        def fake_post(url, **kw):
            sent.update(url=url, **kw)
            return _Resp(body, status)
        monkeypatch.setattr(httpx, "post", fake_post)
        return sent
    return install


def test_request_has_the_documented_shape(jev_says):
    sent = jev_says(_answer("knowledge", 0.9))
    d = jev.decide("oi")
    assert sent["url"].endswith("/decisions") and sent["headers"]["Authorization"] == "Bearer teste"
    assert set(sent["json"]) == {"model", "state", "questions"}
    assert sent["json"]["questions"]["route"]["type"] == "choice" and "out_of_scope" in sent["json"]["questions"]["route"]["criteria"]
    assert d["label"] == "knowledge" and d["p"] == 0.9 and d["cost_usd"] > 0


def test_single_route(jev_says):
    jev_says(_answer("support", 0.8))
    plan = jev.route("x")
    assert [s.agent for s in plan.steps] == ["support"] and plan.source == "jev"


def test_sequence_when_both_question_is_true(jev_says):
    jev_says(_answer("support", 0.8, both=0.9))
    assert [s.agent for s in jev.route("x").steps] == ["support", "knowledge"]


def test_out_of_scope_is_an_explicit_option(jev_says):
    jev_says(_answer("out_of_scope", 0.85))
    plan = jev.route("x")
    assert plan.steps == [] and plan.reason == "out_of_scope"


@pytest.mark.parametrize("body,status", [(_answer("support", 0.3), 200), ({"error": "x"}, 500), ({"answers": {}}, 200)])
def test_unsure_or_broken_returns_none(jev_says, body, status):
    jev_says(body, status)
    assert jev.route("x") is None


@pytest.fixture
def classifier(monkeypatch):
    """Classificador local com resposta fixa: dúvida só na frase UNSURE. Estes testes são da cascata, não do classificador."""
    def fake_predict(text, clf=None):
        p = 0.4 if text == UNSURE else 0.95
        return "knowledge", p, [("knowledge", p), ("support", round(1 - p, 2))]
    monkeypatch.setattr(orchestrator.router_clf, "predict", fake_predict)


def test_cascade_uses_jev_only_when_local_classifier_is_unsure(monkeypatch, classifier):
    monkeypatch.setattr(orchestrator, "ROUTER_FALLBACK", "jev")
    calls = []

    def fake_route(msg):
        calls.append(msg)
        return Plan(steps=[Step(agent="knowledge", question=msg)], confidence=0.9, source="jev", reason="jev")

    monkeypatch.setattr(jev, "route", fake_route)
    assert orchestrator.plan_for("How does receivables advance (antecipação) work with Getnet?").source == "clf"
    assert calls == []
    assert orchestrator.plan_for(UNSURE).source == "jev" and calls == [UNSURE]


def test_cascade_falls_back_to_language_model_when_jev_fails(monkeypatch, classifier):
    monkeypatch.setattr(orchestrator, "ROUTER_FALLBACK", "jev")
    monkeypatch.setattr(jev, "route", lambda msg: None)
    monkeypatch.setattr(agents, "route_llm", lambda msg, cands: Plan(steps=[Step(agent="knowledge", question=msg)], confidence=0.6, source="llm"))
    assert orchestrator.plan_for(UNSURE).source == "llm"
