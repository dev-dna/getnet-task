"""Jev (TypeSafe): modelo de decisão. Recebe perguntas tipadas e devolve escolha + probabilidades; não escreve texto.

Aqui ele é o segundo roteador: entra só quando o classificador local fica em dúvida.
Chamado pela Decisions API do OpenRouter com a mesma chave do resto do projeto.

Formato conferido em 14/nov/2026 com a referência oficial (openrouter.ai/docs, "Submit a decisions request"):
POST /api/alpha/decisions, chave como Bearer, corpo {model, state, questions}; a resposta vem em "answers", e cada
resposta traz "choice" + "probabilities" (pergunta choice), "noul" (pergunta sim/não) ou type "refusal".
A API é alfa: o formato pode mudar. Chamada com chave real: scripts/smoke_jev.py (ainda não rodada).
Outro endereço ou modelo: JEV_URL, JEV_MODEL, JEV_API_KEY (a API direta da TypeSafe não foi conferida).
"""
import logging
import os
import time

import httpx

from .schemas import Plan, Step

log = logging.getLogger("jev")

URL = os.getenv("JEV_URL", "https://openrouter.ai/api/alpha/decisions")
MODEL = os.getenv("JEV_MODEL", "typesafe/jev-1.14")
MIN_P = float(os.getenv("JEV_MIN", "0.5"))  # abaixo disso o Jev também está em dúvida: o modelo de linguagem decide
TIMEOUT_S = float(os.getenv("JEV_TIMEOUT_S", "5"))

# O Jev não tem resposta "nenhuma das opções": por isso out_of_scope é uma opção como as outras.
# Todo o significado tem que estar nas descrições; não existe treino.
QUESTIONS = {
    "route": {
        "type": "choice",
        "instructions": "A merchant wrote this message to the support chat of Getnet, a payments company "
                        "(card machines, Pix, payment links). Which handler should take it?",
        "criteria": {
            "knowledge": "General question about Getnet products, services, fees or how something works. The answer is the same for every merchant.",
            "support": "About this merchant's own account or device: their payouts, their sales or transactions, a declined sale, the state of their card machine, their plan, opening a ticket.",
            "general": "Harmless factual question that is not about Getnet: weather, exchange rates, world facts, news.",
            "escalate": "Fraud, scam, cloned card, chargeback or dispute, formal complaint, legal threat, account cancellation, or an explicit request to talk to a human.",
            "out_of_scope": "Abusive, unsafe, or something a payments support chat should not do: jokes, homework, coding, creative writing.",
        },
    },
    "both": {
        "type": "noul",
        "instructions": "The message reports a problem with the merchant's own card machine or account AND asks what to do or how to fix it.",
    },
}
LABELS = set(QUESTIONS["route"]["criteria"])


def decide(message: str) -> dict:
    """Uma chamada, duas perguntas. Devolve {label, p, probabilities, both, cost_usd, latency_ms}."""
    key = os.getenv("JEV_API_KEY") or os.environ["OPENROUTER_API_KEY"]
    t0 = time.perf_counter()
    r = httpx.post(URL, timeout=TIMEOUT_S, headers={"Authorization": f"Bearer {key}"},
                   json={"model": MODEL, "state": message, "questions": QUESTIONS})
    r.raise_for_status()
    body = r.json()
    route, both = body["answers"]["route"], body["answers"].get("both", {})
    label = route.get("choice")
    probs = route.get("probabilities") if isinstance(route.get("probabilities"), dict) else {}
    p = probs.get(label, route.get("confidence") or 0.0)
    return {"label": label, "p": float(p), "probabilities": probs, "both": float(both.get("noul") or 0.0),
            "cost_usd": float(body.get("usage", {}).get("cost") or 0.0), "latency_ms": int((time.perf_counter() - t0) * 1000)}


def route(message: str) -> Plan | None:
    """Plano decidido pelo Jev, ou None quando ele falha ou fica em dúvida (aí o modelo de linguagem decide)."""
    try:
        d = decide(message)
    except Exception as e:  # noqa: BLE001
        log.warning("jev indisponível, seguindo para o modelo de linguagem: %s", e)
        return None
    if d["label"] not in LABELS or d["p"] < MIN_P:
        return None
    if d["label"] == "out_of_scope":
        return Plan(steps=[], confidence=d["p"], source="jev", reason="out_of_scope")
    agents = ["support", "knowledge"] if d["label"] in ("support", "knowledge") and d["both"] >= 0.5 else [d["label"]]
    return Plan(steps=[Step(agent=a, question=message) for a in agents], confidence=d["p"], source="jev", reason="jev")
