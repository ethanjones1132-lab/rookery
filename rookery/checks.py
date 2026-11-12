"""Audio quality sensors shared by renderer, tools, and acceptance tests."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pyloudnorm as pyln
import soundfile as sf
from scipy.signal import resample_poly


def _report(passed, value, target, hint=None):
    result = {"pass": bool(passed), "value": value, "target": target}
    if not passed and hint:
        result["hint"] = hint
    return result


def _audio_array(audio):
    data = np.asarray(audio, dtype=np.float64)
    if data.ndim == 1:
        data = data[:, None]
    if data.ndim != 2 or data.shape[1] not in (1, 2):
        raise ValueError("audio must be frames x 2 stereo or mono frames")
    return data


def check_audio(audio, sample_rate, expected_samples, deterministic=None, target_lufs=-14.0) -> dict:
    """Measure exact length, periodic true peak, loudness, seam, audibility, and render proof."""
    if isinstance(sample_rate, bool) or not isinstance(sample_rate, (int, np.integer)) or sample_rate <= 0:
        raise ValueError("sample_rate must be a positive integer")
    if isinstance(expected_samples, bool) or not isinstance(expected_samples, (int, np.integer)) or expected_samples < 0:
        raise ValueError("expected_samples must be a non-negative integer")
    data = _audio_array(audio)
    finite = bool(np.isfinite(data).all())
    safe = np.nan_to_num(data, nan=0.0, posinf=1.0, neginf=-1.0)
    length_ok = len(data) == int(expected_samples)
    report = {"length_exact": _report(length_ok, int(len(data)), f"{int(expected_samples)} samples",
                                      "Render the project to its exact sample count.")}

    if len(safe) and finite:
        # wrap padding models repeated loop content; zero padding creates a false edge transient.
        peak = float(np.max(np.abs(resample_poly(safe, 4, 1, axis=0, padtype="wrap"))))
        peak_db = 20 * math.log10(max(peak, 1e-15))
    else:
        peak_db = 0.0 if not finite and len(data) else -300.0
    peak_ok = finite and peak_db <= -1.0
    report["no_clipping"] = _report(peak_ok, float(peak_db), "≤ -1.0 dBTP",
                                    "Lower the master gain or use a limiter.")

    rms = float(np.sqrt(np.mean(safe * safe))) if safe.size else 0.0
    rms_db = 20 * math.log10(max(rms, 1e-15))
    loudness = None
    if finite and len(safe) >= int(sample_rate * 0.4):
        try:
            measured = float(pyln.Meter(int(sample_rate)).integrated_loudness(safe[:, 0] if safe.shape[1] == 1 else safe))
            if math.isfinite(measured):
                loudness = measured
        except (ValueError, ZeroDivisionError):
            pass
    loud_ok = loudness is not None and target_lufs - 1.0 <= loudness <= target_lufs + 1.0
    loud_value = loudness if loudness is not None else ("-inf" if rms == 0 else "unmeasurable")
    report["loudness"] = _report(loud_ok, loud_value, f"{target_lufs:g} ± 1 LUFS",
                                 "Adjust gain or compression toward the loudness target.")

    if len(safe) >= 2 and finite:
        jumps = np.max(np.abs(np.diff(safe, axis=0)), axis=1)
        body = float(np.percentile(jumps, 99.9)) if len(jumps) else 0.0
        seam = float(np.max(np.abs(safe[0] - safe[-1])))
        seam_ok = seam <= body * 1.5
    else:
        seam, body, seam_ok = (0.0, 0.0, True) if len(safe) < 2 else (float("inf"), 0.0, False)
    seam_value = seam if math.isfinite(seam) else "non-finite"
    report["seam_click"] = _report(seam_ok, seam_value, "seam jump ≤ body p99.9 × 1.5",
                                   "Smooth the loop boundary or fold the effect tail into the loop.")
    audible = finite and rms_db > -50.0
    report["not_silent"] = _report(audible, float(rms_db) if math.isfinite(rms_db) else "-inf",
                                    "> -50 dBFS RMS", "Add or raise an audible track.")

    deterministic_ok = deterministic is True
    deterministic_value = "verified" if deterministic_ok else "unverified"
    report["deterministic"] = _report(deterministic_ok, deterministic_value, "independent WAV bytes match",
                                       "Re-render independently and compare the encoded WAV bytes.")
    return report


def evaluate_file(path, expected_samples, deterministic=None, target_lufs=-14.0) -> dict:
    """Decode the rendered WAV from disk before evaluating the actual file."""
    try:
        audio, sample_rate = sf.read(str(Path(path)), dtype="float64", always_2d=True)
    except (OSError, RuntimeError, sf.SoundFileRuntimeError) as exc:
        # Keep the frozen six-check shape on decode failures.
        report = check_audio(np.zeros((0, 2)), 44100, expected_samples, deterministic, target_lufs)
        for key in report:
            report[key]["pass"] = False
            report[key]["hint"] = f"Could not decode rendered WAV: {exc}"
        return report
    return check_audio(audio, sample_rate, expected_samples, deterministic, target_lufs)


def mix_report(audio, sample_rate) -> dict:
    """Measure the master balance, width and spectrum the agent cannot hear.

    Numbers are deterministic and computed from the rendered loop. They are
    diagnostics, not pass/fail checks: the six-check report stays unchanged.
    """
    data = _audio_array(np.asarray(audio, dtype=np.float64))
    if not len(data):
        return {"correlation": 0.0, "width": 0.0, "lr_balance_db": 0.0,
                "crest_db": 0.0, "centroid_hz": 0.0,
                "bands_pct": {"sub": 0.0, "low": 0.0, "mid": 0.0, "high": 0.0, "air": 0.0}}
    mono = data.mean(axis=1)
    peak = float(np.max(np.abs(data)))
    rms = float(np.sqrt(np.mean(data * data)))
    crest = 20.0 * math.log10(max(peak, 1e-12) / max(rms, 1e-12))
    if data.shape[1] == 2:
        left, right = data[:, 0], data[:, 1]
        if np.std(left) and np.std(right):
            correlation = float(np.corrcoef(left, right)[0, 1])
        else:
            correlation = 0.0
        side = float(np.sqrt(np.mean((left - right) ** 2)))
        mid = float(np.sqrt(np.mean((left + right) ** 2)))
        width = side / max(mid, 1e-12)
        lr_balance = 20.0 * math.log10(max(float(np.sqrt(np.mean(left * left))), 1e-12)
                                       / max(float(np.sqrt(np.mean(right * right))), 1e-12))
    else:
        correlation, width, lr_balance = 1.0, 0.0, 0.0
    window = np.hanning(len(mono))
    power = np.abs(np.fft.rfft(mono * window)) ** 2
    freqs = np.fft.rfftfreq(len(mono), 1.0 / int(sample_rate))
    total = float(power.sum()) or 1e-30
    bands = {
        "sub": (20.0, 120.0), "low": (120.0, 400.0), "mid": (400.0, 2500.0),
        "high": (2500.0, 12000.0), "air": (12000.0, 20000.0),
    }
    bands_pct = {
        name: round(100.0 * float(power[(freqs >= low) & (freqs < high)].sum()) / total, 1)
        for name, (low, high) in bands.items()
    }
    centroid = float((power * freqs).sum() / total)
    return {
        "correlation": round(correlation, 3),
        "width": round(width, 3),
        "lr_balance_db": round(lr_balance, 2),
        "crest_db": round(crest, 2),
        "centroid_hz": round(centroid, 0),
        "bands_pct": bands_pct,
    }


def evaluate(audio, sr, project, *, this_hash, other_hash) -> dict:
    """Acceptance API compatibility; hashes are caller-supplied independent render identities."""
    bars = project.get("bars", 4) if isinstance(project, dict) else 4
    bpm = project.get("bpm", 90) if isinstance(project, dict) else 90
    expected = round(int(bars) * 4 * 60 / float(bpm) * int(sr))
    equal = isinstance(this_hash, str) and bool(this_hash) and isinstance(other_hash, str) and bool(other_hash) and this_hash == other_hash
    report = check_audio(audio, sr, expected, deterministic=equal)
    report["deterministic"]["value"] = "match" if equal else "mismatch or missing hash"
    return report
