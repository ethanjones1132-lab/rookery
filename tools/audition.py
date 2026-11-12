"""Write factory one-shots and two patterns for the tuning hour.

    python tools/audition.py

Files land in renders/audition/, which git ignores. 16-bit WAV so the
script stays on the stdlib. The product render is still 24-bit.

This stays red until rookery.kit.factory and rookery.tools exist.
"""
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "renders" / "audition"
SR = 44100
SEED = 1337
GAP = int(0.35 * SR)

BOOM = {
    "bpm": 90,
    "swing": 0.58,
    "kick": "x.....x...x.....",
    "snare": "....x.......x...",
    "hat": "x.x.x.x.x.x.x.x.",
}
TRAP = {
    "bpm": 142,
    "swing": 0.0,
    "kick": "x.........x.....",
    "snare": "........x.......",
    "hat": "x.xxx.xxx.xxx.x.",
}


def to_mono(audio):
    arr = np.asarray(audio, dtype=np.float32)
    if arr.ndim == 2:
        arr = arr.mean(axis=1)
    return np.clip(arr, -1.0, 1.0)


def write_wav(path, audio):
    mono = to_mono(audio)
    pcm = (mono * 32767.0).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SR)
        handle.writeframes(pcm.tobytes())
    print(f"{path.name}  {len(mono) / SR:.2f}s")


def one_shots(synth, names):
    pieces = []
    for name in names:
        hit = to_mono(synth(name, SR, SEED))
        write_wav(OUT / f"{name}.wav", hit)
        pieces.append(hit)
        pieces.append(np.zeros(GAP, dtype=np.float32))
    write_wav(OUT / "all-hits.wav", np.concatenate(pieces))
    print("all-hits order: " + ", ".join(names))


def pattern(tools, label, spec):
    data = OUT / f"project-{label}"
    name = label
    tools.new(data, name, spec["bpm"], bars=4, swing=spec["swing"], seed=SEED)
    tools.track(data, name, "add", "kick", kind="drum", source="factory:kick_boom")
    tools.track(data, name, "add", "snare", kind="drum", source="factory:snare_crack")
    tools.track(data, name, "add", "hat", kind="drum", source="factory:hat_closed")
    tools.steps(data, name, "kick", spec["kick"])
    tools.steps(data, name, "snare", spec["snare"])
    tools.steps(data, name, "hat", spec["hat"])
    tools.mix(data, name, "master", [{"type": "limiter", "ceiling_db": -1.0}])
    out = tools.render(data, name)
    target = OUT / f"pattern-{label}.wav"
    target.write_bytes(Path(out["path"]).read_bytes())
    report = out["report"]
    lights = " ".join(
        f"{key}={'ok' if report[key]['pass'] else 'FAIL'}" for key in report
    )
    print(f"pattern-{label}.wav  {spec['bpm']} bpm  swing {spec['swing']}  {lights}")


def main():
    try:
        from rookery.kit.factory import synth
        from rookery import tools
    except ImportError as exc:
        print(f"audition needs the engine: {exc}")
        return 1
    try:
        from rookery.kit.factory import NAMES
        names = tuple(NAMES)
    except ImportError:
        names = (
            "kick_boom",
            "808",
            "snare_crack",
            "clap",
            "hat_closed",
            "hat_open",
            "rim",
            "perc",
        )
    OUT.mkdir(parents=True, exist_ok=True)
    one_shots(synth, names)
    pattern(tools, "boom-bap", BOOM)
    pattern(tools, "trap", TRAP)
    print(f"listen in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
