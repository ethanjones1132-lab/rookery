"""Deterministic loop renderer and compatibility API for the Rookery engine."""

from __future__ import annotations

import hashlib
import importlib.metadata
import io
import math
import os
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
import pyloudnorm as pyln
from scipy.signal import lfilter, resample_poly

from .arrangement import arrangement_variety, section_track_view
from .kit import BASS_FACTORY_NAMES, FACTORY_NAMES, synthesize
from .kit.factory import is_kick_source
from .checks import mix_report

def _renderer_version():
    versions = []
    for package in ("numpy", "scipy", "pedalboard", "soundfile", "pyloudnorm"):
        try:
            version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            version = "missing"
        versions.append(f"{package}={version}")
    return "rookery-render-2;cyclic-hp;per-track-fx;bar-tail;" + ";".join(versions)


RENDERER_VERSION = _renderer_version()
SAMPLE_RATE = 44100
SR = SAMPLE_RATE
_MAX_SECONDS = 180.0
_MAX_SAMPLE_BYTES = 100 * 1024 * 1024
_FADE_SECONDS = 0.002


def _patterns(value, size, default="."):
    text = str(value or default)
    if not text:
        text = default
    return (text * ((size + len(text) - 1) // len(text)))[:size]


def _db(value):
    return 20.0 * math.log10(max(float(value), 1e-12))


def _layer_lufs(layer, meter):
    if not np.any(layer):
        return None
    try:
        value = float(meter.integrated_loudness(np.asarray(layer, dtype=np.float64)))
    except (ValueError, ZeroDivisionError, RuntimeError):
        return None
    return value if math.isfinite(value) else None


def _note_midi(pitch):
    if isinstance(pitch, (int, float)):
        midi = float(pitch)
    else:
        text = str(pitch).strip()
        names = {"C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3, "E": 4,
                 "F": 5, "F#": 6, "GB": 6, "G": 7, "G#": 8, "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11}
        import re
        match = re.fullmatch(r"([A-Ga-g](?:#|b)?)(-?\d+)", text)
        if not match:
            raise ValueError(f"invalid MIDI note: {pitch}")
        key = match.group(1).upper()
        midi = (int(match.group(2)) + 1) * 12 + names[key]
    if not math.isfinite(midi) or not 0 <= midi <= 127:
        raise ValueError("pitch must be a MIDI note from 0 to 127")
    return midi


def _note_hz(pitch):
    return 440.0 * 2 ** ((_note_midi(pitch) - 69) / 12)


def _safe_sample_path(source, user_kit_dir):
    if not source.startswith("user:"):
        raise ValueError(f"unsupported sample source: {source}")
    if user_kit_dir is None:
        raise ValueError("user sample source requires user_kit_dir")
    relative = Path(source[5:])
    if relative.is_absolute() or any(part in ("..", "") for part in relative.parts):
        raise ValueError("user sample path must stay inside the kit directory")
    from .project import USER_AUDIO_EXTENSIONS
    if relative.suffix.lower() not in USER_AUDIO_EXTENSIONS:
        raise ValueError("user sample must be a supported audio file (.wav, .flac, .aiff, .aif, .ogg)")
    root = Path(user_kit_dir).resolve(strict=True)
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("user sample path escapes the kit directory")
    if path.suffix.lower() not in USER_AUDIO_EXTENSIONS:
        raise ValueError("user sample must resolve to a supported audio file")
    if path.stat().st_size > _MAX_SAMPLE_BYTES:
        raise ValueError("user sample exceeds the 100 MiB size limit")
    return path


def _read_user_sample(source, user_kit_dir, sr):
    path = _safe_sample_path(source, user_kit_dir)
    data, source_sr = sf.read(str(path), dtype="float32", always_2d=True)
    if len(data) > int(_MAX_SECONDS * source_sr):
        raise ValueError("user sample exceeds the 180 second duration limit")
    if data.shape[1] > 2:
        raise ValueError("user samples must be mono or stereo")
    mono = data.mean(axis=1, dtype=np.float64).astype(np.float32)
    if source_sr != sr:
        divisor = math.gcd(int(source_sr), int(sr))
        mono = resample_poly(mono, sr // divisor, source_sr // divisor).astype(np.float32)
    return mono


_PITCH_CLASSES = {"C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3, "E": 4, "F": 5, "F#": 6, "GB": 6,
                  "G": 7, "G#": 8, "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11}
# Semitones from a mode's tonic up to its relative major's tonic.
_MODE_TO_MAJOR = {"major": 0, "ionian": 0, "lydian": 7, "mixolydian": 5, "dorian": 10,
                  "minor": 3, "aeolian": 3, "phrygian": 8, "locrian": 1}


_LATENCY_CACHE = {}


def _stretch_latency(length, mark, sr, ratio, shift):
    """Rubber Band's output delay for this buffer shape, measured once with a click at ``mark``.

    The click should come out at round(mark * ratio); wherever it really lands, the difference
    is the delay to correct so stretched beats sit on the grid.
    """
    key = (int(length), int(mark), int(sr), round(float(ratio), 9), round(float(shift), 6))
    if key not in _LATENCY_CACHE:
        import pedalboard
        probe = np.zeros((int(length), 1), dtype=np.float32)
        probe[int(mark), 0] = 1.0
        out = np.asarray(pedalboard.time_stretch(probe, float(sr), stretch_factor=float(ratio),
                                                 pitch_shift_in_semitones=float(shift), high_quality=True,
                                                 transient_mode="crisp", retain_phase_continuity=True))
        envelope = np.abs(out.reshape(len(out), -1)).sum(axis=1)
        _LATENCY_CACHE[key] = int(np.argmax(envelope)) - round(mark * ratio) if envelope.any() else 0
    return _LATENCY_CACHE[key]


def _key_lock_interval(sample_key, project_key, project_scale):
    """Smallest shift that puts a sample's key on the project's notes, relative keys included.

    "F major" in a D minor (or D dorian's parent C major) project compares relative majors, so an
    F major loop in D minor stays put instead of being dragged to D major.
    """
    try:
        tonic, _, mode = str(sample_key).strip().partition(" ")
        sample_major = (_PITCH_CLASSES[tonic.upper()] + (3 if mode.lower().startswith("min") else 0)) % 12
        project_major = (_PITCH_CLASSES[str(project_key).strip().upper()]
                         + _MODE_TO_MAJOR.get(str(project_scale).lower(), 3)) % 12
    except KeyError:
        return 0
    return (project_major - sample_major + 6) % 12 - 6


def _loop_sample(source, user_kit_dir, sr, project, track):
    """Prepare one bar-locked loop buffer; legacy one-shot path stays untouched."""
    from .sampling import analyze, has_confident_key

    path = _safe_sample_path(source, user_kit_dir)
    file_info = sf.info(str(path))
    if file_info.samplerate > 0 and file_info.frames > int(_MAX_SECONDS * file_info.samplerate):
        raise ValueError("user sample exceeds the 180 second duration limit")
    if file_info.channels > 2:
        raise ValueError("user samples must be mono or stereo")
    info = analyze(path, project_bpm=float(project["bpm"]))
    audio, source_sr = sf.read(str(path), dtype="float32", always_2d=True)
    if audio.shape[1] > 2:
        raise ValueError("user samples must be mono or stereo")
    if source_sr != sr:
        divisor = math.gcd(int(source_sr), int(sr))
        audio = resample_poly(audio, sr // divisor, source_sr // divisor, axis=0).astype(np.float32)
    if project.get("mix_profile") != "targets-v1" or audio.shape[1] != 2:
        # Preserve the legacy mono projection byte-for-byte for unmarked projects.
        audio = audio.mean(axis=1, keepdims=True, dtype=np.float64).astype(np.float32)
    start = min(len(audio), max(0, round(float(info["downbeat_s"]) * sr)))
    audio = audio[start:]
    if not len(audio):
        audio = np.zeros((1, audio.shape[1]), dtype=np.float32)
    shift = float(track.get("pitch", 0))
    flock = project.get("flock") or {}
    target_key = project.get("key") or flock.get("key")
    target_scale = (project.get("scale", "major") if project.get("key")
                    else flock.get("scale", "major"))
    profile = info.get("profile")
    pitched = profile.get("pitched") if isinstance(profile, dict) else None
    if (track.get("key_lock", True) and target_key and info.get("key")
            and pitched is not False and has_confident_key(info)):
        shift += _key_lock_interval(info["key"], target_key, target_scale)
    bpm = info.get("bpm") or float(project["bpm"])
    import pedalboard
    loop_bars = int(track.get("loop_bars", info.get("bars", 1)))
    source_bars = max(1, int(info.get("bars", 1)))
    source_len = round(source_bars * 4 * 60 / float(bpm) * sr)
    target_len = round(source_bars * 4 * 60 / float(project["bpm"]) * sr)
    phrase_src = audio[:source_len]
    if len(phrase_src) < source_len:
        phrase_src = np.pad(phrase_src, ((0, source_len - len(phrase_src)), (0, 0)))
    ratio = float(project["bpm"]) / float(bpm)
    beats = source_bars * 4
    # Beat-sized pieces keep every beat on the grid (a whole-phrase stretch drifts by a few ms).
    # Each piece is stretched with a margin on both sides and overlap-added with an equal-power
    # crossfade across the seam, wrapping around the phrase, so sustained notes never dip and the
    # phrase loops seamlessly.
    # Rubber Band's first and last few tens of ms of a short buffer are unreliable, so each
    # piece is stretched with a wide margin and only its settled middle is used; neighbours meet
    # in a 20 ms equal-power crossfade, phase-aligned within +/- 3 ms (WSOLA-style).
    margin_s = .06
    xf = max(2, round(sr * .02))
    half = xf // 2
    search = max(1, round(sr * .003))
    step = max(1, search // 12)
    src_pad = round(margin_s * sr / ratio) + 1
    tail_pad = round(.08 * sr)
    phrase = np.zeros((target_len, phrase_src.shape[1]), dtype=np.float64)
    weight = np.zeros(target_len, dtype=np.float64)
    rise = np.sin(np.linspace(0, math.pi / 2, xf)) ** 2

    def overlap_score(region_positions, candidate):
        filled = weight[region_positions] > 0
        if not np.any(filled):
            return 0.0
        existing = phrase[region_positions][filled] / weight[region_positions][filled][:, None]
        cand = candidate[filled]
        denom = math.sqrt(float(np.sum(existing * existing)) * float(np.sum(cand * cand))) or 1.0
        return float(np.sum(existing * cand)) / denom

    for beat in range(beats):
        src_start = round(beat * source_len / beats)
        src_end = round((beat + 1) * source_len / beats)
        # Extra source on the right covers Rubber Band's output delay, so the used middle never
        # runs into the zero padding past the end of its output.
        idx = np.arange(src_start - src_pad, src_end + src_pad + tail_pad) % source_len
        piece = pedalboard.time_stretch(np.ascontiguousarray(phrase_src[idx]), float(sr),
                                        stretch_factor=ratio, pitch_shift_in_semitones=shift,
                                        high_quality=True, transient_mode="crisp",
                                        retain_phase_continuity=True)
        piece = np.asarray(piece, dtype=np.float64)
        if piece.ndim == 1:
            piece = piece[:, None]
        dst_start = round(beat * target_len / beats)
        dst_end = round((beat + 1) * target_len / beats)
        want = dst_end - dst_start + xf
        lead = round(src_pad * ratio) - half + _stretch_latency(len(idx), src_pad, sr, ratio, shift)
        if len(piece) < lead + want + search:
            piece = np.pad(piece, ((0, lead + want + search - len(piece)), (0, 0)))
        positions = np.arange(dst_start - half, dst_start - half + want) % target_len
        best, best_score = 0, -2.0
        for offset in range(-search, search + 1, step):
            start = lead + offset
            if start < 0:
                continue
            candidate = piece[start:start + want]
            score = overlap_score(positions[:xf], candidate[:xf])
            if beat == beats - 1:   # the last piece also meets the first piece's head
                score += overlap_score(positions[-xf:], candidate[-xf:])
            if score > best_score:
                best, best_score = offset, score
        chosen = piece[lead + best:lead + best + want]
        window = np.ones(want)
        window[:xf] = rise
        window[-xf:] = rise[::-1]
        np.add.at(phrase, positions, chosen * window[:, None])
        np.add.at(weight, positions, window)
    phrase = np.asarray(phrase / np.maximum(weight, 1e-9)[:, None], dtype=np.float32)
    count = round(loop_bars * 4 * 60 / float(project["bpm"]) * sr)
    reps = -(-count // max(1, len(phrase)))
    audio = np.tile(phrase, (reps, 1))[:count]
    # The beat-piece overlap-add above already wraps the last piece into the first. A
    # second blend here mixes the tail into the loop head and then resets to the head,
    # creating a discontinuity at every repetition (especially audible on tonal loops).
    result = audio if audio.shape[1] == 2 else audio[:, 0]
    return np.asarray(result, dtype=np.float32), info


def _duck_layer(layer, onsets, amount, sr, *, wrap=False):
    if amount <= 0 or not onsets:
        return layer
    gain = np.ones(len(layer), dtype=np.float64)
    attack, release = max(1, round(.005 * sr)), max(1, round(.12 * sr))
    depth = float(amount) * .65
    for onset in onsets:
        if wrap:
            length = min(release, len(gain))
            indices = (onset + np.arange(length)) % len(gain)
        else:
            start, end = max(0, onset), min(len(gain), onset + release)
            if start >= end:
                continue
            length = end - start
            indices = slice(start, end)
        if not length:
            continue
        curve = np.ones(length)
        down = min(attack, length)
        curve[:down] = np.linspace(1, 1 - depth, down, endpoint=True)
        if length > down:
            curve[down:] = np.linspace(1 - depth, 1, length - down, endpoint=True)
        gain[indices] = np.minimum(gain[indices], curve)
    return layer * gain[:, None]


def _fade_voice(voice, sr):
    voice = np.asarray(voice, dtype=np.float32).copy()
    count = min(len(voice), max(1, round(sr * _FADE_SECONDS)))
    if count:
        voice[:count] *= np.linspace(0.0, 1.0, count, endpoint=True, dtype=np.float32)
        voice[-count:] *= np.linspace(1.0, 0.0, count, endpoint=True, dtype=np.float32)
    return voice


def _cached_synthesize(cache, name, *, sr, seed, pitch=0, duration=None, note_hz=None):
    """Reuse immutable factory voices during one render only."""
    key = (name, sr, seed, pitch, duration, note_hz)
    voice = cache.get(key)
    if voice is None:
        voice = synthesize(name, sr=sr, seed=seed, pitch=pitch, duration=duration, note_hz=note_hz)
        cache[key] = voice
    return voice


def _insert_wrap(buffer, voice, start, total, gain, pan):
    if not len(voice):
        return
    if np.ndim(voice) == 2:
        pan = min(1.0, max(-1.0, pan))
        balance = np.asarray([1.0 - max(0.0, pan), 1.0 + min(0.0, pan)])
        offset = 0
        while offset < len(voice):
            position = (start + offset) % total
            count = min(len(voice) - offset, total - position)
            buffer[position:position + count] += voice[offset:offset + count] * (balance * gain)
            offset += count
        return
    angle = (min(1.0, max(-1.0, pan)) + 1.0) * (math.pi / 4.0)
    left, right = math.cos(angle) * gain, math.sin(angle) * gain
    # Voices may be longer than the loop. Periodic accumulation handles that case too.
    offset = 0
    while offset < len(voice):
        position = (start + offset) % total
        count = min(len(voice) - offset, total - position)
        buffer[position:position + count, 0] += voice[offset:offset + count] * left
        buffer[position:position + count, 1] += voice[offset:offset + count] * right
        offset += count


def _highpass(audio, sr):
    # One-pole 20 Hz blocker, with the exact state that makes the input periodic.
    alpha = math.exp(-2.0 * math.pi * 20.0 / sr)
    if not len(audio):
        return np.asarray(audio).copy()
    x = np.asarray(audio, dtype=np.float64)
    _, end_state = lfilter([alpha, -alpha], [1.0, -alpha], x, axis=0,
                           zi=np.zeros((1, x.shape[1]), dtype=np.float64))
    initial_state = end_state / (1.0 - alpha ** len(x))
    out, _ = lfilter([alpha, -alpha], [1.0, -alpha], x, axis=0, zi=initial_state)
    return out


def _highpass_linear(audio, sr):
    """One continuous high-pass pass with zero initial state (no cyclic pre-roll)."""
    alpha = math.exp(-2.0 * math.pi * 20.0 / sr)
    if not len(audio):
        return np.asarray(audio).copy()
    result, _ = lfilter([alpha, -alpha], [1.0, -alpha],
                        np.asarray(audio, dtype=np.float64), axis=0,
                        zi=np.zeros((1, audio.shape[1]), dtype=np.float64))
    return result


def _highpass_at(audio, sr, cutoff):
    alpha = math.exp(-2.0 * math.pi * float(cutoff) / sr)
    x = np.asarray(audio, dtype=np.float64)
    if not len(x):
        return x.copy()
    _, end_state = lfilter([alpha, -alpha], [1.0, -alpha], x, axis=0,
                           zi=np.zeros((1, x.shape[1]), dtype=np.float64))
    initial_state = end_state / (1.0 - alpha ** len(x))
    out, _ = lfilter([alpha, -alpha], [1.0, -alpha], x, axis=0, zi=initial_state)
    return out


def _center_low_frequencies(audio, sr, cutoff=120):
    """Keep stereo width above cutoff while centering the low-frequency side signal."""
    x = np.asarray(audio, dtype=np.float64)
    if x.ndim != 2 or x.shape[1] != 2 or not len(x):
        return np.asarray(audio).copy()
    mid = x.mean(axis=1, keepdims=True)
    side = x - mid
    # A cascaded, periodic split makes the side channel negligible below the crossover
    # without changing the mono signal or introducing a loop-boundary transient.
    high_side = side
    for _ in range(3):
        high_side = _highpass_at(high_side, sr, cutoff)
    return np.asarray(mid + high_side, dtype=np.float32)


def _rendered_onset_profile(layer, sr, bpm, bars):
    """Return onset strength at each rendered sixteenth, preserving bar gating."""
    x = np.asarray(layer, dtype=np.float64)
    if not len(x) or bpm <= 0 or bars <= 0:
        return np.zeros(max(0, int(bars) * 16), dtype=np.float64)
    mono_rms = np.sqrt(np.mean(x * x, axis=1)) if x.ndim == 2 else np.abs(x)
    wanted = max(64, round(sr * .04))
    frame_length = 1 << (wanted - 1).bit_length()
    hop = max(1, frame_length // 4)
    padded = np.pad(mono_rms, (0, frame_length))
    frames = np.lib.stride_tricks.sliding_window_view(padded, frame_length)[::hop]
    spectrum = np.abs(np.fft.rfft(frames * np.hanning(frame_length), axis=1))
    previous = np.vstack((np.zeros((1, spectrum.shape[1])), spectrum[:-1]))
    flux = np.maximum(spectrum - previous, 0.0).sum(axis=1)
    onset = np.maximum(0.0, flux - .1 * previous.sum(axis=1))
    frame_centers = np.arange(len(spectrum), dtype=np.float64) * hop + frame_length / 2
    step_length = 15.0 / float(bpm) * sr
    step_indices = np.floor(frame_centers / step_length).astype(np.int64)
    valid = step_indices < int(bars) * 16
    return np.bincount(step_indices[valid], weights=onset[valid],
                       minlength=int(bars) * 16).astype(np.float64).reshape(int(bars), 16)


def _cosine_overlap(left, right):
    a = np.asarray(left, dtype=np.float64).reshape(-1)
    b = np.asarray(right, dtype=np.float64).reshape(-1)
    if a.shape != b.shape or not a.size:
        return 0.0
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if not math.isfinite(denominator) or denominator <= 1e-15:
        return 0.0
    value = float(np.dot(a, b) / denominator)
    return round(min(1.0, max(0.0, value)), 3)


def _gated_rhythm_overlap(left, right):
    """Compare each rendered 16-step bar, treating gated bars as silence."""
    a = np.asarray(left, dtype=np.float64)
    b = np.asarray(right, dtype=np.float64)
    if a.shape != b.shape or a.ndim != 2 or a.shape[1] != 16:
        return 0.0
    overlaps = []
    for a_bar, b_bar in zip(a, b):
        a_active = float(np.linalg.norm(a_bar)) > 1e-15
        b_active = float(np.linalg.norm(b_bar)) > 1e-15
        if not a_active and not b_active:
            continue
        # Centre each bar first: stretch smear and loop seams give every layer a
        # shared onset floor, which made disjoint hit patterns score ~0.9 raw.
        overlaps.append(_cosine_overlap(a_bar - a_bar.mean(), b_bar - b_bar.mean()))
    return round(float(np.mean(overlaps)), 3) if overlaps else 0.0


def _fx_chain(audio, chain, sr, tail_frames):
    if not chain:
        return audio
    # A fresh apply_fx invocation resets effect state for each independent render.
    # A bar of silence lets decaying effects ring out; fold that tail into the loop.
    from .fx import apply_fx

    extended = np.concatenate((audio, np.zeros((tail_frames, audio.shape[1]), dtype=audio.dtype)))
    processed = np.asarray(apply_fx(extended, chain, sr))
    if processed.shape != extended.shape or not np.all(np.isfinite(processed)):
        raise ValueError("FX processing returned invalid audio")
    result = processed[:len(audio)].copy()
    folded = min(tail_frames, len(result))
    result[:folded] += processed[len(audio):len(audio) + folded]
    return result


def _balance_response(project, measured):
    from .mix import mix_genre, role_target

    levels = measured.get("levels", {})
    roles = measured.get("roles", {})
    tracks = {track["id"]: track for track in project.get("tracks", [])}
    genre = mix_genre(project)
    drum_ids = [ident for ident in levels
                if ident in tracks and tracks[ident].get("kind") == "drum"]
    kick_ids = [ident for ident in drum_ids if roles.get(ident) == "kick"]
    ref_id = max(kick_ids, key=levels.__getitem__) if kick_ids else (
        max(drum_ids, key=levels.__getitem__) if drum_ids else None)
    ref_level = levels.get(ref_id) if ref_id is not None else None
    ref = (f"kick:{ref_id}" if kick_ids else
           f"loudest_drum:{ref_id}" if ref_id is not None else "none")
    ref_desc = "the kick" if kick_ids else f"the loudest drum ({ref_id})" if ref_id else "a drum reference"

    balance = {}
    for ident, value in levels.items():
        role = roles.get(ident)
        target = role_target(role, genre) if role else None
        if target is None:
            continue
        relative = round(value - ref_level, 1) if ref_level is not None else None
        balance[ident] = {
            "role": role,
            "lu_vs_kick": relative,
            "target": target,
            "ok": bool(relative is not None and target[0] <= relative <= target[1]),
        }

    notes = []
    bass_tracks = [ident for ident in levels if ident in tracks
                   and tracks[ident].get("kind") == "bass"]
    flock_basses = [ident for ident in levels if ident.startswith("bird:")
                    and roles.get(ident) == "flock_bass"]
    if bass_tracks and flock_basses:
        notes.append(f"two basses: {bass_tracks[0]} track and Flock bass bird slot {flock_basses[0][5:]} both play; mute one")

    if ref_level is None and levels:
        notes.append("add an audible kick or drum to establish the mix reference")
    else:
        misses = []
        perch_by_slot = {
            f"bird:{slot}": perch
            for slot, perch in enumerate(project.get("flock", {}).get("perches", [])) if perch
        }
        for ident, item in balance.items():
            value = item["lu_vs_kick"]
            if item["ok"] or value is None:
                continue
            lo, hi = item["target"]
            edge = lo if value < lo else hi
            miss = abs(value - edge)
            if ident in tracks:
                current = float(tracks[ident].get("gain_db", 0))
                recommended = min(12.0, max(-60.0, current + edge - value))
                label = ident
                suggestion = f"set {label} gain_db to {recommended:g}"
            else:
                perch = perch_by_slot.get(ident, {})
                bird = perch.get("bird", ident[5:])
                label = f"Flock bird {bird}"
                suggestion = f"ask the user to adjust bird {bird}"
            relation = f"{abs(value):.1f} LU {'over' if value >= 0 else 'under'} {ref_desc}"
            target_text = f"{lo:+g}..{hi:+g}" if hi > 0 else f"{lo:g}..{hi:g}"
            if lo == 0 and hi == 0:
                target_text = "0"
            misses.append((miss, f"{label} is {relation} (target {target_text}): {suggestion}"))
        notes.extend(text for _miss, text in sorted(misses, key=lambda item: (-item[0], item[1]))[:5 - len(notes)])
    fit = []
    fit_notes = []
    sample_profiles = measured.get("sample_fit_profiles", {})
    sample_rhythms = measured.get("sample_fit_rhythms", {})
    pitched_ids = [track["id"] for track in project.get("tracks", [])
                   if track.get("kind") == "sample" and track.get("mode") == "loop"
                   and track["id"] in sample_profiles and track["id"] in sample_rhythms]
    for ident in pitched_ids:
        if not sample_profiles[ident].get("key"):
            fit_notes.append(
                f"{ident} is pitched but its key is unknown; key lock cannot confirm harmony."
            )
    for index, a in enumerate(pitched_ids):
        profile_a = sample_profiles[a]
        for b in pitched_ids[index + 1:]:
            profile_b = sample_profiles[b]
            register_overlap = _cosine_overlap(profile_a.get("bands", []),
                                               profile_b.get("bands", []))
            rhythm_overlap = _gated_rhythm_overlap(sample_rhythms[a], sample_rhythms[b])
            fit.append({"a": a, "b": b, "register_overlap": register_overlap,
                        "rhythm_overlap": rhythm_overlap})
            if register_overlap > .8 and rhythm_overlap > .8:
                fit_notes.append(
                    f"{a} and {b} sit in the same register on the same beats: gate one to alternate "
                    'bars (steps:"x." and ".x"), move one to another section, or swap it for a '
                    "higher/lower, sparser/sustained sound."
                )
    return {"balance": balance, "mix_notes": [*notes[:5], *fit_notes], "ref": ref, "fit": fit}


def _render_audio_with_metadata(project, sample_rate=SAMPLE_RATE, user_kit_dir=None, *, fixed_gain=None,
                                include_balance=False):
    """Render a project to exact-length stereo float32, meters, and planner metadata."""
    factory_voice_cache = {}
    sr = int(sample_rate)
    if sr < 8000 or sr > 192000:
        raise ValueError("sample_rate must be between 8000 and 192000")
    bpm = float(project["bpm"])
    bars = int(project["bars"])
    steps_per_bar = int(project.get("steps_per_bar", 16))
    swing = float(project.get("swing", 0.0))
    if bpm <= 0 or not math.isfinite(bpm) or bars not in (4, 8) or steps_per_bar != 16 or not 0 <= swing <= 1:
        raise ValueError("project has invalid tempo, bars, steps_per_bar, or swing")
    total = round(bars * 4 * 60 / bpm * sr)
    if total > _MAX_SECONDS * sr:
        raise ValueError("render duration exceeds the 180 second limit")
    n_steps = bars * steps_per_bar
    step_len = total / n_steps
    tail_frames = round(4 * 60 / bpm * sr)
    tracks = list(project.get("tracks", []))
    audible = [t for t in tracks if not t.get("mute", False)]
    if any(t.get("solo", False) for t in tracks):
        audible = [t for t in audible if t.get("solo", False)]
    track_audio = {}
    choke_events = {}
    kick_onsets = []
    sample_analyses = {}
    balance_levels = {}
    balance_roles = {}
    sample_fit_profiles = {}
    sample_fit_rhythms = {}
    balance_meter = pyln.Meter(sr) if include_balance else None
    if include_balance:
        from .mix import cached_sample_role_hint, track_role
    for kick_track in audible:
        if kick_track.get("kind") == "drum" and is_kick_source(kick_track.get("source")):
            pattern = _patterns(kick_track.get("steps", "x"), n_steps)
            velocities = kick_track.get("velocity", [1.0]) or [1.0]
            for index, symbol in enumerate(pattern):
                if symbol == "x" and float(velocities[index % len(velocities)]) > 0:
                    onset = round(index * step_len)
                    if index % 2:
                        onset += round(swing * step_len * .5)
                    kick_onsets.append(onset % total)
    for track in audible:
        group = track.get("choke_group")
        if group:
            choke_events.setdefault(group, [])
    for track in audible:
        kind = track.get("kind", "drum")
        source = str(track.get("source", "factory:kick_boom"))
        gain = 10.0 ** (float(track.get("gain_db", 0.0)) / 20.0)
        pan = float(track.get("pan", 0.0))
        if not math.isfinite(gain) or not math.isfinite(pan):
            raise ValueError("track gain and pan must be finite")
        contributions = []
        if kind == "bass":
            notes = track.get("notes", []) or []
            velocity = track.get("velocity", [1.0]) or [1.0]
            transpose = float(track.get("pitch", 0))
            if not math.isfinite(transpose):
                raise ValueError("bass pitch transpose must be finite")
            for note in notes:
                step = int(note["step"])
                length = max(1, int(note.get("len", 1)))
                start = round((step % n_steps) * step_len)
                if step % 2:
                    start = (start + round(swing * step_len * 0.5)) % total
                seconds = min(30.0, max(0.01, length * step_len / sr))
                midi = _note_midi(note.get("pitch", "C1")) + transpose
                hz = _note_hz(midi)
                bass_name = source.partition(":")[2]
                if bass_name in BASS_FACTORY_NAMES and bass_name != "808":
                    voice = _cached_synthesize(
                        factory_voice_cache,
                        bass_name, sr=sr, seed=int(project.get("seed", 1337)), pitch=transpose,
                        duration=seconds, note_hz=hz,
                    )
                else:
                    count = round(seconds * sr)
                    t = np.arange(count, dtype=np.float64) / sr
                    voice = np.tanh(1.15 * np.sin(2 * np.pi * hz * t)) * np.exp(-t / max(seconds * 1.8, 0.08))
                    voice = np.asarray(voice * 0.85, dtype=np.float32)
                voice = _fade_voice(voice, sr)
                contributions.append((start, voice, float(velocity[step % len(velocity)])))
        elif kind == "sample" or source.startswith("user:"):
            if track.get("mode") == "loop":
                sample, analysis = _loop_sample(source, user_kit_dir, sr, project, track)
                if include_balance:
                    sample_analyses[track["id"]] = analysis
                bar_frames = total / bars
                loop_bars = int(track.get("loop_bars", analysis.get("bars", 1)))
                steps = track.get("steps", "x" * bars)
                velocity = track.get("velocity", [1.0]) or [1.0]
                for bar in range(bars):
                    if steps[bar % len(steps)] != "x":
                        continue
                    offset = round((bar % loop_bars) * bar_frames)
                    length = round(bar_frames)
                    voice = sample[offset:offset + length]
                    start = round(bar * bar_frames)
                    contributions.append((start, voice, float(velocity[bar % len(velocity)])))
            else:
                sample = _read_user_sample(source, user_kit_dir, sr)
                steps = _patterns(track.get("steps", "x"), n_steps)
                slices = max(1, int(track.get("slices", 1)))
                for i, symbol in enumerate(steps):
                    if symbol not in "x0123456789" or symbol == ".":
                        continue
                    index = 0 if symbol == "x" else int(symbol) % slices
                    start_slice = round(len(sample) * index / slices)
                    end_slice = round(len(sample) * (index + 1) / slices)
                    voice = sample[start_slice:end_slice]
                    start = round(i * total / n_steps)
                    if i % 2:
                        start = (start + round(swing * step_len * 0.5)) % total
                    velocity = track.get("velocity", [1.0])
                    vel = float(velocity[i % len(velocity)]) if velocity else 1.0
                    contributions.append((start, voice, vel))
                # Legacy sampler truncation is retained byte-for-byte for one-shots.
                hit_starts = sorted({start for start, _voice, _vel in contributions})
                trimmed = []
                for start, voice, vel in contributions:
                    gaps = [(other - start) % total for other in hit_starts if other != start]
                    limit = min(gaps) if gaps else total
                    if len(voice) > limit:
                        voice = voice[:limit]
                    trimmed.append((start, _fade_voice(voice, sr), vel))
                contributions = trimmed
        else:
            name = source.split(":", 1)[-1]
            if name not in FACTORY_NAMES:
                raise ValueError(f"unsupported factory source: {source}")
            steps = _patterns(track.get("steps", "x"), n_steps)
            velocity = track.get("velocity", [1.0]) or [1.0]
            for i, symbol in enumerate(steps):
                if symbol != "x":
                    continue
                start = round(i * total / n_steps)
                if i % 2:
                    start += round(swing * step_len * 0.5)
                start %= total
                vel = float(velocity[i % len(velocity)])
                pitch = track.get("pitch", 0)
                voice = _fade_voice(_cached_synthesize(
                    factory_voice_cache, name, sr=sr, seed=int(project.get("seed", 1337)), pitch=pitch
                ), sr)
                contributions.append((start, voice, vel))
                group = track.get("choke_group")
                if group:
                    choke_events.setdefault(group, []).append((start, track["id"]))
        track_audio[track["id"]] = (contributions, gain, pan)

    mix = np.zeros((total, 2), dtype=np.float64)
    meters = {}
    # Compute per-track meter before master processing; muted tracks have no meter signal.
    for track in tracks:
        ident = track["id"]
        contributions, gain, pan = track_audio.get(ident, ([], 10 ** (float(track.get("gain_db", 0)) / 20), float(track.get("pan", 0))))
        layer = np.zeros_like(mix)
        group = track.get("choke_group")
        stops = sorted(start for start, owner in choke_events.get(group, []) if owner != ident) if group else []
        for start, original, velocity in contributions:
            if not math.isfinite(velocity):
                raise ValueError("velocity must be finite")
            voice = original
            if stops:
                distances = [(p - start) % total for p in stops]
                positive = [distance if distance else total for distance in distances]
                if positive:
                    length = min(len(voice), min(positive))
                    voice = voice[:length].copy()
                    fade = min(length, max(1, round(sr * _FADE_SECONDS)))
                    if fade:
                        voice[-fade:] *= np.linspace(1, 0, fade, endpoint=True, dtype=np.float32)
            _insert_wrap(layer, voice, start, total, gain * velocity, pan)
        if len(contributions):
            meters[ident] = {"rms_db": _db(np.sqrt(np.mean(layer * layer))), "peak_db": _db(np.max(np.abs(layer)))}
        else:
            meters[ident] = {"rms_db": -120.0, "peak_db": -120.0}
        processed_layer = (_fx_chain(layer, track.get("fx", []) or [], sr, tail_frames)
                           if ident in track_audio else layer)
        if track.get("kind") == "sample" and track.get("mode") == "loop":
            if project.get("mix_profile") == "targets-v1":
                processed_layer = _center_low_frequencies(processed_layer, sr)
            processed_layer = _highpass_at(processed_layer, sr, 120)
        if track.get("kind") == "bass" or (track.get("kind") == "sample" and track.get("mode") == "loop"):
            processed_layer = _duck_layer(processed_layer, kick_onsets, float(track.get("duck", 0)), sr, wrap=True)
        if balance_meter is not None:
            level = _layer_lufs(processed_layer, balance_meter)
            if level is not None:
                balance_levels[ident] = level
                role_hint = (cached_sample_role_hint(track, user_kit_dir)
                             if track.get("kind") == "sample" and not track.get("role") else None)
                role = track_role(track, role_hint=role_hint)
                if role:
                    balance_roles[ident] = role
            if (track.get("kind") == "sample" and track.get("mode") == "loop"
                    and np.any(processed_layer)):
                analysis = sample_analyses.get(ident, {})
                profile = analysis.get("profile", {})
                bands = profile.get("bands") if profile.get("pitched") else None
                if isinstance(bands, (list, tuple)) and len(bands) == 4:
                    sample_fit_profiles[ident] = {"bands": bands, "key": analysis.get("key")}
                    sample_fit_rhythms[ident] = _rendered_onset_profile(
                        processed_layer, sr, bpm, bars)
        mix += processed_layer

    if "flock" in project:
        from .flock.synth import render_flock

        if include_balance:
            flock_audio, render_metadata, slot_layers = render_flock(project, sr, include_slots=True)
            for ident, slot_layer in slot_layers.items():
                level = _layer_lufs(slot_layer["audio"], balance_meter)
                if level is not None:
                    balance_levels[ident] = level
                    balance_roles[ident] = slot_layer["role"]
        else:
            flock_audio, render_metadata = render_flock(project, sr)
        mix += flock_audio
        flock_has_audio = bool(np.any(flock_audio))
    else:
        from .flock.synth import compile_events

        render_metadata = compile_events(project, sr)
        flock_has_audio = False
    has_audio = any(track_audio.get(t["id"], ([],))[0] for t in audible) or flock_has_audio
    if balance_meter is not None:
        render_metadata["_balance_layers"] = {
            "levels": balance_levels, "roles": balance_roles,
            "sample_fit_profiles": sample_fit_profiles,
            "sample_fit_rhythms": sample_fit_rhythms,
        }
    if not has_audio:
        # Still resolve requested chains: a missing FX implementation must never
        # be reported as a successful render merely because its input is silent.
        master = project.get("master", {})
        master_chain = master.get("fx", []) or [] if isinstance(master, dict) else []
        if master_chain:
            _fx_chain(mix, master_chain, sr, tail_frames)
        return np.zeros((total, 2), dtype=np.float32), meters, render_metadata
    mix = _highpass(mix, sr)
    master = project.get("master", {})
    master_chain = master.get("fx", []) or [] if isinstance(master, dict) else []
    mix = np.asarray(_fx_chain(mix, master_chain, sr, tail_frames), dtype=np.float64)
    if mix.shape != (total, 2) or not np.all(np.isfinite(mix)):
        raise ValueError("FX processing returned invalid audio")
    # LUFS normalize, then apply a deterministic soft-knee saturation limiter if
    # required. Iterate the knee until both the loudness target and oversampled
    # true-peak ceiling are satisfied; this avoids global attenuation undoing LUFS.
    if fixed_gain is not None:
        # Stem export: the mix's own loudness gain, no limiter, no clipping (written as float WAV).
        return np.asarray(mix * float(fixed_gain), dtype=np.float32), meters, render_metadata
    meter = pyln.Meter(sr)
    loudness = float(meter.integrated_loudness(mix))
    if not math.isfinite(loudness):
        raise ValueError("cannot measure rendered audio loudness")
    target_gain = 10.0 ** ((-14.0 - loudness) / 20.0)
    normalized = mix * target_gain
    if isinstance(render_metadata, dict):
        render_metadata["master_gain"] = target_gain
    ceiling = 10.0 ** (-1.0 / 20.0)
    limited = None
    threshold = 1.0
    for _ in range(18):
        candidate = threshold * np.tanh(normalized / threshold)
        candidate_lufs = float(meter.integrated_loudness(candidate))
        if math.isfinite(candidate_lufs):
            candidate *= 10.0 ** ((-14.0 - candidate_lufs) / 20.0)
            true_peak = float(np.max(np.abs(resample_poly(candidate, 4, 1, axis=0))))
            if true_peak <= ceiling:
                limited = candidate
                break
        threshold *= 0.8
    if limited is None:
        raise ValueError("could not meet -14 LUFS and -1 dBTP within limiter bounds")
    mix = limited
    return np.asarray(np.clip(mix, -1.0, 1.0), dtype=np.float32), meters, render_metadata


def render_audio(project, sample_rate=SAMPLE_RATE, user_kit_dir=None):
    """Render a project to exact-length stereo float32 and per-track meters."""
    audio, meters, _ = _render_audio_with_metadata(project, sample_rate, user_kit_dir)
    return audio, meters


def _insert_linear(buffer, voice, start, gain, pan):
    if start >= len(buffer) or start < 0:
        return
    count = min(len(voice), len(buffer) - start)
    if count <= 0:
        return
    if np.ndim(voice) == 2:
        pan = min(1.0, max(-1.0, pan))
        balance = np.asarray([1.0 - max(0.0, pan), 1.0 + min(0.0, pan)])
        buffer[start:start + count] += voice[:count] * (balance * gain)
        return
    angle = (min(1.0, max(-1.0, pan)) + 1.0) * (math.pi / 4.0)
    buffer[start:start + count, 0] += voice[:count] * math.cos(angle) * gain
    buffer[start:start + count, 1] += voice[:count] * math.sin(angle) * gain


def _fx_chain_linear(audio, chain, sr):
    """Run a chain once with a non-wrapping processing tail beyond song end."""
    if not chain:
        return audio
    from .fx import apply_fx
    tail_frames = max(round(sr * 10), round(sr * 4 * 60 / 30))
    extended = np.concatenate((audio, np.zeros((tail_frames, audio.shape[1]), dtype=audio.dtype)))
    processed = np.asarray(apply_fx(extended, chain, sr))
    if processed.shape != extended.shape or not np.all(np.isfinite(processed)):
        raise ValueError("FX processing returned invalid audio")
    return processed[:len(audio)].copy()


def _normalize_song(mix, sr):
    if not np.any(mix):
        return np.asarray(mix, dtype=np.float32)
    meter = pyln.Meter(sr)
    loudness = float(meter.integrated_loudness(mix))
    if not math.isfinite(loudness):
        raise ValueError("cannot measure rendered audio loudness")
    normalized = mix * (10.0 ** ((-14.0 - loudness) / 20.0))
    ceiling = 10.0 ** (-1.0 / 20.0)
    threshold = 1.0
    for _ in range(18):
        candidate = threshold * np.tanh(normalized / threshold)
        candidate_lufs = float(meter.integrated_loudness(candidate))
        if math.isfinite(candidate_lufs):
            candidate *= 10.0 ** ((-14.0 - candidate_lufs) / 20.0)
            if float(np.max(np.abs(resample_poly(candidate, 4, 1, axis=0)))) <= ceiling:
                count = min(len(candidate), max(1, round(sr * _FADE_SECONDS)))
                candidate[-count:] *= np.linspace(1.0, 0.0, count, endpoint=True)[:, None]
                return np.asarray(np.clip(candidate, -1.0, 1.0), dtype=np.float32)
        threshold *= 0.8
    raise ValueError("could not meet -14 LUFS and -1 dBTP within limiter bounds")


def _render_song_audio(project, sample_rate=SAMPLE_RATE, user_kit_dir=None, *, fixed_gain=None):
    """Separate, linear song renderer. Legacy loop renderer above remains untouched."""
    factory_voice_cache = {}
    from .project import ValidationError, validate_project
    normalized = validate_project(project)
    if "arrangement" not in normalized:
        raise ValidationError("this project has no arrangement; add one with the arrange op")
    sr = int(sample_rate)
    if sr < 8000 or sr > 192000:
        raise ValueError("sample_rate must be between 8000 and 192000")
    bpm, bars = float(normalized["bpm"]), int(normalized["bars"])
    loop_frames = round(bars * 4 * 60 / bpm * sr)
    sections = normalized["arrangement"]["sections"]
    section_timings = []
    cursor = 0
    for section in sections:
        start = cursor
        cursor += loop_frames * section["repeat"]
        section_timings.append({"id": section["id"], "start_s": start / sr, "end_s": cursor / sr})
    total = cursor
    n_steps = bars * 16
    step_len = loop_frames / n_steps
    tracks = normalized["tracks"]
    solos = any(track.get("solo", False) for track in tracks)
    mix = np.zeros((total, 2), dtype=np.float64)
    meters = {}
    # Pass 1 collects every hit; pass 2 inserts them, so choke groups can cut a voice at the
    # next hit of another track in its group, like the loop path does (without wrapping).
    planned = []
    choke_events = {}
    kick_onsets = []
    section_offset = 0
    solo_tracks = any(track.get("solo", False) for track in tracks)
    for section in sections:
        section_muted = set(section["mute"])
        for repeat_index in range(section["repeat"]):
            for kick_track in tracks:
                if (kick_track.get("kind") != "drum" or not is_kick_source(kick_track.get("source"))
                        or kick_track.get("mute") or kick_track["id"] in section_muted
                        or (solo_tracks and not kick_track.get("solo"))):
                    continue
                section_steps, velocity, _notes = section_track_view(
                    normalized, section, kick_track, repeat_index)
                pattern = _patterns(section_steps, n_steps)
                for index, symbol in enumerate(pattern):
                    if symbol != "x" or float(velocity[index % len(velocity)]) <= 0:
                        continue
                    onset = section_offset + round(index * step_len)
                    if index % 2:
                        onset += round(float(normalized.get("swing", 0)) * step_len * .5)
                    kick_onsets.append(onset)
            section_offset += loop_frames
    for track in tracks:
        contributions = []
        allowed_global = not track.get("mute", False) and (not solos or track.get("solo", False))
        kind, source = track.get("kind", "drum"), str(track.get("source", "factory:kick_boom"))
        gain = 10 ** (float(track.get("gain_db", 0)) / 20)
        pan = float(track.get("pan", 0))
        loop_info = None
        has_user_sample = kind == "sample" or source.startswith("user:")
        if has_user_sample and track.get("mode") == "loop":
            sample, loop_info = _loop_sample(source, user_kit_dir, sr, normalized, track)
        elif has_user_sample:
            sample = _read_user_sample(source, user_kit_dir, sr)
        else:
            sample = None
        name = source.split(":", 1)[-1]
        if kind != "bass" and sample is None and name not in FACTORY_NAMES:
            raise ValueError(f"unsupported factory source: {source}")
        if kind == "bass" and name not in BASS_FACTORY_NAMES and name != "808":
            raise ValueError(f"unsupported bass source: {source}")
        section_cursor = 0
        for section in sections:
            muted = track["id"] in section["mute"] or not allowed_global
            for repeat_index in range(section["repeat"]):
                if not muted:
                    section_steps, velocities, notes = section_track_view(
                        normalized, section, track, repeat_index)
                    steps = _patterns(section_steps, n_steps)
                    if sample is not None and track.get("mode") == "loop":
                        bar_frames = loop_frames / bars
                        loop_bars = int(track.get("loop_bars", loop_info.get("bars", 1)))
                        bar_steps = section_steps
                        for bar in range(bars):
                            if bar_steps[bar % len(bar_steps)] != "x":
                                continue
                            offset = round((bar % loop_bars) * bar_frames)
                            length = round(bar_frames)
                            voice = sample[offset:offset + length]
                            start = section_cursor + round(bar * bar_frames)
                            velocity = float(velocities[bar % len(velocities)])
                            contributions.append((start, voice, gain * velocity))
                    elif kind == "bass":
                        for note in notes:
                            step = int(note["step"])
                            start = section_cursor + round(step * step_len)
                            if step % 2:
                                start += round(float(normalized.get("swing", 0)) * step_len * .5)
                            duration = min(30.0, max(.01, int(note.get("len", 1)) * step_len / sr))
                            transpose = float(track.get("pitch", 0))
                            midi = _note_midi(note.get("pitch", "C1")) + transpose
                            hz = _note_hz(midi)
                            if name in BASS_FACTORY_NAMES and name != "808":
                                voice = _cached_synthesize(
                                    factory_voice_cache, name, sr=sr,
                                    seed=int(normalized.get("seed", 1337)), pitch=transpose,
                                    duration=duration, note_hz=hz,
                                )
                            else:
                                count = round(duration * sr)
                                time = np.arange(count, dtype=np.float64) / sr
                                voice = np.asarray(np.tanh(1.15 * np.sin(2 * np.pi * hz * time))
                                                   * np.exp(-time / max(duration * 1.8, .08)) * .85, dtype=np.float32)
                            contributions.append((start, _fade_voice(voice, sr),
                                                  gain * float(velocities[step % len(velocities)])))
                    else:
                        for i, symbol in enumerate(steps):
                            if symbol == ".":
                                continue
                            start = section_cursor + round(i * step_len)
                            if i % 2:
                                start += round(float(normalized.get("swing", 0)) * step_len * .5)
                            velocity = float(velocities[i % len(velocities)])
                            if sample is not None:
                                slices = max(1, int(track.get("slices", 1)))
                                index = 0 if symbol == "x" else int(symbol) % slices
                                voice = sample[round(len(sample) * index / slices):round(len(sample) * (index + 1) / slices)]
                            else:
                                voice = _cached_synthesize(
                                    factory_voice_cache, name, sr=sr,
                                    seed=int(normalized.get("seed", 1337)), pitch=track.get("pitch", 0),
                                )
                            contributions.append((start, _fade_voice(voice, sr), gain * velocity))
                            if track.get("choke_group") and sample is None:
                                choke_events.setdefault(track["choke_group"], []).append((start, track["id"]))
                section_cursor += loop_frames
        planned.append((track, contributions, pan))
    for track, contributions, pan in planned:
        layer = np.zeros_like(mix)
        group = track.get("choke_group")
        stop_list = [start for start, owner in choke_events.get(group, []) if owner != track["id"]] if group else []
        if (track.get("kind") == "sample" or str(track.get("source", "")).startswith("user:")) and track.get("mode") != "loop":
            # Sampler behaviour, as in the loop path: a hit plays until this track's next hit.
            stop_list += [start for start, _voice, _level in contributions]
        stops = np.array(sorted(set(stop_list)), dtype=np.int64)
        for start, voice, level in contributions:
            if stops.size:
                index = int(np.searchsorted(stops, start, side="right"))
                if index < stops.size and stops[index] - start < len(voice):
                    length = int(stops[index] - start)
                    voice = voice[:length].copy()
                    fade = min(length, max(1, round(sr * _FADE_SECONDS)))
                    voice[-fade:] *= np.linspace(1, 0, fade, endpoint=True, dtype=np.float32)
            if len(voice):
                _insert_linear(layer, voice, start, level, pan)
        loop_sample = track.get("kind") == "sample" and track.get("mode") == "loop"
        if loop_sample:
            if normalized.get("mix_profile") == "targets-v1":
                layer = _center_low_frequencies(layer, sr)
            layer = _highpass_at(layer, sr, 120)
        if track.get("kind") == "bass" or loop_sample:
            layer = _duck_layer(layer, kick_onsets, float(track.get("duck", 0)), sr)
        meters[track["id"]] = {"rms_db": _db(np.sqrt(np.mean(layer * layer))) if np.any(layer) else -120.0,
                               "peak_db": _db(np.max(np.abs(layer))) if np.any(layer) else -120.0}
        mix += _fx_chain_linear(layer, track.get("fx", []) or [], sr)
    from .flock.synth import render_song_flock
    flock_audio, metadata = render_song_flock(normalized, sections, sr, kick_onsets)
    mix += flock_audio
    mix = _highpass_linear(mix, sr)
    master_chain = normalized.get("master", {}).get("fx", []) or []
    mix = _fx_chain_linear(mix, master_chain, sr)
    if fixed_gain is not None:
        return np.asarray(mix * float(fixed_gain), dtype=np.float32), meters, metadata, section_timings
    audio = _normalize_song(np.asarray(mix, dtype=np.float64), sr)
    if isinstance(metadata, dict) and np.any(mix):
        metadata["master_gain"] = 10.0 ** ((-14.0 - float(pyln.Meter(sr).integrated_loudness(mix))) / 20.0)
    return audio, meters, metadata, section_timings


def render_song_audio(project, sample_rate=SAMPLE_RATE, user_kit_dir=None):
    return _render_song_audio(project, sample_rate, user_kit_dir)


def wav_bytes(audio, sample_rate=SAMPLE_RATE, subtype="PCM_24"):
    """Encode deterministic WAV bytes (no timestamps or dither)."""
    array = np.asarray(audio, dtype=np.float32)
    if array.ndim != 2 or array.shape[1] != 2 or not np.all(np.isfinite(array)):
        raise ValueError("audio must be finite stereo frames")
    buffer = io.BytesIO()
    sf.write(buffer, array, int(sample_rate), format="WAV", subtype=subtype, endian="LITTLE")
    return buffer.getvalue()


def _content_hash(project):
    from .project import project_hash
    return project_hash(project, RENDERER_VERSION)


def render_project(project, output_dir, user_kit_dir=None, song=False):
    if song:
        from .project import validate_project

        audio, meters, render_metadata, sections = _render_song_audio(project, SAMPLE_RATE, user_kit_dir)
        content = hashlib.sha256((_content_hash(project) + ":song:" + repr(sections) +
                                  repr(project.get("arrangement"))).encode("utf-8")).hexdigest()
    else:
        audio, meters, render_metadata = _render_audio_with_metadata(
            project, SAMPLE_RATE, user_kit_dir, include_balance=True)
        sections = None
        content = _content_hash(project)
    data = wav_bytes(audio, SAMPLE_RATE, "PCM_24")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    destination = out / f"{content}.wav"
    fd, temporary = tempfile.mkstemp(prefix=f".{content}.", suffix=".tmp", dir=out)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    result = {"path": str(destination), "hash": content, "wav_hash": hashlib.sha256(data).hexdigest(),
            "meters": meters, "mix": mix_report(audio, SAMPLE_RATE),
            "duration_samples": len(audio), "sample_rate": SAMPLE_RATE,
            "flock_events": render_metadata["flock_events"],
            "kick_onsets": render_metadata["kick_onsets"],
            "flock_active_combos": render_metadata["flock_active_combos"],
            **({"song": True, "sections": sections,
                "variety": arrangement_variety(validate_project(project))} if song else {})}
    if not song:
        result.update(_balance_response(project, render_metadata.get("_balance_layers", {})))
    return result


# Acceptance-API compatibility aliases.
def render(project):
    return render_audio(project, SAMPLE_RATE)[0]


def content_hash(project):
    return _content_hash(project)


def write_wav(path, audio, sr=SR):
    Path(path).write_bytes(wav_bytes(audio, sr))
