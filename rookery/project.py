"""Project schema, canonical audio identity, and crash-safe project storage."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import os
import re
import tempfile
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from . import events
from .flock.model import apply_flock_edit, audio_projection as flock_audio_projection, flock_diffs, validate_flock
from .kit import BASS_FACTORY_NAMES, FACTORY_NAMES
from .mix import SAMPLE_ROLES, add_track_defaults

SCHEMA = "rookery.project/1"
_FACTORY = set(FACTORY_NAMES)
_BASS_FACTORY = {f"factory:{name}" for name in BASS_FACTORY_NAMES}
_MAX_TRACKS = 32
_MAX_FX = 16
_MAX_NOTES = 128
_MAX_PROJECT_BYTES = 2 * 1024 * 1024
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_TRACK_ID_RE = _NAME_RE
_NOTE_RE = re.compile(r"^([A-Ga-g])([#b])?(-1|[0-9])$")
_NOTE_NAMES = {
    "C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3, "E": 4,
    "F": 5, "F#": 6, "GB": 6, "G": 7, "G#": 8, "AB": 8, "A": 9,
    "A#": 10, "BB": 10, "B": 11,
}
_PITCH_CLASS_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_NOTE_SPELLINGS = "C, C#/Db, D, D#/Eb, E, F, F#/Gb, G, G#/Ab, A, A#/Bb, or B"
_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_PROJECT_KEYS = {"schema", "name", "bpm", "bars", "steps_per_bar", "swing", "humanize_ms", "seed", "genre", "mix_profile", "key", "scale", "tracks", "master", "flock", "arrangement", "rev", "updated_at", "history", "_history_cursor", "_history_parent", "_history_change_source", "_history_change_diff", "_history_to_rev"}
_TRACK_KEYS = {"id", "kind", "source", "gain_db", "pan", "mute", "solo", "pitch", "velocity", "fx", "steps", "notes", "slices", "choke_group", "mode", "key_lock", "loop_bars", "duck", "role"}
_KINDS = {"drum", "bass", "sample"}
USER_AUDIO_EXTENSIONS = frozenset({".wav", ".flac", ".aiff", ".aif", ".ogg"})

_FX_PARAMS: dict[str, dict[str, tuple[float, float]]] = {
    "compressor": {"threshold_db": (-80, 0), "ratio": (1, 20), "attack_ms": (0.1, 500), "release_ms": (1, 5000)},
    "limiter": {"threshold_db": (-40, 0), "ceiling_db": (-40, 0), "release_ms": (1, 2000)},
    "reverb": {"room_size": (0, 1), "damping": (0, 1), "wet_level": (0, 1), "dry_level": (0, 1), "width": (0, 1)},
    "delay": {"delay_seconds": (0, 10), "feedback": (-0.99, 0.99), "mix": (0, 1)},
    "distortion": {"drive_db": (0, 48)},
    "chorus": {"rate_hz": (0, 20), "depth": (0, 1), "centre_delay_ms": (0, 50), "feedback": (-0.99, 0.99), "mix": (0, 1)},
    "highpass": {"cutoff_hz": (20, 20000)},
    "lowpass": {"cutoff_hz": (20, 20000)},
}


class ProjectError(ValueError):
    """A safe, user-facing project or edit error."""


class ValidationError(ProjectError):
    """The project does not satisfy the v1 schema."""


class NotFoundError(ProjectError):
    """The requested project does not exist."""


class ConflictError(ProjectError):
    """An edit used a stale project revision."""

    def __init__(self, message: str, rev: int):
        super().__init__(message)
        self.rev = rev


def _fail(message: str) -> None:
    raise ValidationError(message)


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _number(value: Any, label: str, low: float, high: float, *, integer: bool = False) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"{label} must be a number")
    if isinstance(value, float) and not math.isfinite(value):
        _fail(f"{label} must be between {low:g} and {high:g}")
    if not low <= value <= high:
        _fail(f"{label} must be between {low:g} and {high:g}")
    if integer and not isinstance(value, int):
        _fail(f"{label} must be an integer")
    return value


def _integer(value: Any, label: str, low: int, high: int) -> int:
    return int(_number(value, label, low, high, integer=True))


def _safe_name(value: Any, label: str = "name") -> str:
    if not isinstance(value, str) or not _NAME_RE.fullmatch(value) or value in {".", ".."} or value.endswith("."):
        _fail(f"{label} must be a simple 1-64 character name")
    if value.split(".", 1)[0].upper() in _RESERVED_NAMES:
        _fail(f"{label} is reserved on Windows")
    return value


def _safe_track_id(value: Any, label: str = "track id") -> str:
    track_id = _safe_name(value, label)
    if track_id == "master":
        _fail(f"{label} 'master' is reserved for the master FX chain")
    return track_id


def _validate_key(value: Any) -> str:
    if not isinstance(value, str):
        _fail(f"key must be one of {_NOTE_SPELLINGS}")
    pitch_class = _NOTE_NAMES.get(value.strip().upper())
    if pitch_class is None:
        _fail(f"key must be one of {_NOTE_SPELLINGS}")
    return _PITCH_CLASS_NAMES[pitch_class]


def _path_parts(path: str) -> list[str]:
    return re.split(r"[\\/]", path)


def _audio_suffix(path: str) -> str:
    name = _path_parts(path)[-1]
    index = name.rfind(".")
    return name[index:].lower() if index > 0 else ""


def _validate_source(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 1024 or any(ord(c) < 32 for c in value):
        _fail("source must be a non-empty source identifier")
    if value.startswith("factory:"):
        factory_name = value[len("factory:"):]
        if factory_name not in _FACTORY:
            _fail(f"unknown factory source: {factory_name or '(empty)'}")
        return value
    if value.startswith("user:"):
        relative = value[len("user:"):]
        parts = _path_parts(relative)
        if (not relative or relative.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", relative)
                or any(part in {"", ".", ".."} for part in parts)):
            _fail("user source must be a safe relative path without traversal")
        if _audio_suffix(relative) not in USER_AUDIO_EXTENSIONS:
            _fail("user source must name a supported audio file (.wav, .flac, .aiff, .aif, .ogg)")
        return value
    if value.startswith("vst3:"):
        path = value[len("vst3:"):]
        if not path or path.strip() != path or any(part == ".." for part in _path_parts(path)):
            _fail("vst3 source must name an explicit path without traversal")
        if not path.lower().endswith(".vst3"):
            _fail("vst3 source must name a .vst3 module or bundle")
        return value
    _fail("source must use factory:, user:, or vst3:")


def _validate_pitch(value: Any, label: str) -> str | int:
    if isinstance(value, str):
        match = _NOTE_RE.fullmatch(value)
        if match is None:
            _fail(f"{label} must be a MIDI note number or note name")
        key = match.group(1).upper() + (match.group(2) or "")
        if key not in _NOTE_NAMES:
            _fail(f"{label} note spelling {value!r} is not supported; use {_NOTE_SPELLINGS} with an octave")
        midi = (int(match.group(3)) + 1) * 12 + _NOTE_NAMES[key]
        if not 0 <= midi <= 127:
            _fail(f"{label} must be a MIDI note from 0 to 127")
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"{label} must be a MIDI note number or note name")
    return _integer(value, label, 0, 127)


def _validate_fx(fx: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(fx, list) or len(fx) > _MAX_FX:
        _fail(f"{label} must be a list of at most {_MAX_FX} effects")
    result: list[dict[str, Any]] = []
    for index, effect in enumerate(fx):
        where = f"{label}[{index}]"
        if not isinstance(effect, dict) or not isinstance(effect.get("type"), str):
            _fail(f"{where} must be an effect object with a type")
        kind = effect["type"]
        if kind == "vst3":
            if set(effect) - {"type", "path", "params"}:
                _fail(f"{where} has unknown vst3 settings")
            path = effect.get("path")
            if not isinstance(path, str) or not path or path.strip() != path or len(path) > 1024:
                _fail(f"{where}.path must be an explicit non-empty path")
            if any(ord(c) < 32 for c in path) or any(part == ".." for part in _path_parts(path)):
                _fail(f"{where}.path must not contain traversal")
            if not path.lower().endswith(".vst3"):
                _fail(f"{where}.path must name a .vst3 module or bundle")
            normalized: dict[str, Any] = {"type": kind, "path": path}
            if "params" in effect:
                params = effect["params"]
                if not isinstance(params, dict) or len(params) > 128:
                    _fail(f"{where}.params must be an object with at most 128 settings")
                normalized_params: dict[str, float] = {}
                for key, value in params.items():
                    if not isinstance(key, str) or not key or len(key) > 128 or any(ord(c) < 32 for c in key):
                        _fail(f"{where}.params keys must be non-empty strings")
                    normalized_params[key] = _number(value, f"{where}.params.{key}", -1_000_000, 1_000_000)
                normalized["params"] = normalized_params
            result.append(normalized)
            continue
        if kind not in _FX_PARAMS:
            _fail(f"{where} has unsupported effect type {kind!r}")
        settings = dict(effect)
        if kind in {"highpass", "lowpass"} and "cutoff_frequency_hz" in settings:
            if "cutoff_hz" in settings:
                _fail(f"{where} must not provide both cutoff_hz and cutoff_frequency_hz")
            settings["cutoff_hz"] = settings.pop("cutoff_frequency_hz")
        allowed = {"type", *_FX_PARAMS[kind]}
        if set(settings) - allowed:
            _fail(f"{where} has unknown {kind} settings")
        normalized = {"type": kind}
        for key, value in settings.items():
            if key == "type":
                continue
            low, high = _FX_PARAMS[kind][key]
            normalized[key] = _number(value, f"{where}.{key}", low, high)
        result.append(normalized)
    return result


def _validate_track(track: Any, index: int, total: int) -> dict[str, Any]:
    label = f"tracks[{index}]"
    if not isinstance(track, dict):
        _fail(f"{label} must be an object")
    unknown = set(track) - _TRACK_KEYS
    if unknown:
        _fail(f"{label} has unknown fields: {', '.join(sorted(unknown))}")
    track_id = _safe_track_id(track.get("id"), f"{label}.id")
    kind = track.get("kind")
    if not isinstance(kind, str) or kind not in _KINDS:
        _fail(f"{label}.kind must be drum, bass, or sample")
    if "source" not in track:
        _fail(f"{label}.source is required")
    source = _validate_source(track["source"])
    if source.startswith("vst3:"):
        _fail(f"{label}.source rejects vst3 instrument sources; plugin instrument loading is not supported")
    if kind == "bass" and source not in _BASS_FACTORY:
        _fail(f"{label}.source must be factory:808 or another factory 808 voice for bass tracks")
    if kind == "sample" and not source.startswith("user:"):
        _fail(f"{label}.source must use user: for sample tracks")
    if kind == "drum" and not source.startswith(("factory:", "user:")):
        _fail(f"{label}.source must use factory: or user: for drum tracks")
    result: dict[str, Any] = {
        "id": track_id,
        "kind": kind,
        "source": source,
        "gain_db": _number(track.get("gain_db", 0), f"{label}.gain_db", -60, 12),
        "pan": _number(track.get("pan", 0), f"{label}.pan", -1, 1),
        "mute": track.get("mute", False),
        "solo": track.get("solo", False),
        "pitch": _number(track.get("pitch", 0), f"{label}.pitch", -48, 48),
        "steps": track.get("steps", "x" * int(total / 16) if kind == "sample" and track.get("mode") == "loop" else "."),
        "velocity": copy.deepcopy(track.get("velocity", [1.0])),
        "fx": _validate_fx(track.get("fx", []), f"{label}.fx"),
    }
    if not isinstance(result["mute"], bool) or not isinstance(result["solo"], bool):
        _fail(f"{label}.mute and {label}.solo must be booleans")
    if "mode" in track:
        if kind != "sample" or not isinstance(track["mode"], str) or track["mode"] not in {"oneshot", "loop"}:
            _fail(f"{label}.mode must be oneshot or loop on sample tracks")
        result["mode"] = track["mode"]
    if "role" in track:
        if kind != "sample" or not isinstance(track["role"], str) or track["role"] not in SAMPLE_ROLES:
            _fail(f"{label}.role must be bed, lead, counter, texture, or drums on sample tracks")
        result["role"] = track["role"]
    if "key_lock" in track:
        if kind != "sample" or not isinstance(track["key_lock"], bool):
            _fail(f"{label}.key_lock must be a boolean on sample tracks")
        result["key_lock"] = track["key_lock"]
    if "loop_bars" in track:
        if kind != "sample" or track.get("mode") != "loop":
            _fail(f"{label}.loop_bars is only valid in loop mode")
        result["loop_bars"] = _integer(track["loop_bars"], f"{label}.loop_bars", 1, 8)
        if result["loop_bars"] not in {1, 2, 4, 8}:
            _fail(f"{label}.loop_bars must be 1, 2, 4, or 8")
    if "duck" in track:
        if not (kind == "bass" or (kind == "sample" and track.get("mode") == "loop")):
            _fail(f"{label}.duck is only valid on bass tracks or loop-mode samples")
        result["duck"] = _number(track["duck"], f"{label}.duck", 0, 1)
    if result.get("mode") == "loop":
        result.setdefault("key_lock", True)
    loop_mode = kind == "sample" and result.get("mode") == "loop"
    steps = result["steps"]
    if not isinstance(steps, str) or not steps or len(steps) > total:
        _fail(f"{label}.steps must contain 1 to {total} characters")
    if loop_mode and (steps == "." or len(steps) > int(total / 16)):
        # Legacy step-grid patterns have no bar-gate meaning. Conversion defaults
        # them to all bars, matching the documented loop-mode default.
        steps = "x" * int(total / 16)
        result["steps"] = steps
    alphabet = "x." if kind in {"drum", "bass"} or loop_mode else "x.0123456789"
    if any(char not in alphabet for char in steps):
        _fail(f"{label}.steps contains an invalid symbol for a {kind} track")
    if loop_mode and len(steps) != int(total / 16):
        bars_in_loop = int(total / 16)
        if bars_in_loop % len(steps):
            _fail(f"{label}.steps in loop mode gates bars: use 1 to {bars_in_loop} characters that divide "
                  f"the {bars_in_loop} bars (x plays a bar, . rests); a short pattern repeats")
        steps = steps * (bars_in_loop // len(steps))
        result["steps"] = steps
    if not loop_mode and total % len(steps):
        lengths = [str(length) for length in range(1, total + 1) if total % length == 0]
        valid = ", ".join(lengths[:-1]) + " or " + lengths[-1]
        _fail(f"steps length {len(steps)} does not divide the {total}-step loop; use {valid}")
    slices = track.get("slices", 10)
    if kind == "sample":
        result["slices"] = _integer(slices, f"{label}.slices", 1, 10)
        if any(char.isdigit() and int(char) >= result["slices"] for char in steps):
            _fail(f"{label}.steps references a slice outside the configured slice count")
    elif "slices" in track:
        _fail(f"{label}.slices is only valid on sample tracks")
    velocity = result["velocity"]
    if not isinstance(velocity, list) or not velocity or len(velocity) > total:
        _fail(f"{label}.velocity must contain 1 to {total} values")
    result["velocity"] = [_number(value, f"{label}.velocity[{i}]", 0, 1) for i, value in enumerate(velocity)]
    if "choke_group" in track:
        group = track["choke_group"]
        if kind != "drum" or not isinstance(group, str) or not group or len(group) > 64 or any(ord(c) < 32 for c in group):
            _fail(f"{label}.choke_group must be a short string on a drum track")
        result["choke_group"] = group
    notes = track.get("notes", [])
    if kind != "bass" and "notes" in track:
        _fail(f"{label}.notes is only valid on bass tracks")
    if not isinstance(notes, list) or len(notes) > min(total, _MAX_NOTES):
        _fail(f"{label}.notes must contain at most {min(total, _MAX_NOTES)} notes")
    normalized_notes = []
    note_steps: set[int] = set()
    for note_index, note in enumerate(notes):
        nlabel = f"{label}.notes[{note_index}]"
        if not isinstance(note, dict) or set(note) != {"step", "len", "pitch"}:
            _fail(f"{nlabel} must contain exactly step, len, and pitch")
        step = _integer(note["step"], f"{nlabel}.step", 0, total - 1)
        if step in note_steps:
            _fail(f"{label}.notes contains duplicate step {step}")
        note_steps.add(step)
        length = _integer(note["len"], f"{nlabel}.len", 1, total)
        normalized_notes.append({"step": step, "len": length, "pitch": _validate_pitch(note["pitch"], f"{nlabel}.pitch")})
    if kind == "bass" or notes:
        result["notes"] = normalized_notes
    return result


def validate_project(project: Any) -> dict[str, Any]:
    """Return a normalized deep copy, raising ValidationError without mutation."""
    if not isinstance(project, dict):
        _fail("project must be a JSON object")
    unknown = set(project) - _PROJECT_KEYS
    if unknown:
        _fail(f"project has unknown fields: {', '.join(sorted(unknown))}")
    if project.get("schema") != SCHEMA:
        _fail(f"schema must be {SCHEMA}")
    name = _safe_name(project.get("name"))
    bpm = _number(project.get("bpm"), "bpm", 30, 300)
    bars = project.get("bars")
    if isinstance(bars, bool) or not isinstance(bars, int) or bars not in (4, 8):
        _fail("bars must be 4 or 8")
    steps_per_bar = project.get("steps_per_bar", 16)
    if not isinstance(steps_per_bar, int) or isinstance(steps_per_bar, bool) or steps_per_bar != 16:
        _fail("steps_per_bar must be 16")
    swing = _number(project.get("swing", 0), "swing", 0, 1)
    genre = project.get("genre")
    if genre is not None and (not isinstance(genre, str) or genre not in {"boom-bap", "trap"}):
        _fail("genre must be boom-bap or trap")
    mix_profile = project.get("mix_profile")
    if mix_profile is not None and mix_profile != "targets-v1":
        _fail("mix_profile must be targets-v1")
    humanize_ms = _number(project["humanize_ms"], "humanize_ms", 0, 6) if "humanize_ms" in project else None
    key = _validate_key(project["key"]) if "key" in project else None
    scale = project.get("scale")
    if "scale" in project and (not isinstance(scale, str) or scale not in {"major", "minor"}):
        _fail("scale must be major or minor")
    seed = _integer(project.get("seed", 1337), "seed", 0, 2**32 - 1)
    tracks = project.get("tracks", [])
    if not isinstance(tracks, list) or len(tracks) > _MAX_TRACKS:
        _fail(f"tracks must be a list of at most {_MAX_TRACKS} tracks")
    total = int(bars) * 16
    normalized_tracks = [_validate_track(track, i, total) for i, track in enumerate(tracks)]
    ids = [track["id"] for track in normalized_tracks]
    if len(ids) != len(set(ids)):
        _fail("track IDs must be unique")
    master = project.get("master", {"fx": []})
    if not isinstance(master, dict) or set(master) != {"fx"}:
        _fail("master must contain only an fx list")
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "name": name,
        "bpm": bpm,
        "bars": int(bars),
        "steps_per_bar": 16,
        "swing": swing,
        "seed": seed,
        "tracks": normalized_tracks,
        "master": {"fx": _validate_fx(master.get("fx"), "master.fx")},
    }
    if genre is not None:
        result["genre"] = genre
    if mix_profile is not None:
        result["mix_profile"] = mix_profile
    if key is not None:
        result["key"] = key
    if "scale" in project:
        result["scale"] = scale
    if humanize_ms is not None:
        result["humanize_ms"] = humanize_ms
    if "flock" in project:
        try:
            result["flock"] = validate_flock(project["flock"])
        except (TypeError, ValueError, KeyError) as exc:
            raise ValidationError(str(exc)) from exc
    if "arrangement" in project:
        arrangement = project["arrangement"]
        if not isinstance(arrangement, dict) or set(arrangement) != {"sections"}:
            _fail("arrangement must contain only a sections list")
        sections = arrangement["sections"]
        if not isinstance(sections, list) or not 1 <= len(sections) <= 16:
            _fail("arrangement.sections must contain 1 to 16 sections")
        track_ids = set(ids)
        bird_slots = set()
        if "flock" in result:
            bird_slots = {i for i, perch in enumerate(result["flock"]["perches"]) if perch is not None}
        normalized_sections = []
        seen_sections = set()
        total_repeats = 0
        track_by_id = {track["id"]: (index, track) for index, track in enumerate(normalized_tracks)}
        for index, section in enumerate(sections):
            label = f"arrangement.sections[{index}]"
            required_section = {"id", "repeat", "mute"}
            optional_section = {"steps", "velocity", "notes", "songs", "fill"}
            if not isinstance(section, dict) or not required_section <= set(section) or set(section) - required_section - optional_section:
                _fail(f"{label} must contain id, repeat, and mute, with optional steps, velocity, notes, songs, and fill")
            section_id = _safe_track_id(section["id"], f"{label}.id")
            section_label = f"arrangement section {section_id!r}"
            if section_id in seen_sections:
                _fail(f"arrangement section id is duplicated: {section_id}")
            seen_sections.add(section_id)
            repeat = _integer(section["repeat"], f"{label}.repeat", 1, 8)
            mute = section["mute"]
            if not isinstance(mute, list):
                _fail(f"{label}.mute must be a list")
            normalized_mute = []
            for entry in mute:
                if not isinstance(entry, str):
                    _fail(f"{label}.mute entries must be track ids or bird:<slot>")
                if entry.startswith("bird:"):
                    slot_text = entry[5:]
                    if not slot_text.isdigit() or str(int(slot_text)) != slot_text or not 0 <= int(slot_text) <= 6:
                        _fail(f"{label}.mute has invalid perch reference {entry!r}; use bird:0 through bird:6")
                    if int(slot_text) not in bird_slots:
                        _fail(f"{label}.mute references empty perch {entry}")
                elif entry not in track_ids:
                    _fail(f"{label}.mute references unknown track {entry!r}")
                if entry in normalized_mute:
                    _fail(f"{label}.mute contains duplicate entry {entry!r}")
                normalized_mute.append(entry)
            total_repeats += repeat
            normalized_section = {"id": section_id, "repeat": repeat, "mute": normalized_mute}
            for field in ("steps", "velocity", "notes"):
                if field not in section:
                    continue
                overrides = section[field]
                if not isinstance(overrides, dict):
                    _fail(f"{section_label}.{field} must be an object keyed by track id")
                normalized_overrides = {}
                for track_id, value in overrides.items():
                    if not isinstance(track_id, str) or track_id not in track_by_id:
                        _fail(f"{section_label}.{field} references unknown track {track_id!r}")
                    track_index, track = track_by_id[track_id]
                    if field == "steps" and track["kind"] == "bass":
                        _fail(f"{section_label}.steps cannot override bass track {track_id!r}; use notes")
                    if field == "notes" and track["kind"] != "bass":
                        _fail(f"{section_label}.notes is only valid for bass track {track_id!r}")
                    candidate = copy.deepcopy(track)
                    candidate[field] = value
                    try:
                        checked = _validate_track(candidate, track_index, total)
                    except ValidationError as exc:
                        _fail(f"{section_label}.{field} override for {track_id!r} is invalid: {exc}")
                    normalized_overrides[track_id] = copy.deepcopy(checked[field])
                normalized_section[field] = normalized_overrides
            if "songs" in section:
                songs = section["songs"]
                if not isinstance(songs, dict):
                    _fail(f"{section_label}.songs must be an object keyed by bird:<slot>")
                normalized_songs = {}
                for reference, song in songs.items():
                    if (not isinstance(reference, str) or not reference.startswith("bird:")
                            or not reference[5:].isdigit() or str(int(reference[5:])) != reference[5:]
                            or not 0 <= int(reference[5:]) <= 6):
                        _fail(f"{section_label}.songs has invalid perch reference {reference!r}; use bird:0 through bird:6")
                    slot = int(reference[5:])
                    if slot not in bird_slots:
                        _fail(f"{section_label}.songs references empty perch {reference}")
                    if not isinstance(song, str) or song not in {"A", "B", "C", "D"}:
                        _fail(f"{section_label}.songs for {reference} must be A, B, C, or D")
                    try:
                        perch = result["flock"]["perches"][slot]
                        apply_flock_edit(result["flock"], {"action": "song", "bird": perch["bird"], "song": song})
                    except (TypeError, ValueError, KeyError) as exc:
                        _fail(f"{section_label}.songs for {reference}: {exc}")
                    normalized_songs[reference] = song
                normalized_section["songs"] = normalized_songs
            if "fill" in section:
                if not isinstance(section["fill"], bool):
                    _fail(f"{section_label}.fill must be a boolean")
                normalized_section["fill"] = section["fill"]
            normalized_sections.append(normalized_section)
        song_seconds = total_repeats * int(bars) * 4 * 60 / float(bpm)
        if song_seconds > 180:
            _fail(f"song length {song_seconds:.1f} s exceeds the 180 s limit")
        result["arrangement"] = {"sections": normalized_sections}
    if "rev" in project:
        result["rev"] = _integer(project["rev"], "rev", 0, 2**63 - 1)
    if "updated_at" in project:
        if not isinstance(project["updated_at"], str) or len(project["updated_at"]) > 64:
            _fail("updated_at must be a timestamp string")
        result["updated_at"] = project["updated_at"]
    if "history" in project:
        if not isinstance(project["history"], (str, list, dict)):
            _fail("history metadata must be JSON data")
        result["history"] = copy.deepcopy(project["history"])
    if "_history_cursor" in project:
        cursor = project["_history_cursor"]
        if cursor is not None:
            cursor = _integer(cursor, "_history_cursor", 1, 2**63 - 1)
        result["_history_cursor"] = cursor
    if "_history_parent" in project:
        parent = project["_history_parent"]
        if parent is not None:
            parent = _integer(parent, "_history_parent", 1, 2**63 - 1)
        result["_history_parent"] = parent
    if "_history_change_source" in project:
        source = project["_history_change_source"]
        if not isinstance(source, str) or source not in {"agent", "user"}:
            _fail("history change source must be agent or user")
        result["_history_change_source"] = source
    if "_history_change_diff" in project:
        if not isinstance(project["_history_change_diff"], list):
            _fail("history change diff must be a list")
        result["_history_change_diff"] = copy.deepcopy(project["_history_change_diff"])
    if "_history_to_rev" in project:
        result["_history_to_rev"] = _integer(project["_history_to_rev"], "_history_to_rev", 1, 2**63 - 1)
    try:
        encoded = _json_bytes(result)
    except (TypeError, ValueError) as exc:
        raise ValidationError("project must contain only finite JSON values") from exc
    if len(encoded) > _MAX_PROJECT_BYTES:
        _fail("project exceeds the 2 MiB encoded size limit")
    return result


def validate(project: Any) -> None:
    """Compatibility API: validate without modifying or returning the project."""
    validate_project(project)


def new_project(name: str, bpm: float = 90, bars: int = 4, genre: str | None = None,
                swing: float = 0, seed: int = 1337, key: str | None = None,
                scale: str | None = None) -> dict[str, Any]:
    name = _safe_name(name)
    tracks: list[dict[str, Any]] = []
    if genre is not None:
        if not isinstance(genre, str) or genre not in {"boom-bap", "trap"}:
            _fail("genre must be boom-bap or trap")
        if genre == "boom-bap":
            tracks = [
                {"id": "kick", "kind": "drum", "source": "factory:kick_punch", "steps": "x.....x...x....."},
                {"id": "snare", "kind": "drum", "source": "factory:snare_snap", "steps": "....x.......x...", "velocity": [0.9]},
                {"id": "hat", "kind": "drum", "source": "factory:hat_tight", "steps": "x.x.x.x.x.x.x.x.", "choke_group": "hats"},
            ]
        else:
            tracks = [
                {"id": "kick", "kind": "drum", "source": "factory:kick_deep", "steps": "x.......x...x..."},
                {"id": "snare", "kind": "drum", "source": "factory:snare_snap", "steps": "....x.......x..."},
                {"id": "hat", "kind": "drum", "source": "factory:hat_tight", "steps": "x.x.x.x.x.x.x.x.", "choke_group": "hats"},
                {"id": "808", "kind": "bass", "source": "factory:808_round", "notes": [{"step": 0, "len": 12, "pitch": "C1"}]},
            ]
    project = {"schema": SCHEMA, "name": name, "bpm": bpm, "bars": bars,
               "steps_per_bar": 16, "swing": swing, "seed": seed,
               "tracks": tracks, "master": {"fx": []}}
    if genre is not None:
        project["genre"] = genre
    if key is not None:
        project["key"] = key
    if scale is not None:
        project["scale"] = scale
    return validate_project(project)


def _repeat_pattern(pattern: str, count: int) -> str:
    return (pattern * ((count + len(pattern) - 1) // len(pattern)))[:count]


def _repeat_values(values: list[Any], count: int) -> list[Any]:
    return (values * ((count + len(values) - 1) // len(values)))[:count]


def expand_project(project: Any) -> dict[str, Any]:
    result = validate_project(project)
    total = result["bars"] * result["steps_per_bar"]
    for track in result["tracks"]:
        if not (track.get("kind") == "sample" and track.get("mode") == "loop"):
            track["steps"] = _repeat_pattern(track["steps"], total)
        track["velocity"] = _repeat_values(track["velocity"], total)
    return result


def _canonical_numbers(value: Any) -> Any:
    """Normalize equivalent numeric spellings inside the audio projection."""
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return value
        if value == 0:
            return 0
        if value.is_integer():
            return int(value)
        return value
    if isinstance(value, dict):
        return {key: _canonical_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_canonical_numbers(item) for item in value]
    return value


def _audio_projection(project: Any) -> dict[str, Any]:
    expanded = expand_project(project)
    tracks = []
    for track in expanded["tracks"]:
        item = {key: copy.deepcopy(track[key]) for key in ("id", "kind", "source", "gain_db", "pan", "mute", "solo", "pitch", "steps", "velocity", "fx")}
        for key in ("notes", "slices", "choke_group", "role"):
            if key in track:
                item[key] = copy.deepcopy(track[key])
        if track.get("kind") == "sample" and track.get("mode") == "loop":
            item["mode"] = "loop"
            for key in ("key_lock", "loop_bars"):
                if key in track:
                    item[key] = copy.deepcopy(track[key])
        if "duck" in track:
            item["duck"] = copy.deepcopy(track["duck"])
        tracks.append(item)
    projection = {"schema": SCHEMA, "bpm": expanded["bpm"], "bars": expanded["bars"],
                  "steps_per_bar": 16, "swing": expanded["swing"], "seed": expanded["seed"],
                  "tracks": tracks, "master": copy.deepcopy(expanded["master"])}
    if "genre" in expanded:
        projection["genre"] = expanded["genre"]
    if "mix_profile" in expanded:
        projection["mix_profile"] = expanded["mix_profile"]
    for field in ("key", "scale"):
        if field in expanded:
            projection[field] = expanded[field]
    if "flock" in expanded:
        projection["flock"] = flock_audio_projection(expanded["flock"])
    if "humanize_ms" in expanded:
        projection["humanize_ms"] = expanded["humanize_ms"]
    return _canonical_numbers(projection)


def canonical_project(project: Any) -> str:
    return json.dumps(_audio_projection(project), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def canonical_json(project: Any) -> str:
    """Compatibility API for canonical audio identity."""
    return canonical_project(project)


def project_hash(project: Any, renderer_version: str) -> str:
    if not isinstance(renderer_version, str) or not renderer_version:
        raise ValidationError("renderer_version must be a non-empty string")
    digest = hashlib.sha256()
    digest.update(canonical_project(project).encode("utf-8"))
    digest.update(renderer_version.encode("utf-8"))
    return digest.hexdigest()


def _step_diff(track_id: str, field: str, before: list[Any] | str, after: list[Any] | str) -> dict[str, Any] | None:
    default: Any = "." if field == "steps" else 1.0
    indices = [i for i in range(max(len(before), len(after)))
               if (before[i] if i < len(before) else default) != (after[i] if i < len(after) else default)]
    if not indices:
        return None
    return {"track": track_id, "field": field, "from": before, "to": after, "steps": indices}


def diff_projects(before: Any, after: Any, flock_change: str | None = None) -> list[dict[str, Any]]:
    """Build contract-shaped diffs, using expanded patterns and sorted indexes."""
    new = expand_project(after)
    total = new["bars"] * 16
    if before is None:
        old = {"tracks": [], "master": {"fx": []}, "bpm": new["bpm"], "bars": new["bars"], "swing": new["swing"]}
    else:
        old = expand_project(before)
    old_by_id = {track["id"]: track for track in old["tracks"]}
    new_by_id = {track["id"]: track for track in new["tracks"]}
    diffs: list[dict[str, Any]] = []
    for track in new["tracks"]:
        track_id = track["id"]
        previous = old_by_id.get(track_id)
        if previous is None:
            diffs.append({"track": track_id, "field": "track", "action": "add"})
            previous_steps: str = "." * total
            previous_velocity: list[Any] = [1.0] * total
            step_diff = _step_diff(track_id, "steps", previous_steps, track["steps"])
            velocity_diff = _step_diff(track_id, "velocity", previous_velocity, track["velocity"])
            if step_diff:
                diffs.append(step_diff)
            if velocity_diff:
                diffs.append(velocity_diff)
            continue
        step_diff = _step_diff(track_id, "steps", previous["steps"], track["steps"])
        velocity_diff = _step_diff(track_id, "velocity", previous["velocity"], track["velocity"])
        if step_diff:
            diffs.append(step_diff)
        if velocity_diff:
            diffs.append(velocity_diff)
        for field in ("gain_db", "pan", "mute", "solo", "pitch", "source"):
            if previous.get(field) != track.get(field):
                diffs.append({"track": track_id, "field": field, "from": copy.deepcopy(previous.get(field)), "to": copy.deepcopy(track.get(field))})
        if previous.get("fx", []) != track.get("fx", []):
            diffs.append({"track": track_id, "field": "fx", "from": copy.deepcopy(previous.get("fx", [])), "to": copy.deepcopy(track.get("fx", []))})
        for field in ("notes", "slices", "choke_group", "mode", "key_lock", "loop_bars", "duck", "role"):
            if previous.get(field) != track.get(field):
                diffs.append({"track": track_id, "field": field, "from": copy.deepcopy(previous.get(field)), "to": copy.deepcopy(track.get(field))})
    for track in old["tracks"]:
        if track["id"] not in new_by_id:
            diffs.append({"track": track["id"], "field": "track", "action": "remove"})
    for field in ("bpm", "bars", "swing", "humanize_ms", "key", "scale"):
        if old.get(field) != new.get(field):
            diffs.append({"field": field, "from": old.get(field), "to": new.get(field)})
    if old.get("master", {}).get("fx", []) != new["master"]["fx"]:
        diffs.append({"track": "master", "field": "fx", "from": copy.deepcopy(old.get("master", {}).get("fx", [])), "to": copy.deepcopy(new["master"]["fx"])})
    if old.get("flock") != new.get("flock"):
        diffs.extend(flock_diffs(old.get("flock"), new.get("flock"), flock_change))
    if old.get("arrangement") != new.get("arrangement"):
        diffs.append({"field": "arrangement", "from": copy.deepcopy(old.get("arrangement")),
                      "to": copy.deepcopy(new.get("arrangement"))})
    return diffs


_LOGGER = logging.getLogger(__name__)
_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.RLock] = {}


def _read_json(path: Path) -> Any:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise ProjectError(f"could not read project file: {exc}") from exc
    if len(raw) > _MAX_PROJECT_BYTES:
        raise ValidationError("project file exceeds the 2 MiB resource limit")
    def bad_constant(_value: str) -> None:
        raise ValueError("non-finite JSON number")
    try:
        return json.loads(raw.decode("utf-8"), parse_constant=bad_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValidationError("project file is not valid finite JSON") from exc


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        _LOGGER.debug("Directory fsync unavailable for %s", path, exc_info=True)


def _stage(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", prefix=f".{path.name}.{uuid.uuid4().hex}.", suffix=".tmp", dir=path.parent, delete=False) as stream:
            temp_path = Path(stream.name)
            stream.write(_json_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        return temp_path
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def _atomic_write(path: Path, value: Any) -> None:
    staged = _stage(path, value)
    try:
        os.replace(staged, path)
        _fsync_directory(path.parent)
    finally:
        staged.unlink(missing_ok=True)


@contextmanager
def _locked(projects_dir: Path, name: str) -> Iterator[None]:
    projects_dir.mkdir(parents=True, exist_ok=True)
    lock_path = projects_dir / f".{name}.lock"
    key = str(lock_path.resolve())
    with _LOCKS_GUARD:
        thread_lock = _THREAD_LOCKS.setdefault(key, threading.RLock())
    with thread_lock:
        with open(lock_path, "a+b") as lock_file:
            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b"\0")
                lock_file.flush()
            lock_file.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                lock_file.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _project_dir(projects_dir: Path, name: str) -> Path:
    name = _safe_name(name)
    base = projects_dir.resolve()
    target = projects_dir / name
    if target.exists() or target.is_symlink():
        resolved = target.resolve()
        if resolved.parent != base:
            _fail("project path must stay inside the projects directory")
    return target


def _load_unlocked(project_dir: Path) -> dict[str, Any]:
    path = project_dir / "project.json"
    if not path.is_file():
        raise NotFoundError(f"project not found: {project_dir.name}")
    try:
        project = validate_project(_read_json(path))
    except ValidationError:
        raise
    if project["name"] != project_dir.name:
        raise ValidationError("project name does not match its directory")
    project.setdefault("rev", 1)
    project.setdefault("_history_cursor", None)
    return project


def _next_history_id(project_dir: Path) -> int:
    history_dir = project_dir / "history"
    current = 0
    if history_dir.exists():
        for path in history_dir.glob("[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].json"):
            try:
                current = max(current, int(path.stem))
            except ValueError:
                continue
    return current + 1


def _commit(project_dir: Path, project: dict[str, Any], previous: dict[str, Any] | None,
            change_source: str = "agent", change_diff: list[dict[str, Any]] | None = None) -> tuple[dict[str, Any], int]:
    project_dir.mkdir(parents=True, exist_ok=True)
    project = validate_project(project)
    project["rev"] = 1 if previous is None else int(previous.get("rev", 1)) + 1
    project["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    project.setdefault("_history_cursor", None)
    history_target: Path | None = None
    history_temp: Path | None = None
    history_id: int | None = None
    if previous is not None:
        history_id = _next_history_id(project_dir)
        project["_history_cursor"] = history_id
    project = validate_project(project)
    if previous is not None and history_id is not None:
        history_dir = project_dir / "history"
        history_dir.mkdir(parents=True, exist_ok=True)
        history_target = history_dir / f"{history_id:08d}.json"
        snapshot = copy.deepcopy(previous)
        snapshot["_history_parent"] = previous.get("_history_cursor")
        snapshot["_history_change_source"] = change_source
        snapshot["_history_change_diff"] = copy.deepcopy(change_diff or [])
        snapshot["_history_to_rev"] = int(previous.get("rev", 1)) + 1
        if len(_json_bytes(snapshot)) > _MAX_PROJECT_BYTES:
            _fail("project history snapshot exceeds the 2 MiB encoded size limit")
        history_temp = _stage(history_target, snapshot)
    project_temp = None
    try:
        project_temp = _stage(project_dir / "project.json", project)
        if history_temp is not None and history_target is not None:
            os.replace(history_temp, history_target)
            history_temp = None
            _fsync_directory(history_target.parent)
        os.replace(project_temp, project_dir / "project.json")
        project_temp = None
        _fsync_directory(project_dir)
    except Exception:
        if history_target is not None and history_target.exists() and previous is not None:
            history_target.unlink(missing_ok=True)
        raise
    finally:
        if project_temp is not None:
            project_temp.unlink(missing_ok=True)
        if history_temp is not None:
            history_temp.unlink(missing_ok=True)
    return project, project["rev"]


def _emit_updated(project: dict[str, Any], source: str, tool: str | None, diff: list[dict[str, Any]]) -> None:
    events.emit("project.updated", {"name": project["name"], "rev": project["rev"], "source": source,
                                    "tool": tool, "diff": copy.deepcopy(diff)})


def load(project_dir: str | os.PathLike[str]) -> dict[str, Any]:
    directory = Path(project_dir)
    name = _safe_name(directory.name)
    with _locked(directory.parent, name):
        return copy.deepcopy(_load_unlocked(directory))


def rev(project_dir: str | os.PathLike[str]) -> int:
    return int(load(project_dir).get("rev", 1))


def save(project: Any, project_dir: str | os.PathLike[str]) -> int:
    normalized = validate_project(project)
    directory = Path(project_dir)
    name = _safe_name(directory.name)
    if normalized["name"] != name:
        _fail("project name must match the project directory")
    directory.parent.mkdir(parents=True, exist_ok=True)
    with _locked(directory.parent, name):
        previous = _load_unlocked(directory) if (directory / "project.json").is_file() else None
        old_for_diff = previous
        diff = diff_projects(old_for_diff, normalized)
        saved, new_rev = _commit(directory, normalized, previous, "agent", diff)
    _emit_updated(saved, "agent", None, diff)
    return new_rev


def _undo_directory(project_dir: Path, steps: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    directory = Path(project_dir)
    name = _safe_name(directory.name)
    steps = _integer(steps, "steps", 1, 128)
    with _locked(directory.parent, name):
        current = _load_unlocked(directory)
        cursor = current.get("_history_cursor")
        if cursor is None:
            raise ProjectError("nothing to undo")
        target = copy.deepcopy(current)
        history_dir = directory / "history"
        for _ in range(steps):
            if cursor is None:
                raise ProjectError("not enough project history to undo that many steps")
            snapshot_path = history_dir / f"{int(cursor):08d}.json"
            snapshot = _read_json(snapshot_path)
            if not isinstance(snapshot, dict) or snapshot.get("name") != name:
                raise ValidationError("project history snapshot is malformed")
            cursor = snapshot.get("_history_parent")
            for field in ("_history_parent", "_history_change_source", "_history_change_diff", "_history_to_rev"):
                snapshot.pop(field, None)
            target = validate_project(snapshot)
            target["_history_cursor"] = cursor
        # Undo deliberately does not append the current state: its cursor moves
        # to the restored snapshot's parent, so repeated undo walks backward.
        restored = validate_project(target)
        restored["rev"] = int(current.get("rev", 1)) + 1
        restored["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        restored = validate_project(restored)
        _atomic_write(directory / "project.json", restored)
        diff = diff_projects(current, restored)
    return restored, diff


def undo(project_dir: str | os.PathLike[str], steps: int = 1) -> dict[str, Any]:
    restored, diff = _undo_directory(Path(project_dir), steps)
    _emit_updated(restored, "agent", "rookery_undo", diff)
    return restored


def _set_fx_param(effect: dict[str, Any], param: Any, value: Any, where: str) -> None:
    if not isinstance(param, str) or not param or len(param) > 128 or param.strip() != param or any(ord(c) < 32 for c in param):
        _fail(f"{where} param must be a non-empty setting name")
    if param in {"type", "path", "params"}:
        _fail(f"{where} cannot edit {param!r} via fx_param")
    kind = effect.get("type")
    if kind == "vst3":
        numeric = _number(value, f"{where}.{param}", -1_000_000, 1_000_000)
        effect.setdefault("params", {})[param] = numeric
        return
    if not isinstance(kind, str) or kind not in _FX_PARAMS:
        _fail(f"{where} has unsupported effect type {kind!r}")
    canonical = "cutoff_hz" if kind in {"highpass", "lowpass"} and param == "cutoff_frequency_hz" else param
    if canonical not in _FX_PARAMS[kind]:
        _fail(f"{where}.{param} is not a supported {kind} parameter")
    low, high = _FX_PARAMS[kind][canonical]
    effect[canonical] = _number(value, f"{where}.{canonical}", low, high)


def _apply_edit(project: dict[str, Any], op: str, args: dict[str, Any],
                balancer: Callable[[dict[str, Any]], dict[str, Any]] | None = None) -> dict[str, Any]:
    result = copy.deepcopy(project)
    if op == "steps":
        allowed = {"track", "steps", "velocity"}
        if set(args) - allowed or "track" not in args or "steps" not in args:
            _fail("steps edit requires track and steps, with optional velocity")
        target = next((track for track in result["tracks"] if track["id"] == args["track"]), None)
        if target is None:
            raise NotFoundError(f"track not found: {args['track']}")
        target["steps"] = args["steps"]
        if "velocity" in args:
            target["velocity"] = args["velocity"]
    elif op == "track":
        allowed = {"action", "id", "kind", "source", "gain_db", "pan", "mute", "solo", "pitch", "steps", "velocity", "fx", "notes", "slices", "choke_group", "mode", "key_lock", "loop_bars", "duck", "role"}
        if set(args) - allowed or "action" not in args or "id" not in args:
            _fail("track edit requires action and id")
        action, track_id = args["action"], _safe_track_id(args["id"], "track id")
        existing = next((track for track in result["tracks"] if track["id"] == track_id), None)
        if action == "add":
            if existing is not None:
                _fail(f"track already exists: {track_id}")
            if len(result["tracks"]) >= _MAX_TRACKS:
                _fail(f"project cannot exceed {_MAX_TRACKS} tracks")
            track_data = {key: value for key, value in args.items() if key not in {"action", "id"}}
            if "kind" not in track_data or "source" not in track_data:
                _fail("adding a track requires kind and source")
            add_track_defaults(track_data, result)
            result["tracks"].append({"id": track_id, **track_data})
        elif action == "remove":
            if set(args) != {"action", "id"}:
                _fail("removing a track accepts only action and id")
            if existing is None:
                raise NotFoundError(f"track not found: {track_id}")
            result["tracks"] = [track for track in result["tracks"] if track["id"] != track_id]
            _clean_arrangement_mutes(result, removed_track=track_id)
        elif action == "set":
            if existing is None:
                raise NotFoundError(f"track not found: {track_id}")
            if set(args) == {"action", "id"}:
                _fail("setting a track requires at least one field")
            existing.update({key: value for key, value in args.items() if key not in {"action", "id"}})
        else:
            _fail("track action must be add, remove, or set")
    elif op == "mix":
        if set(args) != {"target", "fx"} or not isinstance(args["target"], str):
            _fail("mix edit requires target and fx")
        if args["target"] == "master":
            result["master"]["fx"] = args["fx"]
        else:
            target = next((track for track in result["tracks"] if track["id"] == args["target"]), None)
            if target is None:
                raise NotFoundError(f"track not found: {args['target']}")
            target["fx"] = args["fx"]
    elif op == "meta":
        if not args or set(args) - {"bpm", "bars", "swing", "humanize_ms", "key", "scale"}:
            _fail("meta edit accepts bpm, bars, swing, humanize_ms, key, and scale")
        if "bars" in args:
            new_bars = args["bars"]
            if isinstance(new_bars, bool) or not isinstance(new_bars, int) or new_bars not in (4, 8):
                _fail("bars must be 4 or 8")
            new_total = new_bars * 16
            if new_total < result["bars"] * 16:
                for track in result["tracks"]:
                    track["steps"] = track["steps"][:new_total]
                    track["velocity"] = track["velocity"][:new_total]
                    if "notes" in track:
                        track["notes"] = [
                            {**note, "len": min(note["len"], new_total)}
                            for note in track["notes"] if note["step"] < new_total
                        ]
        result.update(args)
    elif op == "clear":
        if set(args) - {"track"}:
            _fail("clear edit accepts only an optional track")
        track_id = args.get("track")
        targets = result["tracks"] if track_id is None else [
            track for track in result["tracks"] if track["id"] == track_id
        ]
        if track_id is not None and not targets:
            raise NotFoundError(f"track not found: {track_id}")
        changes = [(track, track["steps"]) for track in targets if any(c != "." for c in track["steps"])]
        if not changes:
            _fail("nothing to clear")
        total = result["bars"] * 16
        for track, _before in changes:
            track["steps"] = "." * total
    elif op == "fx_param":
        if set(args) != {"target", "index", "param", "value"}:
            _fail("fx_param edit requires target, index, param, and value")
        target_id = args["target"]
        if not isinstance(target_id, str):
            _fail("fx_param target must be a track id or master")
        chain = result["master"]["fx"] if target_id == "master" else next((track["fx"] for track in result["tracks"] if track["id"] == target_id), None)
        if chain is None:
            raise NotFoundError(f"track not found: {target_id}")
        index = _integer(args["index"], "fx index", 0, _MAX_FX - 1)
        if index >= len(chain):
            _fail("fx index is outside the effect chain")
        _set_fx_param(chain[index], args["param"], args["value"], f"{target_id}.fx[{index}]")
    elif op == "flock":
        try:
            result["flock"] = apply_flock_edit(result.get("flock"), args)
        except (TypeError, ValueError, KeyError) as exc:
            raise ValidationError(str(exc)) from exc
        _clean_arrangement_mutes(result)
    elif op == "arrange":
        if set(args) != {"sections"}:
            _fail("arrange edit requires sections (a list, or null to remove the arrangement)")
        if args["sections"] is None:
            result.pop("arrangement", None)
        else:
            result["arrangement"] = {"sections": args["sections"]}
    elif op == "balance":
        if args:
            _fail("balance op accepts no fields")
        if balancer is None:
            _fail("balance op requires a balancer; use rookery_apply through the service")
        result["mix_profile"] = "targets-v1"
        result = validate_project(result)
        measured = balancer(result)
        reference = measured.get("ref", "none")
        reference_id = reference.split(":", 1)[1] if ":" in reference else None
        for ident, item in measured.get("balance", {}).items():
            if ident == reference_id or item.get("lu_vs_kick") is None:
                continue
            lo, hi = item["target"]
            target_mid = (float(lo) + float(hi)) / 2
            if ident.startswith("bird:"):
                continue
            track = next((entry for entry in result["tracks"] if entry["id"] == ident), None)
            if track is None:
                continue
            current = float(track.get("gain_db", 0))
            gain = min(12.0, max(-60.0, round(current + target_mid - float(item["lu_vs_kick"]), 1)))
            result = _apply_edit(result, "track", {
                "action": "set", "id": ident, "gain_db": gain,
            })
    else:
        _fail("op must be steps, track, mix, meta, fx_param, clear, flock, arrange, or balance")
    return validate_project(result)


def _clean_arrangement_mutes(project: dict[str, Any], removed_track: str | None = None) -> None:
    arrangement = project.get("arrangement")
    if not arrangement:
        return
    valid_slots = {i for i, perch in enumerate(project.get("flock", {}).get("perches", [])) if perch is not None}
    tracks = {track["id"] for track in project.get("tracks", [])}
    for section in arrangement.get("sections", []):
        section["mute"] = [entry for entry in section.get("mute", [])
                           if (entry in tracks and entry != removed_track)
                           or (entry.startswith("bird:") and entry[5:].isdigit() and int(entry[5:]) in valid_slots)]
        for field in ("steps", "velocity", "notes"):
            overrides = section.get(field)
            if isinstance(overrides, dict):
                cleaned = {track_id: value for track_id, value in overrides.items()
                           if track_id in tracks and track_id != removed_track}
                if cleaned:
                    section[field] = cleaned
                else:
                    section.pop(field, None)
        songs = section.get("songs")
        if isinstance(songs, dict):
            cleaned_songs = {reference: song for reference, song in songs.items()
                             if reference.startswith("bird:") and reference[5:].isdigit()
                             and int(reference[5:]) in valid_slots}
            if cleaned_songs:
                section["songs"] = cleaned_songs
            else:
                section.pop("songs", None)


class ProjectStore:
    """Thread- and process-safe storage rooted at plugin data directory."""

    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root)
        self.projects_dir = self.root / "projects"

    def create(self, name: str, bpm: float = 90, bars: int = 4, genre: str | None = None,
               swing: float = 0, seed: int = 1337, source: str = "agent",
               tool: str | None = "rookery_new", key: str | None = None,
               scale: str | None = None) -> dict[str, Any]:
        if not isinstance(source, str) or source not in {"agent", "user"}:
            _fail("source must be agent or user")
        project = new_project(name, bpm=bpm, bars=bars, genre=genre, swing=swing, seed=seed,
                              key=key, scale=scale)
        project["mix_profile"] = "targets-v1"
        directory = _project_dir(self.projects_dir, project["name"])
        with _locked(self.projects_dir, project["name"]):
            if directory.exists() or directory.is_symlink():
                if (directory / "project.json").is_file():
                    existing = _load_unlocked(directory)
                    raise ConflictError(f"project already exists: {project['name']}", int(existing.get("rev", 1)))
                raise ConflictError(f"project directory already exists: {project['name']}", 0)
            saved, new_rev = _commit(directory, project, None)
            diff = diff_projects(None, saved)
        _emit_updated(saved, source, tool, diff)
        return {"project": expand_project(saved), "rev": new_rev, "diff": diff}

    def create_lifecycle(self, name: str | None = None, bpm: float = 90, bars: int = 4,
                         swing: float = 0, source_name: str | None = None) -> dict[str, Any]:
        if name is None:
            used = {row["name"] for row in self.list_projects()}
            index = 1
            while f"beat-{index}" in used:
                index += 1
            name = f"beat-{index}"
        name = _safe_name(name)
        if source_name is not None:
            source_name = _safe_name(source_name, "from")
            project = copy.deepcopy(self.read(source_name))
            project["name"] = name
            for field in ("rev", "updated_at", "_history_cursor", "_history_parent", "history"):
                project.pop(field, None)
        else:
            project = new_project(name, bpm=bpm, bars=bars, swing=swing)
            project["tracks"] = [
                {"id": "kick", "kind": "drum", "source": "factory:kick_punch", "steps": "."},
                {"id": "snare", "kind": "drum", "source": "factory:snare_snap", "steps": "."},
                {"id": "hat", "kind": "drum", "source": "factory:hat_tight", "steps": "."},
            ]
            project = validate_project(project)
        directory = _project_dir(self.projects_dir, name)
        with _locked(self.projects_dir, name):
            if directory.exists() or directory.is_symlink():
                raise ConflictError(f"project already exists: {name}", 0)
            saved, new_rev = _commit(directory, project, None)
        events.emit("project.created", {"name": name, **({"from": source_name} if source_name else {})})
        return {"project": expand_project(saved), "rev": new_rev, "render": None, "agent_editing": False}

    def rename(self, name: str, to: str, *, emit_event: bool = True) -> None:
        source_name, target_name = _safe_name(name), _safe_name(to, "to")
        if source_name == target_name:
            raise ConflictError(f"project already exists: {target_name}", 0)
        source = _project_dir(self.projects_dir, source_name)
        target = _project_dir(self.projects_dir, target_name)
        with _locked(self.projects_dir, source_name), _locked(self.projects_dir, target_name):
            current = _load_unlocked(source)
            if target.exists() or target.is_symlink():
                raise ConflictError(f"project already exists: {target_name}", 0)
            os.replace(source, target)
            try:
                current["name"] = target_name
                _atomic_write(target / "project.json", validate_project(current))
                history_dir = target / "history"
                if history_dir.is_dir():
                    for path in history_dir.glob("[0-9]*.json"):
                        snapshot = _read_json(path)
                        snapshot["name"] = target_name
                        _atomic_write(path, validate_project(snapshot))
            except Exception:
                os.replace(target, source)
                raise
        if emit_event:
            events.emit("project.renamed", {"from": source_name, "to": target_name})

    def delete(self, name: str, *, emit_event: bool = True) -> Path:
        selected = _safe_name(name)
        source = _project_dir(self.projects_dir, selected)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        trash = self.root / "trash" / f"{selected}-{stamp}"
        with _locked(self.projects_dir, selected):
            _load_unlocked(source)
            trash.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, trash)
        if emit_event:
            events.emit("project.deleted", {"name": selected})
        return trash

    def list_projects(self) -> list[dict[str, Any]]:
        if not self.projects_dir.exists():
            return []
        rows = []
        for directory in self.projects_dir.iterdir():
            if not directory.is_dir() or directory.name.startswith("."):
                continue
            try:
                project = load(directory)
            except (ProjectError, OSError):
                _LOGGER.debug("Skipping unreadable project directory %s", directory, exc_info=True)
                continue
            rows.append({"name": project["name"], "rev": int(project.get("rev", 1)),
                         "updated_at": project.get("updated_at", ""), "bpm": project["bpm"], "bars": project["bars"]})
        return sorted(rows, key=lambda row: (row["updated_at"], row["name"]), reverse=True)

    def _resolve_name(self, name: str | None) -> str:
        if name is not None:
            return _safe_name(name)
        projects = self.list_projects()
        if not projects:
            raise NotFoundError("no projects exist")
        return projects[0]["name"]

    def read(self, name: str | None = None) -> dict[str, Any]:
        selected = self._resolve_name(name)
        directory = _project_dir(self.projects_dir, selected)
        project = load(directory)
        project["rev"] = int(project.get("rev", 1))
        return expand_project(project)

    def edit(self, name: str, op: str, rev: int | None = None, source: str = "agent",
             tool: str | None = None, **args: Any) -> dict[str, Any]:
        selected = _safe_name(name)
        if not isinstance(source, str) or source not in {"agent", "user"}:
            # `source` is also a track field in the schema. Preserve the frozen
            # edit signature by treating a source identifier here as the track
            # source; event origin can be passed with source='agent' plus the
            # unambiguous `track_source` alias.
            if op == "track" and isinstance(source, str) and source.startswith(("factory:", "user:", "vst3:")) and "source" not in args and "track_source" not in args:
                args["source"] = source
                source = "agent"
            else:
                _fail("source must be agent or user")
        if op == "track" and "track_source" in args:
            if "source" in args:
                _fail("provide only one of source and track_source")
            args["source"] = args.pop("track_source")
        directory = _project_dir(self.projects_dir, selected)
        with _locked(self.projects_dir, selected):
            previous = _load_unlocked(directory)
            current_rev = int(previous.get("rev", 1))
            if rev is not None:
                expected = _integer(rev, "rev", 0, 2**63 - 1)
                if expected != current_rev:
                    raise ConflictError(f"stale project revision: expected {expected}, current revision is {current_rev}", current_rev)
            updated = _apply_edit(previous, op, args)
            diff = diff_projects(previous, updated, args.get("action") if op == "flock" else None)
            saved, new_rev = _commit(directory, updated, previous, source, diff)
        event_tool = tool
        if event_tool is None and source == "agent":
            event_tool = {"steps": "rookery_steps", "track": "rookery_track", "mix": "rookery_mix"}.get(op)
        _emit_updated(saved, source, event_tool, diff)
        return {"project": expand_project(saved), "rev": new_rev, "diff": diff}

    def apply_batch(self, name: str, ops: list[dict[str, Any]], rev: int | None = None,
                    source: str = "agent", tool: str | None = "rookery_apply",
                    balancer: Callable[[dict[str, Any]], dict[str, Any]] | None = None) -> dict[str, Any]:
        if not isinstance(source, str) or source not in {"agent", "user"}:
            _fail("source must be agent or user")
        if not isinstance(ops, list) or not 1 <= len(ops) <= 64:
            _fail("ops must contain 1 to 64 edits")
        selected = _safe_name(name)
        directory = _project_dir(self.projects_dir, selected)
        with _locked(self.projects_dir, selected):
            previous = _load_unlocked(directory)
            current_rev = int(previous.get("rev", 1))
            if rev is not None:
                expected = _integer(rev, "rev", 0, 2**63 - 1)
                if expected != current_rev:
                    raise ConflictError(f"stale project revision: expected {expected}, current revision is {current_rev}", current_rev)
            updated = copy.deepcopy(previous)
            for index, item in enumerate(ops):
                if not isinstance(item, dict) or not isinstance(item.get("op"), str):
                    _fail(f"ops[{index}] must be an object with an op")
                updated = _apply_edit(updated, item["op"],
                                      {key: value for key, value in item.items() if key != "op"},
                                      balancer=balancer)
            diff = diff_projects(previous, updated, None)
            saved, new_rev = _commit(directory, updated, previous, source, diff)
        _emit_updated(saved, source, tool, diff)
        return {"project": expand_project(saved), "rev": new_rev, "diff": diff}

    def undo(self, name: str | None = None, steps: int = 1, source: str = "agent",
             tool: str | None = "rookery_undo") -> dict[str, Any]:
        if not isinstance(source, str) or source not in {"agent", "user"}:
            _fail("source must be agent or user")
        selected = self._resolve_name(name)
        directory = _project_dir(self.projects_dir, selected)
        restored, diff = _undo_directory(directory, steps)
        _emit_updated(restored, source, tool, diff)
        return {"project": expand_project(restored), "rev": restored["rev"], "diff": diff}


__all__ = ["SCHEMA", "ProjectError", "ValidationError", "NotFoundError", "ConflictError", "ProjectStore",
           "new_project", "validate_project", "validate", "expand_project", "canonical_project",
           "canonical_json", "project_hash", "diff_projects", "load", "save", "rev", "undo"]
