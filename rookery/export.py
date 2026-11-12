"""Creator-facing deterministic audio, MIDI, and motion cue exports."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import struct
from pathlib import Path

from . import render as renderer
from .arrangement import section_track_view
from .project import ValidationError, canonical_project, validate_project


_GM_DRUMS = {
    "kick_boom": 36, "kick_deep": 36, "kick_tight": 36, "snare_crack": 38,
    "snare_snap": 38, "snare_rim": 37, "clap": 39, "hat_closed": 42,
    "hat_open": 46, "hat_pedal": 44, "tom_low": 45, "tom_mid": 47,
    "tom_high": 50, "perc": 60,
}


def _gm_drum(name: str) -> int:
    """GM drum note for a factory sound: exact name first, then its family prefix."""
    if name in _GM_DRUMS:
        return _GM_DRUMS[name]
    for prefix, note in (("kick", 36), ("snare", 38), ("clap", 39), ("rim", 37), ("hat_open", 46),
                         ("hat", 42), ("tom", 47), ("perc", 60)):
        if name.startswith(prefix):
            return note
    return 38


def _vlq(value: int) -> bytes:
    value = max(0, int(value))
    buffer = value & 0x7F
    out = bytearray()
    while (value := value >> 7):
        buffer <<= 8
        buffer |= ((value & 0x7F) | 0x80)
    while True:
        out.append(buffer & 0xFF)
        if buffer & 0x80:
            buffer >>= 8
        else:
            break
    return bytes(out)


def _midi_track(events: list[tuple[int, bytes]]) -> bytes:
    events.sort(key=lambda item: (item[0], 0 if item[1][0] & 0xF0 == 0x80 else 1))
    data = bytearray()
    previous = 0
    for tick, message in events:
        data.extend(_vlq(tick - previous))
        data.extend(message)
        previous = tick
    data.extend(b"\x00\xff\x2f\x00")
    return b"MTrk" + struct.pack(">I", len(data)) + data


def _midi_bytes(project: dict, metadata: dict, song: bool) -> bytes:
    ppq, bpm = 480, float(project["bpm"])
    tempo = round(60_000_000 / bpm)
    tracks: list[bytes] = []
    meta_events = [(0, b"\xff\x51\x03" + tempo.to_bytes(3, "big")),
                   (0, b"\xff\x58\x04\x04\x02\x18\x08")]
    tracks.append(_midi_track(meta_events))
    arrangement = project.get("arrangement", {}).get("sections", []) if song else []
    repeats = [(section, repetition) for section in arrangement for repetition in range(section["repeat"])]
    loop_seconds = project["bars"] * 4 * 60 / bpm
    sections = []
    cursor = 0.0
    for section, repetition in repeats:
        sections.append((cursor, section, repetition))
        cursor += loop_seconds
    n_steps = project["bars"] * 16
    step_seconds = loop_seconds / n_steps
    track_list = project.get("tracks", [])
    has_solo = any(track.get("solo") for track in track_list)
    for track in track_list:
        ev: list[tuple[int, bytes]] = []
        drum = track.get("kind", "drum") == "drum"
        channel = 9 if drum else 0
        name = str(track.get("id", "track"))[:120].encode("ascii", "replace")
        ev.append((0, b"\xff\x03" + _vlq(len(name)) + name))
        audible = not track.get("mute") and (not has_solo or track.get("solo"))
        if audible:
            if song:
                section_iter = sections
            else:
                section_iter = [(0.0, None)]
            for item in section_iter:
                if len(item) == 3:
                    offset, section, repeat_index = item
                else:
                    offset, section = item
                    repeat_index = 0
                section_muted = section is not None and track["id"] in section["mute"]
                if section_muted:
                    continue
                seconds = offset
                if section is not None:
                    steps, velocity, notes = section_track_view(project, section, track, repeat_index)
                else:
                    steps = track.get("steps", "x")
                    velocity = track.get("velocity", [1.0]) or [1.0]
                    notes = track.get("notes", []) or []
                if drum:
                    pattern = renderer._patterns(steps, n_steps)
                    pitch = _gm_drum(str(track.get("source", "")).split(":")[-1])
                    for i, symbol in enumerate(pattern):
                        if symbol == ".":
                            continue
                        vel = max(1, min(127, round(float(velocity[i % len(velocity)]) * 127)))
                        onset = seconds + i * step_seconds
                        if i % 2:
                            onset += float(project.get("swing", 0)) * step_seconds * .5
                        start_tick = round(onset * bpm / 60 * ppq)
                        end_tick = start_tick + 60
                        ev.extend(((start_tick, bytes((0x90 | channel, pitch, vel))),
                                   (end_tick, bytes((0x80 | channel, pitch, 0)))))
                elif track.get("kind") == "bass":
                    for note in notes:
                        pitch = int(round(renderer._note_midi(note.get("pitch", "C1")) + float(track.get("pitch", 0))))
                        pitch = max(0, min(127, pitch))
                        step = int(note["step"])
                        start = seconds + step * step_seconds
                        if step % 2:
                            start += float(project.get("swing", 0)) * step_seconds * .5
                        duration = max(1, int(note.get("len", 1))) * step_seconds
                        start_tick = round(start * bpm / 60 * ppq)
                        end_tick = round((start + duration) * bpm / 60 * ppq)
                        ev.extend(((start_tick, bytes((0x90, pitch, 100))),
                                   (end_tick, bytes((0x80, pitch, 0)))))
        tracks.append(_midi_track(ev))
    flock_events = metadata.get("flock_events", {})
    birds = sorted(flock_events)
    for bird in birds:
        ev = []
        label = f"Flock: {bird}".encode("ascii", "replace")
        ev.append((0, b"\xff\x03" + _vlq(len(label)) + label))
        for note in flock_events[bird]:
            start = round(float(note["t"]) * bpm / 60 * ppq)
            end = round((float(note["t"]) + float(note["len"])) * bpm / 60 * ppq)
            pitch = max(0, min(127, int(note["midi"])))
            vel = max(1, min(127, round(float(note["vel"]) * 127)))
            ev.extend(((start, bytes((0x90, pitch, vel))), (end, bytes((0x80, pitch, 0)))))
        tracks.append(_midi_track(ev))
    return b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), ppq) + b"".join(tracks)


def _library_credits(user_kit_dir) -> dict:
    """Map library file name -> credit, from the kit's credits.json (written by rookery_samples)."""
    if user_kit_dir is None:
        return {}
    try:
        data = json.loads((Path(user_kit_dir) / "library" / "credits.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {item["file"]: item for item in data.values() if isinstance(item, dict) and isinstance(item.get("file"), str)}


def _license(project: dict, user_kit_dir=None, *, stems: bool = False) -> str:
    """Credit every library sound by source; Openverse stays CC0, Soundza gets its own block."""
    sources = sorted({str(t.get("source", "")) for t in project.get("tracks", [])
                      if str(t.get("source", "")).startswith("user:")})
    library = [s[5:] for s in sources if s.startswith("user:library/")]
    own = [s[5:] for s in sources if not s.startswith("user:library/")]
    credits = _library_credits(user_kit_dir) if library else {}
    cc0: list[tuple[str, dict]] = []
    soundza: list[tuple[str, dict]] = []
    for item in library:
        credit = credits.get(item[len("library/"):], {})
        (soundza if credit.get("source") == "soundza" else cc0).append((item, credit))
    lines = ["Made with Rookery."]
    if soundza:
        lines.append("Sounds from soundza.com.")
    else:
        lines.append("Rookery sounds are original; library sources are CC0.")
    if cc0:
        lines.append("CC0 sounds used (no attribution required; credited as a courtesy):")
        for item, credit in cc0:
            detail = " · ".join(value for value in (
                credit.get("title"), credit.get("creator") and f"by {credit['creator']}",
                credit.get("landing_url"), credit.get("license_url")) if value)
            lines.append(f"- {item}" + (f": {detail}" if detail else ""))
    if soundza:
        lines.append("Soundza sounds used (Soundza Standard License, https://soundza.com/license: "
                     "royalty-free, no attribution required; credited as a courtesy):")
        for item, credit in soundza:
            detail = " · ".join(value for value in (
                credit.get("title"), credit.get("creator") and f"by {credit['creator']}",
                credit.get("landing_url")) if value)
            line = f"- {item}" + (f": {detail}" if detail else "")
            if credit.get("removed") is True:
                line += " (removed by Soundza; replace it before release)"
            lines.append(line)
        lines.append("Don't share these sounds, or stems that are only one of them, as standalone files "
                     "or in a sample pack; they are licensed for use inside your music.")
        if stems:
            soundza_files = {item[len("library/"):] for item, credit in soundza}
            names = [f"stems/{track['id']}.wav" for track in project.get("tracks", [])
                     if str(track.get("source", "")).startswith("user:library/")
                     and str(track.get("source", ""))[len("user:library/"):] in soundza_files]
            if names:
                lines.append("Soundza sounds are in these stems: " + ", ".join(names) + ".")
    if own:
        lines.append("User-provided sounds: your own files (" + ", ".join(own) + ").")
    lines.append("You own the music you made with Rookery.")
    return "\n".join(lines) + "\n"


def _export_project(project: dict, data_dir, *, user_kit_dir=None, name=None, song=None,
                   stems=True, midi=True, fps=None) -> dict:
    """Write a stable creator export and return a compact receipt."""
    project = validate_project(copy.deepcopy(project))
    if not isinstance(stems, bool) or not isinstance(midi, bool):
        raise ValidationError("stems and midi must be booleans")
    if song is None:
        song = "arrangement" in project
    if not isinstance(song, bool):
        raise ValidationError("song must be a boolean")
    if song and "arrangement" not in project:
        raise ValidationError("this project has no arrangement; add one with the arrange op")
    if fps is not None and (isinstance(fps, bool) or not isinstance(fps, int) or not 1 <= fps <= 240):
        raise ValidationError("fps must be an integer from 1 to 240")
    selected = name or project["name"]
    if not isinstance(selected, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", selected):
        raise ValidationError("name must use letters, numbers, dot, underscore, or dash")
    selected = selected.strip(".-_") or "rookery"
    opts = {"song": song, "stems": stems, "midi": midi, "fps": fps}
    digest = hashlib.sha256((canonical_project(project) + renderer.RENDERER_VERSION +
                             json.dumps(opts, sort_keys=True, separators=(",", ":"))).encode()).hexdigest()[:8]
    folder = Path(data_dir) / "exports" / f"{selected}-{digest}"
    folder.mkdir(parents=True, exist_ok=True)
    if song:
        audio, _meters, metadata, section_timings = renderer._render_song_audio(project, renderer.SAMPLE_RATE, user_kit_dir)
        loop = False
    else:
        audio, _meters, metadata = renderer._render_audio_with_metadata(project, renderer.SAMPLE_RATE, user_kit_dir)
        section_timings = []
        loop = True
    wav = renderer.wav_bytes(audio, renderer.SAMPLE_RATE, "PCM_24")
    (folder / f"{selected}.wav").write_bytes(wav)
    files = [folder / f"{selected}.wav"]
    if stems:
        # Stems carry the mix's own loudness gain and skip the final limiter, written as 32-bit
        # float so nothing clips: they line up and sit at mix level in an editor or DAW.
        gain = metadata.get("master_gain") if isinstance(metadata, dict) else None
        if gain is None:
            gain = 1.0
        stem_dir = folder / "stems"
        stem_dir.mkdir(exist_ok=True)

        def silence_birds(item):
            # Birds are silenced, not removed, so arrangement mutes that name a bird stay valid.
            if item.get("flock"):
                for perch in item["flock"]["perches"]:
                    if perch:
                        perch["mute"] = True
                        perch.pop("solo", None)

        def render_stem(isolated):
            if song:
                return renderer._render_song_audio(isolated, renderer.SAMPLE_RATE, user_kit_dir, fixed_gain=gain)[0]
            return renderer._render_audio_with_metadata(isolated, renderer.SAMPLE_RATE, user_kit_dir, fixed_gain=gain)[0]

        for track in project.get("tracks", []):
            isolated = copy.deepcopy(project)
            silence_birds(isolated)
            for item in isolated["tracks"]:
                item["mute"] = item["id"] != track["id"] or bool(track.get("mute"))
                item.pop("solo", None)
            destination = stem_dir / f"{track['id']}.wav"
            destination.write_bytes(renderer.wav_bytes(render_stem(isolated), renderer.SAMPLE_RATE, "FLOAT"))
            files.append(destination)
        if project.get("flock") and any(project["flock"]["perches"]):
            isolated = copy.deepcopy(project)
            for item in isolated.get("tracks", []):
                item["mute"] = True
            destination = stem_dir / "flock.wav"
            destination.write_bytes(renderer.wav_bytes(render_stem(isolated), renderer.SAMPLE_RATE, "FLOAT"))
            files.append(destination)
    duration = len(audio) / renderer.SAMPLE_RATE
    repeat_count = sum(section["repeat"] for section in project.get("arrangement", {}).get("sections", [])) if song else 1
    beats_per_loop = project["bars"] * 4
    n_steps = project["bars"] * 16
    loop_frames = round(project["bars"] * 4 * 60 / float(project["bpm"]) * renderer.SAMPLE_RATE)
    step_frames = loop_frames / n_steps
    step_seconds = step_frames / renderer.SAMPLE_RATE
    beat_frames = loop_frames / beats_per_loop
    bar_frames = loop_frames / project["bars"]
    beats = [round(i * beat_frames) / renderer.SAMPLE_RATE
             for i in range(beats_per_loop * repeat_count)]
    bars = [round(i * bar_frames) / renderer.SAMPLE_RATE
            for i in range(project["bars"] * repeat_count)]
    def cue(times):
        return [{"s": round(float(value), 9), **({"f": round(float(value) * fps)} if fps else {})} for value in times]
    kicks = metadata.get("kick_onsets", [])
    snares = []
    if not song:
        tracks = project.get("tracks", [])
        soloed = any(track.get("solo") for track in tracks)
        for track in tracks:
            if (track.get("kind", "drum") != "drum" or track.get("mute")
                    or (soloed and not track.get("solo"))
                    or not str(track.get("source", "")).split(":")[-1].startswith("snare")):
                continue
            velocity = track.get("velocity", [1.0]) or [1.0]
            for index, symbol in enumerate(renderer._patterns(track.get("steps", "x"), n_steps)):
                if symbol != "x" or float(velocity[index % len(velocity)]) <= 0:
                    continue
                onset = round(index * step_frames) / renderer.SAMPLE_RATE
                if index % 2:
                    onset += round(float(project.get("swing", 0)) * step_frames * .5) / renderer.SAMPLE_RATE
                snares.append(onset)
    else:
        for section, timing in zip(project["arrangement"]["sections"], section_timings):
            for repeat_index in range(section["repeat"]):
                offset = timing["start_s"] + repeat_index * (project["bars"] * 4 * 60 / float(project["bpm"]))
                for track in project.get("tracks", []):
                    if (track.get("kind", "drum") != "drum" or track.get("mute")
                            or (any(item.get("solo") for item in project.get("tracks", []))
                                and not track.get("solo"))
                            or track["id"] in section["mute"]
                            or not str(track.get("source", "")).split(":")[-1].startswith("snare")):
                        continue
                    steps, velocity, _notes = section_track_view(project, section, track, repeat_index)
                    for index, symbol in enumerate(renderer._patterns(steps, n_steps)):
                        if symbol != "x" or float(velocity[index % len(velocity)]) <= 0:
                            continue
                        onset = offset + round(index * step_frames) / renderer.SAMPLE_RATE
                        if index % 2:
                            onset += round(float(project.get("swing", 0)) * step_frames * .5) / renderer.SAMPLE_RATE
                        snares.append(onset)
    cues = {"bpm": project["bpm"], "duration_s": duration, "loop": loop,
            "sample_rate": renderer.SAMPLE_RATE, "beats": cue(beats), "bars": cue(bars),
            "kicks": cue(kicks), "snares": cue(snares),
            "sections": [{"id": item["id"], "start_s": item["start_s"], "end_s": item["end_s"],
                          **({"start_f": round(item["start_s"] * fps),
                             "end_f": round(item["end_s"] * fps)} if fps else {})}
                         for item in section_timings]}
    if fps is not None:
        cues["fps"] = fps
    cues_path = folder / "cues.json"
    cues_path.write_text(json.dumps(cues, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    files.append(cues_path)
    readme_path = folder / "README.txt"
    readme_path.write_text(
        "Use cues.json: cut on bars for scene changes, kicks for hits.\n"
        "Stems are 32-bit float WAVs, sample-aligned with the mix, at the mix's own gain. "
        "They skip the final limiter (and each passes through the master FX on its own), so "
        "together they sum to the mix before limiting, not byte-for-byte to the limited mix.\n",
        encoding="utf-8")
    files.append(readme_path)
    if midi:
        midi_path = folder / f"{selected}.mid"
        midi_path.write_bytes(_midi_bytes(project, metadata, song))
        files.append(midi_path)
    license_path = folder / "LICENSE.txt"
    license_path.write_text(_license(project, user_kit_dir, stems=stems), encoding="utf-8")
    files.append(license_path)
    return {"folder": str(folder.resolve()), "files": [{"path": str(path.relative_to(folder)).replace("\\", "/"),
             "size": path.stat().st_size} for path in files], "duration_s": duration,
            "note": "Use cues.json: cut on bars for scene changes, kicks for hits."}


def export_project(*args, corvus_vst3_path=None, **kwargs):
    """Export with the user's corvus_vst3_path as the only loadable VST3 (none when unset)."""
    from .fx import configured_vst3

    with configured_vst3(corvus_vst3_path):
        return _export_project(*args, **kwargs)
