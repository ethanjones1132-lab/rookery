"""Tool round trip: new, track, steps, mix, state, render, kits. HANDOFF §2.4."""
from pathlib import Path

from spec import CHECKS, FACTORY


def _boom(data):
    from rookery import tools

    made = tools.new(data, "dusty-90", 90, bars=4, swing=0, seed=1337)
    kick = tools.track(
        data, "dusty-90", "add", "kick", kind="drum", source="factory:kick_boom"
    )
    tools.track(data, "dusty-90", "add", "snare", kind="drum", source="factory:snare_crack")
    tools.track(data, "dusty-90", "add", "hat", kind="drum", source="factory:hat_closed")
    steps = tools.steps(data, "dusty-90", "kick", "x...x...x...x...")
    tools.steps(data, "dusty-90", "snare", "....x.......x...")
    tools.steps(data, "dusty-90", "hat", "x.x.x.x.x.x.x.x.")
    mixed = tools.mix(
        data, "dusty-90", "master", [{"type": "limiter", "ceiling_db": -1.0}]
    )
    return made, kick, steps, mixed


def test_bass_notes_ride_on_track_set(tmp_path):
    from rookery import tools
    from rookery.project import load

    tools.new(tmp_path, "low", 142, bars=4, swing=0, seed=1337)
    added = tools.track(
        tmp_path,
        "low",
        "add",
        "sub",
        kind="bass",
        source="factory:808",
        notes=[{"step": 0, "len": 16, "pitch": "C1"}],
    )
    assert added["project"]["tracks"][0]["notes"] == [{"step": 0, "len": 16, "pitch": "C1"}]
    moved = tools.track(
        tmp_path,
        "low",
        "set",
        "sub",
        notes=[{"step": 0, "len": 8, "pitch": "F1"}],
    )
    assert moved["project"]["tracks"][0]["notes"][0]["pitch"] == "F1"
    saved = load(tmp_path / "projects" / "low")
    assert saved["tracks"][0]["notes"][0]["len"] == 8


def test_edits_bump_rev_and_state_shows_the_grid(tmp_path):
    from rookery import tools

    made, kick, steps, mixed = _boom(tmp_path)
    assert made["rev"] == 1
    assert kick["rev"] == 2
    assert steps["rev"] > kick["rev"]
    assert mixed["rev"] > steps["rev"]
    changed = next(item for item in steps["diff"] if item["field"] == "steps")
    assert 0 in changed["steps"]
    text = tools.state(tmp_path, "dusty-90")
    assert "kick" in text
    marks = "".join(ch for ch in text if ch in "x.")
    assert "x...x...x...x..." in marks
    assert mixed["project"]["master"]["fx"][-1]["type"] == "limiter"


def test_render_report_passes_and_wav_is_24_bit(tmp_path):
    from rookery import tools
    from rookery.render import content_hash
    from rookery.project import load

    _boom(tmp_path)
    out = tools.render(tmp_path, "dusty-90")
    again = tools.render(tmp_path, "dusty-90")
    assert out["hash"] == again["hash"]
    assert len(out["hash"]) == 64
    assert int(out["hash"], 16) >= 0
    path = Path(out["path"])
    assert path.name == f"{out['hash']}.wav"
    assert path.read_bytes() == Path(again["path"]).read_bytes()
    blob = path.read_bytes()
    assert blob[:4] == b"RIFF" and blob[8:12] == b"WAVE"
    fmt = blob.find(b"fmt ")
    assert int.from_bytes(blob[fmt + 10 : fmt + 12], "little") == 2
    assert int.from_bytes(blob[fmt + 12 : fmt + 16], "little") == 44100
    assert int.from_bytes(blob[fmt + 22 : fmt + 24], "little") == 24
    for name in CHECKS:
        assert out["report"][name]["pass"] is True, name
    saved = load(tmp_path / "projects" / "dusty-90")
    assert content_hash(saved) == out["hash"]
    listed = tools.kits(tmp_path)
    for sound in FACTORY:
        assert sound in listed["factory"]
    assert "found" in listed["corvus"]
