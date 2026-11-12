"""Print each Flock template's integrated LU relative to its genre's drum reference."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rookery.project import _apply_edit, new_project
from rookery.render import _render_audio_with_metadata


CASES = (
    ("dusty_boom_bap", "boom-bap", "theory-boom-bap-ghost", 90, 0.42),
    ("trap_night", "trap", "pocket-132-trap-bounce", 140, 0.0),
    ("lo_fi_study", "boom-bap", "pocket-89-swung-hats", 86, 0.2),
    ("late_house", "boom-bap", "theory-house-4floor", 124, 0.04),
    ("sunday_soul", "boom-bap", "theory-boom-bap-ghost", 86, 0.42),
)
SOURCES = {
    "kick": "factory:kick_punch", "snare": "factory:snare_snap",
    "clap": "factory:clap_stack", "hat": "factory:hat_tight",
    "hat_open": "factory:hat_open_short", "perc": "factory:perc",
}


def render_case(template: str, genre: str, groove_id: str, bpm: int, swing: float):
    grooves = json.loads((ROOT / "skills/rookery/grooves.json").read_text(encoding="utf-8"))
    groove = next(item for item in grooves["templates"] if item["id"] == groove_id)
    project = new_project(template.replace("_", "-"), bpm=bpm, bars=4, genre=genre, swing=swing)
    project["tracks"] = []
    project = _apply_edit(project, "flock", {"action": "template", "template": template})
    for role, pattern in groove["tracks"].items():
        add = {"action": "add", "id": role, "kind": "drum", "source": SOURCES[role]}
        if role in {"hat", "hat_open"}:
            add["choke_group"] = "hats"
        project = _apply_edit(project, "track", add)
        project = _apply_edit(project, "steps", {"track": role, "steps": pattern["steps"],
                                                 "velocity": pattern["velocity"]})
    _audio, _meters, metadata = _render_audio_with_metadata(project, include_balance=True, fixed_gain=1)
    measured = metadata["_balance_layers"]
    kick_id = next(ident for ident, role in measured["roles"].items() if role == "kick")
    kick_lufs = measured["levels"][kick_id]
    return {role: round(level - kick_lufs, 1)
            for ident, role in measured["roles"].items()
            if ident.startswith("bird:") and (level := measured["levels"].get(ident)) is not None}


def main() -> None:
    columns = []
    for template, genre, groove, bpm, swing in CASES:
        columns.append((template, render_case(template, genre, groove, bpm, swing)))
    roles = ("flock_bass", "flock_keys", "flock_pad", "flock_lead", "flock_arp", "flock_call")
    heading = f"{'role':<12}" + "".join(f"{template:>17}" for template, _ in columns)
    print(heading)
    for role in roles:
        values = []
        for _template, measured in columns:
            value = measured.get(role)
            values.append(f"{value:>17.1f}" if value is not None else f"{'--':>17}")
        print(f"{role:<12}" + "".join(values))


if __name__ == "__main__":
    main()
