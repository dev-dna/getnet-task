"""Ferramentas. Gerais (clima, câmbio, web) e do lojista (user_id preso por closure).

data/merchants.json é SIMULADO e guarda prazos relativos (in_days, days_ago); as datas reais são
calculadas na hora da consulta, então "ontem" e "amanhã" continuam certos em qualquer dia.
"""
import json
import os
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx

MERCHANTS = Path("data/merchants.json")
TICKETS = Path(os.getenv("TICKETS_PATH", "data/tickets.json"))
TIMEOUT = 8
RETRY_STATUS = (429, 500, 502, 503, 504)
_ticket_lock = threading.Lock()


# ---------- gerais ----------
def _get(url: str, **kw) -> httpx.Response:
    """GET com até duas novas tentativas (1 s e 2 s depois). A Open-Meteo devolve 429 a chamadas seguidas;
    sem isto um limite passageiro virava falha de ferramenta e o cenário S2 ia para atendimento humano."""
    for wait in (1, 2, None):
        r = httpx.get(url, timeout=TIMEOUT, **kw)
        try:
            r.raise_for_status()
            return r
        except httpx.HTTPStatusError as e:
            if wait is None or e.response is None or e.response.status_code not in RETRY_STATUS:
                raise
            time.sleep(wait)
def weather(city: str, day: str = "tomorrow") -> dict:
    """Open-Meteo: acha a cidade pelo nome e devolve a previsão. Sem chave."""
    try:
        g = _get("https://geocoding-api.open-meteo.com/v1/search", params={"name": city, "count": 1, "language": "pt"})
        hits = g.json().get("results") or []
        if not hits:
            return {"error": f"cidade não encontrada: {city}"}
        r = _get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": hits[0]["latitude"], "longitude": hits[0]["longitude"], "timezone": "auto", "forecast_days": 2,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max"})
        d = r.json()["daily"]
        i = 1 if day == "tomorrow" else 0
        return {"city": hits[0].get("name", city), "date": d["time"][i], "t_max_c": d["temperature_2m_max"][i],
                "t_min_c": d["temperature_2m_min"][i], "rain_probability_pct": d["precipitation_probability_max"][i],
                "source": "open-meteo.com"}
    except Exception as e:  # noqa: BLE001
        return {"error": f"weather indisponível: {e}"}


def fx_rate(pair: str = "EUR-BRL") -> dict:
    """Câmbio: Frankfurter primeiro (sem chave); AwesomeAPI como reserva (AWESOMEAPI_TOKEN opcional)."""
    base, _, quote = pair.replace("/", "-").upper().partition("-")
    quote = quote or "BRL"
    try:
        d = _get(f"https://api.frankfurter.dev/v2/rate/{base.lower()}/{quote.lower()}").json()
        if isinstance(d, dict) and d.get("rate"):
            return {"pair": f"{base}-{quote}", "rate": float(d["rate"]), "date": d.get("date"), "source": "frankfurter.dev"}
    except Exception:  # noqa: BLE001
        pass
    try:
        params = {"token": os.environ["AWESOMEAPI_TOKEN"]} if os.getenv("AWESOMEAPI_TOKEN") else None
        item = next(iter(_get(f"https://economia.awesomeapi.com.br/json/last/{base}-{quote}", params=params).json().values()))
        return {"pair": f"{base}-{quote}", "rate": float(item["bid"]), "date": item.get("create_date"), "source": "awesomeapi.com.br"}
    except Exception as e:  # noqa: BLE001
        return {"error": f"fx_rate indisponível: {e}"}


def web_search(query: str, k: int = 3) -> dict:
    try:
        from ddgs import DDGS
        hits = list(DDGS().text(query, max_results=k))
        return {"results": [{"title": h.get("title"), "url": h.get("href"), "snippet": h.get("body")} for h in hits],
                "source": "duckduckgo.com"}
    except Exception as e:  # noqa: BLE001
        return {"error": f"web_search indisponível: {e}"}


GENERAL_TOOLS = [
    {"name": "weather", "description": "Previsão do tempo para uma cidade.", "input_schema": {"type": "object", "properties": {"city": {"type": "string"}, "day": {"type": "string", "enum": ["today", "tomorrow"]}}, "required": ["city"]}},
    {"name": "fx_rate", "description": "Cotação de câmbio. Formato do par: EUR-BRL, USD-BRL.", "input_schema": {"type": "object", "properties": {"pair": {"type": "string"}}, "required": ["pair"]}},
    {"name": "web_search", "description": "Busca na web para perguntas gerais.", "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
]


def bind_general() -> tuple[list[dict], dict, list[str]]:
    """Devolve (definições, funções, fontes_usadas). Cada chamada anota de onde veio o dado."""
    used: list[str] = []

    def track(fn):
        def inner(**kw):
            out = fn(**kw)
            if isinstance(out, dict) and out.get("source"):
                used.append(out["source"])
            return out
        return inner

    return GENERAL_TOOLS, {"weather": track(weather), "fx_rate": track(fx_rate), "web_search": track(web_search)}, used


# ---------- lojista ----------
def merchants() -> dict:
    return json.loads(MERCHANTS.read_text(encoding="utf-8"))


def bind(user_id: str) -> tuple[list[dict], dict]:
    """Fecha o user_id dentro das funções. O modelo nunca recebe nem escolhe esse parâmetro."""
    m = merchants().get(user_id)
    today, now = date.today(), datetime.now()
    missing = {"error": "merchant not found"}

    def get_profile() -> dict:
        return missing if not m else {k: m[k] for k in ("name", "plan", "terminal_model", "pix_enabled", "anticipation_enabled")}

    def get_settlements(days: int = 3) -> dict:
        if not m:
            return missing
        return {"settlements": [{"date": str(today + timedelta(days=s["in_days"])), "amount_brl": s["amount_brl"], "origin": s["origin"]}
                                for s in m["settlements"][:days]]}

    def get_transactions(limit: int = 5) -> dict:
        if not m:
            return missing
        return {"transactions": [{**{k: v for k, v in t.items() if k != "days_ago"}, "date": str(today - timedelta(days=t["days_ago"]))}
                                 for t in m["transactions"][:limit]]}

    def get_terminal_status() -> dict:
        if not m:
            return missing
        t = dict(m["terminal"])
        t["last_seen"] = (now - timedelta(hours=t.pop("last_seen_hours_ago"))).isoformat(timespec="minutes")
        return t

    def open_ticket(summary: str, priority: str = "normal") -> dict:
        return open_ticket_record(user_id, summary, priority, source="support")

    tools = [
        {"name": "get_profile", "description": "Perfil e plano do lojista autenticado.", "input_schema": {"type": "object", "properties": {}}},
        {"name": "get_settlements", "description": "Próximos repasses: quando e quanto o lojista vai receber.", "input_schema": {"type": "object", "properties": {"days": {"type": "integer"}}}},
        {"name": "get_transactions", "description": "Últimas transações do lojista, com status e motivo de recusa.", "input_schema": {"type": "object", "properties": {"limit": {"type": "integer"}}}},
        {"name": "get_terminal_status", "description": "Estado da maquininha do lojista: conexão, bateria, versão.", "input_schema": {"type": "object", "properties": {}}},
        {"name": "open_ticket", "description": "Abre chamado para a equipe humana.", "input_schema": {"type": "object", "properties": {"summary": {"type": "string"}, "priority": {"type": "string", "enum": ["low", "normal", "high"]}}, "required": ["summary"]}},
    ]
    handlers = {"get_profile": get_profile, "get_settlements": get_settlements, "get_transactions": get_transactions,
                "get_terminal_status": get_terminal_status, "open_ticket": open_ticket}
    return tools, handlers


def open_ticket_record(user_id: str, summary: str, priority: str, source: str, extra: dict | None = None) -> dict:
    """Grava o chamado em arquivo. Em produção isto seria uma fila ou a API do sistema de atendimento."""
    with _ticket_lock:
        TICKETS.parent.mkdir(parents=True, exist_ok=True)
        data = json.loads(TICKETS.read_text(encoding="utf-8")) if TICKETS.is_file() else []
        tid = f"GN-{date.today():%Y%m%d}-{len(data) + 1:04d}"
        data.append({"ticket_id": tid, "user_id": user_id, "summary": summary, "priority": priority, "source": source,
                     "created_at": datetime.now().isoformat(timespec="seconds"), **(extra or {})})
        TICKETS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ticket_id": tid, "status": "open", "sla_hours": 4 if priority == "high" else 24}
