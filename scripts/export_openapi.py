"""Grava o contrato da API em openapi.json, sem precisar subir o servidor."""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("LLM_PROVIDER", "fake")  # só para importar o app; nenhuma chamada de modelo é feita
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app.api import app  # noqa: E402

spec = app.openapi()
Path("openapi.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
post = spec["paths"]["/chat"]["post"]
print(f"openapi.json: {len(spec['paths'])} rotas, {len(post['requestBody']['content']['application/json']['examples'])} exemplos em POST /chat")
