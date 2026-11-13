"""Quatro agentes. Cada um é uma função que recebe a mensagem ORIGINAL (já mascarada) e devolve AgentResult."""
import logging

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
        steps = [Step(**s) for s in d.get("steps", [])][:3]
        return Plan(steps=steps, confidence=float(d.get("confidence", 0.6)), source="llm",
                    reason=d.get("reason", "") if steps else "out_of_scope")
    except Exception as e:  # noqa: BLE001  # roteador falhou: segue o palpite do classificador
        log.warning("route_llm falhou: %s", e)
        return Plan(steps=[Step(agent=candidates[0], question=message)], confidence=0.5, source="clf", reason="router_llm_failed")


def knowledge(message: str, facts: list[str]) -> AgentResult:
    chunks = retriever.retrieve(message, k=5)
    if not chunks:
        return AgentResult(agent="knowledge", tool_calls=["retrieve"], error="no_chunks")
    # A evidência leva URL e título, iguais ao que o agente lê: sem eles o verificador reprovava a própria citação da fonte.
    evidence = [f"[{c['url']}] {c['title']}\n{c['text']}" for c in chunks]
    user = wrap_data("chunks", "\n\n".join(evidence)) + "\n"
    if facts:
        user += wrap_data("facts_from_previous_agents", "\n".join(facts)) + "\n"
    answer = llm.complete(KNOWLEDGE_SYS + reply_in(message), user + f"Pergunta: {message}")
    if "NOT_FOUND" in answer[:40]:
        return AgentResult(agent="knowledge", tool_calls=["retrieve"], error="not_in_kb")
    return AgentResult(agent="knowledge", facts=[answer], sources=sorted({c["url"] for c in chunks}),
                       evidence=evidence, tool_calls=["retrieve"])


def general(message: str, facts: list[str]) -> AgentResult:
    defs, handlers, used = tools.bind_general()
    text, called = llm.run_tools(GENERAL_SYS + reply_in(message), wrap_data("message", message), defs, handlers, model=llm.MODEL_FAST)
    return AgentResult(agent="general", facts=[text], tool_calls=called, sources=sorted(set(used)))


def support(message: str, user_id: str, facts: list[str]) -> AgentResult:
    if user_id not in tools.merchants():
        return AgentResult(agent="support", error="merchant_not_found")
    defs, handlers = tools.bind(user_id)
    text, called = llm.run_tools(SUPPORT_SYS + reply_in(message), wrap_data("message", message), defs, handlers)
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
