import json
from datetime import date, timedelta

import httpx

from app import tools


def test_model_never_sees_user_id():
    defs, handlers = tools.bind("cliente1988")
    for t in defs:
        assert "user_id" not in json.dumps(t["input_schema"])
    assert handlers["get_settlements"]()["settlements"]


def test_dates_are_relative_to_today():
    _, h = tools.bind("cliente1988")
    assert h["get_settlements"]()["settlements"][0]["date"] == str(date.today() + timedelta(days=1))
    assert h["get_transactions"]()["transactions"][0]["date"] == str(date.today())


def test_one_merchant_cannot_read_another():
    _, h = tools.bind("cliente1988")
    dump = json.dumps([h[n]() for n in ("get_profile", "get_settlements", "get_transactions", "get_terminal_status")], ensure_ascii=False)
    assert "Mercado Dois Mil" not in dump and "9876.54" not in dump and "tx-2000" not in dump


def test_unknown_merchant():
    _, h = tools.bind("ninguem")
    assert "error" in h["get_profile"]()


def test_tickets_get_distinct_ids():
    a = tools.open_ticket_record("cliente1988", "teste", "normal", "test")
    b = tools.open_ticket_record("cliente1988", "teste2", "high", "test")
    assert a["ticket_id"] != b["ticket_id"] and b["sla_hours"] == 4


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


def test_weather_and_fx_parsers(monkeypatch):
    """Confere só o nosso código de leitura, com respostas no formato que eu ASSUMI. As APIs reais: scripts/smoke_tools.py."""
    def fake_get(url, **kw):
        if "geocoding" in url:
            return _Resp({"results": [{"name": "Porto Alegre", "latitude": -30.03, "longitude": -51.23}]})
        if "open-meteo" in url:
            return _Resp({"daily": {"time": ["d0", "d1"], "temperature_2m_max": [20, 25], "temperature_2m_min": [10, 15], "precipitation_probability_max": [5, 60]}})
        if "frankfurter" in url:
            return _Resp({"rate": 6.12, "date": "2026-11-11"})
        raise AssertionError(url)

    monkeypatch.setattr(httpx, "get", fake_get)
    w = tools.weather("Porto Alegre", "tomorrow")
    assert w["t_max_c"] == 25 and w["rain_probability_pct"] == 60 and w["source"] == "open-meteo.com"
    assert tools.fx_rate("EUR-BRL") == {"pair": "EUR-BRL", "rate": 6.12, "date": "2026-11-11", "source": "frankfurter.dev"}


def test_external_failure_returns_error_not_exception(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("sem rede")

    monkeypatch.setattr(httpx, "get", boom)
    assert "error" in tools.weather("Porto Alegre") and "error" in tools.fx_rate("EUR-BRL")


def test_rate_limited_api_is_tried_again_before_failing(monkeypatch):
    """S2: a Open-Meteo devolve 429 de vez em quando; a segunda tentativa resolve sem virar handoff."""
    calls = []

    def flaky_get(url, **kw):
        calls.append(url)
        req = httpx.Request("GET", url)
        if len(calls) == 1:
            return httpx.Response(429, request=req)
        if "geocoding" in url:
            return httpx.Response(200, request=req, json={"results": [{"name": "Porto Alegre", "latitude": -30.03, "longitude": -51.23}]})
        return httpx.Response(200, request=req, json={"daily": {"time": ["d0", "d1"], "temperature_2m_max": [20, 25],
                                                                 "temperature_2m_min": [10, 15], "precipitation_probability_max": [5, 60]}})

    monkeypatch.setattr(httpx, "get", flaky_get)
    monkeypatch.setattr(tools.time, "sleep", lambda s: None)
    assert tools.weather("Porto Alegre")["t_max_c"] == 25 and len(calls) == 3


def test_api_that_stays_down_returns_error_after_the_retries(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, **kw: httpx.Response(503, request=httpx.Request("GET", url)))
    monkeypatch.setattr(tools.time, "sleep", lambda s: None)
    assert "error" in tools.weather("Porto Alegre")
