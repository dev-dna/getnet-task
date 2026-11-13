"""Compara os roteadores nas mesmas mensagens: classificador local, Jev, modelo de linguagem e a cascata completa.

Mede só a ROTA (não a resposta). Usa os casos de evals/dataset.jsonl que têm rota esperada e não são ataques.
Precisa de chave de verdade: OPENROUTER_API_KEY para o Jev e a do provedor do modelo de linguagem.
Saída: tabela no terminal + evals/router_comparison.json (colar no README).
"""
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app import agents, jev, llm, orchestrator, router_clf  # noqa: E402


def accepted(case: dict) -> set[str]:
    routes = [case["expected_route"]] if "expected_route" in case else case.get("expected_route_any", [])
    return {r[0] for r in routes if r}  # o roteador responde pelo PRIMEIRO agente


def by_clf(msg):
    label, p, _ = router_clf.predict(msg)
    return label, p, 0.0


def by_jev(msg):
    d = jev.decide(msg)
    return d["label"], d["p"], d["cost_usd"]


def by_llm(msg):
    _, _, top2 = router_clf.predict(msg)
    plan = agents.route_llm(msg, [c for c, _ in top2])
    return (plan.steps[0].agent if plan.steps else "out_of_scope"), plan.confidence, None


def by_cascade(msg):
    plan = orchestrator.plan_for(msg)
    return (plan.steps[0].agent if plan.steps else "out_of_scope") + f" ({plan.source})", plan.confidence, None


def main() -> int:
    if llm.PROVIDER == "fake":
        print("AVISO: modelo falso. A comparação só faz sentido com chave de verdade.")
    orchestrator.ROUTER_FALLBACK = "jev"
    cases = [c for c in (json.loads(l) for l in Path("evals/dataset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())
             if accepted(c) and accepted(c) != {"guardrail"} and c["id"][0] in "SHA" and c["id"] != "A2"]
    routers = {"classificador local": by_clf, "jev": by_jev, "modelo de linguagem": by_llm, "cascata": by_cascade}
    stats = {name: {"ok": 0, "ms": [], "cost": 0.0, "errors": 0, "alone_ok": 0, "alone_n": 0} for name in routers}
    lines = []
    for c in cases:
        row = [c["id"]]
        for name, fn in routers.items():
            t0 = time.perf_counter()
            try:
                label, p, cost = fn(c["message"])
            except Exception as e:  # noqa: BLE001
                stats[name]["errors"] += 1
                row.append(f"ERRO {type(e).__name__}")
                continue
            ok = label.split(" ")[0] in accepted(c)
            s = stats[name]
            s["ok"] += ok
            s["ms"].append((time.perf_counter() - t0) * 1000)
            s["cost"] += cost or 0.0
            if name == "classificador local" and p >= router_clf.HIGH:
                s["alone_n"] += 1
                s["alone_ok"] += ok
            row.append(f"{'ok ' if ok else 'X  '}{label} {p:.2f}")
        lines.append(row)
    print(f"{'id':4} " + " | ".join(f"{n:26}" for n in routers))
    for row in lines:
        print(f"{row[0]:4} " + " | ".join(f"{x:26}" for x in row[1:]))
    print(f"\n{'roteador':22} {'acerto':>8} {'mediana ms':>11} {'custo US$':>10} {'erros':>6}")
    out = {}
    for name, s in stats.items():
        acc, med = s["ok"] / len(cases), (statistics.median(s["ms"]) if s["ms"] else 0)
        out[name] = {"accuracy": round(acc, 3), "median_ms": round(med, 1), "cost_usd": round(s["cost"], 6), "errors": s["errors"], "n": len(cases)}
        cost = f"{s['cost']:.5f}" if name == "jev" else "-"
        print(f"{name:22} {acc:>8.0%} {med:>11.0f} {cost:>10} {s['errors']:>6}")
    a = stats["classificador local"]
    if a["alone_n"]:
        print(f"\nclassificador local decide sozinho em {a['alone_n']}/{len(cases)} casos e acerta {a['alone_ok']}/{a['alone_n']} deles")
        out["classificador local"]["decides_alone"] = {"n": a["alone_n"], "ok": a["alone_ok"]}
    Path("evals/router_comparison.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(cases)} casos. São poucos: serve para escolher o padrão e mostrar no vídeo, não como prova estatística.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
