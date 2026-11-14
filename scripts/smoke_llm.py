"""Testa o provedor e os modelos do .env: nome do modelo existe, texto, JSON e chamada de ferramenta. Rodar antes da sessão."""
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app import llm  # noqa: E402  (llm.py já lê o .env)

print("provedor:", llm.PROVIDER, "| rápido:", llm.MODEL_FAST, "| principal:", llm.MODEL_SMART)

if llm.PROVIDER == "openrouter":  # confere os nomes na lista pública de modelos
    try:
        data = httpx.get("https://openrouter.ai/api/v1/models", timeout=20).json().get("data", [])
        by_id = {m.get("id"): m for m in data}
        for name in (llm.MODEL_FAST, llm.MODEL_SMART):
            m = by_id.get(name)
            if not m:
                near = [i for i in by_id if i and name.split("/")[0] in i][:8]
                print(f"0 nome   : '{name}' NÃO está na lista. Parecidos: {near}")
            else:
                params = m.get("supported_parameters")
                print(f"0 nome   : '{name}' existe | aceita ferramentas: {'tools' in params if params else 'não informado'}")
    except Exception as e:  # noqa: BLE001
        print("0 nome   : não consegui consultar a lista de modelos:", e)

print("1 texto  :", llm.complete("Responda em 3 palavras.", "Qual a capital do Brasil?", llm.MODEL_FAST)[:60])
print("2 json   :", llm.complete_json('Devolva o JSON {"ok": true}', "diga ok"))
tools = [{"name": "ping", "description": "retorna pong", "input_schema": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}}]
for label, model in (("rápido", llm.MODEL_FAST), ("principal", llm.MODEL_SMART)):
    txt, called = llm.run_tools("Use a ferramenta ping com x='a' e repita o resultado.", "faça o ping", tools, {"ping": lambda x: {"pong": x}}, model)
    print(f"3 tools  : {label} chamou {called} | {txt[:50]}")
    assert called == ["ping"], f"o modelo {model} não chamou a ferramenta; troque no .env"
print("OK")
