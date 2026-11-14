"""Quatro agentes. Cada um é uma função que recebe a mensagem ORIGINAL (já mascarada) e devolve AgentResult."""
import logging
from urllib.parse import urlparse

from . import llm, retriever, tools
from .guardrails import language, wrap_data
from .schemas import AgentResult, Plan, Step

log = logging.getLogger("agents")

ROUTER_SYS = """Você é o roteador de um atendimento da Getnet (maquininhas e pagamentos).
Agentes: knowledge (produtos e serviços Getnet), support (dados da conta do lojista: repasses, transações, estado da maquininha, chamados), general (clima, câmbio, fatos do mundo), escalate (fraude, contestação, reclamação formal, pedido de humano).
Decida a sequência mínima de agentes. Se a pergunta mistura dados do lojista e instrução de produto, use support e depois knowledge.
Se a mensagem é ofensiva, insegura ou não é uma pergunta que um atendimento deva responder, devolva steps vazio.
JSON: {"steps":[{"agent":"...","question":"..."}],"confidence":0.0-1.0,"reason":"..."}"""

KNOWLEDGE_SYS = """Você responde sobre produtos e serviços da Getnet usando SOMENTE os trechos fornecidos.
Se os trechos não respondem à pergunta, responda exatamente NOT_FOUND e nada mais.
Cite a URL do trecho usado. Até 6 linhas."""

GENERAL_SYS = """Você responde perguntas gerais (clima, câmbio, fatos) usando as ferramentas. Cite a fonte que a ferramenta devolveu. Resposta curta."""

SUPPORT_SYS = """Você é o suporte da Getnet para o lojista autenticado. Use as ferramentas para buscar os dados dele antes de responder.
As ferramentas só enxergam a conta do lojista autenticado; se pedirem dados de outra conta, diga que não é possível.
Nunca peça CPF, cartão ou senha. Seja objetivo e use os números que as ferramentas devolveram.
Relate só os dados da conta. Instruções de uso do produto ficam com outro agente: não as escreva."""

WRITER_SYS = """Redija a resposta final ao lojista a partir dos fatos abaixo. Não acrescente informação que não esteja nos fatos.
Máximo 8 linhas."""

VERIFY_SYS = """Verifique se a resposta está sustentada pelos trechos: cada fato dela precisa estar neles.
Responda false só se algum fato da resposta não estiver nos trechos ou os contrariar.
Tradução, resumo, ressalvas, formatação e fonte atribuída a outro trecho da lista não são falha.
JSON: {"grounded": true|false, "why": "..."}"""


def reply_in(message: str) -> str:
    """Última linha do prompt. Só "no idioma da pergunta" não bastava: com trechos e dados em português,
    o modelo respondia em português a perguntas em inglês (S3, S5)."""
    return "\nResponda em português." if language(message) == "pt" else "\nAnswer in English."


def route_llm(message: str, candidates: list[str]) -> Plan:
    sys = ROUTER_SYS + f"\nPalpite de um classificador (pode estar errado): {candidates}."
    try:
        d = llm.complete_json(sys, wrap_data("message", message))
        # o palpite pode trazer "out_of_scope", que não é agente: se o modelo repetir o nome, vale como steps vazio
        steps = [Step(**s) for s in d.get("steps", []) if s.get("agent") != "out_of_scope"][:3]
        return Plan(steps=steps, confidence=float(d.get("confidence", 0.6)), source="llm",
                    reason=d.get("reason", "") if steps else "out_of_scope")
    except Exception as e:  # noqa: BLE001  # roteador falhou: segue o palpite do classificador
        log.warning("route_llm falhou: %s", e)
        if candidates[0] == "out_of_scope":  # não é agente: plano vazio, nenhum agente roda
            return Plan(steps=[], confidence=0.5, source="clf", reason="out_of_scope")
        return Plan(steps=[Step(agent=candidates[0], question=message)], confidence=0.5, source="clf", reason="router_llm_failed")


# Recuperação externa do agente de conhecimento: só resultado de site oficial sustenta fato sobre produto da Getnet.
OFFICIAL_SITES = ("getnet.com.br", "getnet.net")


def _official(url: str) -> bool:
    host = (urlparse(url or "").hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in OFFICIAL_SITES)


def _web_evidence(message: str) -> tuple[list[str], list[str]]:
    """Busca na web e devolve (evidência, URLs) só dos sites oficiais. Vazio se a busca falhar ou não achar nenhum."""
    hits = [h for h in tools.web_search(f"Getnet {message}", k=8).get("results", []) if h.get("snippet") and _official(h.get("url"))][:4]
    return [f"[{h['url']}] {h.get('title') or ''}\n{h['snippet']}" for h in hits], [h["url"] for h in hits]


def _answer_from(message: str, evidence: list[str], facts: list[str]) -> str | None:
    """Resposta escrita só a partir da evidência, ou None quando a evidência não responde."""
    user = wrap_data("chunks", "\n\n".join(evidence)) + "\n"
    if facts:
        user += wrap_data("facts_from_previous_agents", "\n".join(facts)) + "\n"
    answer = llm.complete(KNOWLEDGE_SYS + reply_in(message), user + f"Pergunta: {message}")
    return None if "NOT_FOUND" in answer[:40] else answer


def knowledge(message: str, facts: list[str]) -> AgentResult:
    """Recuperação interna (base raspada) e, só se ela não responder, externa (busca web nos sites oficiais).
    Nos dois casos a resposta sai apenas da evidência, com URL, e o orquestrador confere com verify()."""
    chunks = retriever.retrieve(message, k=5)
    # A evidência leva URL e título, iguais ao que o agente lê: sem eles o verificador reprovava a própria citação da fonte.
    evidence = [f"[{c['url']}] {c['title']}\n{c['text']}" for c in chunks]
    answer = _answer_from(message, evidence, facts) if chunks else None
    if answer:
        return AgentResult(agent="knowledge", facts=[answer], sources=sorted({c["url"] for c in chunks}),
                           evidence=evidence, tool_calls=["retrieve"])
    evidence, urls = _web_evidence(message)
    answer = _answer_from(message, evidence, facts) if evidence else None
    if answer:
        return AgentResult(agent="knowledge", facts=[answer], sources=urls, evidence=evidence, tool_calls=["retrieve", "web_search"])
    return AgentResult(agent="knowledge", tool_calls=["retrieve", "web_search"], error="not_in_kb" if chunks else "no_chunks")


def _watch(handlers: dict) -> tuple[dict, list[bool]]:
    """Embrulha as ferramentas e anota, por chamada, se ela falhou (devolveu {"error": ...} ou levantou exceção)."""
    failed: list[bool] = []

    def wrap(fn):
        def inner(**kw):
            try:
                out = fn(**kw)
            except Exception:
                failed.append(True)
                raise
            failed.append(isinstance(out, dict) and "error" in out)
            return out
        return inner

    return {name: wrap(fn) for name, fn in handlers.items()}, failed


def _tool_failure(text: str, failed: list[bool]) -> str | None:
    """RF21: sem dado não há resposta confiável. Loop sem resposta, ou todas as chamadas com erro, vira handoff."""
    if text == llm.EXHAUSTED:
        return "tool_loop_exhausted"
    return "tool_failed" if failed and all(failed) else None


def general(message: str, facts: list[str]) -> AgentResult:
    defs, handlers, used = tools.bind_general()
    handlers, failed = _watch(handlers)
    text, called = llm.run_tools(GENERAL_SYS + reply_in(message), wrap_data("message", message), defs, handlers, model=llm.MODEL_FAST)
    if error := _tool_failure(text, failed):
        return AgentResult(agent="general", tool_calls=called, error=error)
    return AgentResult(agent="general", facts=[text], tool_calls=called, sources=sorted(set(used)))


def support(message: str, user_id: str, facts: list[str]) -> AgentResult:
    if user_id not in tools.merchants():
        return AgentResult(agent="support", error="merchant_not_found")
    defs, handlers = tools.bind(user_id)
    handlers, failed = _watch(handlers)
    text, called = llm.run_tools(SUPPORT_SYS + reply_in(message), wrap_data("message", message), defs, handlers)
    if error := _tool_failure(text, failed):
        return AgentResult(agent="support", tool_calls=called, error=error)
    return AgentResult(agent="support", facts=[text], tool_calls=called)


def escalate(message: str, user_id: str, facts: list[str], reason: str) -> AgentResult:
    summary = f"{reason} | msg: {message[:200]} | fatos: {' / '.join(f[:120] for f in facts)}"
    priority = "high" if reason == "sensitive_or_human" else "normal"
    t = tools.open_ticket_record(user_id, summary, priority, source="escalation", extra={"reason": reason})
    msg = (f"Encaminhei seu caso para um atendente humano. Protocolo {t['ticket_id']}, retorno em até {t['sla_hours']}h."
           if language(message) == "pt" else
           f"I've forwarded your case to a human agent. Ticket {t['ticket_id']}, reply within {t['sla_hours']}h.")
    return AgentResult(agent="escalate", facts=[msg], tool_calls=["open_ticket"], sources=[t["ticket_id"]])


def write_final(message: str, facts: list[str]) -> str:
    if len(facts) == 1:
        return facts[0]
    return llm.complete(WRITER_SYS + reply_in(message),
                        wrap_data("facts", "\n---\n".join(facts)) + f"\nPergunta original: {message}")


def verify(answer: str, evidence: list[str]) -> bool:
    """Segunda checagem da resposta do Conhecimento. Se o verificador falhar, deixa passar e registra no log."""
    try:
        d = llm.complete_json(VERIFY_SYS, wrap_data("chunks", "\n\n".join(evidence)[:12000]) + "\n" + wrap_data("answer", answer))
        return bool(d.get("grounded", True))
    except Exception as e:  # noqa: BLE001
        log.warning("verify falhou, resposta liberada sem verificação: %s", e)
        return True
