import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.api import EXAMPLES, app


def test_swagger_page_and_redirect():
    with TestClient(app) as c:
        assert c.get("/docs").status_code == 200
        assert c.get("/", follow_redirects=False).headers["location"] == "/docs"


def test_openapi_has_the_ten_challenge_scenarios_as_examples():
    with TestClient(app) as c:
        spec = c.get("/openapi.json").json()
    examples = spec["paths"]["/chat"]["post"]["requestBody"]["content"]["application/json"]["examples"]
    assert {f"S{i}" for i in range(1, 11)} <= set(examples)
    assert "ChatResponse" in spec["components"]["schemas"] and "decided_by" in spec["components"]["schemas"]["ChatResponse"]["properties"]


def test_examples_are_the_same_sentences_as_the_eval():
    dataset = {c["id"]: c["message"] for c in map(json.loads, Path("evals/dataset.jsonl").read_text(encoding="utf-8").splitlines())}
    for key, ex in EXAMPLES.items():
        assert ex["value"]["message"] == dataset[key], key


def test_every_example_gets_an_answer():
    with TestClient(app) as c:
        for key, ex in EXAMPLES.items():
            if key in ("S2", "S7"):  # clima e câmbio precisam de internet; cobertos em test_orchestrator com rede simulada
                continue
            r = c.post("/chat", json=ex["value"])
            assert r.status_code == 200 and r.json()["answer"], key


def test_openapi_file_in_repo_is_up_to_date():
    assert json.loads(Path("openapi.json").read_text(encoding="utf-8")) == app.openapi(), "rode: make openapi"
