"""Rejected writes leave the project and rev untouched. HANDOFF §2.1."""
import pytest

from spec import tiled


def _kick(data, pattern="x..............."):
    from rookery import tools

    tools.new(data, "beat", 90, bars=4, swing=0, seed=1337)
    tools.track(data, "beat", "add", "kick", kind="drum", source="factory:kick_boom")
    return tools.steps(data, "beat", "kick", pattern)


def test_bad_steps_do_not_write(tmp_path):
    from rookery.project import ProjectError, load, rev

    wrote = _kick(tmp_path)
    with pytest.raises(ProjectError) as caught:
        from rookery import tools

        tools.steps(tmp_path, "beat", "kick", "nope")
    assert str(caught.value).strip()
    saved = load(tmp_path / "projects" / "beat")
    assert tiled(saved["tracks"][0]["steps"], 64) == tiled("x...............", 64)
    assert rev(tmp_path / "projects" / "beat") == wrote["rev"]


def test_digit_on_a_drum_is_rejected(tmp_path):
    from rookery.project import ProjectError

    _kick(tmp_path)
    from rookery import tools

    with pytest.raises(ProjectError):
        tools.steps(tmp_path, "beat", "kick", "x.1.............")


def test_short_pattern_is_accepted(tmp_path):
    from rookery.project import load

    _kick(tmp_path, "x...")
    saved = load(tmp_path / "projects" / "beat")
    assert tiled(saved["tracks"][0]["steps"], 64) == tiled("x...", 64)


def test_bpm_bars_and_swing_bounds(tmp_path):
    from rookery.project import ProjectError
    from rookery import tools

    tools.new(tmp_path, "lo", 90, swing=0)
    tools.new(tmp_path, "hi", 90, swing=1, bars=8)
    with pytest.raises(ProjectError) as bpm:
        tools.new(tmp_path, "zero", 0)
    with pytest.raises(ProjectError):
        tools.new(tmp_path, "three", 90, bars=3)
    with pytest.raises(ProjectError):
        tools.new(tmp_path, "wide", 90, swing=1.1)
    with pytest.raises(ProjectError):
        tools.new(tmp_path, "neg", 90, swing=-0.01)
    with pytest.raises(ProjectError):
        tools.new(tmp_path, "", 90)
    assert str(bpm.value).strip()
