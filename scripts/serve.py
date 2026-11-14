"""Sobe a API com um comando, em qualquer sistema, sem make e sem variáveis de ambiente.

    python scripts/serve.py --cli     sem chave: usa o Claude Code instalado e logado na máquina
    python scripts/serve.py           usa o provedor e a chave do arquivo .env

Depois abra http://localhost:8000/docs. Porta diferente: variável PORT.
"""
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)  # os caminhos de dados são relativos à raiz
sys.path.insert(0, str(ROOT / "src"))

if "--cli" in sys.argv:  # antes de importar o app, que lê estas variáveis ao carregar
    os.environ.update(LLM_PROVIDER="claude_cli", ROUTER_FALLBACK="llm")
    if not shutil.which("claude"):
        sys.exit("Claude Code não encontrado nesta máquina. Instale, rode `claude` uma vez para entrar na conta e tente de novo.")

import uvicorn  # noqa: E402

port = int(os.getenv("PORT", "8000"))
print(f"Abra http://localhost:{port}/docs  (para parar: Ctrl+C)")
uvicorn.run("app.api:app", host="127.0.0.1", port=port)
