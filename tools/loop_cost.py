"""Measure chat tool-result and schema bytes for an 8-track, 8-bar beat."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rookery import tools
from rookery import events
from rookery.service import reset_services_for_tests


PATTERNS = {
    "kick": "x.......x...x..." * 8,
    "snare": "....x.......x..." * 8,
    "hat": "x.x.x.x.x.x.x.x." * 8,
    "openhat": "........x......." * 8,
    "clap": "....x.......x..." * 8,
    "perc": "..x.....x...x..." * 8,
    "tom": "..............x." * 8,
    "rim": "...x............" * 8,
}
SOURCES = {
    "kick": "factory:kick_boom", "snare": "factory:snare_crack",
    "hat": "factory:hat_closed", "openhat": "factory:hat_open",
    "clap": "factory:clap", "perc": "factory:perc",
    "tom": "factory:perc", "rim": "factory:rim",
}


class Events:
    def editing(self, _name):
        return nullcontext()


class RawTools:
    """Pre-receipt behavior: expose the same direct, expanded tool responses."""

    def __getattr__(self, name):
        return getattr(tools, name)


def _handler(engine, name):
    return tools.make_handler(engine, name, compact_receipts=engine.compact)


def _run(root: Path, compact: bool) -> tuple[int, int, int]:
    os.environ["ROOKERY_DATA_DIR"] = str(root)
    reset_services_for_tests()
    engine = SimpleNamespace(tools=tools if compact else RawTools(), events=Events(), compact=compact)
    events.emit = lambda *_args, **_kwargs: None
    calls = 0
    result_bytes = 0

    def invoke(tool_name, params):
        nonlocal calls, result_bytes
        value = _handler(engine, tool_name)(params)
        calls += 1
        result_bytes += len(value.encode("utf-8"))

    invoke("rookery_new", {"name": "loop-cost", "bpm": 92, "bars": 8})
    ops = []
    for track_id, source in SOURCES.items():
        add = {"op": "track", "action": "add", "id": track_id,
               "kind": "drum", "source": source}
        steps = {"op": "steps", "track": track_id, "steps": PATTERNS[track_id]}
        ops.extend((add, steps))
        if compact:
            continue
    fx1 = [{"type": "compressor", "threshold_db": -18, "ratio": 3}]
    fx2 = [{"type": "limiter", "ceiling_db": -1}]
    ops.extend((
        {"op": "mix", "target": "master", "fx": fx1},
        {"op": "mix", "target": "kick", "fx": fx2},
        {"op": "meta", "bpm": 92, "swing": 0.12},
        {"op": "meta", "humanize_ms": 1.5},
    ))
    if compact:
        invoke("rookery_apply", {"name": "loop-cost", "ops": ops})
    else:
        for op in ops:
            kind = op["op"]
            if kind == "track":
                invoke("rookery_track", {"name": "loop-cost", **{k: v for k, v in op.items() if k != "op"}})
            elif kind == "steps":
                invoke("rookery_steps", {"name": "loop-cost", **{k: v for k, v in op.items() if k != "op"}})
            elif kind == "mix":
                invoke("rookery_mix", {"name": "loop-cost", **{k: v for k, v in op.items() if k != "op"}})
            else:
                invoke("rookery_track", {"name": "loop-cost", "action": "set", "id": "master",
                                          **{k: v for k, v in op.items() if k != "op"}})

    schema_names = ["rookery_new", "rookery_apply"] if compact else [
        "rookery_new", *(["rookery_track", "rookery_steps"] * 8),
        "rookery_mix", "rookery_track", "rookery_track", "rookery_track",
    ]
    schema_bytes = sum(len(json.dumps(tools.SCHEMAS[name], ensure_ascii=False,
                                      separators=(",", ":")).encode("utf-8"))
                       for name in schema_names)
    return calls, result_bytes, schema_bytes


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="rookery-loop-cost-") as temp:
        before = _run(Path(temp) / "before", compact=False)
        after = _run(Path(temp) / "after", compact=True)
    print(f"before calls={before[0]} result_bytes={before[1]} schema_bytes={before[2]}")
    print(f"after  calls={after[0]} result_bytes={after[1]} schema_bytes={after[2]}")


if __name__ == "__main__":
    main()
