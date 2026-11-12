import numpy as np
import soundfile as sf

from rookery.checks import check_audio, evaluate, evaluate_file, mix_report


def test_silence_and_missing_determinism_fail_with_six_checks():
    report = check_audio(np.zeros((48000, 2)), 48000, 48000)
    assert len(report) == 6
    assert report["length_exact"]["pass"]
    assert not report["loudness"]["pass"]
    assert not report["not_silent"]["pass"]
    assert not report["deterministic"]["pass"]
    assert "hint" in report["deterministic"]


def test_true_peak_exact_length_and_seam_cases():
    n = 48000
    clean = 0.5 * np.sin(2 * np.pi * 440 * np.arange(n) / 48000)
    audio = np.column_stack([clean, clean])
    report = check_audio(audio, 48000, n, deterministic=True)
    assert report["length_exact"]["pass"]
    assert report["no_clipping"]["pass"]
    hot = check_audio(audio * 2, 48000, n)
    assert not hot["no_clipping"]["pass"]
    ramp = np.linspace(0, 0.5, n, dtype=np.float32)
    assert not check_audio(np.column_stack([ramp, ramp]), 48000, n)["seam_click"]["pass"]


def test_loudness_target_uses_measured_integrated_value():
    n = 48000
    signal = 0.1 * np.sin(2 * np.pi * 1000 * np.arange(n) / 48000)
    audio = np.column_stack([signal, signal])
    measured = check_audio(audio, 48000, n)["loudness"]["value"]
    assert check_audio(audio, 48000, n, target_lufs=measured)["loudness"]["pass"]


def test_mix_report_measures_width_balance_and_bands():
    rate = 48000
    t = np.arange(rate) / rate
    left = 0.45 * np.sin(2 * np.pi * 60 * t)
    same = mix_report(np.column_stack([left, left]), rate)
    assert same["correlation"] == 1.0
    assert same["width"] < 0.02
    assert same["bands_pct"]["sub"] > 90.0

    inverted = mix_report(np.column_stack([left, -left]), rate)
    assert inverted["correlation"] == -1.0
    assert inverted["width"] > 1.0

    quiet_right = mix_report(np.column_stack([left, left * 0.5]), rate)
    assert 5.5 < quiet_right["lr_balance_db"] < 6.5

    deterministic = mix_report(np.column_stack([left, left]), rate)
    assert deterministic == same


def test_evaluate_file_decodes_actual_wav_and_acceptance_hashes():
    audio = np.zeros((48000, 2), dtype=np.float32)
    audio[:, 0] = audio[:, 1] = 0.2 * np.sin(2 * np.pi * 440 * np.arange(48000) / 48000)
    def project():
        return {"bars": 4, "bpm": 240}
    report = evaluate(audio, 48000, project(), this_hash="abc", other_hash=None)
    assert not report["deterministic"]["pass"]
    report = evaluate(audio, 48000, project(), this_hash="abc", other_hash="abc")
    assert report["deterministic"]["pass"]
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as directory:
        wav = Path(directory) / "actual.wav"
        sf.write(wav, audio, 48000, subtype="PCM_24")
        decoded = evaluate_file(wav, 48000, deterministic=True)
        assert decoded["length_exact"]["pass"]
        assert decoded["not_silent"]["pass"]
        assert decoded["deterministic"]["pass"]
