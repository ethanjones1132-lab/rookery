"""Judge a local audio file against Rookery's sample quality gate.

The thresholds, reject/flag split and wording live in
``docs/design/research/sample-sources.md`` section 7. This module is the one
implementation of them: ``tools/sample_quality.py`` and the sample fetch paths
all call it rather than measuring twice.

    from rookery.sample_gate import assess, assess_bytes
    result = assess("kick.flac", kind="one-shot")
    result["verdict"]       # "pass" | "flag" | "reject"
    result["reasons"]       # plain words, only when rejected
    result["warnings"]      # plain words, may be non-empty on a pass
    result["metrics"]       # JSON-safe measurements

Pure, offline and deterministic: numpy, soundfile and the same loudness call
``rookery/checks.py`` uses. No network, no writes, no ``ffprobe``. At most the
first 60 s of a file are decoded.
"""

from __future__ import annotations

import io
import math
from pathlib import Path

import numpy as np
import pyloudnorm as pyln
import soundfile as sf

# --- Thresholds (sample-sources.md §7.1) -------------------------------------
MIN_SAMPLE_RATE = 44100
MIN_BIT_DEPTH = 16
MAX_CHANNELS = 2
PREFERRED_SAMPLE_RATE = 48000
CLIP_LEVEL = 0.999
CLIP_RUN = 3                      # a run of >=3 full-scale samples is hard clipping
MAX_CLIPPED_FRACTION = 0.0005     # >0.05% of samples at full scale is clipping
LOOP_BANDWIDTH_FLOOR_HZ = 8000    # hard floor for loops
LOOP_BANDWIDTH_FULL_HZ = 19000    # advisory for loops
ONESHOT_BANDWIDTH_FULL_HZ = 16000  # advisory for one-shots
MAX_NOISE_FLOOR_DBFS = -45.0
MIN_LUFS = -22.0
MAX_LUFS = -6.0
MIN_CREST_DB = 4.0
MAX_CREST_DB = 24.0
MIN_BARS = 1
MAX_BARS = 16
BAR_TOLERANCE_S = 0.025           # 25 ms
BAR_TOLERANCE_RATIO = 0.02        # or 2% of one bar, whichever is larger
MAX_READ_SECONDS = 60.0

LOSSLESS_FORMATS = {"WAV", "WAVEX", "AIFF", "AIFC", "FLAC"}
LOSSY_FORMATS = {"MP3", "MP2", "MPEG", "AAC", "OGG", "OPUS", "WMA", "AC3"}
LOSSY_SUBTYPE_TAGS = ("MPEG", "VORBIS", "OPUS", "AAC")
LOSSY_SUFFIXES = {".mp3", ".mp2", ".ogg", ".oga", ".opus", ".aac", ".m4a", ".wma", ".ac3"}
SUFFIX_FORMATS = {".wav": "WAV", ".aif": "AIFF", ".aiff": "AIFF", ".flac": "FLAC"}
BIT_DEPTHS = {
    "PCM_S8": 8, "PCM_U8": 8,
    "PCM_16": 16, "PCM_24": 24, "PCM_32": 32,
    "FLOAT": 32, "DOUBLE": 64,
}


def assess(path, *, kind=None, bpm=None, bars=None) -> dict:
    """Measure one local audio file and judge it.

    kind: "loop" | "one-shot" | None.
    bpm and bars: the stated tempo and length, when known, so a loop can be
    checked for whole bars.
    """
    _validate(kind, bpm, bars)
    source = str(path)
    suffix = Path(source).suffix
    info = _info(source, suffix)
    if info is None:
        return _undecodable(suffix)
    audio, sample_rate = _read(source, info.samplerate)
    return _judge(info, audio, sample_rate, suffix, kind=kind, bpm=bpm, bars=bars)


def assess_bytes(raw: bytes, suffix: str, **kw) -> dict:
    """The same judgement for bytes that have not been written to disk."""
    if not isinstance(raw, (bytes, bytearray, memoryview)):
        raise TypeError("raw must be bytes")
    _validate(kw.get("kind"), kw.get("bpm"), kw.get("bars"))
    hint = suffix.strip() if isinstance(suffix, str) else ""
    if hint and not hint.startswith("."):
        hint = "." + hint
    info = _info(io.BytesIO(bytes(raw)), hint)
    if info is None:
        return _undecodable(hint)
    audio, sample_rate = _read(io.BytesIO(bytes(raw)), info.samplerate)
    return _judge(info, audio, sample_rate, hint, **kw)


# --- Internals ---------------------------------------------------------------

def _validate(kind, bpm, bars) -> None:
    if kind not in (None, "loop", "one-shot"):
        raise ValueError('kind must be "loop", "one-shot" or None')
    if bpm is not None:
        if (isinstance(bpm, bool)
                or not isinstance(bpm, (int, float, np.integer, np.floating))
                or not math.isfinite(bpm) or bpm <= 0):
            raise ValueError("bpm must be a positive number")
    if bars is not None:
        if (isinstance(bars, bool)
                or not isinstance(bars, (int, float, np.integer, np.floating))
                or not math.isfinite(bars) or bars <= 0):
            raise ValueError("bars must be a positive number")


def _info(source, suffix: str):
    """sf.info, but a known-lossy suffix that libsndfile cannot decode is a reject.

    Some builds can read MP3 but not AAC/M4A; refusing by suffix keeps the gate
    from crashing on exactly the files it must never accept.
    """
    try:
        return sf.info(source)
    except (RuntimeError, ValueError):
        if (suffix or "").lower() in LOSSY_SUFFIXES:
            return None
        raise


def _undecodable(suffix: str) -> dict:
    fmt = (suffix or "").lstrip(".").upper() or "unknown"
    return {
        "verdict": "reject",
        "reasons": [f"lossy codec ({fmt}): libsndfile cannot decode it, "
                    "and Rookery will not import a lossy preview"],
        "warnings": [],
        "metrics": {
            "format": fmt, "subtype": "unknown", "sample_rate": 0, "channels": 0,
            "bit_depth": None, "seconds": 0.0, "peak_dbfs": None, "clipped_runs": 0,
            "bandwidth_khz": 0.0, "noise_floor_dbfs": None, "lufs": None,
            "crest_db": None, "bars_measured": None,
        },
    }


def _read(source, sample_rate: int) -> tuple[np.ndarray, int]:
    """Read at most the first MAX_READ_SECONDS of audio."""
    limit = int(sample_rate * MAX_READ_SECONDS) if sample_rate else -1
    data, rate = sf.read(source, frames=limit if limit > 0 else -1,
                         dtype="float32", always_2d=True)
    return np.asarray(data, dtype=np.float32), int(rate)


def _bit_depth(subtype: str) -> int | None:
    return BIT_DEPTHS.get((subtype or "").upper())


def _is_lossy(fmt: str, subtype: str, suffix: str) -> bool:
    fmt_u, sub_u, suffix_u = (fmt or "").upper(), (subtype or "").upper(), (suffix or "").lower()
    if any(tag in sub_u for tag in LOSSY_SUBTYPE_TAGS):
        return True
    if fmt_u in LOSSY_FORMATS or suffix_u in LOSSY_SUFFIXES:
        return True
    # §7.1 accepts only WAV/AIFF/FLAC containers; anything else is unusable.
    return fmt_u not in LOSSLESS_FORMATS


def _frame_matrix(mono: np.ndarray, size: int) -> np.ndarray:
    """Split mono into whole frames, zero-padding a file shorter than one frame."""
    size = max(1, size)
    if len(mono) < size:
        padded = np.zeros(size, dtype=np.float64)
        padded[: len(mono)] = mono
        return padded.reshape(1, size)
    count = len(mono) // size
    return mono[: count * size].reshape(count, size)


def _long_term_spectrum(mono: np.ndarray, sample_rate: int) -> tuple[np.ndarray, np.ndarray]:
    """Average spectrum of audible frames, in dB relative to the loudest bin.

    Only 50 ms frames within 40 dB of the loudest frame are averaged, so a
    one-shot's decay tail and codec silence cannot define the bandwidth
    (sample-sources.md §2.1).
    """
    size = max(8, int(sample_rate * 0.05))
    framed = _frame_matrix(mono, size)
    rms = np.sqrt(np.mean(framed * framed, axis=1))
    if not np.any(rms):
        return np.fft.rfftfreq(size, 1 / sample_rate), np.zeros(size // 2 + 1)
    keep = rms >= rms.max() * 10 ** (-40 / 20)
    window = np.hanning(size)
    acc = np.zeros(size // 2 + 1)
    for frame in framed[keep]:
        acc += np.abs(np.fft.rfft(frame * window)) ** 2
    power = acc / max(1, int(keep.sum()))
    freqs = np.fft.rfftfreq(size, 1 / sample_rate)
    db = 10 * np.log10(np.maximum(power, 1e-30))
    db -= db.max()
    return freqs, db


def _bandwidth(freqs: np.ndarray, db: np.ndarray) -> float:
    """Highest frequency still within 60 dB of the strongest bin."""
    if not len(db):
        return 0.0
    smooth = np.convolve(db, np.ones(5) / 5, mode="same")
    above = np.flatnonzero(smooth >= -60.0)
    return float(freqs[above[-1]]) if len(above) else 0.0


def _frames(mono: np.ndarray, sample_rate: int, seconds: float) -> np.ndarray:
    size = max(1, int(sample_rate * seconds))
    if len(mono) < size:
        return np.array([np.sqrt(np.mean(mono.astype(np.float64) ** 2))]) if len(mono) else np.zeros(1)
    count = len(mono) // size
    return np.sqrt(np.mean(mono[: count * size].reshape(count, size).astype(np.float64) ** 2, axis=1))


def _db(value: float) -> float:
    return 20 * math.log10(max(float(value), 1e-12))


def _lufs(mono: np.ndarray, sample_rate: int) -> float | None:
    # Same meter as rookery/checks.py; short files fall back to RMS rather than
    # dropping the metric.
    if not len(mono):
        return None
    try:
        meter = pyln.Meter(sample_rate, block=0.4)
        value = float(meter.integrated_loudness(mono.astype(np.float64)))
        if math.isfinite(value):
            return round(value, 2)
    except (ValueError, ZeroDivisionError, TypeError):
        pass
    return round(_db(np.sqrt(np.mean(mono.astype(np.float64) ** 2))) - 3.0, 2)


def _clipping(mono: np.ndarray) -> tuple[float, int, float]:
    if not len(mono):
        return _db(0.0), 0, 0.0
    peak = float(np.max(np.abs(mono)))
    hot = np.abs(mono) >= CLIP_LEVEL
    fraction = float(np.mean(hot))
    # Count runs of >=3 consecutive full-scale samples: hard clipping, not a
    # transient (§7.1).
    padded = np.concatenate(([False], hot, [False]))
    edges = np.flatnonzero(np.diff(padded.astype(np.int8)))
    starts, ends = edges[0::2], edges[1::2]
    runs = int(np.count_nonzero((ends - starts) >= CLIP_RUN))
    return _db(peak), runs, fraction


def _noise_floor(mono: np.ndarray, sample_rate: int) -> float | None:
    """10th-percentile 200 ms frame RMS, only when the file has silence."""
    if not len(mono):
        return None
    frames = _frames(mono, sample_rate, 0.2)
    if not len(frames):
        return None
    frame_db = 20 * np.log10(np.maximum(frames, 1e-12))
    if frame_db.min() > -50.0:
        return None  # continuous material has no meaningful floor (§2.1)
    return float(np.percentile(frame_db, 10))


def _judge(info, audio: np.ndarray, sample_rate: int, suffix: str, *, kind, bpm=None, bars=None) -> dict:
    fmt = str(getattr(info, "format", "") or "").upper()
    subtype = str(getattr(info, "subtype", "") or "").upper()
    if not fmt:
        fmt = SUFFIX_FORMATS.get((suffix or "").lower(), "")
    channels = int(getattr(info, "channels", audio.shape[1] if audio.ndim > 1 else 1))
    frames = int(getattr(info, "frames", len(audio)))
    duration = frames / sample_rate if sample_rate else 0.0
    bit_depth = _bit_depth(subtype)
    lossy = _is_lossy(fmt, subtype, suffix)

    mono = audio.mean(axis=1) if audio.ndim > 1 else audio
    peak_db, clip_runs, clip_fraction = _clipping(mono)
    freqs, spectrum = _long_term_spectrum(mono.astype(np.float64), sample_rate)
    bandwidth_hz = _bandwidth(freqs, spectrum)
    noise_floor = _noise_floor(mono, sample_rate)
    loudness = _lufs(mono, sample_rate)
    rms = float(np.sqrt(np.mean(mono.astype(np.float64) ** 2))) if len(mono) else 0.0
    crest = peak_db - _db(rms) if rms else None

    bar_s = 240.0 / float(bpm) if bpm else None
    bars_measured = round(duration / bar_s, 3) if bar_s else None

    metrics = {
        "format": fmt or "unknown",
        "subtype": subtype or "unknown",
        "sample_rate": int(sample_rate),
        "channels": channels,
        "bit_depth": bit_depth,
        "seconds": round(duration, 3),
        "peak_dbfs": round(float(peak_db), 2),
        "clipped_runs": int(clip_runs),
        "bandwidth_khz": round(bandwidth_hz / 1000.0, 2),
        "noise_floor_dbfs": round(noise_floor, 2) if noise_floor is not None else None,
        "lufs": loudness,
        "crest_db": round(float(crest), 2) if crest is not None else None,
        "bars_measured": bars_measured,
    }

    reasons = _reasons(metrics, kind=kind, bpm=bpm, bars=bars, lossy=lossy,
                       clip_fraction=clip_fraction, duration=duration)
    notes, flagged = _warnings(metrics, kind=kind, bpm=bpm)
    if reasons:
        verdict = "reject"
    elif flagged:
        verdict = "flag"
    else:
        # A "pass" can still carry informational notes, e.g. "48 kHz preferred"
        # or "loop length unverified" (§7.2).
        verdict = "pass"
    return {"verdict": verdict, "reasons": reasons, "warnings": notes, "metrics": metrics}


def _reasons(metrics: dict, *, kind, bpm, bars, lossy: bool, clip_fraction: float, duration: float) -> list[str]:
    # The >30 s and >20 MB caps in §7.2 belong to the fetch layer, where the
    # bytes are counted; the gate judges audio only (a 36 s Iowa piano is a
    # valid one-shot in §7.4).
    reasons: list[str] = []
    if duration <= 0:
        reasons.append("empty file: no audio samples")
    if lossy:
        reasons.append(f"lossy codec ({metrics['format']} {metrics['subtype']}): "
                       "a lossy preview cannot be restored by re-encoding")
    if metrics["sample_rate"] < MIN_SAMPLE_RATE:
        reasons.append(f"sample rate {metrics['sample_rate'] / 1000:.2f} kHz "
                       "(needs 44.1 kHz or more)")
    if metrics["channels"] > MAX_CHANNELS:
        reasons.append(f"channels {metrics['channels']} (needs mono or stereo)")
    if metrics["bit_depth"] is None and not lossy:
        # §7.1 accepts PCM 16/24/32 and float only; µ-law/ADPCM WAVs have no depth.
        reasons.append(f"unsupported subtype {metrics['subtype']} "
                       "(needs 16/24/32-bit PCM or float)")
    elif metrics["bit_depth"] is not None and metrics["bit_depth"] < MIN_BIT_DEPTH:
        reasons.append(f"bit depth {metrics['bit_depth']} (needs 16-bit PCM or better)")
    if (metrics["clipped_runs"] or clip_fraction > MAX_CLIPPED_FRACTION
            or metrics["peak_dbfs"] > 0.0):
        reasons.append(_clip_reason(metrics, clip_fraction))
    if kind == "loop" and metrics["bandwidth_khz"] * 1000.0 < LOOP_BANDWIDTH_FLOOR_HZ:
        reasons.append(f"narrow-band loop: bandwidth {metrics['bandwidth_khz']:.2f} kHz "
                       f"(floor {LOOP_BANDWIDTH_FLOOR_HZ / 1000:g} kHz)")
    if kind == "loop" and bpm:
        reasons.extend(_bar_reasons(bpm, bars, duration))
    return reasons


def _clip_reason(metrics: dict, fraction: float) -> str:
    if metrics["clipped_runs"]:
        return (f"clipping: {metrics['clipped_runs']} run(s) of 3+ full-scale samples, "
                f"peak {metrics['peak_dbfs']:+.2f} dBFS")
    if fraction > MAX_CLIPPED_FRACTION:
        return (f"clipping: {fraction * 100:.2f}% of samples at full scale "
                f"(limit {MAX_CLIPPED_FRACTION * 100:.2f}%)")
    return f"clipping: peak {metrics['peak_dbfs']:+.2f} dBFS is above 0 dBFS"


def _bar_reasons(bpm: float, bars, duration: float) -> list[str]:
    bar_s = 240.0 / float(bpm)
    measured = duration / bar_s
    nearest = round(measured)
    expected = float(bars) if bars is not None else float(nearest)
    tolerance = max(BAR_TOLERANCE_S, BAR_TOLERANCE_RATIO * bar_s)
    out_of_range = not (MIN_BARS <= nearest <= MAX_BARS and MIN_BARS <= expected <= MAX_BARS)
    if out_of_range or abs(measured - expected) * bar_s > tolerance:
        detail = (f", not the stated {expected:g} bars" if bars is not None
                  else " (needs whole bars)")
        return [f"loop is {measured:.2f} bars at {bpm:g} BPM{detail}"]
    return []


def _warnings(metrics: dict, *, kind, bpm) -> tuple[list[str], bool]:
    """Return (all warnings, whether any of them is a flag-level concern).

    §7.2 mixes two kinds of note. Quality concerns (dark, noisy, loud/quiet,
    narrow-band, crushed dynamics) make the verdict "flag". Purely informational
    notes (44.1 kHz preferred, no silence to measure, no stated BPM) are
    returned as warnings but leave a clean file at "pass".
    """
    notes: list[str] = []
    flagged = False
    bandwidth = metrics["bandwidth_khz"] * 1000.0
    if kind == "loop":
        if LOOP_BANDWIDTH_FLOOR_HZ <= bandwidth < LOOP_BANDWIDTH_FULL_HZ:
            notes.append(f"narrow-band loop: bandwidth {metrics['bandwidth_khz']:.2f} kHz "
                         f"(below {LOOP_BANDWIDTH_FULL_HZ / 1000:g} kHz)")
            flagged = True
    elif bandwidth < ONESHOT_BANDWIDTH_FULL_HZ:
        # A kick, 808 or sub is legitimately dark, so this is advisory (§7.1).
        # kind=None is judged with this one-shot advisory, never the loop floor.
        notes.append(f"dark/narrow: bandwidth {metrics['bandwidth_khz']:.2f} kHz "
                     f"(one-shots below {ONESHOT_BANDWIDTH_FULL_HZ / 1000:g} kHz)")
        flagged = True
    if metrics["noise_floor_dbfs"] is None:
        notes.append("noise floor unmeasurable: the file has no silence")
    elif metrics["noise_floor_dbfs"] > MAX_NOISE_FLOOR_DBFS:
        # §7.2 lists the noise floor as a flag, not a hard reject.
        notes.append(f"high noise floor: {metrics['noise_floor_dbfs']:.2f} dBFS "
                     f"(above {MAX_NOISE_FLOOR_DBFS:g} dBFS)")
        flagged = True
    if metrics["lufs"] is not None and not (MIN_LUFS <= metrics["lufs"] <= MAX_LUFS):
        notes.append(f"loudness {metrics['lufs']:.2f} LUFS outside {MIN_LUFS:g}..{MAX_LUFS:g} LUFS")
        flagged = True
    if metrics["crest_db"] is not None and not (MIN_CREST_DB <= metrics["crest_db"] <= MAX_CREST_DB):
        notes.append(f"crest {metrics['crest_db']:.2f} dB outside {MIN_CREST_DB:g}..{MAX_CREST_DB:g} dB")
        flagged = True
    if kind == "loop" and not bpm:
        # A guess cannot prove a bar count; mark it unverified, not failed (§7.4).
        notes.append("loop length unverified: no stated BPM")
    if metrics["sample_rate"] == MIN_SAMPLE_RATE:
        # §7.2 flags it: 44.1 kHz is fine, 48 kHz is preferred.
        notes.append(f"{metrics['sample_rate'] / 1000:g} kHz sample rate "
                     f"({PREFERRED_SAMPLE_RATE / 1000:g} kHz preferred)")
    # §7.2 also flags key confidence <0.5 and a mono source used as a stereo
    # texture. This gate has neither a key estimate nor a texture role; the
    # caller (sample search) adds those two flags.
    return notes, flagged
