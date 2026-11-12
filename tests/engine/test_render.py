import numpy as np
import pytest

from rookery.render import render_audio, render_project, wav_bytes


def _project(bpm=90, bars=4, swing=0.0, tracks=None):
    return {
        "schema": "rookery.project/1",
        "name": "render-test",
        "bpm": bpm,
        "bars": bars,
        "steps_per_bar": 16,
        "swing": swing,
        "seed": 1337,
        "tracks": tracks or [],
    }


def test_length_exact_for_known_tempos_and_bar_counts():
    for bpm, bars in ((90, 4), (90, 8), (93, 4), (93, 8)):
        expected = round(bars * 4 * 60 / bpm * 44100)
        audio, _ = render_audio(_project(bpm, bars))
        assert audio.dtype == np.float32
        assert audio.shape == (expected, 2)
        assert not np.any(audio)


def test_swing_does_not_change_length():
    straight, _ = render_audio(_project())
    swung, _ = render_audio(_project(swing=0.5))
    assert straight.shape == swung.shape == (470400, 2)


def test_factory_kit_is_repeatable_and_seeded():
    from rookery.kit import synthesize

    a = synthesize("hat_closed", seed=1)
    b = synthesize("hat_closed", seed=1)
    c = synthesize("hat_closed", seed=2)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_muted_track_is_silence():
    project = _project(tracks=[{"id": "kick", "kind": "drum", "source": "factory:kick_boom",
                               "steps": "x...", "mute": True}])
    audio, _ = render_audio(project)
    assert not np.any(audio)


def test_render_and_wav_bytes_repeat_without_cache():
    project = _project(tracks=[{"id": "kick", "kind": "drum", "source": "factory:kick_boom",
                               "steps": "x...x..."}])
    first, _ = render_audio(project)
    second, _ = render_audio(project)
    assert np.array_equal(first, second)
    assert wav_bytes(first) == wav_bytes(second)


def test_wav_hash_ignores_the_project_name(tmp_path):
    tracks = [{"id": "kick", "kind": "drum", "source": "factory:kick_punch", "steps": "x...x..."},
              {"id": "hat", "kind": "drum", "source": "factory:hat_tight", "steps": ".x.x"}]
    first = render_project({**_project(tracks=tracks), "name": "dusty-90"}, tmp_path / "first")
    second = render_project({**_project(tracks=tracks), "name": "dusty-90-copy"}, tmp_path / "second")
    # The canonical audio projection leaves out the project name, and the bytes
    # do not read it either: the copy is the same audio under a different name.
    assert first["hash"] == second["hash"]
    assert first["wav_hash"] == second["wav_hash"]
    assert first["path"] != second["path"]
    changed = render_project({**_project(tracks=[{**tracks[0], "steps": "x...x..x"}, tracks[1]]),
                              "name": "dusty-90"}, tmp_path / "changed")
    assert changed["wav_hash"] != first["wav_hash"]


def test_swing_changes_hit_positions():
    track = {"id": "hat", "kind": "drum", "source": "factory:hat_closed", "steps": ".x.."}
    straight, _ = render_audio(_project(tracks=[track]))
    swung, _ = render_audio(_project(swing=1.0, tracks=[track]))
    assert not np.array_equal(straight, swung)


def test_choke_group_cuts_open_hat():
    open_hat = {"id": "open", "kind": "drum", "source": "factory:hat_open", "steps": "x...............",
                "choke_group": "hats"}
    closed_hat = {"id": "closed", "kind": "drum", "source": "factory:hat_closed", "steps": "....x...........",
                  "choke_group": "hats"}
    without_choke, _ = render_audio(_project(tracks=[open_hat]))
    choked, _ = render_audio(_project(tracks=[open_hat, closed_hat]))
    assert not np.array_equal(without_choke, choked)


def test_long_bass_note_wraps_tail_into_loop_start():
    bass = {"id": "bass", "kind": "bass", "source": "factory:808",
            "notes": [{"step": 63, "len": 16, "pitch": "C1"}]}
    audio, _ = render_audio(_project(tracks=[bass]))
    assert np.any(np.abs(audio[:1000]) > 0)


def test_bass_pitch_velocity_and_swing_change_audio_deterministically():
    note = {"step": 1, "len": 2, "pitch": "C2"}
    base = _project(tracks=[{"id": "bass", "kind": "bass", "notes": [note]},
                            {"id": "anchor", "kind": "bass", "notes": [{"step": 8, "len": 2, "pitch": "C2"}]}])
    pitched = {**base, "tracks": [{**base["tracks"][0], "pitch": 5}]}
    softened = {**base, "tracks": [{**base["tracks"][0], "velocity": [0.2]}]}
    swung = {**base, "swing": 0.8}
    results = [render_audio(item)[0] for item in (base, pitched, softened, swung)]
    assert all(result.shape == results[0].shape for result in results)
    assert not np.array_equal(results[0], results[1])
    assert not np.array_equal(results[0], results[2])
    assert not np.array_equal(results[0], results[3])
    assert np.array_equal(results[0], render_audio(base)[0])
    assert wav_bytes(results[0]) == wav_bytes(render_audio(base)[0])


def test_highpass_is_cyclic_and_shift_equivariant():
    from rookery.render import _highpass

    t = np.arange(4096) / 4096
    periodic = np.column_stack((np.sin(2 * np.pi * 7 * t), 0.3 * np.cos(2 * np.pi * 13 * t)))
    filtered = _highpass(periodic, 44100)
    shifted = _highpass(np.roll(periodic, 731, axis=0), 44100)
    assert np.allclose(np.roll(filtered, 731, axis=0), shifted, atol=1e-12)
    assert np.max(np.abs(filtered[0] - filtered[-1])) < 0.03


def test_fx_is_applied_per_track_and_muted_track_does_not_run(monkeypatch):
    import sys
    import types
    import rookery.render as renderer

    calls = []
    fx = types.ModuleType("rookery.fx")

    def apply_fx(audio, chain, sr):
        calls.append((chain, audio.copy()))
        return audio * (2 if chain == ["double"] else 1)

    fx.apply_fx = apply_fx
    monkeypatch.setitem(sys.modules, "rookery.fx", fx)
    monkeypatch.setattr(renderer, "synthesize", lambda name, **kwargs:
                        np.full(100, -1 if name == "snare_crack" else 1, dtype=np.float32))
    monkeypatch.setattr(renderer, "_highpass", lambda audio, sr: audio)

    class FixedMeter:
        def __init__(self, sr):
            pass

        def integrated_loudness(self, audio):
            return -14.0

    monkeypatch.setattr(renderer.pyln, "Meter", FixedMeter)
    one_hit = "x" + "." * 63
    a = {"id": "a", "source": "factory:kick_boom", "steps": one_hit, "fx": ["double"]}
    b = {"id": "b", "source": "factory:snare_crack", "steps": one_hit}
    muted = {"id": "muted", "source": "factory:kick_boom", "steps": one_hit, "mute": True, "fx": ["double"]}
    _, meters = render_audio(_project(tracks=[a, b, muted]))
    assert [chain for chain, _ in calls] == [["double"]]
    assert calls[0][1][:100].max() > 0
    assert calls[0][1][:100].min() >= 0
    assert not np.any(calls[0][1][100:])
    assert set(meters) == {"a", "b", "muted"}


def test_fx_tail_is_folded_into_loop_start(monkeypatch):
    import sys
    import types
    from rookery.render import _fx_chain

    fx = types.ModuleType("rookery.fx")

    def delay(audio, chain, sr):
        delayed = np.zeros_like(audio)
        delayed[1500:] = audio[:-1500]
        return delayed

    fx.apply_fx = delay
    monkeypatch.setitem(sys.modules, "rookery.fx", fx)
    loop = np.zeros((12000, 2), dtype=np.float64)
    loop[-1000:] = 1
    result = _fx_chain(loop, ["delay"], 8000, 4000)
    assert result.shape == loop.shape
    assert np.all(result[500:1500] == 1)
    repeated = np.tile(result, (3, 1))
    jumps = np.max(np.abs(np.diff(repeated, axis=0)), axis=1)
    seam_jumps = np.array([np.max(np.abs(repeated[i * len(result)] - repeated[i * len(result) - 1]))
                           for i in (1, 2)])
    body_jumps = np.delete(jumps, [len(result) - 1, 2 * len(result) - 1])
    assert np.all(seam_jumps <= np.percentile(body_jumps, 99.9) * 1.5)


def test_requested_fx_without_module_fails_loudly(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "rookery.fx", None)
    from rookery.render import _fx_chain

    with pytest.raises(ModuleNotFoundError):
        _fx_chain(np.zeros((16, 2)), ["requested"], 44100, 4)
    with pytest.raises(ModuleNotFoundError):
        render_audio({**_project(), "master": {"fx": ["requested"]}})


def test_clap_synthesis_accepts_duration_shorter_than_stagger_delays():
    from rookery.kit import synthesize

    clap = synthesize("clap", sr=44100, duration=0.001)
    assert clap.shape == (44,)
    assert np.isfinite(clap).all()


def test_choke_from_first_step_cuts_open_hat_across_wrap():
    open_hat = {"id": "open", "source": "factory:hat_open", "steps": "." * 63 + "x",
                "choke_group": "hats"}
    closed_hat = {"id": "closed", "source": "factory:hat_closed", "steps": "x" + "." * 63,
                  "choke_group": "hats"}
    without_choke, meters_without = render_audio(_project(tracks=[open_hat]))
    with_choke, meters_with = render_audio(_project(tracks=[open_hat, closed_hat]))
    assert meters_with["open"]["rms_db"] < meters_without["open"]["rms_db"] - 1
    assert not np.array_equal(without_choke, with_choke)


def test_pitch_changes_all_factory_voices_and_rejects_nonfinite():
    from rookery.kit import FACTORY_NAMES, synthesize

    for name in FACTORY_NAMES:
        low = synthesize(name, sr=16000, seed=9, pitch=-7)
        high = synthesize(name, sr=16000, seed=9, pitch=7)
        assert not np.array_equal(low, high), name
        with pytest.raises(ValueError):
            synthesize(name, sr=16000, pitch=float("nan"))


def test_user_sample_rejects_non_audio_suffix_before_decoding(tmp_path, monkeypatch):
    import rookery.render as render

    kit = tmp_path / "kit"
    kit.mkdir()
    (kit / "notes.json").write_text("{}")
    (kit / "message.txt").write_text("hello")
    calls = []
    monkeypatch.setattr(render.sf, "read", lambda *args, **kwargs: calls.append(args))

    for source in ("user:notes.json", "user:message.txt"):
        with pytest.raises(ValueError, match="audio"):
            render._read_user_sample(source, kit, 44100)
    assert calls == []


def test_user_sample_audio_symlink_resolving_to_non_audio_is_refused(tmp_path, monkeypatch):
    import pathlib

    import rookery.render as render

    kit = tmp_path / "kit"
    kit.mkdir()
    notes = kit / "notes.json"
    notes.write_text("{}")
    link = kit / "clip.wav"
    try:
        link.symlink_to(notes)
    except (OSError, NotImplementedError):
        real_resolve = pathlib.Path.resolve

        def fake_resolve(self, *args, **kwargs):
            return notes if self == link else real_resolve(self, *args, **kwargs)

        monkeypatch.setattr(pathlib.Path, "resolve", fake_resolve)
    calls = []
    monkeypatch.setattr(render.sf, "read", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(ValueError, match="audio"):
        render._read_user_sample("user:clip.wav", kit, 44100)
    assert calls == []


@pytest.mark.parametrize("suffix", [".WAV", ".Flac", ".AIFF", ".aif", ".OGG"])
def test_user_sample_accepts_supported_audio_suffixes_case_insensitively(tmp_path, suffix):
    import rookery.render as render

    kit = tmp_path / "kit"
    kit.mkdir()
    sample = kit / f"kick{suffix}"
    sample.touch()

    assert render._safe_sample_path(f"user:kick{suffix}", kit) == sample.resolve()


def test_user_sample_path_still_cannot_escape_the_kit(tmp_path):
    import rookery.render as render

    kit = tmp_path / "kit"
    kit.mkdir()
    (tmp_path / "outside.wav").touch()

    with pytest.raises(ValueError, match="inside|escape"):
        render._safe_sample_path("user:../outside.wav", kit)


def test_renderer_imports_under_hermes_namespace_from_other_cwd(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    script = r"""
import importlib
import sys
import types
namespace = types.ModuleType('hermes_plugin_rookery')
namespace.__path__ = [sys.argv[1]]
sys.modules[namespace.__name__] = namespace
renderer = importlib.import_module('hermes_plugin_rookery.rookery.render')
assert renderer.synthesize('hat_closed', sr=8000).shape[0] > 0
assert 'rookery' not in sys.modules
assert 'hermes_plugin_rookery.rookery.project' not in sys.modules
"""
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run([sys.executable, "-c", script, str(repo)], cwd=tmp_path,
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_long_sample_plays_until_its_next_hit_instead_of_failing(tmp_path):
    # A sample longer than one step used to be rejected ("would require time-stretching").
    # It now plays like a sampler: until the track's next hit, wrapping, never past the loop.
    import numpy as np
    import soundfile as sf
    from rookery.project import new_project, validate_project
    from rookery.render import render_audio
    sr = 44100
    tone = 0.5 * np.sin(2 * np.pi * 220 * np.arange(sr * 3) / sr)
    sf.write(tmp_path / "long.wav", tone, sr)
    def render(steps):
        project = new_project("long-sample", bpm=120, bars=4)
        project["tracks"] = [{"id": "s", "kind": "sample", "source": "user:long.wav", "steps": steps, "slices": 1}]
        return render_audio(validate_project(project), user_kit_dir=tmp_path)[0]
    once = render("x" + "." * 63)        # one hit in an 8 s loop: the full 3 s plays
    twice = render("x" + "." * 7 + "x" + "." * 55)  # second hit at 1 s cuts the first
    def energy(audio, a, b):
        return float(np.mean(audio[int(a * sr):int(b * sr)] ** 2))
    assert energy(once, 1.5, 2.5) > 1e-4           # still sounding 2 s in
    assert energy(once, 4.0, 7.0) < 1e-6           # silent once the sample ends
    assert energy(twice, 1.5, 2.0) > 1e-4          # the second hit sounds
    assert energy(twice, 4.5, 7.0) < 1e-6          # and is not stacked with the first
