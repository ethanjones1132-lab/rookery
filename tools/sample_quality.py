"""Measure candidate sample files against Rookery's quality gate.

Offline only: it reads the paths you give it and prints a table. It never
downloads, copies or writes audio files. The measurements and the gate itself
live in ``rookery/sample_gate.py``; this script only adds ffprobe's bitrate and
the plugin's own BPM/key estimate for the research tables.

    python tools/sample_quality.py path/to/loop.wav path/to/hit.flac
    python tools/sample_quality.py --bpm 128 --kind loop stems/*.wav
    python tools/sample_quality.py --json samples/*

The gate is documented in docs/design/research/sample-sources.md §7. Exit
status is 0 unless a file is rejected (flagged files are accepted with
warnings), 2 on a usage/read error.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rookery.sample_gate import assess  # noqa: E402


def _ffprobe(path: Path) -> dict:
    """Read container/codec facts with ffprobe when it is installed."""
    exe = shutil.which("ffprobe")
    if not exe:
        return {}
    try:
        out = subprocess.run(
            [exe, "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=codec_name,bit_rate",
             "-show_entries", "format=format_name,bit_rate",
             "-of", "json", str(path)],
            check=True, capture_output=True, text=True, timeout=20,
        )
        data = json.loads(out.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return {}
    streams = data.get("streams") or [{}]
    fmt = data.get("format") or {}
    stream = streams[0] if isinstance(streams[0], dict) else {}
    return {
        "codec": stream.get("codec_name") or "",
        "bitrate_kbps": round(int(stream.get("bit_rate") or fmt.get("bit_rate") or 0) / 1000, 1),
    }


def _analyze(path: Path) -> dict:
    from rookery.sampling import analyze
    try:
        return analyze(path, title=path.name)
    except Exception as exc:  # analysis must not hide the measurements
        return {"error": f"{type(exc).__name__}: {exc}"}


def measure(path: Path, *, bpm: float | None, kind: str) -> dict:
    result = assess(path, kind=kind, bpm=bpm)
    metrics = result["metrics"]
    probe = _ffprobe(path)
    analysis = _analyze(path)
    return {
        "path": str(path),
        **metrics,
        "codec": (probe.get("codec") or metrics["subtype"]).lower(),
        "bitrate_kbps": probe.get("bitrate_kbps"),
        "kind": kind,
        "bpm_audio": (round(analysis["bpm"], 2)
                      if isinstance(analysis.get("bpm"), (int, float)) else analysis.get("bpm")),
        "bpm_source": analysis.get("bpm_source"),
        "key_audio": analysis.get("key"),
        "key_source": analysis.get("key_source"),
        "bars_analyze": analysis.get("bars"),
        "confidence": analysis.get("confidence"),
        "bpm_stated": bpm,
        "verdict": result["verdict"],
        "failures": result["reasons"],
        "warnings": result["warnings"],
        "pass": result["verdict"] != "reject",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--bpm", type=float, default=None, help="stated tempo for loop-length checking")
    parser.add_argument("--kind", choices=("loop", "one-shot"), default="one-shot")
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = parser.parse_args(argv)

    rows = []
    for path in args.paths:
        if not path.is_file():
            print(f"error: not a file: {path}", file=sys.stderr)
            return 2
        try:
            row = measure(path, bpm=args.bpm, kind=args.kind)
        except Exception as exc:
            print(f"error: {path}: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        rows.append(row)

    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0 if all(row["pass"] for row in rows) else 1

    header = ["file", "sec", "sr", "ch", "bit", "codec", "kbps", "BW kHz", "peak", "clip",
              "floor", "LUFS", "crest", "BPM", "key", "bars", "gate"]
    print("  ".join(f"{name:>7}" if name not in {"file", "codec", "key", "gate"} else
                    f"{name:<7}" for name in header))
    labels = {"pass": "PASS", "flag": "FLAG", "reject": "FAIL"}
    for row in rows:
        name = Path(row["path"]).name
        print("  ".join([
            f"{name[:28]:<28}",
            f"{row['seconds']:>7.2f}",
            f"{row['sample_rate']:>7}",
            f"{row['channels']:>3}",
            f"{str(row['bit_depth'] or '-'):>4}",
            f"{row['codec'][:7]:<7}",
            f"{str(row['bitrate_kbps'] or '-'):>7}",
            f"{row['bandwidth_khz']:>6.1f}",
            f"{row['peak_dbfs']:>7.2f}",
            f"{row['clipped_runs']:>4}",
            f"{str(row['noise_floor_dbfs']):>7}",
            f"{str(row['lufs']):>7}",
            f"{str(row['crest_db']):>6}",
            f"{str(row['bpm_audio'] or '-'):>6}",
            f"{str(row['key_audio'] or '-')[:9]:<9}",
            f"{str(row['bars_analyze'] or '-'):>4}",
            labels[row["verdict"]],
        ]))
        if row["failures"]:
            print(f"    FAIL: {', '.join(row['failures'])}")
        if row["warnings"]:
            print(f"    note: {', '.join(row['warnings'])}")
    return 0 if all(row["pass"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
