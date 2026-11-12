"""Same project, two fresh processes, identical hash and identical wav bytes."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SCRIPT = """
import json, sys
from pathlib import Path
from rookery import tools
root = Path(sys.argv[1])
name = "same"
tools.new(root, name, 90, bars=4, swing=0, seed=1337)
tools.track(root, name, "add", "kick", kind="drum", source="factory:kick_boom")
tools.track(root, name, "add", "snare", kind="drum", source="factory:snare_crack")
tools.track(root, name, "add", "hat", kind="drum", source="factory:hat_closed")
tools.steps(root, name, "kick", "x.....x...x.....")
tools.steps(root, name, "snare", "....x.......x...")
tools.steps(root, name, "hat", "x.x.x.x.x.x.x.x.")
tools.mix(root, name, "master", [{"type": "limiter", "ceiling_db": -1.0}])
out = tools.render(root, name)
print(json.dumps({"hash": out["hash"], "path": out["path"]}))
"""


def _render(data):
    proc = subprocess.run(
        [sys.executable, "-c", SCRIPT, str(data)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_two_processes_match(tmp_path):
    first = _render(tmp_path / "a")
    second = _render(tmp_path / "b")
    assert first["hash"] == second["hash"]
    assert Path(first["path"]).read_bytes() == Path(second["path"]).read_bytes()


def test_swing_changes_the_hash(tmp_path):
    from rookery import tools
    from rookery.project import load, save

    made = _render(tmp_path / "c")
    project_dir = tmp_path / "c" / "projects" / "same"
    project = load(project_dir)
    project["swing"] = 0.5
    save(project, project_dir)
    swung = tools.render(tmp_path / "c", "same")
    assert swung["hash"] != made["hash"]
