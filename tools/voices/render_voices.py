"""Build Serum one-shots. Requires Xfer Serum 1.368 and pedalboard locally."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
SERUM = Path(r"C:\Program Files\Common Files\VST3\Serum.vst3\Contents\x86_64-win\Serum.vst3")
SR = 44100
SPACING = 3
HOLDS = {"bramble": (1.2, .35), "cinder": (.5, 1.5), "quill": (1., 1.2),
         "sable": (.8, .6), "corvus": (.8, .6), "hush": (3.4, 1.8), "moss": (3.4, 1.8),
         "jinx": (.6, .4), "glint": (.4, 1.2), "tick": (.15, .3), "pip": (.15, .3),
         "echo": (.4, .6), "wren_not": (.5, .6)}
ROLES = {"bramble": "bass", "cinder": "bass", "quill": "keys", "sable": "keys",
         "corvus": "keys", "hush": "pad", "moss": "pad", "jinx": "lead", "glint": "lead",
         "tick": "arp", "pip": "arp", "echo": "call", "wren_not": "call"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serum", type=Path, default=SERUM)
    parser.add_argument("--output", type=Path, default=ROOT / "rookery/flock/voices")
    args = parser.parse_args()
    import pedalboard

    recipes = json.loads((ROOT / "tools/voices/serum_patches.json").read_text(encoding="utf-8"))
    catalog = json.loads((ROOT / "rookery/flock/birds.json").read_text(encoding="utf-8"))
    roles = catalog["registers"]
    birds = [*catalog["birds"], catalog["corvus"]]
    manifest = {"schema": "rookery.serum-voices/1", "serum_version": "1.368",
                "sample_rate": SR, "render_date": datetime.now(timezone.utc).isoformat(),
                "provenance": "Rendered by the Rookery authors with Xfer Serum from original patches; no Serum presets or wavetable files are included.", "birds": {}}
    for bird in birds:
        bird_id = bird["id"]
        patch = recipes["patches"][bird_id]
        role = ROLES[bird_id]
        low, high = roles[role]
        notes = list(range(low, high + 1, SPACING))
        if notes[-1] != high:
            notes.append(high)
        hold, tail = HOLDS[bird_id]
        plugin = pedalboard.load_plugin(str(args.serum))
        parameters = plugin.parameters
        unknown = sorted(set(patch["parameters"]) - set(parameters))
        if unknown:
            raise ValueError(f"{bird_id}: recipe parameters not in plugin: {unknown}")
        def apply(target, name, value):
            parameter = target.parameters[name]
            if isinstance(value, str) and value in parameter.valid_values:
                setattr(target, name, value)
                return
            if isinstance(value, str):
                try:
                    numeric = float(value)
                except ValueError:
                    setattr(target, name, value)
                    return
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                numeric = float(value)
            else:
                setattr(target, name, value)
                return
            candidates = []
            for shown in parameter.valid_values:
                if not isinstance(shown, str):
                    try:
                        candidates.append((abs(float(shown) - numeric), shown))
                    except (TypeError, ValueError):
                        pass
                    continue
                match = re.search(r"[-+]?\d+(?:\.\d+)?", shown)
                if match:
                    candidates.append((abs(float(match.group()) - numeric), shown))
            if candidates:
                setattr(target, name, min(candidates)[1])
            elif name in {"a_warp", "b_warp"}:
                # Serum exposes these as normalized raw controls and labels the
                # value "no Warp type" until a warp mode is selected.
                parameter.raw_value = min(1.0, max(0.0, numeric / 100.0))
            else:
                setattr(target, name, str(value))

        for name, value in {"a_unison": "1", "b_unison": "1",
                            "a_phase_deg": "180", "b_phase_deg": "180",
                            "a_randphase": "0", "b_randphase": "0",
                            "noise_randphase": "0"}.items():
            if name in parameters:
                apply(plugin, name, value)
        for name, value in patch["parameters"].items():
            apply(plugin, name, value)
        # Universal render hygiene, irrespective of the per-patch recipe.
        for name in ("a_randphase", "b_randphase", "noise_randphase"):
            if name in parameters:
                apply(plugin, name, "0")
        gap = .12
        stride = hold + tail + gap
        messages = []
        starts = []
        for i, midi in enumerate(notes):
            start = i * stride
            starts.append(round(start * SR))
            messages += [(bytes((0x90, midi, 100)), start),
                         (bytes((0x80, midi, 0)), start + hold)]
        duration = len(notes) * stride + .1
        rendered = plugin(midi_messages=messages, duration=duration, sample_rate=SR)
        plugin_repeat = pedalboard.load_plugin(str(args.serum))
        for name, value in {"a_unison": "1", "b_unison": "1",
                            "a_phase_deg": "180", "b_phase_deg": "180",
                            "a_randphase": "0", "b_randphase": "0",
                            "noise_randphase": "0"}.items():
            if name in plugin_repeat.parameters:
                apply(plugin_repeat, name, value)
        for name, value in patch["parameters"].items():
            apply(plugin_repeat, name, value)
        for name in ("a_randphase", "b_randphase", "noise_randphase"):
            if name in plugin_repeat.parameters:
                apply(plugin_repeat, name, "0")
        repeated = plugin_repeat(midi_messages=messages, duration=duration, sample_rate=SR)
        deterministic = np.array_equal(np.asarray(rendered), np.asarray(repeated))
        if not deterministic:
            print(f"WARNING: {bird_id} Serum output is not byte-identical; retaining first render as source of truth")
        audio = np.asarray(rendered, dtype=np.float64)
        if audio.ndim == 2 and audio.shape[0] <= 2:
            audio = audio.T
        if audio.ndim == 1:
            audio = audio[:, None]
        bird_manifest = {"bird": bird_id, "role": role, "notes": [], "sample_rate": SR,
                         "patch_sha256": hashlib.sha256(json.dumps(patch["parameters"], sort_keys=True).encode()).hexdigest(),
                         "gui_todo": patch["gui_todo"], "deterministic_repeat": deterministic}
        bird_dir = args.output / bird_id
        bird_dir.mkdir(parents=True, exist_ok=True)
        for midi, begin in zip(notes, starts):
            count = round((hold + tail) * SR)
            clip = audio[begin:min(len(audio), begin + count)].copy()
            if not len(clip):
                raise RuntimeError(f"empty Serum render for {bird_id} MIDI {midi}")
            peak = float(np.max(np.abs(clip)))
            if peak:
                clip *= (10 ** (-3 / 20)) / peak
            # Trim leading silence and add a 20 ms terminal fade.
            active = np.flatnonzero(np.max(np.abs(clip), axis=1) > max(1e-7, np.max(np.abs(clip)) * 1e-5))
            if len(active):
                clip = clip[active[0]:active[-1] + 1]
            fade = min(len(clip), round(.02 * SR))
            clip[-fade:] *= np.linspace(1.0, 0.0, fade)[:, None]
            path = bird_dir / f"{midi}.flac"
            sf.write(path, clip.astype(np.float32), SR, format="FLAC", subtype="PCM_16")
            bird_manifest["notes"].append({"midi": midi, "file": path.relative_to(args.output).as_posix(),
                                            "peak_dbfs": -3.0 if peak else None, "frames": len(clip)})
        expected_files = {f"{midi}.flac" for midi in notes}
        for stale in bird_dir.glob("*.flac"):
            if stale.stem.isdigit() and stale.name not in expected_files:
                stale.unlink()
        manifest["birds"][bird_id] = bird_manifest
        print(f"{bird_id}: {len(notes)} notes")
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    total = sum(path.stat().st_size for path in args.output.rglob("*") if path.is_file())
    print(f"voices folder size: {total} bytes ({total / 1024 / 1024:.2f} MiB)")
    if total > 8 * 1024 * 1024:
        raise SystemExit("voices folder exceeds 8 MiB budget")


if __name__ == "__main__":
    main()
