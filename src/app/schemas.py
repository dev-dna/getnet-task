from typing import Literal

from pydantic import BaseModel, Field

Agent = Literal["knowledge", "support", "general", "escalate"]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000, description="The merchant's message, in Portuguese or English.")
    user_id: str = Field(min_length=1, max_length=64, description="Merchant identifier. The demo data has `cliente1988`.")


class Step(BaseModel):
    agent: Agent
    question: str  # leitura do roteador, só para o log; os agentes recebem a mensagem original


class Plan(BaseModel):
    steps: list[Step]
    confidence: float
    source: Literal["rule", "clf", "jev", "llm"]
    reason: str = ""


class AgentResult(BaseModel):
    agent: str
    facts: list[str] = []
    sources: list[str] = []
    evidence: list[str] = []  # trechos que sustentam a resposta; usados pelo verificador, não vão na resposta
    tool_calls: list[str] = []
    error: str | None = None


class ChatResponse(BaseModel):
    answer: str = Field(description="Final answer, in the language of the message. Card numbers, CPF and CNPJ are masked.")
    route: list[str] = Field(description="Agents that ran, in order: `knowledge`, `support`, `general`, `escalate`. "
                                         "Or `guardrail` (blocked) / `out_of_scope` (declined).")
    decided_by: Literal["guardrail", "rule", "clf", "jev", "llm", "error"] = Field(
        description="Which step of the routing cascade decided: fixed rule, local classifier, Jev decision model, or language model.")
    confidence: float = Field(description="Probability reported by whoever decided the route (0 to 1).")
    sources: list[str] = Field(default=[], description="URLs of the knowledge-base pages used, or the external data source.")
    tool_calls: list[str] = Field(default=[], description="Tools the agents called, in order.")
    handoff: bool = Field(default=False, description="True when the case was passed to a human agent.")
    ticket_id: str | None = Field(default=None, description="Ticket number when `handoff` is true.")
    trace_id: str = Field(description="Id of this request in the structured log.")
    latency_ms: int

    model_config = {"json_schema_extra": {"examples": [{
        "answer": "Your next payout is R$ 1,834.50 on 2026-11-13 (yesterday's debit and Pix sales).",
        "route": ["support"], "decided_by": "clf", "confidence": 0.84, "sources": [], "tool_calls": ["get_settlements"],
        "handoff": False, "ticket_id": None, "trace_id": "3f9a1c2b7d10", "latency_ms": 1840}]}}


class Health(BaseModel):
    status: str
    llm_provider: str = Field(description="`anthropic`, `openrouter`, `claude_cli` (local, no API key) or `fake` (tests).")
    router_fallback: str = Field(description="Who decides when the local classifier is unsure: `jev` or `llm`.")
    corpus_chunks: int
    corpus_is_placeholder: bool = Field(description="True means the knowledge base is still the sample file. Run scripts/ingest.py.")
