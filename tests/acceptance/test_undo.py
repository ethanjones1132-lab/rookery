"""Undo restores the previous pattern and still bumps rev."""
from spec import tiled


def test_undo_one_steps_edit(tmp_path):
    from rookery import tools

    tools.new(tmp_path, "beat", 90, bars=4, swing=0, seed=1337)
    tools.track(tmp_path, "beat", "add", "kick", kind="drum", source="factory:kick_boom")
    tools.steps(tmp_path, "beat", "kick", "x...............")
    second = tools.steps(tmp_path, "beat", "kick", "....x...........")
    undone = tools.undo(tmp_path, "beat", steps=1)
    assert undone["rev"] > second["rev"]
    pattern = undone["project"]["tracks"][0]["steps"]
    assert tiled(pattern, 64) == tiled("x...............", 64)
