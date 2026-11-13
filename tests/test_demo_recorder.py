"""Partes puras do gravador (demo/record.py). A gravação em si precisa de navegador e ffmpeg: `make demo`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path("demo").resolve()))
import record  # noqa: E402


def test_variable_frames_become_fixed_rate():
    # o navegador mandou 3 quadros em 1 segundo; a 30 qps viram 30, cada um repetindo o último visto
    frames = [(100.0, "a"), (100.5, "b"), (100.9, "c")]
    plan = record.cfr_plan(frames, 100.0, 101.0, fps=30)
    assert len(plan) == 30 and plan[0] == "a" and plan[14] == "a" and plan[15] == "b" and plan[-1] == "c"


def test_scene_starting_before_first_frame_uses_first_frame():
    assert record.cfr_plan([(10.0, "a")], 9.5, 10.5, fps=10)[0] == "a"


def test_caption_shows_what_the_api_returned():
    resp = {"route": ["support", "knowledge"], "decided_by": "rule", "tool_calls": ["get_terminal_status", "retrieve", "retrieve"],
            "handoff": False, "latency_ms": 75}
    name, line = record.caption_for("S5", "S5 · support → knowledge · machine offline", resp, "pt")
    assert name == "S5 · machine offline"
    assert line == "rota: support → knowledge · decidiu: regra · get_terminal_status, retrieve · 75 ms"


def test_caption_for_handoff_shows_ticket():
    resp = {"route": ["escalate"], "decided_by": "rule", "tool_calls": ["open_ticket"], "handoff": True, "ticket_id": "GN-1", "latency_ms": 0}
    assert "passou para humano: GN-1" in record.caption_for("A4", "A4 · escalate · asks for a human", resp, "pt")[1]


def test_project_chapters_follow_scene_durations_and_fake_model_is_flagged():
    scenes = [{"name": "S1 · a", "duration": 10.0, "clip": "s1.mp4"}, {"name": "S2 · b", "duration": 61.0, "clip": "s2.mp4"}]
    warn = record.warnings_for({"llm_provider": "fake", "corpus_is_placeholder": False}, "pt")
    p = record.build_project(Path("out.mp4"), "intro.mp4", scenes, warn, "T")
    assert [c["at"] for c in p["chapters"]] == ["0:00", "0:04", "0:14"]
    assert p["transition"] == {"type": "none"} and [c["src"] for c in p["clips"]] == ["intro.mp4", "s1.mp4", "s2.mp4"]
    assert p["graphics"][0]["template"] == "bug" and "FALSO" in p["graphics"][0]["title"]
    assert record.build_project(Path("o.mp4"), "i.mp4", scenes, [], "T")["graphics"] == []


def test_skill_is_in_the_project_with_its_license():
    assert (record.SKILL / "scripts" / "render.py").exists()
    assert (record.SKILL / "LICENSE").read_text().startswith("MIT License")
    assert "github.com/kajisho5/ffmpeg-skill" in (record.SKILL / "VENDORED.txt").read_text()
