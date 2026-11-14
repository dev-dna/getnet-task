"""Provedor claude_cli com a linha de comando simulada. A chamada de verdade: `make eval-cli`."""
import json

import pytest

from app import llm


class _Done:
    def __init__(self, result, is_error=False):
        self.stdout = json.dumps({"result": result, "is_error": is_error})


@pytest.fixture
def cli(monkeypatch):
    monkeypatch.setattr(llm, "PROVIDER", "claude_cli")
    monkeypatch.setattr(llm.shutil, "which", lambda name: "claude")  # o teste não depende do Claude Code instalado
    sent = []

    def install(*answers):
        queue = list(answers)

        def fake_run(cmd, input, **kw):
            sent.append({"cmd": cmd, "input": input, **kw})
            return queue.pop(0)
        monkeypatch.setattr(llm.subprocess, "run", fake_run)
        return sent
    return install


def test_text_call_uses_no_claude_code_tools_and_stays_out_of_the_project(cli):
    sent = cli(_Done("Brasília"))
    assert llm.complete("Responda curto.", "Capital do Brasil?", llm.MODEL_FAST) == "Brasília"
    cmd = sent[0]["cmd"]
    assert cmd[:2] == ["claude", "-p"] and cmd[cmd.index("--tools") + 1] == "" and cmd[cmd.index("--model") + 1] == "haiku"
    assert cmd[cmd.index("--system-prompt") + 1] == "Responda curto." and sent[0]["input"] == "Capital do Brasil?"
    assert sent[0]["cwd"] != "."
    assert sent[0]["encoding"] == "utf-8"  # no Windows o padrão não é UTF-8 e estragava os acentos


def test_missing_claude_code_gives_a_clear_error(monkeypatch):
    monkeypatch.setattr(llm, "PROVIDER", "claude_cli")
    monkeypatch.setattr(llm.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="Claude Code não encontrado"):
        llm.complete("s", "u")


def test_tool_loop_runs_the_tool_and_feeds_the_result_back(cli):
    sent = cli(_Done('{"tool": "ping", "args": {"x": "a"}}'), _Done('{"final": "pong a"}'))
    tools = [{"name": "ping", "description": "retorna pong", "input_schema": {"type": "object", "properties": {"x": {"type": "string"}}}}]
    text, called = llm.run_tools("Use ping.", "faça o ping", tools, {"ping": lambda x: {"pong": x}})
    assert (text, called) == ("pong a", ["ping"])
    assert '"ping"' in sent[0]["cmd"][sent[0]["cmd"].index("--system-prompt") + 1]  # a ferramenta foi descrita ao modelo
    assert '{"pong": "a"}' in sent[1]["input"]  # o resultado voltou na segunda chamada


def test_plain_text_counts_as_the_final_answer(cli):
    cli(_Done("sem JSON aqui"))
    assert llm.run_tools("s", "u", [], {}) == ("sem JSON aqui", [])


def test_cli_error_raises_so_the_orchestrator_hands_off(cli):
    cli(_Done("limite atingido", is_error=True))
    with pytest.raises(RuntimeError):
        llm.complete("s", "u")


@pytest.mark.parametrize("provider,env,problem", [
    ("openrouter", {}, "OPENROUTER_API_KEY"),
    ("openrouter", {"OPENROUTER_API_KEY": "sk-or-v1-..."}, "placeholder"),   # o valor que vem no .env.example
    ("openrouter", {"OPENROUTER_API_KEY": "sk-or-v1-abc123"}, None),
    ("anthropic", {}, "ANTHROPIC_API_KEY"),
    ("anthropic", {"ANTHROPIC_API_KEY": "sk-ant-abc123"}, None),
    ("fake", {}, None),
    ("gemini", {}, "unknown LLM_PROVIDER"),
])
def test_missing_key_is_reported_without_calling_the_model(monkeypatch, provider, env, problem):
    """Sem este aviso, chave ausente parece sucesso: HTTP 200 e toda resposta encaminhada para humano."""
    monkeypatch.setattr(llm, "PROVIDER", provider)
    for name in llm.KEY_ENV.values():
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    found = llm.config_problem()
    assert (found is None) if problem is None else (problem in found)


# ---------- provedores de API: o raciocínio do modelo conta no limite de saída ----------
class _Choice:
    def __init__(self, text, finish):
        self.finish_reason = finish
        self.message = type("M", (), {"content": text, "tool_calls": None})()


class _OpenAIStub:
    """Imita o cliente do formato OpenAI (OpenRouter): guarda o que foi pedido e devolve o fim configurado."""
    def __init__(self, finish):
        self.sent, self.finish = {}, finish
        self.chat = type("C", (), {"completions": self})()

    def create(self, **kw):
        self.sent = kw
        return type("R", (), {"choices": [_Choice("Toque em Configurar e depois em Conex", self.finish)]})()


@pytest.mark.parametrize("call", ["complete", "run_tools"])
def test_answer_cut_at_the_output_limit_is_an_error_not_an_answer(monkeypatch, call):
    """Rodada com chave real de 14/nov: o raciocínio consumiu o limite e a S5 foi entregue sem as instruções."""
    stub = _OpenAIStub("length")
    monkeypatch.setattr(llm, "PROVIDER", "openrouter")
    monkeypatch.setattr(llm, "_client_for", lambda: stub)
    with pytest.raises(llm.Truncated):
        llm.complete("s", "u") if call == "complete" else llm.run_tools("s", "u", [], {})


def test_output_limit_leaves_room_for_the_model_to_reason(monkeypatch):
    stub = _OpenAIStub("stop")
    monkeypatch.setattr(llm, "PROVIDER", "openrouter")
    monkeypatch.setattr(llm, "_client_for", lambda: stub)
    assert llm.complete("s", "u", max_tokens=700).startswith("Toque")
    assert stub.sent["max_tokens"] == 700 + llm.THINKING_ROOM and llm.THINKING_ROOM >= 1000
