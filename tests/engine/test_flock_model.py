import copy
import hashlib
import json

import pytest

from rookery.flock.model import (
    FLOCK_RENDERER_VERSION,
    active_combos,
    apply_flock_edit,
    audio_projection,
    default_flock,
    flock_diffs,
    load_catalog,
    state_lines,
    validate_flock,
)
from rookery.project import ConflictError, ProjectStore, canonical_json, new_project, project_hash, validate_project


def _perch(flock, bird, slot, **changes):
    value = copy.deepcopy(flock)
    value["perches"][slot] = {"bird": bird, "song": "A", "mute": False, "solo": False, **changes}
    return value


def test_catalog_has_exact_exports_and_full_prototype_data() -> None:
    catalog = load_catalog()
    assert set(catalog) == {"scales", "chordTables", "registers", "birds", "corvus", "templates", "combos", "comboSongs", "secretUnlock"}
    assert len(catalog["birds"]) == 12
    assert catalog["secretUnlock"]["seenRequired"] == [bird["id"] for bird in catalog["birds"]]
    catalog["birds"].clear()
    assert len(load_catalog()["birds"]) == 12


def test_default_and_validation_are_normalized_deep_copies() -> None:
    value = default_flock()
    value["perches"][0] = {"bird": "bramble"}
    normalized = validate_flock(value)
    assert normalized["perches"][0] == {"bird": "bramble", "song": "A", "mute": False, "solo": False}
    assert value["perches"][0] == {"bird": "bramble"}
    assert validate_flock(default_flock()) == {"key": "D", "scale": "dorian", "progression": ["i", "IV", "VII", "III"],
                                              "weather": "clear", "perches": [None] * 6, "seen": [], "unlocked": []}


@pytest.mark.parametrize("patch", [
    {"perches": []}, {"perches": [None] * 5}, {"perches": [None] * 8},
    {"perches": [None] * 6 + [{"bird": "bramble"}]}, {"perches": [{"bird": "ghost"}] + [None] * 5},
    {"perches": [{"bird": "bramble"}, {"bird": "bramble"}] + [None] * 4},
    {"perches": [{"bird": "bramble"}, {"bird": "cinder"}, {"bird": "bramble"}] + [None] * 3},
    {"perches": [{"bird": "bramble", "mute": 1}] + [None] * 5},
    {"perches": [{"bird": "bramble", "unknown": True}] + [None] * 5},
    {"key": "Cb"}, {"scale": "blues"}, {"progression": ["VIII"]}, {"weather": "snow"},
    {"seen": ["bramble", "bramble"]}, {"unlocked": ["unknown"]}, {"extra": 1},
])
def test_malformed_flock_schema_is_rejected(patch) -> None:
    value = {**default_flock(), **patch}
    with pytest.raises(ValueError):
        validate_flock(value)


def test_flats_and_roman_numeral_case_are_supported() -> None:
    value = {**default_flock(), "key": "Bb", "progression": ["i", "VII", "iv"]}
    assert validate_flock(value)["key"] == "A#"


def test_perch_edits_track_seen_discovery_and_auto_unlock_corvus() -> None:
    value = default_flock()
    for bird in (item["id"] for item in load_catalog()["birds"]):
        value = apply_flock_edit(value, {"action": "perch", "bird": bird, "slot": 0})
        if bird != "wren_not":
            value = apply_flock_edit(value, {"action": "unperch", "slot": 0})
    assert set(value["seen"]) == {bird["id"] for bird in load_catalog()["birds"]}
    assert len(value["perches"]) == 7 and value["perches"][6]["bird"] == "corvus"


def test_actions_reject_unknown_or_invalid_arguments_and_occupied_slot() -> None:
    value = apply_flock_edit(None, {"action": "perch", "bird": "bramble"})
    for args in ({"action": "perch", "bird": "quill", "slot": 0},
                 {"action": "mute", "bird": "bramble", "on": 1},
                 {"action": "perch", "bird": "quill", "banana": 2},
                 {"action": "unperch", "bird": "bramble", "slot": 0},
                 {"action": "song", "bird": "missing", "song": "B"}):
        with pytest.raises(ValueError):
            apply_flock_edit(value, args)


@pytest.mark.parametrize("template", [item["id"] for item in load_catalog()["templates"]] +
                         [item["name"] for item in load_catalog()["templates"]])
def test_every_template_applies_with_role_order_and_cumulative_seen(template) -> None:
    before = apply_flock_edit(None, {"action": "perch", "bird": "pip"})
    after = apply_flock_edit(before, {"action": "template", "template": template})
    roles = {item["id"]: item["role"] for item in load_catalog()["birds"]}
    landed = [p["bird"] for p in after["perches"][:6] if p]
    assert [roles[bird] for bird in landed] == sorted((roles[bird] for bird in landed), key=("bass", "keys", "pad", "lead", "arp", "call").index)
    assert "pip" in after["seen"]


def test_template_diffs_include_removals_and_land_in_role_order() -> None:
    before = default_flock()
    before["scale"] = "major"
    before["perches"][:6] = [{"bird": bird, "song": "A", "mute": False, "solo": False}
                             for bird in ("jinx", "sable", "bramble", "pip", "hush", "echo")]
    after = apply_flock_edit(before, {"action": "template", "template": "Dusty Boom Bap"})
    diffs = flock_diffs(before, after, "template")
    slots = [d["slot"] for d in diffs if d["change"] == "template"]
    assert slots == [0, 1, 2, 4, 3, 5]
    assert all("from" in d and "to" in d for d in diffs)
    assert any(d["change"] == "harmony" for d in diffs)
    assert any(d["change"] == "weather" for d in diffs)


def test_combo_discovery_is_cumulative_and_active_requires_audible_perches() -> None:
    value = default_flock()
    for slot, bird in enumerate(("bramble", "quill", "hush", "jinx", "tick", "echo")):
        value = apply_flock_edit(value, {"action": "perch", "bird": bird, "slot": slot})
    assert "parliament" in active_combos(value)
    assert "parliament" in value["unlocked"]
    muted = apply_flock_edit(value, {"action": "mute", "bird": "echo", "on": True})
    assert "parliament" not in active_combos(muted)
    assert "parliament" in muted["unlocked"]


def test_song_d_gate_and_automatic_fallback_when_combo_breaks() -> None:
    value = default_flock()
    for slot, bird in enumerate(("hush", "sable", "echo")):
        value = apply_flock_edit(value, {"action": "perch", "bird": bird, "slot": slot})
    value = apply_flock_edit(value, {"action": "harmony", "scale": "minor"})
    assert "night_shift" in active_combos(value)
    value = apply_flock_edit(value, {"action": "song", "bird": "echo", "song": "D"})
    assert value["perches"][2]["song"] == "D"
    broken = apply_flock_edit(value, {"action": "unperch", "bird": "hush"})
    assert broken["perches"][2]["song"] == "A"
    invalid = _perch(default_flock(), "echo", 0, song="D")
    with pytest.raises(ValueError, match="song D"):
        validate_flock(invalid)


def test_audio_projection_excludes_discovery_metadata_and_contains_flock_identity() -> None:
    first = default_flock()
    second = {**first, "seen": ["bramble"], "unlocked": ["parliament"]}
    assert audio_projection(first) == audio_projection(second)
    assert audio_projection(first)["renderer_version"] == FLOCK_RENDERER_VERSION
    assert len(audio_projection(first)["catalog_fingerprint"]) == 64


def test_combo_d_override_is_rendered_without_changing_stored_song() -> None:
    value = default_flock()
    for slot, bird in enumerate(("hush", "sable", "echo")):
        value = apply_flock_edit(value, {"action": "perch", "bird": bird, "slot": slot})
    value = apply_flock_edit(value, {"action": "harmony", "scale": "minor"})
    assert value["perches"][2]["song"] == "A"
    assert audio_projection(value)["perches"][2]["song"] == "D"


def test_project_flock_roundtrip_edit_history_diff_source_and_absent_identity(tmp_path, monkeypatch) -> None:
    project = new_project("old")
    baseline = canonical_json(project)
    assert hashlib.sha256(baseline.encode()).hexdigest() == "36d8939c0f5ffc1a56e14b3cf59477fc1a04f9d5a64dd4556af3620a0788506d"
    assert "flock" not in validate_project(project)
    assert canonical_json(project) == baseline
    store = ProjectStore(tmp_path)
    store.create("beat")
    events = []
    from rookery import events as event_module
    monkeypatch.setattr(event_module, "publisher", lambda plugin, event, payload: events.append(payload))
    first = store.edit("beat", "flock", action="template", template="Dusty Boom Bap", source="user")
    assert first["rev"] == 2 and first["project"]["flock"]["key"] == "D"
    assert events[-1]["tool"] is None
    assert events[-1]["source"] == "user"
    assert all(item["field"] == "flock" for item in first["diff"])
    with pytest.raises(ConflictError, match="stale project revision"):
        store.edit("beat", "flock", rev=1, action="weather", weather="rain")
    assert project_hash(first["project"], "renderer") != project_hash(new_project("beat"), "renderer")
    metadata = copy.deepcopy(first["project"])
    metadata["flock"]["seen"] = ["bramble"]
    assert project_hash(metadata, "renderer") == project_hash(first["project"], "renderer")
    undone = store.undo("beat")
    assert undone["rev"] == 3 and "flock" not in undone["project"]
    assert any(item["field"] == "flock" for item in undone["diff"])
    assert undone["diff"] == flock_diffs(first["project"]["flock"], default_flock())


def test_explicit_perch_song_d_without_combo_is_rejected() -> None:
    value = apply_flock_edit(None, {"action": "perch", "bird": "echo", "slot": 0})
    with pytest.raises(ValueError, match="song D"):
        apply_flock_edit(value, {"action": "perch", "bird": "echo", "song": "D"})


def test_corvus_unlocks_once_then_unperch_reperch_and_weather_do_not_respawn() -> None:
    ordinary = [bird["id"] for bird in load_catalog()["birds"]]
    value = default_flock()
    for bird in ordinary:
        value = apply_flock_edit(value, {"action": "perch", "bird": bird, "slot": 0})
        if bird != ordinary[-1]:
            value = apply_flock_edit(value, {"action": "unperch", "slot": 0})
    assert len(value["perches"]) == 7 and value["perches"][6]["bird"] == "corvus"
    assert value["perches"][6]["song"] == "A"
    seen = value["seen"]

    unperched = apply_flock_edit(value, {"action": "unperch", "slot": 6})
    assert len(unperched["perches"]) == 6
    assert unperched["seen"] == seen
    weathered = apply_flock_edit(unperched, {"action": "weather", "weather": "rain"})
    assert len(weathered["perches"]) == 6 and weathered["seen"] == seen

    reperched = apply_flock_edit(weathered, {"action": "perch", "bird": "corvus"})
    assert len(reperched["perches"]) == 7 and reperched["perches"][6]["bird"] == "corvus"
    with pytest.raises(ValueError, match="song A"):
        apply_flock_edit(reperched, {"action": "song", "bird": "corvus", "song": "B"})


def test_state_lines_marks_solo_and_hints_a_reachable_one_change_combo() -> None:
    value = apply_flock_edit(None, {"action": "perch", "bird": "hush", "slot": 0})
    value = apply_flock_edit(value, {"action": "perch", "bird": "sable", "slot": 1})
    value = apply_flock_edit(value, {"action": "harmony", "scale": "minor"})
    night_shift = next(combo["riddle"] for combo in load_catalog()["combos"] if combo["id"] == "night_shift")
    lines = state_lines(value)
    assert night_shift in lines[1]
    assert "·solo" not in lines[0]

    soloed = apply_flock_edit(value, {"action": "solo", "bird": "hush", "on": True})
    assert "·solo" in state_lines(soloed)[0]

    unlocked = apply_flock_edit(value, {"action": "perch", "bird": "echo", "slot": 2})
    assert night_shift not in state_lines(unlocked)[1]

    clear_window = apply_flock_edit(None, {"action": "perch", "bird": "quill", "slot": 0})
    clear_window = apply_flock_edit(clear_window, {"action": "perch", "bird": "moss", "slot": 1})
    rain_only = next(combo["riddle"] for combo in load_catalog()["combos"] if combo["id"] == "lo_fi_window")
    assert rain_only in state_lines(clear_window)[1]
    rainy = apply_flock_edit(clear_window, {"action": "weather", "weather": "rain"})
    assert "lo_fi_window" in active_combos(rainy)
    assert rain_only not in state_lines(rainy)[1]


def test_flock_diffs_infer_property_changes_and_split_multi_property_edits() -> None:
    before = apply_flock_edit(None, {"action": "perch", "bird": "bramble", "slot": 0})
    muted = apply_flock_edit(before, {"action": "mute", "bird": "bramble", "on": True})
    assert [item["change"] for item in flock_diffs(before, muted, "mute")] == ["mute"]

    moved = apply_flock_edit(before, {"action": "perch", "bird": "bramble", "slot": 3})
    placements = {(item["slot"], item["change"]) for item in flock_diffs(before, moved, "perch")}
    assert (0, "unperch") in placements and (3, "perch") in placements

    after = copy.deepcopy(before)
    after["perches"][0].update(song="B", mute=True)
    split = flock_diffs(before, after)
    assert [item["change"] for item in split] == ["song", "mute"]
    assert all(item["from"] == before["perches"][0] and item["to"] == after["perches"][0] for item in split)

    night = apply_flock_edit(None, {"action": "perch", "bird": "hush", "slot": 0})
    night = apply_flock_edit(night, {"action": "perch", "bird": "sable", "slot": 1})
    night = apply_flock_edit(night, {"action": "perch", "bird": "echo", "slot": 2})
    night = apply_flock_edit(night, {"action": "harmony", "scale": "minor"})
    night = apply_flock_edit(night, {"action": "song", "bird": "echo", "song": "D"})
    broken = apply_flock_edit(night, {"action": "unperch", "bird": "hush"})
    echo_diffs = [item for item in flock_diffs(night, broken, "unperch") if item["slot"] == 2]
    assert [item["change"] for item in echo_diffs] == ["song"]
    assert echo_diffs[0]["from"]["song"] == "D" and echo_diffs[0]["to"]["song"] == "A"


def test_perch_without_slot_keeps_slot_flags_and_song_unless_explicit() -> None:
    value = apply_flock_edit(None, {"action": "perch", "bird": "bramble", "slot": 2})
    value = apply_flock_edit(value, {"action": "song", "bird": "bramble", "song": "B"})
    value = apply_flock_edit(value, {"action": "mute", "bird": "bramble", "on": True})
    value = apply_flock_edit(value, {"action": "solo", "bird": "bramble", "on": True})
    expected = {"bird": "bramble", "song": "B", "mute": True, "solo": True}

    kept = apply_flock_edit(value, {"action": "perch", "bird": "bramble"})
    assert kept["perches"][2] == expected
    resung = apply_flock_edit(value, {"action": "perch", "bird": "bramble", "song": "C"})
    assert resung["perches"][2] == {**expected, "song": "C"}
    moved = apply_flock_edit(value, {"action": "perch", "bird": "bramble", "slot": 4})
    assert moved["perches"][2] is None and moved["perches"][4] == expected
