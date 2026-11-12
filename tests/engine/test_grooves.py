import json
import re
from pathlib import Path

import pytest

from rookery import events
from rookery.kit import FACTORY_NAMES
from rookery.service import Service
from rookery.tools import SCHEMAS

ROOT = Path(__file__).resolve().parents[2]
GROOVES = ROOT / "skills" / "rookery" / "grooves.json"
CATALOG = json.loads(GROOVES.read_text(encoding="utf-8"))
ROLES = ("kick", "snare", "clap", "hat", "hat_open", "perc")
CHECKS = ("length_exact", "no_clipping", "loudness", "seam_click", "not_silent", "deterministic")
PROJECT_BARS = 4


@pytest.fixture(autouse=True)
def quiet_events(monkeypatch):
    monkeypatch.setattr(events, "publisher", lambda *args: None)


def _repeat(text, count):
    return (text * ((count + len(text) - 1) // len(text)))[:count]


def test_grooves_file_parses_and_matches_the_schema():
    assert CATALOG["schema"] == "rookery.grooves/1"
    assert CATALOG["steps_per_bar"] == 16
    assert CATALOG["roles"] == list(ROLES)
    assert CATALOG["sources"] == {
        "kick": "factory:kick_boom",
        "snare": "factory:snare_crack",
        "clap": "factory:clap",
        "hat": "factory:hat_closed",
        "hat_open": "factory:hat_open",
        "perc": "factory:perc",
    }
    assert set(CATALOG["sources"].values()) <= {f"factory:{name}" for name in FACTORY_NAMES}

    templates = CATALOG["templates"]
    assert len(templates) == 20
    ids = [item["id"] for item in templates]
    assert len(ids) == len(set(ids))

    for template in templates:
        where = template["id"]
        assert template["name"] and template["genre"], where
        assert isinstance(template["bars"], int) and 1 <= template["bars"] <= 8, where
        assert isinstance(template["bpm_range"], list) and len(template["bpm_range"]) == 2, where
        low, high = template["bpm_range"]
        assert 30 <= low <= high <= 300, where
        assert isinstance(template["swing"], (int, float)) and 0 <= template["swing"] <= 0.5, where
        assert template["feel"] and len(template["feel"].split()) <= 14, where
        assert len(template["variations"]) >= 3, where
        assert template["tracks"], where
        assert set(template["tracks"]) <= set(ROLES), where
        for role, part in template["tracks"].items():
            assert len(part["steps"]) == 16 * template["bars"], (where, role)
            assert set(part["steps"]) <= {"x", "."}, (where, role)
            assert len(part["velocity"]) == len(part["steps"]), (where, role)
            assert all(isinstance(value, (int, float)) and 0 <= value <= 1
                       for value in part["velocity"]), (where, role)
            assert all(value > 0 for symbol, value in zip(part["steps"], part["velocity"])
                       if symbol == "x"), (where, role)
        if template["source"] == "theory":
            assert template["rationale"], where


def test_sample_song_recipe_uses_full_phrases_and_schema_supported_ops():
    skill = (ROOT / "skills" / "rookery" / "SKILL.md").read_text(encoding="utf-8")
    code_start = skill.index("```text") + len("```text")
    code_end = skill.index("```", code_start)
    example = skill[code_start:code_end]
    patterns = dict(re.findall(
        r'"op":"steps", "track":"(kick|snare|hat)", "steps":"([x.]+)"', example,
    ))
    assert set(patterns) == {"kick", "snare", "hat"}
    assert all(len(pattern) == 128 and set(pattern) <= {"x", "."}
               for pattern in patterns.values())
    assert all(len({pattern[index:index + 16] for index in range(0, 64, 16)}) > 1
               for pattern in patterns.values())
    apply_properties = SCHEMAS["rookery_apply"]["parameters"]["properties"]["ops"]["items"]["properties"]
    assert "steps" in apply_properties["op"]["enum"]
    assert apply_properties["steps"]["type"] == "string"
    swing = re.search(r'rookery_new\(name="amber-room", bpm=90, bars=8, swing=([0-9.]+)', example)
    assert swing and 0.54 <= float(swing.group(1)) <= 0.66


def _load_template(service: Service, template: dict) -> str:
    name = template["id"]
    bpm = sum(template["bpm_range"]) / 2
    service.new(name, bpm, bars=PROJECT_BARS, swing=template["swing"])
    total = PROJECT_BARS * 16
    for role, part in template["tracks"].items():
        body = {
            "name": name,
            "op": "track",
            "action": "add",
            "id": role,
            "kind": "drum",
            "source": CATALOG["sources"][role],
            "steps": _repeat(part["steps"], total),
            "velocity": _repeat(part["velocity"], total),
        }
        if role in {"hat", "hat_open"}:
            body["choke_group"] = "hats"
        service.edit(body, source="user")
    return name


@pytest.mark.parametrize("template", CATALOG["templates"], ids=lambda item: item["id"])
def test_template_loads_through_edits_and_renders_six_checks(tmp_path, template):
    service = Service(tmp_path)
    name = _load_template(service, template)
    project = service.get_project(name)["project"]
    assert project["swing"] == template["swing"]
    assert [track["id"] for track in project["tracks"]] == list(template["tracks"])

    result = service.render(name)
    report = result["report"]
    assert set(report) == set(CHECKS)
    failed = {check: report[check] for check in CHECKS if not report[check]["pass"]}
    assert not failed, f"{template['id']} failed {failed}"
    assert result["duration_samples"] == round(
        PROJECT_BARS * 4 * 60 / project["bpm"] * 44100)
