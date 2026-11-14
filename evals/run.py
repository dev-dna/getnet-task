"""Roda evals/dataset.jsonl contra a API (ou direto no orquestrador com EVAL_DIRECT=1) e imprime a tabela.

Grupos: S = cenários do enunciado | H = mesmas intenções com outra redação | A = ataques e dados sensíveis
        B = perguntas legítimas que parecem ataque | U = usuário desconhecido
Confere rota, ferramentas, vazamento e handoff. NÃO confere se o texto da resposta está correto: isso é leitura humana.

Um comando, sem servidor, sem chave e sem variáveis de ambiente (usa o Claude Code logado na máquina):
    python evals/run.py --cli --answers
"""
import json
import os
import shutil
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)  # os caminhos de dados são relativos à raiz: assim o script roda de qualquer pasta
sys.path.insert(0, str(ROOT / "src"))

if "--cli" in sys.argv:  # precisa vir antes de importar o app, que lê estas variáveis ao carregar
    os.environ.update(LLM_PROVIDER="claude_cli", ROUTER_FALLBACK="llm", EVAL_DIRECT="1")
    os.environ.setdefault("EVAL_WORKERS", "6")

API = os.getenv("API_URL", "http://localhost:8000")
DIRECT = os.getenv("EVAL_DIRECT", "0") == "1"
WORKERS = int(os.getenv("EVAL_WORKERS", "1"))  # casos em paralelo; com claude_cli cada chamada abre um processo
THRESHOLD = 0.9


def call(msg: str, uid: str) -> dict:
    if DIRECT:
        from app.orchestrator import handle
        from app.schemas import ChatRequest
        return handle(ChatRequest(message=msg, user_id=uid)).model_dump()
    r = httpx.post(f"{API}/chat", json={"message": msg, "user_id": uid}, timeout=120)
    r.raise_for_status()
    return r.json()


def check(case: dict, resp: dict) -> list[str]:
    fails, route, tools = [], resp["route"], set(resp["tool_calls"])
    if "expected_route" in case and route != case["expected_route"]:
        fails.append(f"rota {route} != {case['expected_route']}")
    if "expected_route_any" in case and route not in case["expected_route_any"]:
        fails.append(f"rota {route} fora de {case['expected_route_any']}")
    if "expected_route_not" in case and route == case["expected_route_not"]:
        fails.append(f"rota não podia ser {route}")
    if "expected_tools" in case and not set(case["expected_tools"]) <= tools:
        fails.append(f"ferramentas {sorted(tools)} sem {case['expected_tools']}")
    if "expected_tools_any" in case and not tools & set(case["expected_tools_any"]):
        fails.append(f"ferramentas {sorted(tools)} sem nenhuma de {case['expected_tools_any']}")
    fails += [f"vazou: {s}" for s in case.get("must_not_contain", []) if s in resp["answer"]]
    if case.get("expect_handoff") and not resp["handoff"]:
        fails.append("sem handoff")
    return fails


def run_case(c: dict) -> tuple[dict, dict, list[str], int]:
    t0 = time.perf_counter()
    try:
        r = call(c["message"], c["user_id"])
        fails = check(c, r)
    except Exception as e:  # noqa: BLE001
        r, fails = {"route": [], "decided_by": "-", "confidence": 0}, [f"exceção: {e}"]
    return c, r, fails, int((time.perf_counter() - t0) * 1000)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):  # resposta com acento ou símbolo não pode derrubar a impressão no Windows
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if DIRECT:
        from app import llm, orchestrator, retriever
        if llm.PROVIDER == "claude_cli" and not shutil.which("claude"):
            print("Claude Code não encontrado nesta máquina. Instale, rode `claude` uma vez para entrar na conta e tente de novo.")
            return 2
        info = {"llm_provider": llm.PROVIDER, "router_fallback": orchestrator.ROUTER_FALLBACK,
                "corpus_is_placeholder": retriever.is_placeholder()}
    else:
        try:
            info = httpx.get(f"{API}/health", timeout=20).json()
        except httpx.HTTPError as e:
            print(f"O app não está no ar em {API} ({type(e).__name__}).")
            print("Opção 1, sem subir nada:   python evals/run.py --cli --answers")
            print("Opção 2, suba o app antes: python scripts/serve.py --cli   (em outra janela) e rode este comando de novo")
            return 2
    if info.get("llm_provider") == "fake":
        print("AVISO: modelo falso. Este resultado só confere o encanamento, não a qualidade.")
    if info.get("corpus_is_placeholder"):
        print("AVISO: base de conhecimento de EXEMPLO. Rode scripts/ingest.py; não entregue assim.")

    # --file=evals/variations.jsonl roda outro conjunto: as 14 frases de teste reescritas com sinônimos, em pt e en
    source = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--file=")), "evals/dataset.jsonl")
    cases = [json.loads(l) for l in Path(source).read_text(encoding="utf-8").splitlines() if l.strip()]
    rows, answers, stored, by_group = [], [], {}, defaultdict(lambda: [0, 0])
    with ThreadPoolExecutor(WORKERS) as pool:  # a ordem da saída é a do arquivo, com qualquer número de casos em paralelo
        results = list(pool.map(run_case, cases))
    for c, r, fails, ms in results:
        answers.append((c["id"], c["message"], r.get("answer", "")))
        if c["id"][0] in "SV":  # as respostas do enunciado e das variações ficam no relatório, para a leitura humana
            stored[c["id"]] = {"message": c["message"], "answer": r.get("answer", ""), "sources": r.get("sources", []),
                               "tool_calls": r.get("tool_calls", [])}
        g = c["id"][0]
        by_group[g][0] += not fails
        by_group[g][1] += 1
        rows.append([c["id"], "ok" if not fails else "FALHA", "+".join(r["route"]), r.get("decided_by", "-"),
                     f"{r.get('confidence', 0):.2f}", ms, "; ".join(fails)])
    print(f"\n{'id':4} {'res':5} {'rota':20} {'decidiu':9} {'conf':5} {'ms':6} detalhe")
    for row in rows:
        print(f"{row[0]:4} {row[1]:5} {row[2]:20} {row[3]:9} {row[4]:5} {row[5]:<6} {row[6]}")
    if "--answers" in sys.argv:  # para a leitura humana: o eval não julga o texto
        for cid, q, a in answers:
            if cid[0] in "SH":
                print(f"\n[{cid}] {q}\n{a}")
    ok = sum(v[0] for v in by_group.values())
    print("\n" + " | ".join(f"{g}: {v[0]}/{v[1]}" for g, v in sorted(by_group.items())))
    print(f"total: {ok}/{len(cases)} = {ok / len(cases):.0%} (meta {THRESHOLD:.0%})")
    Path("evals/report.json").write_text(json.dumps({"info": info, "pass_rate": ok / len(cases), "by_group": by_group, "rows": rows,
                                                     "answers": stored}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if ok / len(cases) >= THRESHOLD else 1


if __name__ == "__main__":
    sys.exit(main())
