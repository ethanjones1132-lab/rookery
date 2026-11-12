"""Deterministic melodic voices and weather for the Rookery Flock."""

from __future__ import annotations

import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np

from ..kit.factory import is_kick_source
from ..mix import mix_profile_enabled
import soundfile as sf
from scipy.signal import lfilter, resample_poly

from .model import active_combos, load_catalog, validate_flock


_CATALOG = load_catalog()
_BIRDS = {bird["id"]: bird for bird in [*_CATALOG["birds"], _CATALOG["corvus"]]}
_KEYS = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_KEY_PC = {key: index for index, key in enumerate(_KEYS)}
_KEY_PC.update({"Db": 1, "Eb": 3, "Gb": 6, "Ab": 8, "Bb": 10})
_ROLE_SETTINGS = {
    "bass": (-3.0, 0.0),
    "keys": (-6.0, -0.25),
    "pad": (-10.0, 0.6),
    "lead": (-4.0, 0.15),
    "arp": (-8.0, 0.35),
    "call": (-4.0, -0.1),
}
# Measured target profile. Legacy projects retain _ROLE_SETTINGS until they
# explicitly opt into the target profile, preserving their PCM.
_CALIBRATED_ROLE_SETTINGS = {
    "bass": (3.7, 0.0),
    "keys": (-2.5, -0.25),
    "pad": (13.1, 0.6),
    "lead": (4.1, 0.15),
    "arp": (19.5, 0.35),
    "call": (0.9, -0.1),
}
_ROLE_BASE_MIDI = {"bass": 36, "keys": 60, "pad": 48, "lead": 72, "arp": 84, "call": 72}
_ROMAN = _CATALOG["chordTables"]["romanDegrees"]
_COMBOS = {combo["id"]: combo for combo in _CATALOG["combos"]}
_VOICE_SAMPLE_ROOT = Path(__file__).with_name("voices")
_VOICE_SAMPLE_CACHE: dict[tuple[str, int], np.ndarray] = {}


def _seed_int(seed: Any, *labels: Any) -> int:
    """Make a process-independent local RNG seed without Python's salted hash."""
    payload = json.dumps([seed, *labels], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big")


def _rng(seed: Any, *labels: Any) -> np.random.Generator:
    return np.random.default_rng(_seed_int(seed, *labels))


def _patterns(value: Any, size: int, default: str = ".") -> str:
    text = str(value or default) or default
    return (text * ((size + len(text) - 1) // len(text)))[:size]


def _audible_tracks(project: dict[str, Any]) -> list[dict[str, Any]]:
    tracks = list(project.get("tracks", []))
    audible = [track for track in tracks if not track.get("mute", False)]
    if any(track.get("solo", False) for track in tracks):
        audible = [track for track in audible if track.get("solo", False)]
    return audible


def _kick_sample_positions(project: dict[str, Any], sample_rate: int) -> list[int]:
    """List distinct audible kick onsets using render.py's exact sample timing."""
    bpm = float(project["bpm"])
    bars = int(project["bars"])
    steps_per_bar = int(project.get("steps_per_bar", 16))
    if bpm <= 0 or not math.isfinite(bpm) or bars not in (4, 8) or steps_per_bar != 16:
        return []
    total = round(bars * 4 * 60 / bpm * sample_rate)
    n_steps = bars * steps_per_bar
    step_len = total / n_steps
    swing = float(project.get("swing", 0.0))
    positions: set[int] = set()
    for track in _audible_tracks(project):
        if track.get("kind", "drum") != "drum" or not is_kick_source(str(track.get("source", "factory:kick_boom"))):
            continue
        steps = _patterns(track.get("steps", "x"), n_steps)
        velocities = track.get("velocity", [1.0]) or [1.0]
        for index, symbol in enumerate(steps):
            velocity = float(velocities[index % len(velocities)])
            if symbol != "x" or velocity <= 0:
                continue
            start = round(index * step_len)
            if index % 2:
                start += round(swing * step_len * 0.5)
            positions.add(start % total)
    return sorted(positions)


def _fold_midi(note: int, role: str) -> int:
    low, high = _CATALOG["registers"][role]
    candidates = [value for value in range(low, high + 1) if value % 12 == note % 12]
    if candidates:
        return min(candidates, key=lambda value: abs(value - note))
    # The call lane is narrower than an octave. If its desired scale tone does
    # not occur there, keep the note inside the band rather than leaking lanes.
    return min(range(low, high + 1), key=lambda value: abs(value - note))


def _resolve_midi(flock: dict[str, Any], role: str, degree: int, octave: int, bar: int) -> int:
    scale = _CATALOG["scales"][flock["scale"]]["semitones"]
    n_scale = len(scale)
    chord_degree = _ROMAN[flock["progression"][bar % len(flock["progression"])]]
    position = chord_degree + int(degree)
    scale_index, octave_wrap = position % n_scale, position // n_scale
    raw = _ROLE_BASE_MIDI[role] + _KEY_PC[flock["key"]] + scale[scale_index] + 12 * (int(octave) + octave_wrap)
    return _fold_midi(raw, role)


def _bar_root_pc(flock: dict[str, Any], bar: int) -> int:
    scale = _CATALOG["scales"][flock["scale"]]["semitones"]
    chord_degree = _ROMAN[flock["progression"][bar % len(flock["progression"])]]
    return (_KEY_PC[flock["key"]] + scale[chord_degree % len(scale)]) % 12


def _active_perches(flock: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    entries = [(index, perch) for index, perch in enumerate(flock["perches"])
               if perch is not None and not perch["mute"]]
    soloed = [entry for entry in entries if entry[1]["solo"]]
    return soloed or entries


def _plan(project: dict[str, Any], sample_rate: int = 44100) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    sr = int(sample_rate)
    if sr < 8000 or sr > 192000:
        raise ValueError("sample_rate must be between 8000 and 192000")
    kick_samples = _kick_sample_positions(project, sr)
    metadata = {
        "flock_events": {},
        "kick_onsets": [sample / sr for sample in kick_samples],
        "flock_active_combos": [],
    }
    if "flock" not in project:
        return metadata, []

    flock = validate_flock(project["flock"])
    combos = active_combos(flock)
    metadata["flock_active_combos"] = list(combos)
    if not combos and not flock["perches"]:
        return metadata, []

    bpm = float(project["bpm"])
    bars = int(project["bars"])
    n_steps = bars * 16
    total = round(bars * 4 * 60 / bpm * sr)
    step_len = total / n_steps
    swing = float(project.get("swing", 0.0))
    seed = project.get("seed", 1337)
    active = _active_perches(flock)
    bass_present = any(_BIRDS[perch["bird"]]["role"] == "bass" for _, perch in active)
    role_ordinals: dict[str, int] = {}
    slot_mix: dict[str, tuple[float, float]] = {}
    # Require the explicit target-profile marker; legacy genre metadata alone
    # must not change the frozen Flock trims.
    has_mix_targets = mix_profile_enabled(project)
    role_settings = _CALIBRATED_ROLE_SETTINGS if has_mix_targets else _ROLE_SETTINGS
    for _, perch in active:
        bird = _BIRDS[perch["bird"]]
        role = bird["role"]
        ordinal = role_ordinals.get(role, 0)
        role_ordinals[role] = ordinal + 1
        gain_db, pan = role_settings.get(role, (0.0, 0.0))
        if ordinal:
            gain_db -= 2.0
            pan = -pan
            if role == "pad":
                pan = 0.0
        gain_db += float(perch.get("gain_db", 0.0))
        pan = min(1.0, max(-1.0, pan + float(perch.get("pan", 0.0))))
        slot_mix[perch["bird"]] = (10.0 ** (gain_db / 20.0), pan)

    overrides: dict[str, str] = {}
    extra_layers: list[str] = []
    for combo_id in combos:
        bonus = _COMBOS[combo_id].get("bonus", {})
        overrides.update(bonus.get("song_overrides", {}))
        if bonus.get("extra_layer"):
            extra_layers.append(bonus["extra_layer"])

    planned: list[dict[str, Any]] = []

    def add_event(bird_id: str, role: str, voice: str, bar: int, step: int, length: int,
                  midi: int, velocity: float, *, layer: str = "voice", humanize: bool = True,
                  deg: int | None = None, octave: int | None = None) -> None:
        if velocity <= 0:
            return
        global_step = bar * 16 + int(step)
        start = round(global_step * step_len)
        if global_step % 2:
            start = (start + round(swing * step_len * 0.5)) % total
        duration = max(1, round(int(length) * step_len))
        if humanize:
            local = _rng(seed, "event", bird_id, bar, step, midi, layer)
            velocity *= float(local.uniform(0.985, 1.015))
            # Optional seeded timing humanization; bounded by the musical contract.
            humanize_ms = min(6.0, max(0.0, float(project.get("humanize_ms", 0.0))))
            if humanize_ms:
                jitter = float(local.uniform(-humanize_ms, humanize_ms))
                start = int(min(total - 1, max(0, start + round(jitter * sr / 1000.0))))
        if velocity <= 0:
            return
        item = {
            "bird_id": bird_id, "role": role, "voice": voice, "sample": start,
            "voice_mode": flock.get("voices", "samples"),
            "duration_samples": duration, "midi": int(midi), "vel": float(velocity),
            "bar": int(bar), "step": int(step), "length_steps": int(length), "layer": layer,
            "deg": None if deg is None else int(deg),
            "oct": None if octave is None else int(octave),
            "gain": slot_mix.get(bird_id, (1.0, 0.0))[0],
            "pan": slot_mix.get(bird_id, (1.0, 0.0))[1],
            "seed": _seed_int(seed, "voice", bird_id, bar, step, midi, layer),
        }
        planned.append(item)

    for _, perch in active:
        bird_id = perch["bird"]
        if bird_id == "corvus":
            continue
        bird = _BIRDS[bird_id]
        role, voice = bird["role"], bird["voice"]
        song = overrides.get(bird_id, perch["song"])
        patterns = bird["songs"].get(song)
        if song == "D":
            patterns = _CATALOG["comboSongs"].get(bird_id, {}).get("D")
        if not patterns:
            continue
        for bar in range(bars):
            response_event_used = False
            for event_index, event in enumerate(patterns):
                # New catalog motifs explicitly assign each event to one of the
                # four bars. Legacy one-bar catalogs continue to repeat safely.
                if ("bar" in event and int(event["bar"]) != bar % 4
                        and not ("call_response" in extra_layers and bird_id in {"echo", "wren_not"})):
                    continue
                # Back and Forth gives each singer one answer in alternating bars.
                if "call_response" in extra_layers and bird_id in {"echo", "wren_not"}:
                    expected_parity = 0 if bird_id == "echo" else 1
                    if bar % 2 != expected_parity:
                        continue
                    if response_event_used:
                        continue
                step = int(event["step"])
                midi = _resolve_midi(flock, role, int(event["deg"]), int(event.get("oct", 0)), bar)
                add_event(bird_id, role, voice, bar, step, int(event["len"]), midi,
                          float(event["vel"]), layer=f"song:{song}:{event_index}",
                          deg=int(event["deg"]), octave=int(event.get("oct", 0)))
                if "call_response" in extra_layers and bird_id in {"echo", "wren_not"}:
                    response_event_used = True

    # Keys and pads voice a full diatonic triad on every actual chord attack.
    # Attacks from simultaneous birds of one role are grouped so a shared tone
    # is generated once, never tripled.
    seventh_modes = _CATALOG["chordTables"]["extensions"]["seventhModes"]
    for role in ("keys", "pad"):
        role_events = [event for event in planned
                       if event["role"] == role and event["layer"].startswith("song:")
                       and event["deg"] in {0, 2, 4}]
        attacks: dict[tuple[int, int], list[dict[str, Any]]] = {}
        bar_attacks: dict[int, list[dict[str, Any]]] = {}
        for event in role_events:
            bar_attacks.setdefault(event["bar"], []).append(event)
            if event["step"] % 4 == 0:
                attacks.setdefault((event["bar"], event["step"]), []).append(event)
        for bar, events in bar_attacks.items():
            if not any(key[0] == bar for key in attacks):
                first = min(events, key=lambda event: (event["step"], event["bird_id"]))
                attacks[(bar, first["step"])] = [first]
        for (bar, step), group in sorted(attacks.items()):
            source = max(group, key=lambda event: (event["vel"], event["bird_id"]))
            present = {event["midi"] for event in planned
                       if event["role"] == role and event["bar"] == bar and event["step"] == step}
            for chord_tone in (0, 2, 4):
                midi = _resolve_midi(flock, role, chord_tone, int(source["oct"] or 0), bar)
                if midi not in present:
                    add_event(source["bird_id"], role, source["voice"], bar, step,
                              source["length_steps"], midi, source["vel"] * 0.45,
                              layer="auto_chord_tone", humanize=False)
                    present.add(midi)
            earliest = min(events, key=lambda event: (event["step"], event["bird_id"]))
            same_role_birds = sum(_BIRDS[perch["bird"]]["role"] == role for _, perch in active)
            song_has_seventh = any(
                event["role"] == role and event["layer"].startswith("song:")
                and event.get("deg") is not None and event["deg"] % 7 == 6
                for event in planned
            )
            seventh_allowed = (same_role_birds == 1 and not song_has_seventh
                               and (not bass_present or "parliament" in combos))
            if seventh_allowed and flock["scale"] in seventh_modes and step == earliest["step"]:
                seventh = _resolve_midi(flock, role, 6, int(source["oct"] or 0), bar)
                if seventh not in present:
                    seventh_step = step if len(active) == 1 else min(15, step + 1)
                    seventh_length = source["length_steps"] if len(active) == 1 else 1
                    add_event(source["bird_id"], role, source["voice"], bar, seventh_step,
                              seventh_length, seventh, source["vel"] * 0.5,
                              layer="auto_seventh", humanize=False)

    # Catalog extra_layer IDs drive the combo's additional audio behavior.
    if "harmony_chorus" in extra_layers:
        lead_events = [event for event in planned if event["role"] == "lead"]
        call_bird = next((perch["bird"] for _, perch in active if _BIRDS[perch["bird"]]["role"] == "call"), None)
        if call_bird:
            call_voice = _BIRDS[call_bird]["voice"]
            for event in lead_events:
                target_pc = (event["midi"] - _KEY_PC[flock["key"]]) % 12
                scale = _CATALOG["scales"][flock["scale"]]["semitones"]
                source_degree = next((i for i, semitone in enumerate(scale) if semitone == target_pc), None)
                if source_degree is None:
                    continue
                target_degree = (source_degree - 2) % len(scale)
                call_pc = (_KEY_PC[flock["key"]] + scale[target_degree]) % 12
                low, high = _CATALOG["registers"]["call"]
                candidates = [note for note in range(low, high + 1)
                              if note % 12 == call_pc and note < event["midi"]]
                if not candidates:
                    candidates = [note for note in range(low, high + 1) if note % 12 == call_pc]
                if not candidates:
                    midi = _resolve_midi(flock, "call", 0, 0, event["bar"])
                else:
                    midi = max(candidates)
                add_event(call_bird, "call", call_voice, event["bar"], event["step"],
                          event["length_steps"], midi, event["vel"] * 0.28,
                          layer="harmony_chorus", humanize=False)

    if "bell_sparkle" in extra_layers:
        for event in list(planned):
            if event["bird_id"] != "glint":
                continue
            upper = event["midi"] + 12
            sparkle_midi = upper if upper <= _CATALOG["registers"]["lead"][1] else event["midi"]
            add_event("glint", "lead", "bell", event["bar"], event["step"],
                      max(1, round(event["length_steps"] * 0.5)), sparkle_midi,
                      event["vel"] * 0.2, layer="bell_sparkle", humanize=False)

    if "sub_octave_drop" in extra_layers:
        bassers = [perch["bird"] for _, perch in active if perch["bird"] in {"bramble", "cinder"}]
        if len(bassers) == 2:
            # The extra_layer implements the alternating-bar exchange.
            for event in planned:
                if event["bird_id"] in bassers and event["role"] == "bass":
                    expected = 0 if event["bird_id"] == "bramble" else 1
                    if event["bar"] % 2 != expected:
                        event["skip_dsp"] = True
            last_bar = bars - 1
            last_bird = "bramble" if last_bar % 2 == 0 else "cinder"
            candidates = [event for event in planned if event["bird_id"] == last_bird
                          and event["bar"] == last_bar and event["layer"].startswith("song:")]
            source = max(candidates, key=lambda event: event["midi"]) if candidates else None
            low_note: int | None = None
            velocity = 0.4 if source is None else float(source["vel"])
            if source is not None and 28 <= source["midi"] - 12 <= 48:
                low_note = source["midi"] - 12
            if low_note is None:
                # Register priority: use the lowest in-key octave of the bar root.
                root_pc = _bar_root_pc(flock, last_bar)
                legal = [note for note in range(28, 49) if note % 12 == root_pc]
                low_note = legal[0] if legal else 28
            add_event(last_bird, "bass", _BIRDS[last_bird]["voice"], last_bar, 14, 2,
                      low_note, velocity * 0.52, layer="sub_octave_drop", humanize=False)

    planned.sort(key=lambda event: (event["sample"], event["bird_id"], event["midi"], event["layer"]))
    public: dict[str, list[dict[str, Any]]] = {}
    for event in planned:
        if event.get("skip_dsp"):
            continue
        entry = {
            "t": event["sample"] / sr,
            "len": (event["duration_samples"] + _voice_release_samples(event["voice"], sr)) / sr,
            "midi": int(event["midi"]),
            "vel": float(event["vel"]),
        }
        public.setdefault(event["bird_id"], []).append(entry)
    metadata["flock_events"] = public
    return metadata, [event for event in planned if not event.get("skip_dsp")]


def compile_events(project: dict[str, Any], sample_rate: int = 44100) -> dict[str, Any]:
    """Return the audible note planner output and rendered kick onsets."""
    metadata, _ = _plan(project, sample_rate)
    return metadata


def _phase(freq: np.ndarray, sample_rate: int, phase: float) -> np.ndarray:
    return phase + 2.0 * np.pi * np.cumsum(freq, dtype=np.float64) / sample_rate


def _periodic_filter(data: np.ndarray, numerator: list[float], denominator: list[float]) -> np.ndarray:
    """Filter repeated loop material so IIR state at the seam is already settled."""
    repeated = np.concatenate((data, data), axis=0)
    return lfilter(numerator, denominator, repeated, axis=0)[len(data):]


def _partials(freq: np.ndarray, phase: np.ndarray, sample_rate: int,
              harmonics: list[tuple[int, float]]) -> np.ndarray:
    output = np.zeros(len(freq), dtype=np.float64)
    max_freq = float(np.max(freq)) if len(freq) else 0.0
    for harmonic, amplitude in harmonics:
        if harmonic * max_freq >= sample_rate * 0.48:
            continue
        output += amplitude * np.sin(phase * harmonic)
    return output


def _voice_release_seconds(voice: str) -> float:
    """The single source of truth for each voice's audible release tail."""
    if voice in {"softPad", "triangleChoir"}:
        return 0.22
    if voice in {"sawPluck", "squarePluck", "bell", "epiano", "formant", "whistle"}:
        return 0.10
    return 0.12


def _voice_release_samples(voice: str, sample_rate: int) -> int:
    return max(1, round(int(sample_rate) * _voice_release_seconds(voice)))


def _note_signal(event: dict[str, Any], sample_rate: int) -> np.ndarray:
    sr = sample_rate
    sustain = max(1, int(event["duration_samples"]))
    voice = event["voice"]
    release = _voice_release_samples(voice, sr)
    count = sustain + release
    bird_id = event.get("bird_id")
    if (bird_id and event.get("voice_mode", "samples") != "synth"
            and _VOICE_SAMPLE_ROOT.is_dir() and (_VOICE_SAMPLE_ROOT / bird_id).is_dir()):
        return _sample_note_signal(event, sr, count, sustain, release)
    time = np.arange(count, dtype=np.float64) / sr
    base = 440.0 * 2.0 ** ((int(event["midi"]) - 69) / 12.0)
    rng = np.random.default_rng(int(event["seed"]))
    phase0 = float(rng.uniform(0.0, 2.0 * np.pi))
    previous = event.get("previous_midi")

    if voice == "sub":
        glide = min(count, max(1, round(sr * 0.028)))
        freq = np.full(count, base, dtype=np.float64)
        if previous is not None:
            start_hz = 440.0 * 2.0 ** ((int(previous) - 69) / 12.0)
            freq[:glide] = np.linspace(start_hz, base, glide, endpoint=True)
        phase = _phase(freq, sr, phase0)
        signal = np.sin(phase) * 0.8 + np.sin(phase * 2.0) * 0.16
        signal = np.tanh(signal * 1.2) / 1.2
        attack, tau = 0.012, 0.45
    elif voice == "808":
        pitch_drop = min(count, max(1, round(sr * 0.035)))
        freq = np.full(count, base, dtype=np.float64)
        freq[:pitch_drop] = np.geomspace(base * 2.1, base, pitch_drop)
        if previous is not None:
            start_hz = 440.0 * 2.0 ** ((int(previous) - 69) / 12.0)
            glide = min(count, max(1, round(sr * 0.018)))
            freq[:glide] = np.geomspace(start_hz, freq[glide - 1], glide)
        phase = _phase(freq, sr, phase0)
        signal = np.sin(phase)
        attack, tau = 0.003, max(0.08, sustain / sr * 1.5)
    elif voice == "epiano":
        phase = _phase(np.full(count, base), sr, phase0)
        mod = np.sin(phase * 2.0) * (1.2 * np.exp(-time * 5.5))
        signal = np.sin(phase + mod) + 0.17 * np.sin(phase * 2.0 + 0.4)
        signal *= 0.88 + 0.12 * np.sin(2 * np.pi * 4.2 * time)
        attack, tau = 0.009, 0.48
    elif voice == "organ":
        phase = _phase(np.full(count, base), sr, phase0)
        signal = _partials(np.full(count, base), phase, sr, [(1, 1.0), (2, 0.55), (3, 0.22)])
        signal *= 0.9 + 0.1 * np.sin(2 * np.pi * 0.7 * time)
        attack, tau = 0.035, 3.0
    elif voice == "squareLead":
        glide = min(count, max(1, round(sr * 0.045)))
        freq = np.full(count, base, dtype=np.float64)
        if previous is not None:
            start_hz = 440.0 * 2.0 ** ((int(previous) - 69) / 12.0)
            freq[:glide] = np.geomspace(start_hz, base, glide)
        vibrato = np.zeros(count)
        delayed = np.maximum(0.0, time - 0.11)
        vibrato = np.sin(2 * np.pi * 5.2 * delayed) * np.minimum(1.0, delayed / 0.1) * 0.003
        freq *= 2.0 ** vibrato
        phase = _phase(freq, sr, phase0)
        signal = _partials(freq, phase, sr, [(1, 1.0), (3, 1 / 3), (5, 1 / 5), (7, 1 / 7)])
        attack, tau = 0.008, 2.0
    elif voice == "bell":
        phase = _phase(np.full(count, base), sr, phase0)
        mod = np.sin(phase * 3.5) * (2.0 * np.exp(-time * 14))
        signal = np.sin(phase + mod) + 0.18 * np.sin(phase * 2.71)
        attack, tau = 0.001, 0.24
    elif voice == "softPad":
        phase = _phase(np.full(count, base), sr, phase0)
        signal = _partials(np.full(count, base), phase, sr,
                           [(1, 1.0), (2, 0.48), (3, 0.25), (4, 0.13), (5, 0.08)])
        signal += 0.12 * np.sin(phase * (1.005 + 0.003 * np.sin(2 * np.pi * 0.13 * time)))
        cutoff = math.exp(-2.0 * math.pi * 1200.0 / sr)
        signal = lfilter([1.0 - cutoff], [1.0, -cutoff], signal)
        attack, tau = 0.38, 4.0
    elif voice == "triangleChoir":
        phase = _phase(np.full(count, base), sr, phase0)
        opened = 1.0 - np.exp(-time / 0.55)
        signal = np.sin(phase) + opened * (-np.sin(phase * 3.0) / 9.0 +
                                           np.sin(phase * 5.0) / 25.0 - np.sin(phase * 7.0) / 49.0)
        signal += 0.2 * np.sin(phase * 1.003 + 0.3)
        # A real filter swell: blend three fixed low-passes, vectorized end-to-end.
        filtered = []
        for cutoff_hz in (480.0, 1400.0, 3400.0):
            alpha = math.exp(-2.0 * math.pi * cutoff_hz / sr)
            filtered.append(lfilter([1.0 - alpha], [1.0, -alpha], signal))
        dark, middle, bright = filtered
        signal = dark + (middle - dark) * opened + (bright - middle) * opened * opened
        attack, tau = 0.32, 3.5
    elif voice in {"sawPluck", "squarePluck"}:
        phase = _phase(np.full(count, base), sr, phase0)
        if voice == "sawPluck":
            signal = _partials(np.full(count, base), phase, sr,
                               [(h, 1.0 / h) for h in range(1, 10)])
            tau = 0.075
        else:
            signal = _partials(np.full(count, base), phase, sr,
                               [(h, 1.0 / h) for h in (1, 3, 5, 7, 9)])
            signal += 0.32 * np.sin(phase * 2.0)
            tau = 0.095
        attack = 0.001
    elif voice == "formant":
        freq = np.full(count, base)
        phase = _phase(freq, sr, phase0)
        signal = np.zeros(count, dtype=np.float64)
        for harmonic in range(1, min(48, int(sr * 0.45 / max(base, 1.0)))):
            hz = harmonic * base
            weight = math.exp(-0.5 * ((hz - 720.0) / 230.0) ** 2)
            weight += 0.85 * math.exp(-0.5 * ((hz - 1180.0) / 310.0) ** 2)
            signal += weight / harmonic * np.sin(phase * harmonic)
        attack, tau = 0.018, 0.32
    elif voice == "whistle":
        phase = _phase(np.full(count, base), sr, phase0)
        signal = np.sin(phase)
        breath = rng.standard_normal(count)
        breath = lfilter([1.0, -0.92], [1.0], breath)
        signal += breath * np.exp(-time / 0.035) * 0.045
        attack, tau = 0.012, 0.65
    else:
        # Corvus is a bus effect and never reaches the note synthesizer.
        return np.zeros(count, dtype=np.float64)

    attack_samples = max(1, round(sr * attack))
    envelope = np.ones(count, dtype=np.float64)
    envelope[:min(count, attack_samples)] = np.linspace(0.0, 1.0, min(count, attack_samples), endpoint=True)
    if voice in {"sub", "808", "epiano", "bell", "sawPluck", "squarePluck", "formant", "whistle"}:
        envelope[:sustain] *= np.exp(-time[:sustain] / max(tau, 1e-4))
    if count > sustain:
        release_curve = np.exp(-np.arange(count - sustain, dtype=np.float64) / max(1, release * 0.42))
        envelope[sustain:] = envelope[sustain - 1] * release_curve
    signal *= envelope
    signal *= float(event["vel"])
    if event["role"] == "pad":
        alpha = math.exp(-2.0 * math.pi * 180.0 / sr)
        signal = lfilter([alpha, -alpha], [1.0, -alpha], signal)
    peak = float(np.max(np.abs(signal))) if len(signal) else 0.0
    if peak > 0:
        signal = signal / max(1.8, peak * 1.8)
    # The release curve is exponential, so end it with a short raised-cosine
    # fade that reaches exact zero (including the pad's high-pass tail).
    fade = min(count, max(8, round(sr * 0.018)))
    terminal = 0.5 * (1.0 + np.cos(np.linspace(0.0, np.pi, fade)))
    signal[-fade:] *= terminal
    return signal


def _sample_note_signal(event: dict[str, Any], sample_rate: int, count: int,
                        sustain: int, release: int) -> np.ndarray:
    """Load the closest baked root, band-limited repitch, and apply note gate."""
    bird_id = str(event["bird_id"])
    folder = _VOICE_SAMPLE_ROOT / bird_id
    roots = sorted(int(path.stem.split("_", 1)[0]) for path in folder.glob("*.flac")
                   if path.stem.split("_", 1)[0].isdigit())
    if not roots:
        return _note_signal_synth(event, sample_rate)
    midi = int(event["midi"])
    root = min(roots, key=lambda note: (abs(note - midi), note))
    key = (bird_id, root)
    sample = _VOICE_SAMPLE_CACHE.get(key)
    if sample is None:
        path = folder / f"{root}.flac"
        if not path.is_file():
            return _note_signal_synth(event, sample_rate)
        sample, source_rate = sf.read(str(path), dtype="float32", always_2d=True)
        sample = sample.mean(axis=1, dtype=np.float64).astype(np.float32)
        if source_rate != sample_rate:
            divisor = math.gcd(int(source_rate), int(sample_rate))
            sample = resample_poly(sample, sample_rate // divisor, source_rate // divisor).astype(np.float32)
        _VOICE_SAMPLE_CACHE[key] = sample
    semitones = midi - root
    ratio = 2.0 ** (semitones / 12.0)
    pitch_fraction = Fraction(ratio).limit_denominator(100)
    pitched = resample_poly(sample, pitch_fraction.denominator,
                            pitch_fraction.numerator).astype(np.float64)
    result = np.zeros(count, dtype=np.float64)
    take = min(count, len(pitched))
    result[:take] = pitched[:take]
    # Gate at the requested note length, preserving the sample's baked timbre
    # while using the same role-specific release duration as the synth fallback.
    if release and sustain < len(result):
        release_frames = min(release, len(result) - sustain)
        result[sustain:sustain + release_frames] *= np.linspace(
            1.0, 0.0, release_frames, endpoint=True
        )
    if len(result):
        result[-1] = 0.0
    result *= float(event["vel"])
    if event["role"] == "pad":
        # Keep the sampled Serum path in the same low-end lane as the synth
        # fallback.  Fixed-coefficient IIR filtering is deterministic here.
        alpha = math.exp(-2.0 * math.pi * 180.0 / sample_rate)
        result = lfilter([alpha, -alpha], [1.0, -alpha], result)
    peak = float(np.max(np.abs(result)))
    if peak > 1.0:
        result /= peak
    return result


def _note_signal_synth(event: dict[str, Any], sample_rate: int) -> np.ndarray:
    """Call the built-in voice path without consulting bundled sample files."""
    saved = event.pop("_force_synth", None)
    try:
        bird_id = event.pop("bird_id", None)
        return _note_signal(event, sample_rate)
    finally:
        if bird_id is not None:
            event["bird_id"] = bird_id
        if saved is not None:
            event["_force_synth"] = saved


def _duck_envelope(total: int, sample_rate: int, onsets: list[int]) -> np.ndarray:
    envelope = np.ones(total, dtype=np.float64)
    if not onsets:
        return envelope
    duck = 10.0 ** (-3.0 / 20.0)
    attack = max(1, round(sample_rate * 0.002))
    release = max(1, round(sample_rate * 0.08))
    # After 40 release time constants the release expression rounds to exactly
    # 1.0 in float64. Only touch this short window rather than rebuilding a
    # full-song curve for every kick.
    window = min(total, attack + math.ceil(40 * release))
    distance = np.arange(window, dtype=np.int64)
    curve = np.ones(window, dtype=np.float64)
    attacking = distance < attack
    curve[attacking] = 1.0 - (1.0 - duck) * distance[attacking] / attack
    releasing = ~attacking
    elapsed = distance[releasing] - attack
    curve[releasing] = duck + (1.0 - duck) * (1.0 - np.exp(-elapsed / release))
    for onset in onsets:
        start = int(onset) % total
        first = min(window, total - start)
        view = envelope[start:start + first]
        np.minimum(view, curve[:first], out=view)
        if first < window:
            view = envelope[:window - first]
            np.minimum(view, curve[first:], out=view)
    return envelope


def _pad_stereo(signal: np.ndarray, event: dict[str, Any], sample_rate: int) -> np.ndarray:
    """Spread one pad voice across a deterministic, decorrelated stereo field."""
    sr = int(sample_rate)
    pan = min(1.0, max(-1.0, float(event["pan"])))
    width = 0.6
    left_pan = max(-1.0, pan - width)
    right_pan = min(1.0, pan + width)
    left_gain = math.cos((left_pan + 1.0) * (math.pi / 4.0))
    right_gain = math.sin((right_pan + 1.0) * (math.pi / 4.0))
    # A short, seed-picked Haas delay decorrelates the sides without any host clock.
    delay = max(1, round(sr * (0.005 + 0.0015 * (int(event["seed"]) % 4))))
    right = np.zeros_like(signal)
    if delay < len(signal):
        right[delay:] = signal[:-delay]
    stereo = np.stack((signal * left_gain, right * right_gain), axis=1)
    stereo *= float(event["gain"])
    fade = min(len(stereo), max(8, round(sr * 0.02)))
    if fade:
        terminal = 0.5 * (1.0 + np.cos(np.linspace(0.0, np.pi, fade)))
        stereo[-fade:] *= terminal[:, None]
    return stereo


def _insert_stereo(buffer: np.ndarray, stereo: np.ndarray, event: dict[str, Any],
                   duck: np.ndarray | None = None) -> None:
    total = len(buffer)
    offset = 0
    start = int(event["sample"])
    while offset < len(stereo):
        position = (start + offset) % total
        count = min(len(stereo) - offset, total - position)
        block = stereo[offset:offset + count]
        if duck is not None:
            block = block * duck[position:position + count, None]
        buffer[position:position + count] += block
        offset += count


def _insert_mono(buffer: np.ndarray, signal: np.ndarray, event: dict[str, Any], duck: np.ndarray | None = None) -> None:
    total = len(buffer)
    pan = min(1.0, max(-1.0, float(event["pan"])))
    angle = (pan + 1.0) * (math.pi / 4.0)
    left = math.cos(angle) * float(event["gain"])
    right = math.sin(angle) * float(event["gain"])
    offset = 0
    start = int(event["sample"])
    while offset < len(signal):
        position = (start + offset) % total
        count = min(len(signal) - offset, total - position)
        block = signal[offset:offset + count]
        if duck is not None:
            block = block * duck[position:position + count]
        buffer[position:position + count, 0] += block * left
        buffer[position:position + count, 1] += block * right
        offset += count


def _weather(project: dict[str, Any], flock: dict[str, Any], sample_rate: int, total: int) -> np.ndarray:
    result = np.zeros((total, 2), dtype=np.float64)
    weather = flock["weather"]
    if weather == "clear":
        return result
    rng = _rng(project.get("seed", 1337), "weather", weather)
    raw = rng.standard_normal((total, 2))
    if weather == "dust":
        impulses = np.zeros((total, 2), dtype=np.float64)
        locations = np.flatnonzero(rng.random(total) < 0.00085)
        if len(locations):
            impulses[locations] = rng.choice((-1.0, 1.0), size=(len(locations), 2)) * rng.uniform(0.7, 1.0, (len(locations), 2))
        decay = math.exp(-1.0 / max(1.0, sample_rate * 0.008))
        texture = _periodic_filter(impulses, [1.0], [1.0, -decay])
        texture += raw * 0.025
    elif weather == "rain":
        low = math.exp(-2.0 * math.pi * 5200.0 / sample_rate)
        filtered = _periodic_filter(raw, [1.0 - low], [1.0, -low])
        drops = (rng.random(total) < 0.0007).astype(np.float64)
        drops *= rng.uniform(0.2, 1.0, total)
        drop_env = _periodic_filter(drops, [1.0], [1.0, -math.exp(-1.0 / max(1, sample_rate * 0.012))])
        texture = filtered * 0.72 + drop_env[:, None] * rng.choice((-1.0, 1.0), size=(1, 2)) * 0.5
    else:  # wind
        cutoff = math.exp(-2.0 * math.pi * 310.0 / sample_rate)
        filtered = _periodic_filter(raw, [1.0 - cutoff], [1.0, -cutoff])
        phase = float(rng.uniform(0, 2 * np.pi))
        time = np.arange(total) / sample_rate
        cycles = max(1, round(total / sample_rate * 0.075))
        swell = 0.22 + 0.78 * (0.5 + 0.5 * np.sin(2 * np.pi * cycles * np.arange(total) / total + phase))
        texture = filtered * swell[:, None] * 2.3
    result += texture * (10.0 ** (-24.0 / 20.0))
    return result


def render_flock(project: dict[str, Any], sample_rate: int = 44100, *, include_slots: bool = False):
    """Render the flock and weather to one exact-length stereo loop plus its metadata."""
    sr = int(sample_rate)
    if sr < 8000 or sr > 192000:
        raise ValueError("sample_rate must be between 8000 and 192000")
    bpm = float(project["bpm"])
    bars = int(project["bars"])
    if bpm <= 0 or not math.isfinite(bpm) or bars not in (4, 8):
        raise ValueError("project has invalid tempo or bars")
    total = round(bars * 4 * 60 / bpm * sr)
    if total <= 0:
        result = (np.zeros((0, 2), dtype=np.float32), compile_events(project, sr))
        return (*result, {}) if include_slots else result
    metadata, planned = _plan(project, sr)
    bus = np.zeros((total, 2), dtype=np.float64)
    if "flock" not in project:
        result = (bus.astype(np.float32), metadata)
        return (*result, {}) if include_slots else result

    flock = validate_flock(project["flock"])
    bus += _weather(project, flock, sr, total)
    duck = _duck_envelope(total, sr, [round(value * sr) for value in metadata["kick_onsets"]])
    slot_buses = None
    slot_by_bird = {}
    if include_slots:
        active = _active_perches(flock)
        slot_buses = {slot: np.zeros_like(bus) for slot, _perch in active}
        slot_by_bird = {perch["bird"]: slot for slot, perch in active}
    previous_by_bird: dict[str, int] = {}
    for event in planned:
        event["previous_midi"] = previous_by_bird.get(event["bird_id"])
        previous_by_bird[event["bird_id"]] = event["midi"]
        signal = _note_signal(event, sr)
        if event["role"] == "pad":
            stereo = _pad_stereo(signal, event, sr)
            _insert_stereo(bus, stereo, event, duck)
            if slot_buses is not None:
                slot = slot_by_bird.get(event["bird_id"])
                if slot is not None:
                    _insert_stereo(slot_buses[slot], stereo, event, duck)
        else:
            _insert_mono(bus, signal, event, duck if event["role"] == "bass" else None)
            if slot_buses is not None:
                slot = slot_by_bird.get(event["bird_id"])
                if slot is not None:
                    _insert_mono(slot_buses[slot], signal, event,
                                 duck if event["role"] == "bass" else None)

    audible_ids = {perch["bird"] for _, perch in _active_perches(flock)}
    if "corvus" in audible_ids:
        bus = np.tanh(bus * 1.65) / 1.65
    audio = np.asarray(bus, dtype=np.float32)
    if slot_buses is None:
        return audio, metadata
    from ..mix import bird_role
    slot_layers = {
        f"bird:{slot}": {"audio": np.asarray(layer, dtype=np.float32),
                         "role": bird_role(_BIRDS[flock["perches"][slot]["bird"]]["role"])}
        for slot, layer in slot_buses.items()
    }
    return audio, metadata, slot_layers


def render_song_flock(project: dict[str, Any], sections: list[dict[str, Any]],
                      sample_rate: int = 44100, kick_onsets: list[int] | None = None) -> tuple[np.ndarray, dict[str, Any]]:
    """Render bird voices on a linear song timeline; unlike loop render, nothing wraps."""
    sr = int(sample_rate)
    loop_frames = round(int(project["bars"]) * 4 * 60 / float(project["bpm"]) * sr)
    total = loop_frames * sum(section["repeat"] for section in sections)
    bus = np.zeros((total, 2), dtype=np.float64)
    metadata: dict[str, Any] = {"flock_events": {},
                                "kick_onsets": [sample / sr for sample in (kick_onsets or [])],
                                "flock_active_combos": []}
    if "flock" not in project:
        return bus.astype(np.float32), metadata
    from .model import validate_flock
    from ..arrangement import section_flock

    original_flock = validate_flock(project["flock"])
    metadata["flock_active_combos"] = list(active_combos(original_flock))
    weather = original_flock["weather"]
    if weather != "clear":
        rng = _rng(project.get("seed", 1337), "weather", weather)
        raw = rng.standard_normal((total, 2))
        if weather == "dust":
            impulses = np.zeros((total, 2), dtype=np.float64)
            locations = np.flatnonzero(rng.random(total) < 0.00085)
            if len(locations):
                impulses[locations] = rng.choice((-1.0, 1.0), size=(len(locations), 2)) * rng.uniform(0.7, 1.0, (len(locations), 2))
            decay = math.exp(-1.0 / max(1.0, sr * 0.008))
            texture = lfilter([1.0], [1.0, -decay], impulses, axis=0) + raw * 0.025
        elif weather == "rain":
            cutoff = math.exp(-2.0 * math.pi * 5200.0 / sr)
            filtered = lfilter([1.0 - cutoff], [1.0, -cutoff], raw, axis=0)
            drops = (rng.random(total) < 0.0007).astype(np.float64)
            drops *= rng.uniform(0.2, 1.0, total)
            env = lfilter([1.0], [1.0, -math.exp(-1.0 / max(1, sr * 0.012))], drops)
            texture = filtered * 0.72 + env[:, None] * rng.choice((-1.0, 1.0), size=(1, 2)) * 0.5
        else:
            cutoff = math.exp(-2.0 * math.pi * 310.0 / sr)
            filtered = lfilter([1.0 - cutoff], [1.0, -cutoff], raw, axis=0)
            phase = float(rng.uniform(0, 2 * np.pi))
            cycles = max(1, round(total / sr * 0.075))
            swell = 0.22 + 0.78 * (0.5 + 0.5 * np.sin(2 * np.pi * cycles * np.arange(total) / total + phase))
            texture = filtered * swell[:, None] * 2.3
        bus += texture * (10.0 ** (-24.0 / 20.0))
    previous_by_bird: dict[str, int] = {}
    cursor = 0
    duck = _duck_envelope(total, sr, kick_onsets or [])
    for section in sections:
        for _ in range(section["repeat"]):
            section_project = dict(project)
            section_project["flock"] = section_flock(project, section)
            muted_birds = {original_flock["perches"][int(entry[5:])]["bird"]
                           for entry in section["mute"] if entry.startswith("bird:")}
            local_metadata, planned = _plan(section_project, sr)
            if planned:
                for event in planned:
                    if event["bird_id"] in muted_birds:
                        continue
                    event = dict(event)
                    event["sample"] += cursor
                    event["previous_midi"] = previous_by_bird.get(event["bird_id"])
                    previous_by_bird[event["bird_id"]] = event["midi"]
                    signal = _note_signal(event, sr)
                    if event["role"] == "pad":
                        stereo = _pad_stereo(signal, event, sr)
                        take = min(len(stereo), total - event["sample"])
                        if take > 0:
                            bus[event["sample"]:event["sample"] + take] += stereo[:take] * duck[
                                event["sample"]:event["sample"] + take, None]
                    else:
                        take = min(len(signal), total - event["sample"])
                        if take <= 0:
                            continue
                        pan = min(1.0, max(-1.0, float(event["pan"])))
                        angle = (pan + 1.0) * math.pi / 4.0
                        block = signal[:take]
                        if event["role"] == "bass":
                            block = block * duck[event["sample"]:event["sample"] + take]
                        bus[event["sample"]:event["sample"] + take, 0] += block * math.cos(angle) * float(event["gain"])
                        bus[event["sample"]:event["sample"] + take, 1] += block * math.sin(angle) * float(event["gain"])
                    metadata["flock_events"].setdefault(event["bird_id"], []).append({
                        "t": event["sample"] / sr,
                        "len": (event["duration_samples"] + _voice_release_samples(event["voice"], sr)) / sr,
                        "midi": int(event["midi"]), "vel": float(event["vel"]),
                    })
            # Preserve the first section's planner summaries while reporting song offsets.
            cursor += loop_frames
    if any(perch is not None and perch["bird"] == "corvus" and not perch["mute"]
           for perch in original_flock["perches"]):
        bus = np.tanh(bus * 1.65) / 1.65
    return np.asarray(bus, dtype=np.float32), metadata


__all__ = ["compile_events", "render_flock"]
