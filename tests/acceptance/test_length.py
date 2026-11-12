"""Exact length from HANDOFF §2.2. Python round. Swing does not add frames."""
import numpy as np

from spec import empty_project


def test_four_bars_at_90_is_470400_stereo_frames():
    from rookery.render import render

    audio = render(empty_project(bpm=90, bars=4))
    assert isinstance(audio, np.ndarray)
    assert audio.dtype == np.float32
    assert audio.shape == (470400, 2)


def test_eight_bars_at_93_is_910452_frames():
    from rookery.render import render

    audio = render(empty_project(bpm=93, bars=8, name="odd"))
    assert audio.shape[0] == 910452
    assert audio.shape[1] == 2


def test_swing_does_not_change_length():
    from rookery.render import render

    straight = render(empty_project(swing=0.0, name="straight"))
    swung = render(empty_project(swing=0.5, name="swung"))
    assert straight.shape[0] == swung.shape[0] == 470400
