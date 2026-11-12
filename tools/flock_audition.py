"""Audition one Flock song over a drum bed, with a text grid and hook stats.

This is an authoring tool, not a plugin surface. It renders through the real
engine, so what you hear is what the project will render.

    python tools/flock_audition.py --bird glint --song A
    python tools/flock_audition.py --bird glint --events my-hook.json --out hook.wav

`--events` is a JSON list of {bar, step, len, deg, oct, vel}. `deg` is a
zero-based chord-relative scale degree (0 = chord root, 2 = third, 4 = fifth,
6 = seventh, 7 = root octave). It replaces the bird's song in memory only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import soundfile as sf  # noqa: E402

from rookery import render  # noqa: E402
from rookery.flock import synth  # noqa: E402

BIRDS = {bird["id"]: bird for bird in synth._CATALOG["birds"]}
GROOVE = ROOT / "skills" / "rookery" / "grooves.json"
TEMPLATE = next(t for t in synth._CATALOG["templates"] if t["id"] == "dusty_boom_bap")


def _drum_tracks() -> list[dict]:
    data = json.loads(GROOVE.read_text(encoding="utf-8"))
    groove = next(t for t in data["templates"] if t["id"] == "theory-boom-bap-ghost")
    sources = {"kick": "factory:kick_boom", "snare": "factory:snare_crack",
               "hat": "factory:hat_closed", "hat_open": "factory:hat_open"}
    tracks = []
    for role, spec in groove["tracks"].items():
        track = {"id": role, "kind": "drum", "source": sources[role],
                 "steps": spec["steps"], "velocity": spec["velocity"],
                 "gain_db": 0, "pan": 0, "mute": False, "solo": False, "pitch": 0, "fx": []}
        if role in {"hat", "hat_open"}:
            track["choke_group"] = "hats"
        tracks.append(track)
    return tracks


def _perch(bird: str, song: str) -> dict:
    return {"bird": bird, "song": song, "mute": False, "solo": False}


def _project(bird: str, song: str, bpm: float, swing: float, context: str) -> dict:
    if context == "template":
        perches = [None] * 6
        by_id = {b["id"]: b for b in synth._CATALOG["birds"]}
        order = ["bass", "keys", "pad", "lead", "arp", "call"]
        landing = sorted(TEMPLATE["birds"], key=lambda item: (order.index(by_id[item["bird"]]["role"]), item["bird"]))
        for slot, item in enumerate(landing):
            perches[slot] = _perch(item["bird"], item["song"])
        if not any(p and p["bird"] == bird for p in perches):
            free = next(i for i, p in enumerate(perches) if p is None)
            perches[free] = _perch(bird, song)
        weather = TEMPLATE["weather"]
    else:
        perches = [_perch(bird, song)] + [None] * 5
        weather = "clear"
    return {
        "schema": "rookery.project/1", "name": "flock-audition", "bpm": bpm,
        "bars": 4, "steps_per_bar": 16, "swing": swing, "seed": 1337,
        "tracks": _drum_tracks(), "master": {"fx": []},
        "flock": {"key": TEMPLATE["key"], "scale": TEMPLATE["scale"],
                  "progression": list(TEMPLATE["progression"]), "weather": weather,
                  "perches": perches, "seen": [], "unlocked": []},
    }


def _grid(events: list[dict]) -> str:
    rows = []
    for bar in range(4):
        cells = ["." for _ in range(16)]
        for event in events:
            if event.get("bar") == bar:
                cells[event["step"]] = str(event["deg"])
        rows.append("bar%d: " % (bar + 1) + " ".join(cells))
    return "\n".join(rows)


def _stats(events: list[dict]) -> str:
    ordered = sorted(events, key=lambda event: (event.get("bar", 0), event["step"]))
    pitches = [event["deg"] + 7 * event.get("oct", 0) for event in ordered]
    intervals = [b - a for a, b in zip(pitches, pitches[1:])]
    leaps = sum(1 for value in intervals if abs(value) >= 5)
    degrees = {event["deg"] for event in ordered}
    passing = any(degree % 7 in (1, 3, 5) for degree in degrees)
    velocities = [event["vel"] for event in ordered]
    bars = {}
    for event in ordered:
        bars.setdefault(event.get("bar", 0), []).append((event["step"], event["len"], event["deg"]))
    unique = len({tuple(value) for value in bars.values()})
    return (f"notes {len(ordered)} ({len(ordered) / 4:.1f}/bar), distinct pitches {len(set(pitches))}, "
            f"leaps {leaps}/{len(intervals)}, passing tones {'yes' if passing else 'no'}, "
            f"velocity {min(velocities):.2f}-{max(velocities):.2f}, unique bars {unique}/4")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bird", default="glint", choices=sorted(BIRDS))
    parser.add_argument("--song", default="A", choices=["A", "B", "C"])
    parser.add_argument("--events", type=Path, help="JSON list replacing the song in memory")
    parser.add_argument("--out", type=Path, default=ROOT / "flock-audition.wav")
    parser.add_argument("--bpm", type=float, default=90)
    parser.add_argument("--swing", type=float, default=0.58)
    parser.add_argument("--context", choices=["solo", "template"], default="solo",
                        help="solo: the bird + drums; template: the whole Dusty flock")
    args = parser.parse_args()

    events = BIRDS[args.bird]["songs"][args.song]
    print(f"current {args.bird} {args.song}")
    print(_grid(events))
    print(_stats(events))

    if args.events:
        events = json.loads(args.events.read_text(encoding="utf-8"))
        if not isinstance(events, list) or not events:
            raise SystemExit("--events must be a non-empty JSON list")
        for index, event in enumerate(events):
            if not isinstance(event, dict) or not {"bar", "step", "len", "deg", "vel"} <= set(event):
                raise SystemExit(f"event {index} needs bar, step, len, deg, vel")
        synth._BIRDS[args.bird]["songs"][args.song] = events
        print(f"\nnew {args.bird} {args.song}")
        print(_grid(events))
        print(_stats(events))

    project = _project(args.bird, args.song, args.bpm, args.swing, args.context)
    audio, _meters, _meta = render._render_audio_with_metadata(project, render.SAMPLE_RATE, None)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(args.out, audio, render.SAMPLE_RATE, subtype="PCM_24")
    print(f"\nwrote {args.out} ({len(audio) / render.SAMPLE_RATE:.2f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
