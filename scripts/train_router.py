"""Treina o classificador de rota e imprime a avaliação honesta (separada por molde)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app import router_clf as rc  # noqa: E402

rep = rc.train()
print(f"{rep['n']} frases, {rep['n_templates']} moldes | {rep['split']}")
print(f"acerto geral: {rep['accuracy_all']:.1%}")
d = rep["decides_alone"]
print(f"decide sozinho (p >= {rc.HIGH}): {d['share']:.1%} das frases, acerto {d['accuracy']:.1%}")
print(f"vai para o modelo decidir (p < {rc.HIGH}): {rep['goes_to_llm']['share']:.1%}")
print("\nlimiar  cobertura  acerto")
for r in rep["thresholds"]:
    print(f"{r['threshold']:<7} {r['coverage']:<10.1%} {r['accuracy'] if r['accuracy'] is None else format(r['accuracy'], '.1%')}")
print("\nmatriz de confusão (linha = real, coluna = previsto):", rep["labels"])
for lab, row in zip(rep["labels"], rep["confusion"]):
    print(f"{lab:10s} {row}")
