from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import threading
from uuid import uuid4

import pytest

from rookery import events
from rookery.project import (
    ConflictError,
    ProjectError,
    ProjectStore,
    ValidationError,
    canonical_json,
    load,
    new_project,
    project_hash,
    rev,
    save,
    validate_project,
)


@pytest.fixture
def project_data_dir():
    directory = Path(__file__).resolve().parents[2] / f".project-test-{uuid4().hex}"
    directory.mkdir()
    try:
        yield directory
    finally:
        shutil.rmtree(directory)


def test_validation_rejection_leaves_project_and_revision_unchanged(project_data_dir: Path) -> None:
    store = ProjectStore(project_data_dir)
    store.create("beat")
    added = store.edit("beat", "track", action="add", id="kick", kind="drum", source="factory:kick_boom")
    path = project_data_dir / "projects" / "beat" / "project.json"
    before = path.read_bytes()

    with pytest.raises(ProjectError):
        store.edit("beat", "steps", track="kick", steps="x.1.............")

    assert path.read_bytes() == before
    assert rev(path.parent) == added["rev"]


def test_track_creation_diff_uses_expanded_patterns_and_sorted_indices(project_data_dir: Path) -> None:
    store = ProjectStore(project_data_dir)
    store.create("beat")

    result = store.edit("beat", "track", action="add", id="kick", kind="drum",
                        source="factory:kick_boom", steps="x...", velocity=[0.5])

    step_diff = next(item for item in result["diff"] if item["field"] == "steps")
    velocity_diff = next(item for item in result["diff"] if item["field"] == "velocity")
    assert step_diff["steps"] == list(range(0, 64, 4))
    assert len(step_diff["from"]) == len(step_diff["to"]) == 64
    assert velocity_diff["steps"] == list(range(64))
    assert result["project"]["tracks"][0]["steps"] == "x..." * 16


def test_stale_revision_does_not_write(project_data_dir: Path) -> None:
    store = ProjectStore(project_data_dir)
    created = store.create("beat")
    before = (project_data_dir / "projects" / "beat" / "project.json").read_bytes()

    with pytest.raises(ConflictError) as caught:
        store.edit("beat", "meta", rev=created["rev"] - 1, swing=0.25)

    assert caught.value.rev == created["rev"]
    assert (project_data_dir / "projects" / "beat" / "project.json").read_bytes() == before


def test_user_edits_preserve_none_tool_while_agent_edits_infer(project_data_dir: Path,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    store = ProjectStore(project_data_dir)
    store.create("beat")
    store.edit("beat", "track", action="add", id="kick", kind="drum", source="factory:kick_boom")
    published = []
    monkeypatch.setattr(events, "publisher", lambda plugin, event, payload: published.append(payload))

    agent = store.edit("beat", "steps", track="kick", steps="x...............")
    user = store.edit("beat", "steps", track="kick", steps="....x...........", source="user", tool=None)
    explicit = store.edit("beat", "steps", track="kick", steps="........x.......", source="user",
                          tool="custom_tool")

    assert published[-3]["source"] == "agent"
    assert published[-3]["tool"] == "rookery_steps"
    assert published[-2]["source"] == "user"
    assert published[-2]["tool"] is None
    assert published[-1]["tool"] == "custom_tool"
    assert [agent["rev"], user["rev"], explicit["rev"]] == [agent["rev"], agent["rev"] + 1, agent["rev"] + 2]
    saved = load(project_data_dir / "projects" / "beat")
    assert saved["rev"] == explicit["rev"]
    assert saved["tracks"][0]["steps"] == "........x......."


def test_repeated_undo_walks_back_and_never_bounces(project_data_dir: Path) -> None:
    store = ProjectStore(project_data_dir)
    store.create("beat")
    store.edit("beat", "track", action="add", id="kick", kind="drum", source="factory:kick_boom")
    first = store.edit("beat", "steps", track="kick", steps="x...............")
    second = store.edit("beat", "steps", track="kick", steps="....x...........")

    undone_once = store.undo("beat")
    undone_twice = store.undo("beat")
    undone_three = store.undo("beat")

    assert [undone_once["rev"], undone_twice["rev"], undone_three["rev"]] == [second["rev"] + 1, second["rev"] + 2, second["rev"] + 3]
    assert undone_once["project"]["tracks"][0]["steps"] == "x..............." * 4
    assert undone_twice["project"]["tracks"][0]["steps"] == "." * 64
    assert undone_three["project"]["tracks"] == []
    with pytest.raises(ProjectError, match="nothing to undo"):
        store.undo("beat")
    assert rev(project_data_dir / "projects" / "beat") == undone_three["rev"]
    assert first["rev"] < second["rev"]


def test_concurrent_edits_are_atomic_and_revisions_do_not_get_lost(project_data_dir: Path) -> None:
    store = ProjectStore(project_data_dir)
    store.create("beat")
    store.edit("beat", "track", action="add", id="kick", kind="drum", source="factory:kick_boom")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda value: store.edit("beat", "meta", swing=value), (0.2, 0.4)))

    assert sorted(result["rev"] for result in results) == [3, 4]
    saved = load(project_data_dir / "projects" / "beat")
    assert saved["rev"] == 4
    assert saved["swing"] in {0.2, 0.4}
    assert len(list((project_data_dir / "projects" / "beat" / "history").glob("*.json"))) == 3


def test_canonical_audio_identity_ignores_metadata_and_name() -> None:
    first = new_project("one")
    second = {**new_project("two"), "rev": 27, "updated_at": "later", "history": []}

    assert canonical_json(first) == canonical_json(second)


def test_project_song_key_scale_validate_edit_and_affect_audio_identity(project_data_dir: Path) -> None:
    legacy = new_project("legacy-key")
    assert "key" not in legacy and "scale" not in legacy

    keyed = new_project("keyed", key="Db", scale="minor")
    alias = new_project("alias", key="C#", scale="minor")
    assert keyed["key"] == "C#" and keyed["scale"] == "minor"
    assert canonical_json(keyed) == canonical_json(alias)
    assert project_hash(keyed, "v") != project_hash(legacy, "v")
    assert project_hash(keyed, "v") != project_hash(new_project("major", key="C#", scale="major"), "v")

    with pytest.raises(ValidationError, match="key must be one of"):
        new_project("bad-key", key="H")
    with pytest.raises(ValidationError, match="scale must be major or minor"):
        new_project("bad-scale", scale="dorian")

    store = ProjectStore(project_data_dir)
    store.create("meta-key", key="Bb", scale="minor")
    result = store.edit("meta-key", "meta", key="F#", scale="major")
    assert result["project"]["key"] == "F#"
    assert result["project"]["scale"] == "major"
    assert {item["field"] for item in result["diff"]} >= {"key", "scale"}

    with pytest.raises(ValidationError, match="key must be one of"):
        store.edit("meta-key", "meta", key="H")


def _numeric_equivalent_project(name: str, ints: bool) -> dict:
    number = int if ints else float
    project = new_project(name, bpm=number(90), swing=number(0))
    project["tracks"] = [{
        "id": "kick", "kind": "drum", "source": "factory:kick_boom", "steps": "x...",
        "gain_db": number(0), "pan": -0.0 if not ints else 0, "pitch": number(0),
        "velocity": [number(1), number(0)],
        "fx": [{"type": "delay", "delay_seconds": number(0), "feedback": number(0), "mix": number(1)}],
    }]
    project["master"] = {"fx": [{"type": "reverb", "room_size": number(0), "damping": 0.5,
                                 "wet_level": number(1), "dry_level": number(1), "width": number(1)}]}
    return project


def test_canonical_identity_normalizes_equivalent_numeric_audio_fields() -> None:
    integer_spelled = _numeric_equivalent_project("one", ints=True)
    float_spelled = _numeric_equivalent_project("two", ints=False)

    assert project_hash(integer_spelled, "v") == project_hash(float_spelled, "v")
    assert canonical_json(integer_spelled) == canonical_json(float_spelled)

    changed_velocity = _numeric_equivalent_project("three", ints=False)
    changed_velocity["tracks"][0]["velocity"] = [0.5, 0]
    assert project_hash(changed_velocity, "v") != project_hash(integer_spelled, "v")

    changed_fx = _numeric_equivalent_project("four", ints=True)
    changed_fx["master"]["fx"][0]["damping"] = 0.25
    assert project_hash(changed_fx, "v") != project_hash(integer_spelled, "v")

    changed_bpm = _numeric_equivalent_project("five", ints=True)
    changed_bpm["bpm"] = 91
    assert project_hash(changed_bpm, "v") != project_hash(integer_spelled, "v")


def test_validation_returns_normalized_copy_without_mutating_input() -> None:
    project = new_project("safe")
    original = {**project, "tracks": [{"id": "kick", "kind": "drum", "source": "factory:kick_boom", "steps": "x"}]}
    snapshot = {**original, "tracks": [dict(original["tracks"][0])]}

    normalized = validate_project(original)

    assert original == snapshot
    assert normalized["tracks"][0]["gain_db"] == 0
    assert normalized["tracks"][0]["velocity"] == [1.0]


@pytest.mark.parametrize("bad_source", ["factory:unknown", "user:../secret.wav", "user:C:/secret.wav"])
def test_invalid_sources_are_rejected(bad_source: str) -> None:
    project = new_project("safe")
    project["tracks"] = [{"id": "sample", "kind": "sample", "source": bad_source}]

    with pytest.raises(ProjectError):
        validate_project(project)


@pytest.mark.parametrize("bad_source", [
    "user:notes.json", "user:message.txt", "user:kick.wav.json", "user:kick", "user:loops/notes.txt",
])
def test_user_sources_require_a_supported_audio_suffix(bad_source: str) -> None:
    project = new_project("safe")
    project["tracks"] = [{"id": "sample", "kind": "sample", "source": bad_source}]

    with pytest.raises(ValidationError):
        validate_project(project)


@pytest.mark.parametrize("source", [
    "user:kick.WAV", "user:loops/kick.Flac", "user:kick.aiff", "user:kick.AIF", "user:kick.OGG",
])
def test_user_sources_accept_supported_audio_suffixes_case_insensitively(source: str) -> None:
    project = new_project("safe")
    project["tracks"] = [{"id": "sample", "kind": "sample", "source": source}]

    assert validate_project(project)["tracks"][0]["source"] == source


@pytest.mark.parametrize("bad_path", ["C:/plugins/corvus.dll", "C:/plugins/corvus.json", "C:/plugins/corvus.txt"])
def test_fx_vst3_paths_require_the_vst3_suffix(bad_path: str) -> None:
    project = new_project("safe")
    project["tracks"] = [{"id": "kick", "kind": "drum", "source": "factory:kick_boom",
                          "fx": [{"type": "vst3", "path": bad_path}]}]

    with pytest.raises(ValidationError):
        validate_project(project)


def test_fx_vst3_suffix_is_case_insensitive() -> None:
    project = new_project("safe")
    project["tracks"] = [{"id": "kick", "kind": "drum", "source": "factory:kick_boom",
                          "fx": [{"type": "vst3", "path": "C:/plugins/Corvus.VST3"}]}]

    assert validate_project(project)["tracks"][0]["fx"][0]["path"] == "C:/plugins/Corvus.VST3"


@pytest.mark.parametrize("track", [
    {"id": "bass", "kind": "bass", "source": "factory:kick_boom", "notes": [{"step": 0, "len": 1, "pitch": "C1"}]},
    {"id": "bass", "kind": "bass", "source": "user:bass.wav", "notes": [{"step": 0, "len": 1, "pitch": "C1"}]},
    {"id": "bass", "kind": "bass", "source": "vst3:C:/bass.vst3", "notes": [{"step": 0, "len": 1, "pitch": "C1"}]},
    {"id": "sample", "kind": "sample", "source": "factory:kick_boom"},
    {"id": "sample", "kind": "sample", "source": "vst3:C:/sample.vst3"},
    {"id": "drum", "kind": "drum", "source": "vst3:C:/drum.vst3"},
])
def test_unsupported_kind_and_source_combinations_are_rejected(track: dict) -> None:
    project = new_project("safe")
    project["tracks"] = [track]

    with pytest.raises(ValidationError):
        validate_project(project)


@pytest.mark.parametrize("track", [
    {"id": "bass", "kind": "bass", "source": "factory:808", "notes": [{"step": 0, "len": 1, "pitch": "C1"}]},
    {"id": "sample", "kind": "sample", "source": "user:loops/kick.wav"},
    {"id": "kick", "kind": "drum", "source": "factory:kick_boom"},
    {"id": "loop", "kind": "drum", "source": "user:loops/kick.wav"},
])
def test_supported_kind_and_source_combinations_are_accepted(track: dict) -> None:
    project = new_project("safe")
    project["tracks"] = [track]

    assert validate_project(project)["tracks"][0]["source"] == track["source"]


def test_kind_and_genre_membership_reject_json_arrays_with_validation_errors() -> None:
    project = new_project("safe")
    project["tracks"] = [{"id": "kick", "kind": [], "source": "factory:kick_boom"}]

    with pytest.raises(ValidationError):
        validate_project(project)
    with pytest.raises(ProjectError):
        new_project("safe", genre=[])


@pytest.mark.parametrize("name", ["beat.", "con", "CON.mid", 123])
def test_safe_names_reject_windows_aliases_and_non_strings(name) -> None:
    with pytest.raises(ProjectError):
        new_project(name)


def test_master_is_reserved_as_a_track_id() -> None:
    project = new_project("safe")
    project["tracks"] = [{"id": "master", "kind": "drum", "source": "factory:kick_boom"}]

    with pytest.raises(ValidationError, match="reserved"):
        validate_project(project)


def test_track_id_rejects_trailing_dot() -> None:
    project = new_project("safe")
    project["tracks"] = [{"id": "kick.", "kind": "drum", "source": "factory:kick_boom"}]

    with pytest.raises(ValidationError):
        validate_project(project)


@pytest.mark.parametrize("pitch", ["B9", "A9", "G#9"])
def test_note_names_reject_out_of_range_midi(pitch: str) -> None:
    project = new_project("safe")
    project["tracks"] = [{"id": "bass", "kind": "bass", "source": "factory:808",
                          "notes": [{"step": 0, "len": 1, "pitch": pitch}]}]

    with pytest.raises(ValidationError, match="0 to 127"):
        validate_project(project)


@pytest.mark.parametrize("pitch", ["Cb4", "E#4", "Fb4", "B#4"])
def test_note_names_reject_spellings_the_renderer_cannot_parse(pitch: str) -> None:
    project = new_project("safe")
    project["tracks"] = [{"id": "bass", "kind": "bass", "source": "factory:808",
                          "notes": [{"step": 0, "len": 1, "pitch": pitch}]}]

    with pytest.raises(ValidationError, match="not supported"):
        validate_project(project)


def test_note_boundaries_and_numeric_midi_range() -> None:
    for pitch in ("C-1", "G9", 0, 127):
        project = new_project("safe")
        project["tracks"] = [{"id": "bass", "kind": "bass", "source": "factory:808",
                              "notes": [{"step": 0, "len": 1, "pitch": pitch}]}]
        assert validate_project(project)["tracks"][0]["notes"][0]["pitch"] == pitch
    for pitch in (-1, 128, 1.5):
        project = new_project("safe")
        project["tracks"] = [{"id": "bass", "kind": "bass", "source": "factory:808",
                              "notes": [{"step": 0, "len": 1, "pitch": pitch}]}]
        with pytest.raises(ValidationError):
            validate_project(project)


def test_filter_param_map_matches_fx_worker_and_normalizes_cutoff_alias() -> None:
    project = new_project("safe")
    project["master"] = {"fx": [{"type": "highpass", "cutoff_frequency_hz": 120},
                                {"type": "lowpass", "cutoff_hz": 900}]}

    normalized = validate_project(project)["master"]["fx"]
    assert normalized == [{"type": "highpass", "cutoff_hz": 120},
                          {"type": "lowpass", "cutoff_hz": 900}]
    for effect in ({"type": "highpass", "q": 0.7},
                   {"type": "highpass", "cutoff_hz": 100, "cutoff_frequency_hz": 200},
                   {"type": "reverb", "freeze_mode": True}):
        project["master"] = {"fx": [effect]}
        with pytest.raises(ValidationError):
            validate_project(project)


def test_fx_param_edits_vst3_params_preserves_chain_and_publishes_fx_diff(project_data_dir: Path,
                                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    store = ProjectStore(project_data_dir)
    store.create("beat")
    path = "C:/Plugins/Corvus.vst3"
    store.edit("beat", "mix", target="master",
               fx=[{"type": "vst3", "path": path, "params": {"master_drive": 0.1, "output_trim": 0.2}}])
    published = []
    monkeypatch.setattr(events, "publisher", lambda plugin, event, payload: published.append(payload))

    result = store.edit("beat", "fx_param", target="master", index=0, param="master_drive", value=0.6)
    effect = result["project"]["master"]["fx"][0]
    assert effect["path"] == path
    assert effect["params"] == {"master_drive": 0.6, "output_trim": 0.2}
    assert published[-1]["diff"] == result["diff"]
    assert any(item.get("track") == "master" and item.get("field") == "fx" for item in result["diff"])

    result = store.edit("beat", "fx_param", target="master", index=0, param="fatness", value=0.4)
    effect = result["project"]["master"]["fx"][0]
    assert effect["params"] == {"master_drive": 0.6, "output_trim": 0.2, "fatness": 0.4}


@pytest.mark.parametrize("param,value", [
    ("type", "limiter"), ("path", "other.vst3"), ("params", {}),
    ("bad\x01key", 1), ("", 1), ("fatness", float("nan")), ("fatness", "loud"),
])
def test_fx_param_rejects_non_numeric_and_structural_vst3_edits(project_data_dir: Path,
                                                               param: str, value) -> None:
    store = ProjectStore(project_data_dir)
    store.create("beat")
    store.edit("beat", "mix", target="master",
               fx=[{"type": "vst3", "path": "C:/Plugins/Corvus.vst3", "params": {"master_drive": 0.1}}])

    with pytest.raises(ProjectError):
        store.edit("beat", "fx_param", target="master", index=0, param=param, value=value)


def test_fx_param_can_add_omitted_builtin_parameter_and_normalize_cutoff(project_data_dir: Path) -> None:
    store = ProjectStore(project_data_dir)
    store.create("beat")
    store.edit("beat", "mix", target="master", fx=[{"type": "compressor"},
                                                    {"type": "highpass", "cutoff_hz": 1000}])

    result = store.edit("beat", "fx_param", target="master", index=0, param="threshold_db", value=-12)
    assert result["project"]["master"]["fx"][0] == {"type": "compressor", "threshold_db": -12}
    result = store.edit("beat", "fx_param", target="master", index=1,
                        param="cutoff_frequency_hz", value=250)
    assert result["project"]["master"]["fx"][1] == {"type": "highpass", "cutoff_hz": 250}
    with pytest.raises(ProjectError):
        store.edit("beat", "fx_param", target="master", index=1, param="q", value=0.7)


def test_shrinking_bars_crops_expanded_patterns_velocity_and_notes(project_data_dir: Path) -> None:
    store = ProjectStore(project_data_dir)
    store.create("beat", bars=8)
    expanded = "x..." * 32
    store.edit("beat", "track", action="add", id="kick", kind="drum", source="factory:kick_boom",
               steps=expanded, velocity=[0.25] * 128)
    store.edit("beat", "track", action="add", id="bass", kind="bass", source="factory:808",
               notes=[{"step": 10, "len": 100, "pitch": "C1"},
                      {"step": 100, "len": 10, "pitch": "E1"}])

    result = store.edit("beat", "meta", bars=4)

    kick, bass = result["project"]["tracks"]
    assert kick["steps"] == "x..." * 16
    assert kick["velocity"] == [0.25] * 64
    assert bass["notes"] == [{"step": 10, "len": 64, "pitch": "C1"}]
    assert any(item.get("field") == "bars" and item.get("from") == 8 and item.get("to") == 4
               for item in result["diff"])


def test_oversized_normalized_project_is_rejected_before_any_write_or_event(project_data_dir: Path,
                                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    store = ProjectStore(project_data_dir)
    created = store.create("beat")
    directory = project_data_dir / "projects" / "beat"
    path = directory / "project.json"
    before = path.read_bytes()
    history_before = sorted(item.name for item in (directory / "history").glob("*.json")) \
        if (directory / "history").exists() else []
    published = []
    monkeypatch.setattr(events, "publisher", lambda plugin, event, payload: published.append(payload))

    project = load(directory)
    project["history"] = ["y" * 4096 for _ in range(600)]
    with pytest.raises(ValidationError, match="2 MiB"):
        save(project, directory)

    assert path.read_bytes() == before
    assert (sorted(item.name for item in (directory / "history").glob("*.json"))
            if (directory / "history").exists() else []) == history_before
    assert rev(directory) == created["rev"]
    assert published == []


def test_nonfinite_nested_metadata_is_rejected() -> None:
    project = new_project("safe")
    project["history"] = {"values": [1.0, float("nan")]}

    with pytest.raises(ValidationError):
        validate_project(project)


def test_overlapping_editing_transitions_are_emitted_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded = []
    false_entered = threading.Event()
    true_emitted = threading.Event()

    def fake_emit(event: str, payload: dict) -> None:
        if payload["editing"]:
            recorded.append(True)
            true_emitted.set()
        else:
            false_entered.set()
            # An overlapping start must not overtake this false transition.
            true_emitted.wait(0.2)
            recorded.append(False)

    monkeypatch.setattr(events, "emit", fake_emit)
    first = events.editing("beat")
    first.__enter__()
    try:
        def overlap() -> None:
            false_entered.wait()
            with events.editing("beat"):
                pass

        worker = threading.Thread(target=overlap)
        worker.start()
        true_emitted.clear()
    finally:
        first.__exit__(None, None, None)
        worker.join()

    assert recorded == [True, False, True, False]


def test_failing_editing_publisher_does_not_strand_the_count(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_emit(event: str, payload: dict) -> None:
        raise RuntimeError("publisher down")

    monkeypatch.setattr(events, "emit", broken_emit)
    with events.editing("beat"):
        assert events.is_editing("beat")

    assert not events.is_editing("beat")
