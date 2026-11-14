"""Monta data/corpus.jsonl a partir de data/sources.txt. Aceita página HTML e PDF.

Formato de data/sources.txt, uma entrada por linha:
    <idioma> <url>                 ex.: pt https://site.getnet.com.br/contato/
    sitemap <idioma> <url>         expande o mapa do site e fica só com URLs que casem com KEYWORDS
    sitemap <idioma> <url> <texto> idem, e só URLs que contenham <texto> (ex.: /en/ deixa de fora os sites de outros países)

Sai com código 1 se vierem menos de MIN_CHUNKS trechos: melhor quebrar aqui do que entregar a base de exemplo.
"""
import io
import json
import re
import sys
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

SOURCES = Path("data/sources.txt")
OUT = Path("data/corpus.jsonl")
MIN_CHUNKS = 15
MAX_SITEMAP_PAGES = 40
CHUNK_CHARS = 1200
KEYWORDS = ("maquin", "smart", "classica", "pix", "link", "antecip", "crediario", "ajuda", "faq", "taxa", "conta", "tap", "product", "solution", "payment")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; getnet-challenge-ingest/0.2)"}


def split_text(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """Quebra em blocos de até `size` caracteres, respeitando frases."""
    text = re.sub(r"[ \t]+", " ", text).strip()
    parts, buf = [], ""
    for sent in re.split(r"(?<=[.!?])\s+|\n{2,}", text):
        if len(buf) + len(sent) > size and buf:
            parts.append(buf.strip())
            buf = ""
        buf += sent + " "
    if buf.strip():
        parts.append(buf.strip())
    return [p for p in parts if len(p) > 80]


def chunks_from_html(url: str, lang: str, html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "nav", "footer", "header", "noscript", "form"]):
        t.decompose()
    page = soup.title.get_text(strip=True) if soup.title else url
    out, title, buf = [], page, []

    def flush():
        for part in split_text(" ".join(buf)):
            out.append({"url": url, "title": title, "lang": lang, "text": part})
        buf.clear()

    for el in soup.find_all(["h1", "h2", "h3", "p", "li"]):
        if el.name in ("h1", "h2", "h3"):
            flush()
            title = el.get_text(" ", strip=True) or page
        else:
            buf.append(el.get_text(" ", strip=True))
    flush()
    return out


def chunks_from_pdf(url: str, lang: str, content: bytes) -> list[dict]:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(content))
    name = url.rsplit("/", 1)[-1]
    out = []
    for n, page in enumerate(reader.pages, 1):
        for part in split_text(page.extract_text() or ""):
            out.append({"url": url, "title": f"{name} (página {n})", "lang": lang, "text": part})
    return out


def expand_sitemap(client: httpx.Client, url: str, depth: int = 0, only: str = "") -> list[str]:
    r = client.get(url)
    r.raise_for_status()
    locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", r.text)
    pages = []
    for loc in locs:
        if loc.endswith(".xml") and depth < 1:
            try:
                pages += expand_sitemap(client, loc, depth + 1, only)
            except Exception as e:  # noqa: BLE001
                print(f"ERR  sitemap {loc}: {e}")
        elif only in loc and any(k in loc.lower() for k in KEYWORDS):
            pages.append(loc)
    return pages[:MAX_SITEMAP_PAGES]


def read_sources(client: httpx.Client) -> list[tuple[str, str]]:
    items = []
    for line in SOURCES.read_text(encoding="utf-8").splitlines():
        parts = line.split("#")[0].split()
        if len(parts) == 2:
            items.append((parts[0], parts[1]))
        elif len(parts) in (3, 4) and parts[0] == "sitemap":
            try:
                found = expand_sitemap(client, parts[2], only=parts[3] if len(parts) == 4 else "")
                print(f"ok   sitemap {parts[2]} -> {len(found)} páginas")
                items += [(parts[1], u) for u in found]
            except Exception as e:  # noqa: BLE001
                print(f"ERR  sitemap {parts[2]}: {e}")
    return list(dict.fromkeys(items))


def main() -> int:
    rows = []
    with httpx.Client(headers=HEADERS, timeout=25, follow_redirects=True) as client:
        for lang, url in read_sources(client):
            try:
                r = client.get(url)
                r.raise_for_status()
                is_pdf = url.lower().endswith(".pdf") or "pdf" in r.headers.get("content-type", "")
                got = chunks_from_pdf(url, lang, r.content) if is_pdf else chunks_from_html(url, lang, r.text)
                rows += got
                print(f"{'ok  ' if got else 'VAZIO'} {url} -> {len(got)} trechos")
            except Exception as e:  # noqa: BLE001
                print(f"ERR  {url}: {e}")
    seen, unique = set(), []
    for r in rows:
        if r["text"] not in seen:
            seen.add(r["text"])
            unique.append({"id": f"c{len(unique):04d}", **r})
    if len(unique) < MIN_CHUNKS:
        print(f"\nFALHOU: só {len(unique)} trechos (mínimo {MIN_CHUNKS}). {OUT} não foi alterado. Revise data/sources.txt.")
        return 1
    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in unique), encoding="utf-8")
    print(f"\n{len(unique)} trechos de {len({r['url'] for r in unique})} fontes em {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
