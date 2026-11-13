"""Fluxo: máscara → injeção → regras → classificador local → (Jev, depois modelo, se houver dúvida) → agentes → verificação → resposta.

Roteamento em cascata, do mais barato para o mais caro: cada degrau só é chamado quando o anterior não tem certeza.
"""
import json
import logging
import os
import re
import time
import uuid

from . import agents, guardrails, jev, router_clf
from .schemas import AgentResult, ChatRequest, ChatResponse, Plan, Step

log = logging.getLogger("orchestrator")

# Quem decide quando o classificador local fica abaixo do limiar: "jev" (decisão barata e rápida) ou "llm".
ROUTER_FALLBACK = os.getenv("ROUTER_FALLBACK", "llm")

# "minha maquininha ... o que eu faço?" pede dado da conta E instrução de produto: Suporte e depois Conhecimento.
MINE = re.compile(r"\b(my|minha|meu)\b.{0,30}\b(maquininha|maquina|terminal|machine|reader|leitor)\b")
HOWTO = re.compile(r"\b(what should i do|what do i do|how (do|can) i fix|how to fix|o que (eu )?(faco|devo fazer)|o que fazer|como (resolver|resolvo|arrumar|arrumo|consertar))\b")


def plan_for(msg: str) -> Plan:
    n = guardrails.normalize(msg)
    if guardrails.is_sensitive(msg) or guardrails.wants_human(msg):
        return Plan(steps=[Step(agent="escalate", question=msg)], confidence=1.0, source="rule", reason="sensitive_or_human")
    if MINE.search(n) and HOWTO.search(n):
        return Plan(steps=[Step(agent="support", question=msg), Step(agent="knowledge", question=msg)],
                    confidence=1.0, source="rule", reason="account_problem_plus_howto")
    label, p, top2 = router_clf.predict(msg)
    if p >= router_clf.HIGH:
        return Plan(steps=[Step(agent=label, question=msg)], confidence=p, source="clf", reason="clf_high")
    if ROUTER_FALLBACK == "jev":
        plan = jev.route(msg)
        if plan is not None:
            return plan
    return agents.route_llm(msg, [c for c, _ in top2])


def handle(req: ChatRequest) -> ChatResponse:
    t0 = time.perf_counter()
    trace = uuid.uuid4().hex[:12]
    lang = guardrails.language(req.message)
    msg = guardrails.mask(req.message)

    def done(answer, route, decided_by, conf, results: list[AgentResult], handoff=False, ticket=None) -> ChatResponse:
        resp = ChatResponse(
            answer=guardrails.mask_output(answer), route=route, decided_by=decided_by, confidence=round(conf, 3),
            sources=sorted({s for r in results if r.agent != "escalate" for s in r.sources if s}),
            tool_calls=[t for r in results for t in r.tool_calls], handoff=handoff, ticket_id=ticket,
            trace_id=trace, latency_ms=int((time.perf_counter() - t0) * 1000))
        log.info(json.dumps({"trace_id": trace, "user_id": req.user_id, "route": route, "decided_by": decided_by,
                             "confidence": resp.confidence, "tool_calls": resp.tool_calls, "handoff": handoff,
                             "errors": [r.error for r in results if r.error], "latency_ms": resp.latency_ms}, ensure_ascii=False))
        return resp

    def hand_off(route, decided_by, conf, results, facts, reason) -> ChatResponse:
        e = agents.escalate(msg, req.user_id, facts, reason)
        partial = (agents.write_final(msg, facts) + "\n\n") if facts else ""
        return done(partial + e.facts[0], route + ["escalate"], decided_by, conf, results + [e], handoff=True, ticket=e.sources[0])

    if guardrails.detect_injection(msg):
        return done(guardrails.REFUSAL[lang], ["guardrail"], "guardrail", 1.0, [])

    try:
        plan = plan_for(msg)
        if not plan.steps:
            return done(guardrails.OUT_OF_SCOPE[lang], ["out_of_scope"], plan.source, plan.confidence, [])

        results: list[AgentResult] = []
        facts: list[str] = []
        route: list[str] = []
        for step in plan.steps:
            if step.agent == "escalate":
                return hand_off(route, plan.source, plan.confidence, results, facts, plan.reason or "router")
            route.append(step.agent)
            if step.agent == "knowledge":
                r = agents.knowledge(msg, facts)
                # fatos dos agentes anteriores (dados da conta) também sustentam a resposta, além dos trechos da base
                if not r.error and not agents.verify(r.facts[0], r.evidence + facts):
                    r = AgentResult(agent="knowledge", tool_calls=r.tool_calls, error="ungrounded_answer")
            elif step.agent == "support":
                r = agents.support(msg, req.user_id, facts)
            else:
                r = agents.general(msg, facts)
            results.append(r)
            if r.error:
                return hand_off(route, plan.source, plan.confidence, results, facts, f"agent_error:{r.error}")
            facts += r.facts
        return done(agents.write_final(msg, facts), route, plan.source, plan.confidence, results)
    except Exception:  # noqa: BLE001  # provedor fora do ar, tempo esgotado, erro nosso: nunca devolver 500 ao cliente
        log.exception("trace_id=%s falha no fluxo", trace)
        try:
            return hand_off([], "error", 0.0, [], [], "internal_error")
        except Exception:  # noqa: BLE001
            return done(guardrails.FALLBACK[lang], ["error"], "error", 0.0, [], handoff=True)
