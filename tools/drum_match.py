"""Measure Capital Drum Kit 4 one-shots against Rookery's synthesized voices.

The reference pack is read-only and only ever measured: no audio is copied,
shipped or required by the plugin. Results are printed as compact tables and,
with ``--write-targets``, summarised as medians and robust spreads in
``tools/drum_targets.json`` (numeric targets only) so tests can run without the
pack installed.

Usage (from the repo root, offline)::

    python tools/drum_match.py                    # full table
    python tools/drum_match.py --family kick      # one family
    python tools/drum_match.py --write-targets    # refresh drum_targets.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rookery.kit import factory as factory_module  # noqa: E402
from rookery.kit.measure import analyse, build_targets, distance, read_mono  # noqa: E402

DEFAULT_REFERENCE = Path(
    r"C:\Program Files\Image-Line\Packs\Capital Drum Kit 4\Capital Drum Kit 4"
)
TARGETS_PATH = Path(__file__).with_name("drum_targets.json")

# Reference category -> factory family. Cymbals are split by filename because
# the pack keeps closed and open hats in one folder.
_CATEGORIES = {
    "kick": ("Kick", None),
    "snare": ("Snare", None),
    "clap": ("Claps", None),
    "808": ("808", None),
    "perc": ("Perc", None),
    "rim": ("Rim", None),
    "hat_closed": ("Cymbals", "closed"),
    "hat_open": ("Cymbals", "open"),
}

_FAMILY_ORDER = ("kick", "snare", "clap", "hat_closed", "hat_open", "808", "perc", "rim")

LEGACY_FAMILIES = {
    "kick_boom": "kick",
    "808": "808",
    "snare_crack": "snare",
    "clap": "clap",
    "hat_closed": "hat_closed",
    "hat_open": "hat_open",
    "rim": "rim",
    "perc": "perc",
}


def factory_families() -> dict[str, str]:
    """Map every factory voice name to its measured family."""
    mapping = dict(LEGACY_FAMILIES)
    for name, recipe in factory_module._RECIPES.items():
        mapping[name] = recipe["family"]
    return mapping


def _is_open_hat(name: str) -> bool:
    return "open hat" in name.lower()


NEW_SOUNDS = frozenset((
    "kick_deep",
    "snare_snap",
    "clap_body",
    "hat_tight",
    "hat_bright",
    "hat_open_short",
    "808_round",
))


def reference_files(root: Path) -> dict[str, list[Path]]:
    """Group reference WAVs by family, excluding crashes and other non-hat cymbals."""
    found: dict[str, list[Path]] = {family: [] for family in _CATEGORIES}
    for family, (folder, cymbal_kind) in _CATEGORIES.items():
        directory = root / folder
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.wav")):
            if cymbal_kind is not None:
                name = path.stem.lower()
                is_hat = name.endswith(("hat", "hat 2", "hat 3", "tap", "tap 2"))
                if not is_hat:
                    continue
                if _is_open_hat(name) != (cymbal_kind == "open"):
                    continue
            found[family].append(path)
    return found


def measure_factory(family: str, sr: int = 44100) -> dict[str, dict]:
    """Measure every factory voice that belongs to one family."""
    mapping = factory_families()
    rows = {}
    for name, voice_family in mapping.items():
        if voice_family != family:
            continue
        audio = factory_module.synthesize(name, sr=sr)
        row = analyse(audio, sr, family)
        row["is_new"] = name in NEW_SOUNDS
        rows[name] = row
    return rows


def measure_references(files: list[Path], family: str) -> dict[str, dict]:
    rows = {}
    for path in files:
        audio, sr = read_mono(path)
        rows[path.stem] = analyse(audio, sr, family)
    return rows


def _fmt(value, digits=2, width=6):
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "-".rjust(width)
    return f"{value:.{digits}f}".rjust(width)


def print_family(family, refs, voices):
    tonal = family in ("kick", "808", "perc", "rim")
    header = (
        f"{'name':32s} {'len':>5s} {'atk':>5s} {'crest':>5s} {'tcrest':>6s} "
        f"{'click':>5s} {'t60':>5s} {'ctr':>5s} "
        f"{'sub':>4s} {'low':>4s} {'mid':>4s} {'pres':>4s} {'air':>4s}"
    )
    if tonal:
        header += f" {'p5':>5s} {'p60':>5s} {'tau':>5s} {'thd':>5s}"
    header += f" {'d_med':>5s} {'d_near':>6s}"
    print(f"\n=== {family} ({len(refs)} reference, {len(voices)} factory) ===")
    print(header)

    def line(name, stats, marker=""):
        text = (
            f"{name[:32]:32s} {stats['length_s']*1000:5.0f} {stats['attack_ms']:5.2f} "
            f"{stats['crest_db']:5.1f} {stats['transient_crest_db']:6.1f} "
            f"{stats['click_ratio_db']:5.1f} {stats['t60_s']*1000:5.0f} "
            f"{stats['centroid_hz']:5.0f} "
            f"{stats['sub_pct']:4.0f} {stats['low_pct']:4.0f} {stats['mid_pct']:4.0f} "
            f"{stats['presence_pct']:4.0f} {stats['air_pct']:4.0f}"
        )
        if tonal:
            text += (
                f" {_fmt(stats['pitch_5hz'], 0, 5)} {_fmt(stats['pitch_60hz'], 0, 5)} "
                f"{_fmt(stats['sweep_tau_s']*1000 if math.isfinite(stats['sweep_tau_s']) else math.nan, 0, 5)} "
                f"{_fmt(stats['thd_pct'], 0, 5)}"
            )
        text += f" {_fmt(stats.get('d_med'), 2, 5)} {_fmt(stats.get('d_near'), 2, 6)} {marker}"
        print(text)

    for name, stats in refs.items():
        line(name, stats)
    print("-" * 40)
    for name, stats in voices.items():
        line(name, stats, "*" if stats.get("is_new") else "")


def score(family, refs, voices, targets):
    target = targets["families"][family]
    ref_rows = list(refs.values())
    for stats in voices.values():
        stats["d_med"] = distance(stats, target, family)
        stats["d_near"] = min(distance(stats, _one(target, row, family), family) for row in ref_rows)
    return voices


def _one(target, row, family):
    features = target["features"]
    return {
        "features": features,
        "median": {f: row.get(f) for f in features},
        "scale": target["scale"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-root", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--family", action="append", choices=_FAMILY_ORDER)
    parser.add_argument("--write-targets", action="store_true")
    parser.add_argument("--json", type=Path, help="also write the measured rows as JSON")
    args = parser.parse_args(argv)

    if not args.reference_root.is_dir():
        raise SystemExit(f"reference pack not found: {args.reference_root}")

    families = args.family or list(_FAMILY_ORDER)
    files = reference_files(args.reference_root)
    ref_rows, voice_rows = {}, {}
    for family in families:
        if not files.get(family):
            continue
        ref_rows[family] = measure_references(files[family], family)
        voice_rows[family] = measure_factory(family)

    targets = build_targets({family: list(rows.values()) for family, rows in ref_rows.items()})
    if args.write_targets:
        TARGETS_PATH.write_text(json.dumps(targets, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {TARGETS_PATH.relative_to(ROOT)}")

    for family in families:
        if family not in ref_rows:
            continue
        score(family, ref_rows[family], voice_rows[family], targets)
        print_family(family, ref_rows[family], voice_rows[family])

    print("\n=== distances (robust z; lower is closer) ===")
    for family in families:
        if family not in ref_rows:
            continue
        voices = voice_rows[family]
        target = targets["families"][family]
        ref_d = [distance(row, target, family) for row in ref_rows[family].values()]
        ours = sorted((s["d_med"], name) for name, s in voices.items())
        closest = ", ".join(f"{name}={value:.2f}" for value, name in ours[:4])
        print(
            f"{family:11s} cloud mean={np.mean(ref_d):5.2f} cloud max={np.max(ref_d):5.2f} | {closest}"
        )

    if args.json:
        payload = {
            "reference": ref_rows,
            "factory": voice_rows,
        }
        args.json.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
