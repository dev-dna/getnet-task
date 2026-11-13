"""Grava o sistema em uso e monta o vídeo de demonstração.

Abre o Swagger (/docs) num navegador, escolhe cada exemplo, clica em Execute contra a API de verdade
e filma a tela. Depois monta: cartela de abertura, uma legenda por cenário com a rota REAL devolvida,
capítulos, exportação no padrão do YouTube e conferência final.

Captura:  Playwright (Chromium) + transmissão de quadros do próprio navegador (JPEG).
Montagem: ffmpeg-skill em .claude/skills/ffmpeg-skill (sequence, background, render, look).

Uso:  python demo/record.py                      # API em http://localhost:8000
      python demo/record.py --cases S1,S3,S5     # só alguns cenários
"""
import argparse
import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = Path(os.getenv("FFMPEG_SKILL_DIR", ROOT / ".claude" / "skills" / "ffmpeg-skill"))
FPS = 30
SCALE = 1.5                      # janela de 1280x720 desenhada a 1,5x = quadros de 1920x1080 com letra grande
WINDOW = (1280, 720)
DEFAULT_CASES = "S1,S2,S3,S5,S7,A1,B1,A2,A4"
INTRO_S = 4.0
LOWER_THIRD_SCALE = 0.6

TEXT = {
    "pt": {"route": "rota", "by": "decidiu", "tools": "ferramentas", "human": "passou para humano", "ticket": "protocolo",
           "subtitle": "Sistema em uso", "fake": "MODELO FALSO (ensaio)", "sample": "BASE DE EXEMPLO",
           "who": {"guardrail": "filtro de ataque", "rule": "regra", "clf": "classificador local", "jev": "Jev", "llm": "modelo de linguagem", "error": "erro"}},
    "en": {"route": "route", "by": "decided by", "tools": "tools", "human": "handed to a human", "ticket": "ticket",
           "subtitle": "System in use", "fake": "FAKE MODEL (rehearsal)", "sample": "SAMPLE KNOWLEDGE BASE",
           "who": {"guardrail": "attack filter", "rule": "rule", "clf": "local classifier", "jev": "Jev", "llm": "language model", "error": "error"}},
}

CURSOR_JS = """
(() => { const c = document.createElement('div');
  c.style.cssText = 'position:fixed;left:-50px;top:-50px;width:20px;height:20px;margin:-10px 0 0 -10px;border-radius:50%;'
    + 'background:rgba(255,90,0,.5);border:2px solid #fff;box-shadow:0 0 0 1px rgba(0,0,0,.45);z-index:2147483647;'
    + 'pointer-events:none;transition:transform .12s';
  document.body.appendChild(c);
  addEventListener('mousemove', e => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
  addEventListener('mousedown', () => c.style.transform = 'scale(.55)', true);
  addEventListener('mouseup', () => c.style.transform = 'scale(1)', true); })();
"""


# ---------- ffmpeg-skill ----------
def skill(tool: str, *args) -> dict:
    """Roda uma ferramenta da skill e devolve o resultado em JSON. Para com a mensagem da própria ferramenta se falhar."""
    cmd = [sys.executable, str(SKILL / "scripts" / f"{tool}.py"), *map(str, args), "--json-brief"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:
        out = json.loads(r.stdout)
    except ValueError:
        out = {}
    if r.returncode != 0 and tool != "render":  # o render devolve 1 quando a conferência final reprova; quem chama decide
        sys.exit(f"\nffmpeg-skill/{tool} falhou (código {r.returncode}):\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
    out["_exit"] = r.returncode
    return out


# ---------- funções puras (testadas em tests/test_demo_recorder.py) ----------
def cfr_plan(frames: list[tuple[float, str]], t0: float, t1: float, fps: int = FPS) -> list[str]:
    """O navegador só manda quadro quando a tela muda. Aqui vira ritmo fixo: a cada 1/fps, o último quadro visto."""
    n = max(1, round((t1 - t0) * fps))
    plan, j, current = [], 0, None
    for k in range(n):
        tick = t0 + k / fps
        while j < len(frames) and frames[j][0] <= tick:
            current = frames[j][1]
            j += 1
        plan.append(current if current is not None else frames[0][1])
    return plan


def caption_for(case_id: str, summary: str, resp: dict, lang: str) -> tuple[str, str]:
    """Duas linhas da legenda: o cenário e o que a API devolveu de verdade (não o que era esperado)."""
    t = TEXT[lang]
    label = summary.split("·")[-1].strip() if "·" in summary else summary
    parts = [f"{t['route']}: {' → '.join(resp.get('route') or ['?'])}",
             f"{t['by']}: {t['who'].get(resp.get('decided_by'), resp.get('decided_by') or '?')}"]
    if resp.get("tool_calls"):
        parts.append(", ".join(dict.fromkeys(resp["tool_calls"])))
    if resp.get("handoff"):
        parts.append(f"{t['human']}: {resp.get('ticket_id')}")
    if resp.get("latency_ms") is not None:
        parts.append(f"{resp['latency_ms']} ms")
    return f"{case_id} · {label}", " · ".join(parts)


def warnings_for(health: dict, lang: str) -> list[str]:
    t = TEXT[lang]
    return ([t["fake"]] if health.get("llm_provider") == "fake" else []) + ([t["sample"]] if health.get("corpus_is_placeholder") else [])


def build_project(output: Path, intro: str, scenes: list[dict], warn: list[str], title: str) -> dict:
    """Projeto da skill (render.py): junta os clipes já legendados, marca os capítulos e exporta no padrão do YouTube."""
    chapters, at = [{"at": "0:00", "title": title}], INTRO_S
    for s in scenes:
        chapters.append({"at": f"{int(at) // 60}:{int(at) % 60:02d}", "title": s["name"]})
        at += s["duration"]
    # aviso fixo no canto durante o vídeo inteiro: ninguém confunde ensaio com resultado
    graphics = [{"template": "bug", "title": " · ".join(warn), "position": "top-right", "scale": 0.8}] if warn else []
    return {"output": str(output), "frame": {"aspect": "16:9", "width": 1920, "fps": FPS},
            "clips": [{"src": intro}] + [{"src": s["clip"]} for s in scenes],
            "transition": {"type": "none"},  # corte seco: a duração é a soma dos clipes e os capítulos batem
            "graphics": graphics, "chapters": chapters, "export": {"preset": "youtube", "normalize": False}}


# ---------- captura ----------
class Screencast:
    def __init__(self, cdp, folder: Path):
        self.cdp, self.folder, self.frames = cdp, folder, []
        folder.mkdir(parents=True, exist_ok=True)
        cdp.on("Page.screencastFrame", lambda ev: asyncio.create_task(self._on(ev)))

    async def _on(self, ev):
        path = self.folder / f"raw_{len(self.frames):06d}.jpg"
        self.frames.append((float(ev["metadata"]["timestamp"]), str(path)))
        path.write_bytes(base64.b64decode(ev["data"]))
        try:
            await self.cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
        except Exception:  # noqa: BLE001  # navegador fechando
            pass

    async def start(self):
        await self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "everyNthFrame": 1})

    async def stop(self):
        await self.cdp.send("Page.stopScreencast")


class Stage:
    """O que aparece na tela: mouse que desliza, rolagem suave, um cenário por vez."""

    def __init__(self, page):
        self.page, self.mouse = page, (WINDOW[0] / 2, WINDOW[1] / 2)
        self.op = page.locator("#operations-chat-chat_chat_post")

    async def glide(self, locator, ms: int = 500):
        box = await locator.bounding_box()
        to = (box["x"] + min(box["width"] / 2, 180), box["y"] + box["height"] / 2)
        steps = max(8, ms // 16)
        for i in range(1, steps + 1):
            e = (i / steps) ** 2 * (3 - 2 * i / steps)
            await self.page.mouse.move(self.mouse[0] + (to[0] - self.mouse[0]) * e, self.mouse[1] + (to[1] - self.mouse[1]) * e)
            await asyncio.sleep(0.016)
        self.mouse = to

    async def scroll_to(self, locator, margin: int = 70, wait_ms: int = 800):
        await locator.evaluate("(e, m) => scrollTo({top: e.getBoundingClientRect().top + scrollY - m, behavior: 'smooth'})", margin)
        await self.page.wait_for_timeout(wait_ms)

    async def open(self):
        await self.op.locator(".opblock-summary-control").click()
        await self.op.locator(".examples-select-element").wait_for()

    async def run_case(self, case_id: str, hold: float, timeout_s: int) -> tuple[dict, float]:
        """Devolve (resposta da API, instante em que a resposta apareceu)."""
        clear = self.op.locator(".btn-clear")
        if await clear.count():  # limpa a resposta do cenário anterior
            await clear.click()
        select = self.op.locator(".examples-select-element")
        await self.scroll_to(self.op.locator(".opblock-section-request-body, .opblock-section").first)
        await self.glide(select)
        await select.select_option(case_id)
        await self.page.wait_for_timeout(1500)  # tempo de ler a pergunta
        execute = self.op.locator(".btn.execute")
        await self.glide(execute)
        async with self.page.expect_response(lambda r: r.request.method == "POST" and r.url.rstrip("/").endswith("/chat"),
                                             timeout=timeout_s * 1000) as info:
            await self.page.mouse.down()
            await self.page.mouse.up()
        resp = await info.value
        body = await resp.json()
        live = self.op.locator(".live-responses-table")
        await live.wait_for()
        answered = time.time()
        await self.scroll_to(live, margin=110)
        await self.page.wait_for_timeout(int(hold * 1000))  # tempo de ler a resposta
        return body, answered


async def capture(args, examples: dict, work: Path) -> list[dict]:
    from playwright.async_api import async_playwright

    scenes = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=[f"--force-device-scale-factor={SCALE}", f"--window-size={WINDOW[0]},{WINDOW[1]}"])
        ctx = await browser.new_context(no_viewport=True)
        page = await ctx.new_page()
        if args.swagger_assets:  # sem internet: serve os arquivos do Swagger de uma pasta local
            assets = Path(args.swagger_assets)

            async def local(route):
                f = assets / route.request.url.rsplit("/", 1)[-1]
                await (route.fulfill(path=str(f)) if f.exists() else route.abort())
            await page.route("**/cdn.jsdelivr.net/**", local)
            await page.route("**/fastapi.tiangolo.com/**", lambda r: r.abort())
        await page.goto(f"{args.base_url}/docs")
        try:
            await page.wait_for_selector("#operations-chat-chat_chat_post", timeout=20000)
        except Exception:  # noqa: BLE001
            sys.exit("O Swagger não carregou. Sem internet? Use --swagger-assets PASTA (veja demo/README.md).")
        await page.evaluate(CURSOR_JS)
        stage = Stage(page)
        await stage.open()
        cast = Screencast(await ctx.new_cdp_session(page), work / "raw")
        await cast.start()
        await page.wait_for_timeout(400)
        for case_id in args.cases:
            t0 = time.time()
            body, answered = await stage.run_case(case_id, args.hold, args.timeout)
            t1 = time.time()
            name, line = caption_for(case_id, examples[case_id]["summary"], body, args.lang)
            scenes.append({"id": case_id, "t0": t0, "t1": t1, "answer_at": round(answered - t0 + 0.9, 2), "duration": round(t1 - t0, 3),
                           "name": name, "line": line, "response": body, "request": examples[case_id]["value"]})
            print(f"  {case_id}: {line}")
        await cast.stop()
        await browser.close()
    frames = sorted(cast.frames)
    for s in scenes:  # um arquivo de vídeo por cenário
        folder = work / f"scene_{s['id']}"
        folder.mkdir(parents=True, exist_ok=True)
        plan = cfr_plan(frames, s["t0"], s["t1"])
        for k, src in enumerate(plan):
            dst = folder / f"f_{k:05d}.jpg"
            try:
                os.link(src, dst)
            except OSError:
                shutil.copyfile(src, dst)
        s["duration"] = round(len(plan) / FPS, 3)
        raw = work / f"scene_{s['id']}_raw.mp4"
        s["clip"] = str(work / f"scene_{s['id']}.mp4")
        fast = [] if args.best else ["--fast"]
        skill("sequence", "--dir", folder, "--pattern", "f_%05d.jpg", "--fps", FPS, "-o", raw, "--overwrite", *fast)
        skill("graphics", raw, "--template", "lower-third", "--name", s["name"], "--title", s["line"], "--scale", LOWER_THIRD_SCALE,
              "--start", min(s["answer_at"], s["duration"] - 1), "--end", round(s["duration"] - 0.2, 2), "-o", s["clip"], "--overwrite", *fast)
    return scenes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--cases", default=DEFAULT_CASES, help=f"ids dos exemplos do Swagger, separados por vírgula (padrão {DEFAULT_CASES})")
    ap.add_argument("--out", default=str(ROOT / "demo" / "out"))
    ap.add_argument("--hold", type=float, default=4.0, help="segundos parado em cada resposta (padrão 4)")
    ap.add_argument("--timeout", type=int, default=180, help="segundos de espera por resposta da API")
    ap.add_argument("--lang", choices=["pt", "en"], default="pt", help="idioma das legendas")
    ap.add_argument("--title", default="Getnet Multi-Agent Support")
    ap.add_argument("--swagger-assets", help="pasta com swagger-ui-bundle.js e swagger-ui.css, para gravar sem internet")
    ap.add_argument("--best", action="store_true", help="codificação lenta: arquivo menor, mesma imagem, 2 a 3 vezes mais demorado")
    ap.add_argument("--keep-work", action="store_true", help="não apaga os quadros e clipes intermediários")
    args = ap.parse_args()
    args.cases = [c.strip() for c in args.cases.split(",") if c.strip()]
    args.base_url = args.base_url.rstrip("/")

    import httpx
    if not (SKILL / "scripts" / "render.py").exists():
        sys.exit(f"ffmpeg-skill não encontrada em {SKILL}. Rode: npx ffmpeg-skill --project")
    try:
        health = httpx.get(f"{args.base_url}/health", timeout=10).json()
        spec = httpx.get(f"{args.base_url}/openapi.json", timeout=10).json()
    except Exception as e:  # noqa: BLE001
        sys.exit(f"A API não respondeu em {args.base_url} ({e}). Suba com `make run` ou `docker compose up -d`.")
    examples = spec["paths"]["/chat"]["post"]["requestBody"]["content"]["application/json"]["examples"]
    unknown = [c for c in args.cases if c not in examples]
    if unknown:
        sys.exit(f"Cenário(s) inexistente(s): {unknown}. Disponíveis: {', '.join(examples)}")
    if health.get("llm_provider") == "fake":
        print("AVISO: a API está com o modelo FALSO. O vídeo sai com um aviso fixo na tela.")
    if health.get("corpus_is_placeholder"):
        print("AVISO: a base de conhecimento é a de EXEMPLO. Rode `make ingest` antes de gravar para valer.")

    out, work = Path(args.out), Path(args.out) / "work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    print(f"Gravando {len(args.cases)} cenários em {args.base_url}/docs ...")
    scenes = asyncio.run(capture(args, examples, work))

    print("Montando o vídeo com a ffmpeg-skill ...")
    fast = [] if args.best else ["--fast"]
    warn = warnings_for(health, args.lang)
    blank, intro = work / "intro_raw.mp4", work / "intro.mp4"
    skill("background", "-o", blank, "--duration", INTRO_S, "--width", 1920, "--height", 1080, "--fps", FPS,
          "--gradient", "0x0b1f3a:0x163d6b", "--overwrite", *fast)
    skill("graphics", blank, "--template", "title", "--title", args.title,
          "--subtitle", f"{TEXT[args.lang]['subtitle']} · {date.today():%d/%m/%Y}",
          "--start", 0.3, "--end", INTRO_S - 0.3, "-o", intro, "--overwrite", *fast)
    video = out / "demo.mp4"
    project = build_project(video, str(intro), scenes, warn, args.title)
    (work / "project.json").write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    result = skill("render", work / "project.json", "--work", work / "render", "--overwrite", *fast)
    if result.get("_exit") != 0 or not video.exists():
        sys.exit(f"O render falhou:\n{json.dumps(result, ensure_ascii=False, indent=2)[:2500]}")
    sheet = out / "demo_contact.png"
    skill("look", video, "--tiles", "4x3", "-o", sheet, "--overwrite")
    rows = subprocess.run([sys.executable, str(SKILL / "scripts" / "check.py"), str(video), "--platform", "youtube", "--json"],
                          capture_output=True, text=True)
    try:
        checks = json.loads(rows.stdout).get("checks", [])
    except ValueError:
        checks = []
    failed = [c["check"] for c in checks if c.get("status") == "FAIL"]

    (out / "results.json").write_text(json.dumps({"health": health, "scenes": [
        {k: s[k] for k in ("id", "name", "line", "duration", "request", "response")} for s in scenes]}, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "chapters.txt").write_text("\n".join(f"{c['at']} {c['title']}" for c in project["chapters"]) + "\n", encoding="utf-8")
    if not args.keep_work:
        shutil.rmtree(work, ignore_errors=True)
    total = INTRO_S + sum(s["duration"] for s in scenes)
    print(f"\nvídeo:       {video}  ({total:.0f} s, {len(scenes)} cenários)")
    print(f"mosaico:     {sheet}   (12 quadros para conferir de relance)")
    print(f"capítulos:   {out / 'chapters.txt'}   (colar na descrição do YouTube)")
    print(f"respostas:   {out / 'results.json'}")
    print(f"conferência: {len(checks) - len(failed)} de {len(checks)} itens do padrão do YouTube passaram"
          + (f"; reprovados: {', '.join(failed)}" if failed else ""))
    if set(failed) <= {"audio", "loudness"} and failed:
        print("             (áudio e volume reprovam porque a gravação é muda; a narração é sua)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
