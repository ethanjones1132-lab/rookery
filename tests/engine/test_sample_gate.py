"""The sample quality gate, judged against synthetic files.

Thresholds and wording: docs/design/research/sample-sources.md §7.
All audio is generated here with numpy and soundfile; no fixtures on disk.
"""

import json
import math

import numpy as np
import pytest
import soundfile as sf
from scipy.signal import butter, sosfiltfilt

from rookery.sample_gate import assess, assess_bytes

SR = 44100
METRIC_KEYS = {
    "format", "subtype", "sample_rate", "channels", "bit_depth", "seconds",
    "peak_dbfs", "clipped_runs", "bandwidth_khz", "noise_floor_dbfs",
    "lufs", "crest_db", "bars_measured",
}


def noise(n, seed=7):
    return np.random.default_rng(seed).standard_normal(n).astype(np.float32)


def write(path, audio, *, sr=SR, subtype="PCM_24", format="WAV"):
    sf.write(path, np.asarray(audio, dtype=np.float32), sr, subtype=subtype, format=format)
    return path


def lowpass(audio, cutoff_hz, sr=SR):
    sos = butter(8, cutoff_hz / (sr / 2), "low", output="sos")
    return sosfiltfilt(sos, audio).astype(np.float32)


def clean_oneshot(seconds=0.5, sr=SR):
    """A bright, transient-rich hit: tone + broadband noise under a decay."""
    t = np.arange(int(seconds * sr)) / sr
    envelope = np.exp(-t * 8.0)
    tone = 0.5 * np.sin(2 * math.pi * 440 * t) + 0.25 * np.sin(2 * math.pi * 3000 * t)
    return (tone + 0.05 * noise(len(t))) * envelope


def musical_loop(bars=2.0, bpm=90):
    """A full-band two-bar loop: a kick on every beat over a noise bed."""
    bar_s = 240.0 / bpm
    n = round(bars * bar_s * SR)
    t = np.arange(n) / SR
    audio = 0.05 * noise(n, seed=11)
    beat_s = 60.0 / bpm
    for start in np.arange(0.0, bars * bar_s - 1e-9, beat_s):
        hit = np.arange(int(0.18 * SR)) / SR
        kick = 0.8 * np.sin(2 * math.pi * 60 * hit) * np.exp(-hit * 18.0)
        at = int(round(start * SR))
        end = min(n, at + len(kick))
        audio[at:end] += kick[: end - at]
    return np.clip(audio, -0.98, 0.98)


def test_clean_oneshot_passes(tmp_path):
    path = write(tmp_path / "clean.wav", clean_oneshot())

    result = assess(path, kind="one-shot")

    assert result["verdict"] == "pass"
    assert result["reasons"] == []
    assert set(result["metrics"]) == METRIC_KEYS
    metrics = result["metrics"]
    assert (metrics["format"], metrics["subtype"]) == ("WAV", "PCM_24")
    assert metrics["sample_rate"] == SR
    assert metrics["bit_depth"] == 24
    assert metrics["channels"] == 1
    assert metrics["bandwidth_khz"] > 16.0
    assert metrics["peak_dbfs"] < 0.0


def test_low_sample_rate_is_rejected(tmp_path):
    path = write(tmp_path / "small.wav", clean_oneshot(sr=22050), sr=22050)

    result = assess(path, kind="one-shot")

    assert result["verdict"] == "reject"
    assert any("sample rate" in reason for reason in result["reasons"])


def test_eight_bit_is_rejected(tmp_path):
    path = write(tmp_path / "eight.wav", clean_oneshot(), subtype="PCM_U8")

    result = assess(path, kind="one-shot")

    assert result["verdict"] == "reject"
    assert any("bit depth 8" in reason for reason in result["reasons"])


def test_more_than_two_channels_is_rejected(tmp_path):
    mono = clean_oneshot()
    four = np.column_stack([mono, mono * 0.9, mono * 0.8, mono * 0.7])
    path = write(tmp_path / "four.wav", four, subtype="PCM_16")

    result = assess(path, kind="one-shot")

    assert result["verdict"] == "reject"
    assert any("channels 4" in reason for reason in result["reasons"])


def test_hard_clipping_is_rejected(tmp_path):
    t = np.arange(int(0.5 * SR)) / SR
    hot = np.clip(8.0 * (np.sin(2 * math.pi * 220 * t) + 0.4 * noise(len(t))), -1.0, 1.0)
    path = write(tmp_path / "clipped.wav", hot)

    result = assess(path, kind="one-shot")

    assert result["verdict"] == "reject"
    assert result["metrics"]["clipped_runs"] > 0
    assert any("clipping" in reason for reason in result["reasons"])


def test_dark_loop_is_rejected_but_dark_oneshot_is_only_flagged(tmp_path):
    filtered = lowpass(musical_loop(), 5000.0)
    loop_path = write(tmp_path / "dark-loop.wav", filtered)
    t = np.arange(int(0.5 * SR)) / SR
    one_path = write(tmp_path / "dark-one.wav", filtered[: int(0.5 * SR)] * np.exp(-t * 6.0))

    loop = assess(loop_path, kind="loop", bpm=90, bars=2)
    one = assess(one_path, kind="one-shot")

    assert loop["verdict"] == "reject"
    assert any("bandwidth" in reason for reason in loop["reasons"])
    assert one["verdict"] == "flag"
    assert one["reasons"] == []
    assert any("dark/narrow" in warning for warning in one["warnings"])


def test_two_bar_loop_passes_and_short_loop_is_rejected(tmp_path):
    exact = write(tmp_path / "exact.wav", musical_loop(bars=2.0))
    short = write(tmp_path / "short.wav", musical_loop(bars=1.9))

    good = assess(exact, kind="loop", bpm=90, bars=2)
    bad = assess(short, kind="loop", bpm=90, bars=2)

    assert good["verdict"] == "pass"
    assert good["metrics"]["bars_measured"] == pytest.approx(2.0, abs=1e-3)
    assert bad["verdict"] == "reject"
    assert any("bars" in reason for reason in bad["reasons"])


def test_loop_without_stated_bpm_is_unverified_not_rejected(tmp_path):
    path = write(tmp_path / "unknown-tempo.wav", musical_loop())

    result = assess(path, kind="loop")

    assert result["verdict"] == "pass"
    assert result["metrics"]["bars_measured"] is None
    assert any("unverified" in warning for warning in result["warnings"])


def test_hiss_is_flagged_not_rejected(tmp_path):
    hiss = 0.02 * noise(int(4.0 * SR), seed=3)
    audio = np.concatenate([np.zeros(int(0.2 * SR), dtype=np.float32), hiss])
    path = write(tmp_path / "hissy.wav", audio)

    result = assess(path, kind="one-shot")

    assert result["verdict"] == "flag"
    assert result["reasons"] == []
    assert any("noise" in warning for warning in result["warnings"])


@pytest.mark.parametrize(("format", "subtype"), [("MP3", None), ("OGG", "VORBIS")])
def test_lossy_codec_is_rejected(tmp_path, format, subtype):
    path = tmp_path / f"lossy.{format.lower()}"
    try:
        write(path, clean_oneshot(seconds=1.0), format=format, subtype=subtype)
    except (RuntimeError, ValueError, sf.SoundFileError) as exc:
        pytest.skip(f"this libsndfile build cannot write {format}: {exc}")

    result = assess(path, kind="one-shot")

    assert result["verdict"] == "reject"
    assert any("lossy codec" in reason for reason in result["reasons"])


def test_an_undecodable_lossy_suffix_is_rejected_not_raised(tmp_path):
    # Not every libsndfile build can decode AAC/M4A; the gate must still refuse it.
    path = tmp_path / "preview.m4a"
    path.write_bytes(b"not really an audio file")

    result = assess(path, kind="one-shot")

    assert result["verdict"] == "reject"
    assert any("lossy codec" in reason for reason in result["reasons"])


def test_assess_bytes_matches_assess(tmp_path):
    path = write(tmp_path / "bytes.wav", clean_oneshot())
    raw = path.read_bytes()

    from_path = assess(path, kind="one-shot")
    from_bytes = assess_bytes(raw, ".wav", kind="one-shot")

    assert from_bytes == from_path


def test_assess_bytes_detects_a_lossy_codec(tmp_path):
    path = tmp_path / "bytes.mp3"
    try:
        write(path, clean_oneshot(seconds=1.0), format="MP3", subtype=None)
    except (RuntimeError, ValueError, sf.SoundFileError) as exc:
        pytest.skip(f"this libsndfile build cannot write MP3: {exc}")

    result = assess_bytes(path.read_bytes(), ".mp3", kind="one-shot")

    assert result["verdict"] == "reject"
    assert any("lossy codec" in reason for reason in result["reasons"])


def test_every_result_is_json_serialisable(tmp_path):
    dark = write(tmp_path / "dark.wav", lowpass(clean_oneshot(), 4000.0))
    clipped = write(tmp_path / "hot.wav", np.clip(clean_oneshot() * 20, -1, 1))
    results = [
        assess(write(tmp_path / "ok.wav", clean_oneshot()), kind="one-shot"),
        assess(dark, kind="one-shot"),
        assess(clipped, kind="one-shot"),
    ]
    for result in results:
        encoded = json.dumps(result, allow_nan=False)
        assert json.loads(encoded)["verdict"] in {"pass", "flag", "reject"}
        for value in result["metrics"].values():
            assert value is None or isinstance(value, (int, float, str))


def test_invalid_arguments_are_refused(tmp_path):
    path = write(tmp_path / "ok.wav", clean_oneshot())

    with pytest.raises(ValueError):
        assess(path, kind="texture")
    with pytest.raises(ValueError):
        assess(path, kind="loop", bpm=0)
