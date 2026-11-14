"""Única porta de saída para o modelo. LLM_PROVIDER = anthropic | openrouter | claude_cli | fake.

claude_cli não usa chave de API: chama o Claude Code instalado e logado na máquina (`claude -p`).
Serve para desenvolver e rodar a avaliação sem chave. Não funciona dentro do Docker (o contêiner não tem o Claude Code).
"""
import json
import os
import shutil
import subprocess
import tempfile
from typing import Any

from .guardrails import wrap_data

try:  # fora do Docker (make run, evals) o .env precisa ser lido aqui; variável já definida não é sobrescrita
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "40"))
PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")
MODEL_FAST = os.getenv("MODEL_FAST", "claude-haiku-5-5")
MODEL_SMART = os.getenv("MODEL_SMART", "claude-sonnet-5-5")
EXHAUSTED = "Não consegui concluir a consulta."  # o loop de ferramentas acabou sem resposta; o agente trata como falha

KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openrouter": "OPENROUTER_API_KEY"}

_client = None


def config_problem() -> str | None:
    """O que impede o provedor de responder, visto sem chamar o modelo; None se nada foi encontrado.
    Sem este aviso, chave ausente parece sucesso: toda resposta vira encaminhamento para humano com HTTP 200."""
    if PROVIDER in KEY_ENV:
        key = os.getenv(KEY_ENV[PROVIDER], "").strip()
        if not key or key.endswith("..."):
            return f"{KEY_ENV[PROVIDER]} is missing or still the placeholder of .env.example: every answer will be a handoff"
    elif PROVIDER == "claude_cli":
        if not shutil.which("claude"):
            return "Claude Code CLI not found on PATH (LLM_PROVIDER=claude_cli does not work inside Docker)"
    elif PROVIDER != "fake":
        return f"unknown LLM_PROVIDER '{PROVIDER}': use anthropic, openrouter, claude_cli or fake"
    return None


def _client_for():
    global _client
    if _client is not None:
        return _client
    if PROVIDER == "anthropic":
        import anthropic
        _client = anthropic.Anthropic(timeout=TIMEOUT_S, max_retries=1)
    elif PROVIDER == "openrouter":
        from openai import OpenAI
        _client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ["OPENROUTER_API_KEY"],
            timeout=TIMEOUT_S, max_retries=1,
            default_headers={"HTTP-Referer": os.getenv("APP_URL", "https://github.com/getnet-multi-agent"),
                             "X-Title": "getnet-multi-agent"},
        )
    return _client


def complete(system: str, user: str, model: str = MODEL_SMART, max_tokens: int = 700) -> str:
    if PROVIDER == "fake":
        return FakeLLM.complete(system, user)
    if PROVIDER == "claude_cli":
        return _cli(system, user, model)
    if PROVIDER == "anthropic":
        r = _client_for().messages.create(model=model, max_tokens=max_tokens, system=system,
                                          messages=[{"role": "user", "content": user}])
        return "".join(b.text for b in r.content if b.type == "text")
    r = _client_for().chat.completions.create(
        model=model, max_tokens=max_tokens,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    return r.choices[0].message.content or ""


def complete_json(system: str, user: str, model: str = MODEL_FAST) -> dict[str, Any]:
    text = complete(system + "\nResponda SOMENTE com JSON válido, sem markdown.", user, model, 400)
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    return json.loads(text)


def _to_openai_tools(tools: list[dict]) -> list[dict]:
    return [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                              "parameters": t["input_schema"]}} for t in tools]


def _call(handlers: dict, name: str, args: dict) -> str:
    try:
        out = handlers[name](**args)
    except Exception as e:  # noqa: BLE001
        out = {"error": str(e)}
    # Saída de ferramenta é conteúdo externo (API, página da web): volta ao modelo marcada como dados (D18)
    return wrap_data("tool_result", json.dumps(out, ensure_ascii=False))


def run_tools(system: str, user: str, tools: list[dict], handlers: dict,
              model: str = MODEL_SMART, max_rounds: int = 4) -> tuple[str, list[str]]:
    """Loop de tool use. Devolve (texto final, nomes das ferramentas chamadas)."""
    if PROVIDER == "fake":
        return FakeLLM.run_tools(user, handlers)
    if PROVIDER == "claude_cli":
        return _run_tools_cli(system, user, tools, handlers, model, max_rounds)
    if PROVIDER == "anthropic":
        return _run_tools_anthropic(system, user, tools, handlers, model, max_rounds)
    return _run_tools_openai(system, user, tools, handlers, model, max_rounds)


# ---------- claude_cli ----------
CLI_PROTOCOL = """

Ferramentas disponíveis (JSON Schema):
{tools}

Protocolo: responda com UM objeto JSON e nada mais.
- Para usar uma ferramenta: {{"tool": "<nome>", "args": {{...}}}}
- Para dar a resposta final: {{"final": "<texto>"}}
As chamadas que você já fez aparecem no fim da mensagem, cada uma com o resultado. Não repita chamada que já tem resultado:
use o resultado e, quando tiver o que precisa, dê a resposta final."""


def _cli(system: str, user: str, model: str) -> str:
    """Uma chamada ao Claude Code, sem as ferramentas dele e fora da pasta do projeto (para não carregar o CLAUDE.md)."""
    alias = "haiku" if model == MODEL_FAST else "sonnet"  # apelidos do Claude Code; os nomes do .env são de outro provedor
    exe = shutil.which("claude")  # caminho completo: no Windows o nome sozinho não acha o claude.exe fora da pasta atual
    if not exe:
        raise RuntimeError("Claude Code não encontrado. Instale, rode `claude` uma vez para entrar na conta e tente de novo.")
    # encoding fixo: o padrão do Windows não é UTF-8 e estragava acentos e símbolos dos trechos em português
    r = subprocess.run([exe, "-p", "--system-prompt", system, "--tools", "", "--strict-mcp-config", "--model", alias,
                        "--output-format", "json"], input=user, capture_output=True, text=True, encoding="utf-8",
                       timeout=TIMEOUT_S * 3, cwd=tempfile.gettempdir())
    d = json.loads(r.stdout)
    if d.get("is_error"):
        raise RuntimeError(f"claude -p falhou: {str(d.get('result'))[:200]}")
    return d.get("result") or ""


def _run_tools_cli(system, user, tools, handlers, model, max_rounds):
    """O Claude Code não recebe ferramentas nossas pela linha de comando, então o pedido de ferramenta vem como JSON no texto.
    É uma imitação da chamada de ferramenta das APIs: confere agentes e prompts, não o formato de rede dos outros provedores."""
    system += CLI_PROTOCOL.format(tools=json.dumps(tools, ensure_ascii=False))
    called: list[str] = []
    for _ in range(max_rounds):
        text = _cli(system, user, model)
        try:
            d = json.loads(text[text.index("{"): text.rindex("}") + 1])
        except ValueError:  # respondeu em texto puro: vale como resposta final
            return text, called
        if "tool" not in d:
            return str(d.get("final", text)), called
        args = d.get("args") or {}
        called.append(d["tool"])
        user += f"\n\n[chamada já feita] {d['tool']}({json.dumps(args, ensure_ascii=False)}) devolveu:\n{_call(handlers, d['tool'], args)}"
    return EXHAUSTED, called


def _run_tools_anthropic(system, user, tools, handlers, model, max_rounds):
    client = _client_for()
    messages = [{"role": "user", "content": user}]
    called: list[str] = []
    for _ in range(max_rounds):
        r = client.messages.create(model=model, max_tokens=800, system=system, tools=tools, messages=messages)
        messages.append({"role": "assistant", "content": r.content})
        if r.stop_reason != "tool_use":
            return "".join(b.text for b in r.content if b.type == "text"), called
        results = []
        for b in r.content:
            if b.type == "tool_use":
                called.append(b.name)
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": _call(handlers, b.name, b.input)})
        messages.append({"role": "user", "content": results})
    return EXHAUSTED, called


def _run_tools_openai(system, user, tools, handlers, model, max_rounds):
    client = _client_for()
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    called: list[str] = []
    for _ in range(max_rounds):
        r = client.chat.completions.create(model=model, max_tokens=800, messages=messages,
                                           tools=_to_openai_tools(tools), tool_choice="auto")
        m = r.choices[0].message
        messages.append(m)
        if not m.tool_calls:
            return m.content or "", called
        for tc in m.tool_calls:
            called.append(tc.function.name)
            args = json.loads(tc.function.arguments or "{}")
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": _call(handlers, tc.function.name, args)})
    return EXHAUSTED, called


class FakeLLM:
    """Dublê determinístico para testes sem chave. Só confere o encanamento; não mede qualidade de resposta."""

    @staticmethod
    def complete(system: str, user: str) -> str:
        if "JSON" in system and "steps" in system:
            u = user.lower()
            if any(k in u for k in ("receita", "bolo", "piada", "recipe", "joke")):
                return json.dumps({"steps": [], "confidence": 0.9, "reason": "out_of_scope"})
            agent = "knowledge"
            if any(k in u for k in ("weather", "chove", "clima", "euro", "dolar", "dólar", "exchange")):
                agent = "general"
            elif any(k in u for k in (" my ", "minha", "meu ", "dinheiro de ontem", "money from", "recusando")):
                agent = "support"
            return json.dumps({"steps": [{"agent": agent, "question": "fake"}], "confidence": 0.7, "reason": "fake"})
        if "sustentada" in system:
            return json.dumps({"grounded": True})
        return f"[fake] {user[:120]}"

    @staticmethod
    def run_tools(user: str, handlers: dict) -> tuple[str, list[str]]:
        u = user.lower()
        if "weather" in handlers:
            if any(k in u for k in ("weather", "tempo", "clima", "chuva", "chove", "rain")):
                return "[fake] " + json.dumps(handlers["weather"](city="Porto Alegre"))[:200], ["weather"]
            if any(k in u for k in ("euro", "dolar", "dólar", "exchange", "cotac", "cotaç")):
                return "[fake] " + json.dumps(handlers["fx_rate"](pair="EUR-BRL"))[:200], ["fx_rate"]
            return "[fake] sem ferramenta", []
        order = []
        if any(k in u for k in ("deposit", "cai ", "receb", "settle", "dinheiro", "money")):
            order.append("get_settlements")
        if any(k in u for k in ("declin", "recus", "transa", "vendas", "sales")):
            order.append("get_transactions")
        if any(k in u for k in ("connect", "conect", "internet", "machine", "maquin")):
            order.append("get_terminal_status")
        if not order:
            order.append("get_profile")
        outs = [handlers[n]() for n in order if n in handlers]
        return "[fake] " + json.dumps(outs, ensure_ascii=False)[:300], order
