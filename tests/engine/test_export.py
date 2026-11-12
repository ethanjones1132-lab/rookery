import json
import struct
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from rookery.export import _license, export_project
from rookery.flock.model import default_flock
from rookery.project import ValidationError, new_project, validate_project
from rookery.render import SAMPLE_RATE, render_audio, render_song_audio, wav_bytes


def _project(arranged=False, muted=False):
    project = new_project("export-test", bpm=120, bars=4, genre="trap")
    project["tracks"][0]["steps"] = "x...x...x...x..."
    project["tracks"][0]["mute"] = muted
    project["flock"] = default_flock()
    project["flock"]["perches"][0] = {"bird": "echo", "song": "A"}
    if arranged:
        project["arrangement"] = {"sections": [
            {"id": "intro", "repeat": 1, "mute": []},
            {"id": "outro", "repeat": 2, "mute": []},
        ]}
    return validate_project(project)


def _midi_note_ons(data):
    """Tiny SMF reader: count note-on messages across tracks."""
    assert data[:4] == b"MThd"
    _, fmt, tracks, ppq = struct.unpack(">IHHH", data[4:14])
    assert fmt == 1 and ppq == 480
    offset, result = 14, []
    for _ in range(tracks):
        assert data[offset:offset + 4] == b"MTrk"
        length = int.from_bytes(data[offset + 4:offset + 8], "big")
        payload = data[offset + 8:offset + 8 + length]
        offset += 8 + length
        cursor, running = 0, None
        while cursor < len(payload):
            delta = 0
            while True:
                byte = payload[cursor]
                cursor += 1
                delta = (delta << 7) | (byte & 0x7f)
                if not byte & 0x80:
                    break
            status = payload[cursor]
            if status < 0x80:
                status = running
            else:
                cursor += 1
                running = status
            if status == 0xff:
                kind = payload[cursor]
                cursor += 1
                size = 0
                while True:
                    byte = payload[cursor]
                    cursor += 1
                    size = (size << 7) | (byte & 0x7f)
                    if not byte & 0x80:
                        break
                value = payload[cursor:cursor + size]
                cursor += size
                if kind == 0x2f:
                    break
                if kind == 0x51:
                    result.append(("tempo", int.from_bytes(value, "big")))
                elif kind == 0x58:
                    result.append(("time_signature", tuple(value)))
                continue
            first = payload[cursor]
            second = payload[cursor + 1]
            cursor += 2
            if status & 0xf0 == 0x90 and second:
                result.append(("note", first, second))
    return result


def test_export_wav_matches_render_and_stems_are_aligned_with_muted_silence(tmp_path):
    project = _project(muted=True)
    result = export_project(project, tmp_path, stems=True, midi=False)
    mix, _ = render_audio(project)
    export_dir = Path(result["folder"])
    assert (export_dir / "export-test.wav").read_bytes() == wav_bytes(mix, SAMPLE_RATE, "PCM_24")
    mixed, _ = sf.read(export_dir / "export-test.wav", dtype="float32", always_2d=True)
    stem, _ = sf.read(export_dir / "stems" / f"{project['tracks'][0]['id']}.wav", dtype="float32", always_2d=True)
    assert len(stem) == len(mixed)
    assert not np.any(stem)
    assert result["duration_s"] == len(mixed) / SAMPLE_RATE


def test_midi_has_tempo_and_drum_note_events(tmp_path):
    project = _project()
    result = export_project(project, tmp_path, stems=False)
    data = (Path(result["folder"]) / "export-test.mid").read_bytes()
    parsed = _midi_note_ons(data)
    assert ("tempo", 500000) in parsed
    assert ("time_signature", (4, 2, 24, 8)) in parsed
    kick_hits = sum(item[0] == "note" and item[1] == 36 for item in parsed)
    expected_kicks = sum(
        1 for track in project["tracks"]
        if track.get("kind", "drum") == "drum"
        and str(track.get("source", "")).startswith("factory:kick")
        and not track.get("mute")
        for symbol in (track.get("steps", "x") * 4)[:project["bars"] * 16]
        if symbol == "x"
    )
    assert kick_hits == expected_kicks > 0


def test_song_cues_sections_hits_and_frames_match_render(tmp_path):
    project = _project(arranged=True)
    result = export_project(project, tmp_path, fps=30, stems=False, midi=False)
    cues = json.loads((Path(result["folder"]) / "cues.json").read_text())
    audio, _, metadata, sections = render_song_audio(project)
    assert cues["loop"] is False
    assert len(cues["beats"]) == project["bars"] * 4 * 3
    assert len(cues["bars"]) == project["bars"] * 3
    assert [item["s"] for item in cues["kicks"]] == pytest.approx(metadata["kick_onsets"])
    assert all(item["f"] == round(item["s"] * 30) for field in ("beats", "bars", "kicks") for item in cues[field])
    assert [{key: item[key] for key in ("id", "start_s", "end_s")} for item in cues["sections"]] == sections
    assert all(item["start_f"] == round(item["start_s"] * 30)
               and item["end_f"] == round(item["end_s"] * 30) for item in cues["sections"])
    assert cues["duration_s"] == pytest.approx(len(audio) / SAMPLE_RATE)


def test_export_is_idempotent_and_song_without_arrangement_errors(tmp_path):
    project = _project()
    first = export_project(project, tmp_path, stems=False)
    before = {item["path"]: (Path(first["folder"]) / item["path"]).read_bytes()
              for item in first["files"]}
    second = export_project(project, tmp_path, stems=False)
    after = {item["path"]: (Path(second["folder"]) / item["path"]).read_bytes()
             for item in second["files"]}
    assert first["folder"] == second["folder"] and before == after
    with pytest.raises(ValidationError, match="no arrangement"):
        export_project(project, tmp_path, song=True)


def test_license_lists_user_library_cc0_credit(tmp_path):
    project = _project()
    project["tracks"][0]["source"] = "user:library/CC0-kick.wav"
    kit = tmp_path / "kits" / "library"
    kit.mkdir(parents=True)
    sf.write(kit / "CC0-kick.wav", np.zeros(128, dtype=np.float32), SAMPLE_RATE)
    (kit / "credits.json").write_text(json.dumps({"abc": {
        "id": "abc", "file": "CC0-kick.wav", "title": "Dusty Kick", "creator": "someone",
        "license": "cc0", "landing_url": "https://freesound.org/people/someone/sounds/1"}}), encoding="utf-8")
    result = export_project(validate_project(project), tmp_path, user_kit_dir=tmp_path / "kits",
                            stems=False, midi=False)
    license_text = (Path(result["folder"]) / "LICENSE.txt").read_text(encoding="utf-8")
    assert "- library/CC0-kick.wav: Dusty Kick · by someone · https://freesound.org/people/someone/sounds/1" in license_text
    assert "You own the music" in license_text


def _credits(tmp_path, entries):
    library = tmp_path / "kits" / "library"
    library.mkdir(parents=True, exist_ok=True)
    (library / "credits.json").write_text(json.dumps(entries), encoding="utf-8")
    return tmp_path / "kits"


def _soundza_credit(**overrides):
    credit = {
        "id": "soundza:cmudkgpuo000409gmjonfn7qq", "source": "soundza",
        "file": "skipit-horns.flac", "title": "Skipit Horns", "creator": "Antronical",
        "license": "soundza-standard", "license_url": "https://soundza.com/license",
        "landing_url": "https://soundza.com/sound/skipit-horns",
    }
    credit.update(overrides)
    return credit


def test_license_without_library_sounds_is_byte_identical_to_today():
    project = {"tracks": [{"id": "808", "source": "factory:808"}]}
    assert _license(project) == (
        "Made with Rookery.\n"
        "Rookery sounds are original; library sources are CC0.\n"
        "You own the music you made with Rookery.\n"
    )


def test_license_openverse_only_is_byte_identical_to_today(tmp_path):
    kit = _credits(tmp_path, {"abc": {
        "id": "abc", "file": "CC0-kick.wav", "title": "Dusty Kick", "creator": "someone",
        "license": "cc0", "landing_url": "https://freesound.org/people/someone/sounds/1"}})
    project = {"tracks": [{"id": "kick", "source": "user:library/CC0-kick.wav"}]}
    assert _license(project, kit) == (
        "Made with Rookery.\n"
        "Rookery sounds are original; library sources are CC0.\n"
        "CC0 sounds used (no attribution required; credited as a courtesy):\n"
        "- library/CC0-kick.wav: Dusty Kick · by someone · "
        "https://freesound.org/people/someone/sounds/1\n"
        "You own the music you made with Rookery.\n"
    )


def test_license_soundza_only_has_its_own_block_and_license_terms(tmp_path):
    kit = _credits(tmp_path, {"soundza:cmudkgpuo000409gmjonfn7qq": _soundza_credit()})
    project = {"tracks": [{"id": "guitar", "source": "user:library/skipit-horns.flac"}]}
    text = _license(project, kit)
    assert text == (
        "Made with Rookery.\n"
        "Sounds from soundza.com.\n"
        "Soundza sounds used (Soundza Standard License, https://soundza.com/license: "
        "royalty-free, no attribution required; credited as a courtesy):\n"
        "- library/skipit-horns.flac: Skipit Horns · by Antronical · "
        "https://soundza.com/sound/skipit-horns\n"
        "Don't share these sounds, or stems that are only one of them, as standalone files "
        "or in a sample pack; they are licensed for use inside your music.\n"
        "You own the music you made with Rookery.\n"
    )
    assert "CC0" not in text


def test_license_mixed_sources_drop_the_blanket_cc0_sentence(tmp_path):
    kit = _credits(tmp_path, {
        "abc": {"id": "abc", "file": "CC0-kick.wav", "title": "Dusty Kick",
                "creator": "someone", "license": "cc0",
                "landing_url": "https://freesound.org/people/someone/sounds/1"},
        "soundza:cmudkgpuo000409gmjonfn7qq": _soundza_credit(),
    })
    project = {"tracks": [
        {"id": "kick", "source": "user:library/CC0-kick.wav"},
        {"id": "guitar", "source": "user:library/skipit-horns.flac"},
    ]}
    text = _license(project, kit)
    assert "Rookery sounds are original; library sources are CC0." not in text
    assert text.index("CC0 sounds used") < text.index("Soundza sounds used")
    assert "Dusty Kick" in text and "Skipit Horns" in text


def test_license_names_stems_that_carry_a_soundza_sound(tmp_path):
    kit = _credits(tmp_path, {"soundza:cmudkgpuo000409gmjonfn7qq": _soundza_credit()})
    project = {"tracks": [
        {"id": "kick", "source": "factory:kick_punch"},
        {"id": "guitar", "source": "user:library/skipit-horns.flac"},
    ]}
    with_stems = _license(project, kit, stems=True)
    assert "Soundza sounds are in these stems: stems/guitar.wav." in with_stems
    assert "stems/kick.wav" not in with_stems
    assert "these stems" not in _license(project, kit, stems=False)


def test_license_marks_a_removed_soundza_credit(tmp_path):
    kit = _credits(tmp_path, {"soundza:cmudkgpuo000409gmjonfn7qq": _soundza_credit(removed=True)})
    project = {"tracks": [{"id": "guitar", "source": "user:library/skipit-horns.flac"}]}
    assert "removed by Soundza; replace it before release" in _license(project, kit)


def test_stems_sit_at_mix_level_and_sum_to_the_pre_limiter_mix(tmp_path):
    # A stem must not be loudness-normalized on its own: quiet parts stay quiet.
    project = _project()
    result = export_project(project, tmp_path, stems=True, midi=False)
    stems_dir = Path(result["folder"]) / "stems"
    stems = {path.stem: sf.read(path, dtype="float64", always_2d=True)[0] for path in stems_dir.glob("*.wav")}
    assert sf.info(str(stems_dir / "flock.wav")).subtype == "FLOAT"
    mix, _ = sf.read(Path(result["folder"]) / "export-test.wav", dtype="float64", always_2d=True)
    total = sum(stems.values())
    rms = lambda audio: float(np.sqrt(np.mean(audio * audio)))
    # Every stem is quieter than the mix, and together they land near the mix level
    # (the mix adds only the limiter on top).
    assert all(rms(stem) < rms(total) for stem in stems.values())
    assert abs(20 * np.log10(rms(total) / rms(mix))) < 3.0


def test_song_stems_work_when_a_section_mutes_a_bird(tmp_path):
    project = _project()
    project["arrangement"] = {"sections": [{"id": "intro", "repeat": 1, "mute": ["bird:0"]},
                                           {"id": "verse", "repeat": 1, "mute": []}]}
    project = validate_project(project)
    result = export_project(project, tmp_path, song=True, stems=True, midi=False)
    names = {item["path"] for item in result["files"]}
    assert "stems/flock.wav" in names
    flock, _ = sf.read(Path(result["folder"]) / "stems" / "flock.wav", dtype="float64", always_2d=True)
    half = len(flock) // 2
    assert np.sqrt(np.mean(flock[:half] ** 2)) < 0.1 * np.sqrt(np.mean(flock[half:] ** 2))


def test_song_midi_and_cues_use_section_track_overrides(tmp_path):
    project = _project()
    project.pop("flock")
    project["arrangement"] = {"sections": [
        {"id": "verse", "repeat": 1, "mute": []},
        {"id": "break", "repeat": 1, "mute": [],
         "steps": {"kick": "................", "snare": "................"},
         "notes": {"808": [{"step": 4, "len": 2, "pitch": "D1"}]}},
        {"id": "hook", "repeat": 1, "mute": []},
    ]}
    project = validate_project(project)
    result = export_project(project, tmp_path, song=True, stems=False, midi=True)
    folder = Path(result["folder"])
    notes = _midi_note_ons((folder / "export-test.mid").read_bytes())
    assert sum(1 for item in notes if item[0] == "note" and item[1] == 36) == 32
    assert sum(1 for item in notes if item[0] == "note" and item[1] == 26) == 1
    cues = json.loads((folder / "cues.json").read_text())
    assert len(cues["snares"]) == 16
