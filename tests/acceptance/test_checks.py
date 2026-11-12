"""Check boundaries from HANDOFF §2.3. Obvious buffers only, so the threshold can't hide."""
import numpy as np

from spec import SR, dc, empty_project


def _report(audio, project=None, this="a" * 64, other="a" * 64):
    from rookery.checks import evaluate

    return evaluate(audio, SR, project or empty_project(), this_hash=this, other_hash=other)


def test_silence_fails_loudness_and_not_silent():
    report = _report(dc(470400, 0.0))
    assert report["length_exact"]["pass"] is True
    assert report["not_silent"]["pass"] is False
    assert report["loudness"]["pass"] is False
    assert report["no_clipping"]["pass"] is True
    assert report["seam_click"]["pass"] is True
    assert report["deterministic"]["pass"] is True


def test_hot_dc_fails_clipping():
    report = _report(dc(470400, 0.99))
    assert report["no_clipping"]["pass"] is False


def test_half_scale_dc_passes_clipping_and_is_audible():
    report = _report(dc(470400, 0.5))
    assert report["no_clipping"]["pass"] is True
    assert report["not_silent"]["pass"] is True
    assert report["seam_click"]["pass"] is True


def test_ramp_fails_the_seam():
    ramp = np.linspace(0.0, 0.5, 470400, dtype=np.float32)
    audio = np.column_stack([ramp, ramp])
    report = _report(audio)
    assert report["seam_click"]["pass"] is False


def test_short_buffer_fails_length():
    report = _report(dc(100, 0.2))
    assert report["length_exact"]["pass"] is False


def test_mismatched_hashes_fail_deterministic():
    report = _report(dc(470400, 0.2), this="a" * 64, other="b" * 64)
    assert report["deterministic"]["pass"] is False
    assert "value" in report["deterministic"]
