"""Erros de empacotamento que só aparecem na máquina do avaliador."""
import sys
from pathlib import Path

sys.path.insert(0, "scripts")


def test_compose_does_not_mount_a_file_that_may_not_exist():
    # Montar ./data/tickets.json sem o arquivo existir faz o Docker criar uma PASTA com esse nome e o handoff quebra.
    assert "tickets.json" not in Path("docker-compose.yml").read_text()


def test_env_file_is_not_copied_into_the_image():
    assert ".env" in Path(".dockerignore").read_text().split()


def test_video_tooling_stays_out_of_the_service_image():
    ignored = Path(".dockerignore").read_text().split()
    assert "demo" in ignored and ".claude" in ignored


def test_dockerfile_does_not_hide_failed_steps():
    assert "||" not in Path("Dockerfile").read_text()


def test_every_import_is_in_requirements():
    req = Path("requirements.txt").read_text().lower()
    for pkg in ("fastapi", "uvicorn", "pydantic", "httpx", "anthropic", "openai", "python-dotenv", "scikit-learn", "joblib", "rank-bm25", "beautifulsoup4", "pypdf", "ddgs"):
        assert pkg in req, pkg


def test_ingest_chunkers():
    import ingest
    html = "<html><title>Getnet</title><body><nav>menu</nav><h2>Pix</h2><p>" + "Receba com Pix na maquininha. " * 8 + "</p><h2>Link</h2><p>" + "Cobre por link. " * 10 + "</p></body></html>"
    chunks = ingest.chunks_from_html("https://exemplo/p", "pt", html)
    assert [c["title"] for c in chunks] == ["Pix", "Link"] and all("menu" not in c["text"] for c in chunks)
    parts = ingest.split_text("Frase um. " * 400)
    assert len(parts) > 1 and all(len(p) <= ingest.CHUNK_CHARS + 20 for p in parts)


def test_sitemap_can_be_limited_to_one_country_site():
    import ingest

    class Page:
        text = "<loc>https://x/en/payment-link</loc><loc>https://x/es/link-de-pago</loc><loc>https://x/en/careers</loc>"

        def raise_for_status(self):
            pass

    class Client:
        def get(self, url):
            return Page()

    assert ingest.expand_sitemap(Client(), "https://x/sitemap", only="/en/") == ["https://x/en/payment-link"]
    assert len(ingest.expand_sitemap(Client(), "https://x/sitemap")) == 2
