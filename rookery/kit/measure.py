"""Objective measurements shared by the drum-match tool and its tests.

Everything here works on one mono signal at a time. No audio is embedded or
loaded by the engine; the tool reads reference files only when asked to.

The feature set is deliberately small and perceptual: transient shape (attack,
short-time crest), body (decay, total length), tone (pitch sweep, centroid,
band balance) and harmonic distortion (saturation). Distances are computed in
robust z-units against a stored cloud of reference medians, so a score of 1.0
means "one typical spread away from the middle of the commercial cloud".
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from scipy.optimize import curve_fit
from scipy.signal import butter, sosfilt, welch

BAND_EDGES = (20.0, 60.0, 200.0, 2000.0, 6000.0)
BAND_NAMES = ("sub", "low", "mid", "presence", "air")

TONAL_FAMILIES = frozenset(("kick", "808", "perc"))

_BASE_FEATURES = (
    "log_attack",
    "transient_crest",
    "crest",
    "click_ratio",
    "log_t60",
    "log_centroid",
    "sub_pct",
    "low_pct",
    "mid_pct",
    "presence_pct",
    "air_pct",
)
_TONAL_FEATURES = ("log_pitch5", "log_pitch60", "log_tau", "thd_pct")


def distance_features(family: str) -> tuple[str, ...]:
    """Feature names compared for one family."""
    if family in TONAL_FAMILIES:
        return _BASE_FEATURES + _TONAL_FEATURES
    return _BASE_FEATURES


def _db(value: float, floor: float = 1e-12) -> float:
    return 20.0 * math.log10(max(float(value), floor))


def _rms(segment: np.ndarray) -> float:
    if not len(segment):
        return 0.0
    return float(np.sqrt(np.mean(np.square(segment, dtype=np.float64))))


def _frame_rms(y: np.ndarray, sr: int, hop: float = 0.001, width: float = 0.004):
    """Return (times, rms) frames used for decay and loudness measurements."""
    step = max(1, round(hop * sr))
    size = max(step, round(width * sr))
    if len(y) <= size:
        return np.array([0.0]), np.array([_rms(y)])
    count = 1 + (len(y) - size) // step
    out = np.empty(count, dtype=np.float64)
    for i in range(count):
        start = i * step
        out[i] = _rms(y[start:start + size])
    return np.arange(count) * step / sr, out


def _f0_at(y: np.ndarray, sr: int, t: float, window: float = 0.018,
           low: float = 22.0, high: float = 900.0) -> float:
    """Dominant low-frequency peak in a short window, or NaN when unvoiced.

    A zero-padded spectral peak is used instead of autocorrelation because
    commercial one-shots sweep fast enough that a single-period lag is less
    coherent than the high band inside a short window.
    """
    start = int(round(t * sr))
    stop = min(len(y), start + int(round(window * sr)))
    if stop - start < 96:
        return math.nan
    seg = np.asarray(y[start:stop], dtype=np.float64)
    seg = seg - seg.mean()
    if np.max(np.abs(seg)) < 1e-6:
        return math.nan
    high = min(high, sr * 0.45)
    sos = butter(4, high, btype="lowpass", fs=sr, output="sos")
    seg = sosfilt(sos, seg) * np.hanning(len(seg))
    nfft = 1
    while nfft < max(8 * len(seg), 4096):
        nfft *= 2
    magnitude = np.abs(np.fft.rfft(seg, nfft))
    freqs = np.fft.rfftfreq(nfft, 1.0 / sr)
    band = (freqs >= low) & (freqs <= high)
    if not np.any(band):
        return math.nan
    indexes = np.flatnonzero(band)
    best = int(indexes[np.argmax(magnitude[band])])
    if best <= 0 or best + 1 >= len(magnitude):
        return math.nan
    left, centre, right = magnitude[best - 1], magnitude[best], magnitude[best + 1]
    denom = left - 2.0 * centre + right
    offset = 0.5 * (left - right) / denom if abs(denom) > 1e-15 else 0.0
    offset = max(-0.5, min(0.5, offset))
    return float((best + offset) * sr / nfft)


def _sweep(times, freqs) -> float:
    """Time constant (seconds) of an exponential pitch fall, or NaN."""
    pairs = [(t, f) for t, f in zip(times, freqs) if math.isfinite(f) and f > 10.0]
    if len(pairs) < 4:
        return math.nan
    ts = np.array([p[0] for p in pairs])
    fs = np.array([p[1] for p in pairs])

    def model(t, low, high, tau):
        return low + high * np.exp(-np.maximum(t, 0.0) / tau)

    try:
        popt, _ = curve_fit(
            model, ts, fs, p0=(fs.min(), max(fs.max() - fs.min(), 1.0), 0.03),
            bounds=([10.0, 0.0, 0.002], [500.0, 5000.0, 0.4]), maxfev=4000,
        )
    except (RuntimeError, ValueError):
        return math.nan
    return float(popt[2])


def _t60(times: np.ndarray, env: np.ndarray) -> float:
    """Seconds to fall 60 dB, fitted between -5 dB and -38 dB of the peak."""
    if not len(env):
        return 0.0
    peak_index = int(np.argmax(env))
    peak = max(float(env[peak_index]), 1e-12)
    levels = 20.0 * np.log10(np.maximum(env / peak, 1e-12))
    start = peak_index
    while start < len(levels) and levels[start] > -5.0:
        start += 1
    end = start
    while end < len(levels) and levels[end] > -38.0:
        end += 1
    if end - start < 4:
        return max(0.0, float(times[-1] - times[peak_index]))
    segment_t = times[start:end]
    segment_l = levels[start:end]
    slope = np.polyfit(segment_t, segment_l, 1)[0]
    if slope >= -1e-3:
        return max(0.0, float(times[-1] - times[peak_index]))
    return float(60.0 / -slope)


def _thd(y: np.ndarray, sr: int, f0: float) -> float:
    """Harmonic distortion percentage (harmonics 2-8 over the fundamental)."""
    if not math.isfinite(f0) or f0 <= 20.0:
        return math.nan
    start = int(round(0.02 * sr))
    stop = min(len(y), start + int(round(0.06 * sr)))
    seg = np.asarray(y[start:stop], dtype=np.float64)
    if len(seg) < 256:
        return math.nan
    seg = seg - seg.mean()
    seg = seg * np.hanning(len(seg))
    spectrum = np.abs(np.fft.rfft(seg)) ** 2
    freqs = np.fft.rfftfreq(len(seg), 1.0 / sr)

    def power(hz):
        width = max(hz * 0.04, 1.5 * sr / len(seg))
        mask = (freqs >= hz - width) & (freqs <= hz + width)
        return float(spectrum[mask].sum()) if np.any(mask) else 0.0

    fundamental = power(f0)
    overtones = sum(power(f0 * k) for k in range(2, 9) if f0 * k < sr * 0.45)
    if fundamental <= 0.0:
        return math.nan
    return float(100.0 * math.sqrt(overtones / fundamental))


def analyse(y: np.ndarray, sr: int, family: str) -> dict:
    """Measure one mono signal. Returns human-readable stats plus log features."""
    y = np.asarray(y, dtype=np.float64).reshape(-1)
    if y.size == 0:
        y = np.zeros(1)
    y = y - float(y.mean())
    length = len(y) / sr
    peak = float(np.max(np.abs(y)))
    if peak <= 0.0:
        peak = 1e-12
    magnitude = np.abs(y)
    start = int(np.argmax(magnitude >= 0.005 * peak)) if np.any(magnitude >= 0.005 * peak) else 0
    peak_index = int(np.argmax(magnitude))
    attack_ms = max(0.0, (peak_index - start) / sr * 1000.0)
    crest = _db(peak / max(_rms(y), 1e-12))

    first = max(1, int(round(0.03 * sr)))
    transient_crest = _db(peak / max(_rms(y[:first]), 1e-12))
    early = _rms(y[:max(1, int(round(0.010 * sr)))])
    body = _rms(y[int(round(0.010 * sr)):max(int(round(0.010 * sr)) + 1, int(round(0.100 * sr)))])
    click_ratio = _db(early / max(body, 1e-12))

    times, env = _frame_rms(y, sr)
    t60 = _t60(times, env)

    nperseg = min(len(y), 2048)
    freqs, spectrum = welch(y, fs=sr, nperseg=nperseg, noverlap=nperseg // 2,
                            scaling="spectrum", detrend=False)
    power = np.maximum(spectrum, 0.0)
    band = (freqs >= 10.0)
    total = max(float(power[band].sum()), 1e-12)
    bands = {}
    edges = BAND_EDGES
    for i, name in enumerate(BAND_NAMES):
        low = edges[i]
        high = edges[i + 1] if i + 1 < len(edges) else sr / 2
        mask = (freqs >= low) & (freqs < high)
        bands[name] = 100.0 * float(power[mask].sum()) / total
    centroid = float((freqs[band] * power[band]).sum() / total)

    stats = {
        "length_s": length,
        "attack_ms": attack_ms,
        "crest_db": crest,
        "transient_crest_db": transient_crest,
        "click_ratio_db": click_ratio,
        "t60_s": t60,
        "centroid_hz": centroid,
        "sub_pct": bands["sub"],
        "low_pct": bands["low"],
        "mid_pct": bands["mid"],
        "presence_pct": bands["presence"],
        "air_pct": bands["air"],
        "clip_pct": 100.0 * float(np.mean(magnitude >= 0.999 * peak)),
    }
    tau = math.nan
    if family in TONAL_FAMILIES:
        probe_times = (0.004, 0.008, 0.016, 0.030, 0.050, 0.080)
        if family == "808":
            window, high = 0.060, 400.0
        elif family == "kick":
            window, high = 0.040, 600.0
        else:
            window, high = 0.025, 1200.0
        probes = [_f0_at(y, sr, t, window=window, high=high) for t in probe_times]
        p5 = _f0_at(y, sr, 0.005, window=window, high=high)
        p60 = _f0_at(y, sr, 0.060, window=window, high=high)
        tau = _sweep(probe_times, probes)
        stats.update(pitch_5hz=p5, pitch_60hz=p60, sweep_tau_s=tau,
                     thd_pct=_thd(y, sr, p60))
    else:
        stats.update(pitch_5hz=math.nan, pitch_60hz=math.nan,
                     sweep_tau_s=math.nan, thd_pct=math.nan)

    stats.update(
        log_attack=math.log10(max(attack_ms, 0.01) / 1000.0),
        transient_crest=transient_crest,
        crest=crest,
        click_ratio=click_ratio,
        log_t60=math.log10(max(t60, 1e-3)),
        log_centroid=math.log10(max(centroid, 20.0)),
        sub_pct=bands["sub"],
        low_pct=bands["low"],
        mid_pct=bands["mid"],
        presence_pct=bands["presence"],
        air_pct=bands["air"],
        log_pitch5=math.log10(max(stats["pitch_5hz"], 1.0)) if math.isfinite(stats["pitch_5hz"]) else math.nan,
        log_pitch60=math.log10(max(stats["pitch_60hz"], 1.0)) if math.isfinite(stats["pitch_60hz"]) else math.nan,
        log_tau=math.log10(max(tau, 1e-3)) if math.isfinite(tau) else math.nan,
        thd_pct=stats["thd_pct"],
    )
    return stats


def read_mono(path: str | Path) -> tuple[np.ndarray, int]:
    import soundfile as sf

    audio, sr = sf.read(str(path), always_2d=True, dtype="float64")
    if audio.shape[1] > 1:
        # Use the louder channel instead of a phase-cancelling fold-down so
        # stereo-wide hits keep their true amplitude and spectrum.
        energy = np.sqrt(np.mean(np.square(audio), axis=0))
        audio = audio[:, int(np.argmax(energy))]
    else:
        audio = audio[:, 0]
    return audio, int(sr)


def _median(values) -> float:
    finite = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    return float(np.median(finite)) if finite else math.nan


def _scale(values, median: float) -> float:
    finite = np.array([float(v) for v in values if v is not None and math.isfinite(float(v))])
    if len(finite) < 2:
        return max(abs(median) * 0.15, 0.05)
    q25, q75 = np.percentile(finite, [25.0, 75.0])
    spread = float(q75 - q25) / 1.349
    return max(spread, abs(median) * 0.05, 0.02)


def build_targets(rows: dict[str, list[dict]]) -> dict:
    """Summarise measured reference rows into a compact, audio-free target file."""
    families = {}
    for family, stats_list in sorted(rows.items()):
        features = distance_features(family)
        entry = {"count": len(stats_list), "features": list(features), "median": {}, "scale": {}}
        for feature in features:
            values = [row.get(feature, math.nan) for row in stats_list]
            median = _median(values)
            entry["median"][feature] = None if not math.isfinite(median) else round(median, 6)
            scale = _scale(values, median)
            entry["scale"][feature] = round(scale, 6)
        families[family] = entry
    return {
        "schema": "rookery.drum_targets/1",
        "source": "measured one-shot statistics; no audio is stored",
        "metric": "root-mean-square robust z-distance over each family's features",
        "families": families,
    }


def distance(stats: dict, target: dict, family: str) -> float:
    """Robust RMS z-distance from one measurement to a stored family cloud."""
    features = target.get("features") or list(distance_features(family))
    total = 0.0
    used = 0
    for feature in features:
        median = target["median"].get(feature)
        scale = target["scale"].get(feature)
        value = stats.get(feature)
        if median is None or scale is None:
            continue
        if value is None or not math.isfinite(float(value)):
            # Missing tonal data counts as poor fit but does not explode.
            total += 4.0
            used += 1
            continue
        z = (float(value) - float(median)) / max(float(scale), 1e-9)
        total += min(z * z, 16.0)
        used += 1
    return math.sqrt(total / used) if used else math.inf
