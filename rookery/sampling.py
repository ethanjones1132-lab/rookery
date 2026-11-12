"""Deterministic analysis and fit helpers for imported audio loops."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import find_peaks, welch

_KEYS = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
_NAMES = {"C": 0, "B#": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3,
          "E": 4, "FB": 4, "F": 5, "E#": 5, "F#": 6, "GB": 6, "G": 7,
          "G#": 8, "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11}
_PITCHED_CHROMA_FLATNESS_MAX = .9  # diffuse chroma near 1 is unpitched noise/percussion
_DENSE_ONSETS_PER_BAR = 4  # roughly one detected onset per beat
_BPM_RE = re.compile(r"(?<!\d)(\d{2,3})[\s_-]*(?:bpm|beats\s*per\s*minute)\b", re.I)
_NOKEY_RE = re.compile(r"(?<![a-z])nokey(?![a-z])", re.I)
_PITCHED_TITLE_RE = re.compile(r"(?<![a-z])(vocal|voice|singer|singing|choir)(?![a-z])", re.I)
_KEY_RE = re.compile(r"(?<![A-Za-z])([A-Ga-g])\s*([#b]?)[\s_-]*(major|maj|minor|min|m)?(?![A-Za-z])", re.I)
_ANALYSIS_CACHE_VERSION = 5
_BAR_COUNTS = (1, 2, 4, 8, 16)
_PROJECT_TEMPO_TOLERANCE = 0.20


def parse_title(text: str) -> dict:
    bpm_match = _BPM_RE.search(text or "")
    bpm = int(bpm_match.group(1)) if bpm_match and 30 <= int(bpm_match.group(1)) <= 300 else None
    key = None
    # Require a mode suffix for bare A-G to avoid interpreting ordinary words as keys.
    for match in _KEY_RE.finditer(text or ""):
        letter, accidental, mode = match.groups()
        if not mode:
            continue
        name = (letter + accidental).upper()
        if name in _NAMES:
            key = f"{_KEYS[_NAMES[name]]} {'minor' if mode.lower() in {'m', 'min', 'minor'} else 'major'}"
            break
    if key is None:
        # Handle explicit minor shorthand such as F#m and Am.
        match = re.search(r"(?<![A-Za-z])([A-Ga-g])([#b]?)m(?![A-Za-z])", text or "")
        if match:
            name = (match.group(1) + match.group(2)).upper()
            if name in _NAMES:
                key = f"{_KEYS[_NAMES[name]]} minor"
    return {"bpm": bpm, "key": key}


def _onset_envelope(audio: np.ndarray, sr: int) -> tuple[np.ndarray, int]:
    hop = max(1, round(sr * 0.01))
    mono = np.mean(audio, axis=1, dtype=np.float64) if audio.ndim > 1 else audio.astype(np.float64)
    frames = len(mono) // hop
    if not frames:
        return np.zeros(0), hop
    framed = mono[:frames * hop].reshape(frames, hop)
    rms = np.sqrt(np.mean(framed * framed, axis=1))
    novelty = np.maximum(0, np.diff(rms, prepend=rms[0]))
    return novelty, hop


def _estimate_bpm(audio: np.ndarray, sr: int, project_bpm: float | None) -> tuple[float | None, float]:
    env, hop = _onset_envelope(audio, sr)
    if len(env) < 8 or not np.any(env):
        return None, 0.0
    env = env - env.mean()
    corr = np.correlate(env, env, mode="full")[len(env)-1:]
    lo = max(1, round(60 * sr / (180 * hop)))
    hi = min(len(corr) - 1, round(60 * sr / (70 * hop)))
    if hi <= lo:
        return None, 0.0
    local = corr[lo:hi + 1]
    peaks, _ = find_peaks(local)
    candidates = (peaks + lo).tolist()
    candidates += [int(np.argmax(local)) + lo]
    scored = []
    for lag in candidates:
        bpm = 60 * sr / (lag * hop)
        score = corr[lag] / max(corr[0], 1e-12)
        if project_bpm:
            variants = (bpm, bpm * 2, bpm / 2)
            distance = min(abs(math.log(v / project_bpm)) for v in variants if 70 <= v <= 180)
            score *= 1.15 if distance < 0.035 else 1.0
        scored.append((score, bpm))
    score, bpm = max(scored)
    if project_bpm:
        bpm = min((bpm, bpm * 2, bpm / 2), key=lambda v: abs(math.log(v / project_bpm)) if 30 <= v <= 300 else float("inf"))
    return float(round(bpm, 2)), float(max(0, min(1, score * 4)))


def _chroma(audio: np.ndarray, sr: int) -> np.ndarray:
    mono = np.mean(audio, axis=1, dtype=np.float64) if audio.ndim > 1 else audio.astype(np.float64)
    if len(mono) < 2048 or not np.any(mono):
        return np.zeros(12, dtype=np.float64)
    n = 2 ** int(math.ceil(math.log2(min(len(mono), sr * 2))))
    windowed = np.zeros(n, dtype=np.float64)
    windowed[:min(n, len(mono))] = mono[:n] * np.hanning(min(n, len(mono)))
    spectrum = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(n, 1 / sr)
    valid = (freqs >= 40) & (freqs <= 5000)
    midi = np.rint(69 + 12 * np.log2(np.maximum(freqs[valid], 1e-9) / 440)).astype(int)
    chroma = np.zeros(12)
    np.add.at(chroma, midi % 12, spectrum[valid])
    return chroma


def _estimate_key_from_chroma(chroma: np.ndarray) -> tuple[str | None, float]:
    if np.linalg.norm(chroma) == 0:
        return None, 0.0
    chroma = (chroma - chroma.mean()) / (chroma.std() + 1e-12)
    scores = []
    for root in range(12):
        scores.append((float(np.dot(chroma, np.roll(_MAJOR, root))), root, "major"))
        scores.append((float(np.dot(chroma, np.roll(_MINOR, root))), root, "minor"))
    scores.sort(reverse=True)
    best, root, mode = scores[0]
    confidence = (best - scores[1][0]) / (abs(best) + 1e-12)
    return f"{_KEYS[root]} {mode}", float(max(0, min(1, confidence)))


def _chroma_flatness(chroma: np.ndarray) -> float:
    if not np.any(chroma):
        return 1.0
    epsilon = max(float(chroma.max()) * 1e-12, 1e-12)
    values = chroma + epsilon
    return float(np.exp(np.mean(np.log(values))) / np.mean(values))


def _register_profile(mono: np.ndarray, sr: int) -> tuple[str, float, list[float]]:
    if not len(mono) or not np.any(mono):
        return "mid", 0.0, [0.0, 0.0, 0.0, 0.0]
    nperseg = min(len(mono), max(1, sr))
    frequencies, power = welch(mono, fs=sr, nperseg=nperseg,
                               noverlap=min(nperseg // 2, nperseg - 1), scaling="spectrum")
    masks = (
        frequencies < 250,
        (frequencies >= 250) & (frequencies < 800),
        (frequencies >= 800) & (frequencies <= 3000),
        frequencies > 3000,
    )
    energies = np.asarray([float(power[mask].sum()) for mask in masks])
    total = float(energies.sum())
    if total <= 0:
        return "mid", 0.0, [0.0, 0.0, 0.0, 0.0]
    fractions = energies / total
    centroid = float(np.dot(frequencies, power) / max(float(power.sum()), 1e-30))
    register = ("low", "low_mid", "mid", "high")[int(np.argmax(energies))]
    return register, round(centroid, 1), [round(float(value), 4) for value in fractions]


def _rhythm_profile(envelope: np.ndarray, hop: int, sr: int, bpm: float | None,
                    bars: int, peaks: np.ndarray) -> tuple[str, float, int]:
    if not bpm or bpm <= 0 or not len(envelope) or bars <= 0:
        return "0" * 16, 0.0, 0
    step_seconds = 15.0 / bpm
    strengths = np.zeros((bars, 16), dtype=np.float64)
    # Onset-envelope values summarize each hop; use their centers so a peak
    # near a sixteenth boundary is assigned to the correct slot.
    peak_times = (peaks * hop + hop / 2) / sr
    for bar in range(bars):
        for step in range(16):
            start = (bar * 16 + step) * step_seconds
            end = start + step_seconds
            in_step = (peak_times >= start) & (peak_times < end)
            if np.any(in_step):
                strengths[bar, step] = float(envelope[peaks[in_step]].max())
    mean_strengths = strengths.mean(axis=0)
    strongest = float(mean_strengths.max())
    if strongest > 0:
        digits = np.rint(mean_strengths / strongest * 9).astype(int)
        rhythm = "".join(str(int(value)) for value in digits)
    else:
        rhythm = "0" * 16
    density = round(float(len(peaks)) / bars, 2)
    busy_steps = sum(char >= "5" for char in rhythm)
    return rhythm, density, busy_steps


def _sample_profile(mono: np.ndarray, sr: int, chroma: np.ndarray,
                    envelope: np.ndarray, hop: int, frame_rms: np.ndarray,
                    peaks: np.ndarray, bpm: float | None, bars: int,
                    *, pitched_hint: bool = False, force_unpitched: bool = False) -> dict:
    register, centroid_hz, bands = _register_profile(mono, sr)
    peak_rms = float(frame_rms.max()) if len(frame_rms) else 0.0
    sustain = (float(np.mean(frame_rms >= peak_rms * .1))
               if peak_rms > 0 else 0.0)
    sustain = round(sustain, 3)
    rhythm_peaks = peaks
    rhythm_envelope = envelope
    if peak_rms > 0 and len(frame_rms) and frame_rms[0] >= peak_rms * .15:
        # diff(rms[0]) is zero by construction; count a genuine downbeat attack
        # explicitly and fold any nearby detector peak into that same event.
        first_window = min(.05, 7.5 / bpm) if bpm else .05
        peak_times = (peaks * hop + hop / 2) / sr
        rhythm_peaks = np.r_[0, peaks[peak_times >= first_window]]
        rhythm_envelope = envelope.copy()
        rhythm_envelope[0] = max(float(rhythm_envelope[0]), float(frame_rms[0]))
    rhythm, density, busy_steps = _rhythm_profile(
        rhythm_envelope, hop, sr, bpm, bars, rhythm_peaks)
    # Explicit key metadata is stronger evidence than a diffuse spectral chroma:
    # strummed guitars and vocal loops often smear pitch across many bins.
    pitched = (not force_unpitched
               and (pitched_hint or _chroma_flatness(chroma) < _PITCHED_CHROMA_FLATNESS_MAX))
    if pitched:
        if sustain >= .55 and register in {"low_mid", "mid"}:
            role_hint = "bed"
        elif register in {"mid", "high"} and sustain < .55:
            role_hint = "lead"
        else:
            role_hint = "counter"
    else:
        role_hint = "drums" if density >= _DENSE_ONSETS_PER_BAR else "texture"
    return {"register": register, "centroid_hz": centroid_hz, "bands": bands,
            "rhythm": rhythm, "density": density, "busy_steps": busy_steps,
            "sustain": sustain, "pitched": pitched, "role_hint": role_hint}


def analyze(path: str | Path, *, title: str | None = None, project_bpm: float | None = None) -> dict:
    """Analyze file; cache metadata next to files under a library directory."""
    path = Path(path)
    size = path.stat().st_size
    cache_path = path.parent / "analysis.json"
    is_library = path.parent.name.lower() == "library"
    cache_project_bpm = round(float(project_bpm), 6) if project_bpm is not None else None
    if is_library:
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            entry = cache.get(path.name, {}) if isinstance(cache, dict) else {}
            if (isinstance(entry, dict) and entry.get("size") == size
                    and entry.get("analysis_version") == _ANALYSIS_CACHE_VERSION
                    and entry.get("project_bpm") == cache_project_bpm
                    and isinstance(entry.get("analysis"), dict)
                    and isinstance(entry["analysis"].get("profile"), dict)
                    and "bar_aligned" in entry["analysis"]):
                return entry["analysis"]
        except (OSError, ValueError, TypeError):
            cache = {}
    parsed = parse_title(title or path.name)
    audio, sr = sf.read(path, dtype="float32", always_2d=True)
    mono = audio.mean(axis=1)
    envelope, hop = _onset_envelope(mono, sr)
    peaks, _ = find_peaks(envelope, distance=max(1, round(0.08 * sr / hop)), prominence=max(float(envelope.max()) * .12, 1e-8)) if len(envelope) else ([], {})
    peaks = np.asarray(peaks, dtype=int)
    initial_frames = max(1, round(.05 * sr / hop))
    initial_rms = float(np.sqrt(np.mean(mono[:min(len(mono), initial_frames * hop)].astype(np.float64) ** 2)))
    frame_rms = np.sqrt(np.mean((mono[:len(mono) // hop * hop].reshape(-1, hop).astype(np.float64)) ** 2, axis=1)) if len(mono) >= hop else np.zeros(0)
    if len(frame_rms) and initial_rms >= float(frame_rms.max()) * .15:
        downbeat = 0.0
    else:
        downbeat = float(peaks[0] * hop / sr) if len(peaks) else 0.0
    estimated, bpm_conf = _estimate_bpm(mono, sr, project_bpm)
    bpm = parsed["bpm"] or estimated
    bpm_source = "title" if parsed["bpm"] else ("audio" if estimated else "unknown")
    chroma = _chroma(mono, sr)
    estimated_key, key_conf = _estimate_key_from_chroma(chroma)
    key = parsed["key"] or estimated_key
    key_source = "title" if parsed["key"] else ("audio" if estimated_key else "unknown")
    if _NOKEY_RE.search(title or path.name):
        # Unpitched material (drums, percussion) named "nokey" by its importer: a detected
        # key would only make loop-mode key lock detune it.
        key, key_source = None, "none"
    bars = 1
    bar_aligned = False
    if bpm:
        duration = len(mono) / sr
        # A project's tempo can disambiguate a half/double-time onset estimate.
        # Compare exact integer-bar tempos from duration rather than trusting the
        # autocorrelation peak alone (which often follows the snare or every other
        # kick). Only prefer the project-near candidate when it is musically close;
        # otherwise keep the audio/title estimate for normal time stretching.
        duration_choice = None
        if not parsed["bpm"] and project_bpm and duration > 0:
            choices = [(abs(math.log((candidate_bars * 240 / duration) / project_bpm)),
                        candidate_bars, candidate_bars * 240 / duration)
                       for candidate_bars in _BAR_COUNTS
                       if 30 <= candidate_bars * 240 / duration <= 300]
            if choices:
                distance, candidate_bars, candidate_bpm = min(choices)
                if distance <= math.log1p(_PROJECT_TEMPO_TOLERANCE):
                    duration_choice = (candidate_bars, candidate_bpm)

        if duration_choice is not None:
            bars, bpm = duration_choice[0], duration_choice[1]
            bar_aligned = True
            downbeat = 0.0
        else:
            bar_count = duration * bpm / 240
            bars = min(_BAR_COUNTS, key=lambda candidate: abs(candidate - bar_count))
            # A file that is a whole number of bars long was cut on its downbeat: a quiet
            # start is a musical rest (a lead answering on the "and"), not lead-in silence.
            # Trimming it would move the phrase onto the beat and break call and response.
            bar_aligned = abs(bar_count - bars) <= .03 * bars
            if bar_aligned:
                downbeat = 0.0
            # The onset envelope has 10 ms resolution, so its autocorrelation estimate
            # can be several tenths of a BPM off. Once the duration identifies an
            # integer musical phrase, its exact bar length is a much better tempo
            # measurement (and prevents cumulative stretch drift across the phrase).
            if bpm_source == "audio" and bar_aligned and len(mono):
                bpm = bars * 240 * sr / len(mono)
    confidence = (max(bpm_conf, .85 if bpm_source == "title" else 0) + max(key_conf, .85 if key_source == "title" else 0)) / 2
    key_confidence = (.85 if key_source == "title" else key_conf if key_source == "audio" else 0.0)
    title_text = title or path.name
    force_unpitched = bool(_NOKEY_RE.search(title_text))
    pitched_hint = (not force_unpitched and
                    (parsed["key"] is not None or bool(_PITCHED_TITLE_RE.search(title_text))))
    profile = _sample_profile(mono, sr, chroma, envelope, hop, frame_rms, peaks, bpm, bars,
                              pitched_hint=pitched_hint, force_unpitched=force_unpitched)
    result = {"bpm": bpm, "bpm_source": bpm_source, "key": key, "key_source": key_source,
              "key_confidence": round(float(key_confidence), 3),
              "downbeat_s": round(downbeat, 6), "bar_aligned": bool(bar_aligned),
              "bars": bars, "confidence": round(float(confidence), 3),
              "profile": profile}
    if is_library:
        cache = cache if isinstance(cache, dict) else {}
        cache[path.name] = {"size": size, "analysis_version": _ANALYSIS_CACHE_VERSION,
                            "project_bpm": cache_project_bpm, "analysis": result}
        try:
            cache_path.write_text(json.dumps(cache, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        except OSError:
            # User-supplied kit libraries can be deliberately read-only.
            pass
    return result


def key_fit(sample_key: str | None, target_key: str | None) -> float:
    if not sample_key or not target_key:
        return .5
    a, b = parse_title(sample_key)["key"], parse_title(target_key)["key"]
    if a is None:
        a = f"{sample_key.strip()} major" if sample_key.strip().upper() in _NAMES else None
    if b is None:
        b = f"{target_key.strip()} major" if target_key.strip().upper() in _NAMES else None
    if not a or not b:
        return .5
    def pc(value):
        token = value.split()[0].upper()
        return _NAMES.get(token)
    a_pc, b_pc = pc(a), pc(b)
    if a_pc == b_pc:
        return 1.0
    if (a_pc - b_pc) % 12 in (3, 9) and a.split()[-1] != b.split()[-1]:
        return .85
    if (a_pc - b_pc) % 12 in (5, 7):
        return .75
    return .1


def has_confident_key(analysis: dict) -> bool:
    """Whether automatic key lock should trust this analysis' key estimate."""
    if not isinstance(analysis, dict) or not analysis.get("key"):
        return False
    if analysis.get("key_source") == "title":
        return True
    if "key_confidence" not in analysis:
        # Compatibility for legacy cached/test analysis that predates the field.
        return True
    confidence = analysis.get("key_confidence")
    return (isinstance(confidence, (int, float)) and not isinstance(confidence, bool)
            and math.isfinite(float(confidence)) and float(confidence) >= .5)


def key_lock_shift(sample_key: str | None, target_key: str | None,
                   target_scale: str = "major") -> int | None:
    """Return the renderer's loop key-lock shift, or None when either key is unknown."""
    if not sample_key or not target_key:
        return None
    from .render import _key_lock_interval
    return int(_key_lock_interval(sample_key, target_key, target_scale))


__all__ = ["analyze", "parse_title", "key_fit", "has_confident_key", "key_lock_shift"]
