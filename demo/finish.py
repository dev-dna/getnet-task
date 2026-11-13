"""Deixa o SEU vídeo narrado pronto para o YouTube: volume no padrão, formato certo e conferência.

Entrada: a gravação da sua apresentação (tela + voz), em qualquer formato que o ffmpeg leia.
Faz:     (opcional) corta os silêncios longos → normaliza o volume em -14 LUFS → exporta no padrão do YouTube
         → confere o arquivo e avisa se passar dos 15 minutos que o desafio permite.

Uso:  python demo/finish.py minha_gravacao.mkv
      python demo/finish.py minha_gravacao.mkv --cut-silence       # tira pausas de mais de 1,2 s
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record import SKILL, skill  # noqa: E402

LIMIT_S = 15 * 60  # limite do enunciado


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("input")
    ap.add_argument("-o", "--output", help="padrão: <entrada>_youtube.mp4")
    ap.add_argument("--cut-silence", action="store_true", help="remove pausas de mais de 1,2 s")
    ap.add_argument("--best", action="store_true", help="codificação lenta: arquivo menor, 2 a 3 vezes mais demorado")
    args = ap.parse_args()
    src = Path(args.input).resolve()
    if not src.exists():
        sys.exit(f"Arquivo não encontrado: {src}")
    out = Path(args.output).resolve() if args.output else src.with_name(src.stem + "_youtube.mp4")
    work = out.with_name(out.stem + "_work")
    project = {"output": str(out), "clips": [{"src": str(src)}],
               **({"silence": {"threshold": -38, "min_silence": 1.2}} if args.cut_silence else {}),
               "loudness": {"lufs": -14, "tp": -1}, "export": {"preset": "youtube", "normalize": True}}
    work.mkdir(parents=True, exist_ok=True)
    (work / "project.json").write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    result = skill("render", work / "project.json", "--work", work / "render", "--overwrite", *([] if args.best else ["--fast"]))
    if result.get("_exit") != 0 or not out.exists():
        sys.exit(f"O render falhou:\n{json.dumps(result, ensure_ascii=False, indent=2)[:2500]}")

    def run(tool, *a):
        r = subprocess.run([sys.executable, str(SKILL / "scripts" / f"{tool}.py"), *map(str, a), "--json"], capture_output=True, text=True)
        try:
            return json.loads(r.stdout)
        except ValueError:
            return {}

    before, after = run("probe", src), run("probe", out)
    checks = run("check", out, "--platform", "youtube").get("checks", [])
    failed = [f"{c['check']} ({c.get('value')})" for c in checks if c.get("status") == "FAIL"]
    dur = float(after.get("duration") or 0)
    print(f"\nentrada:     {src.name}  {float(before.get('duration') or 0) / 60:.1f} min")
    print(f"saída:       {out}  {dur / 60:.1f} min")
    print(f"conferência: {len(checks) - len(failed)} de {len(checks)} itens do padrão do YouTube passaram" + (f"; reprovados: {', '.join(failed)}" if failed else ""))
    if dur > LIMIT_S:
        print(f"ATENÇÃO: {dur / 60:.1f} min passa do limite de 15 min do desafio. Corte {dur - LIMIT_S:.0f} s (tente --cut-silence).")
        return 1
    print(f"duração:     dentro do limite de 15 min (sobram {(LIMIT_S - dur) / 60:.1f} min)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
