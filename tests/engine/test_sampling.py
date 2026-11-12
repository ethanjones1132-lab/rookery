import io
import json

import numpy as np
import soundfile as sf
import pytest

from rookery import samples
from rookery import tools
from rookery.project import new_project, project_hash, validate_project
from rookery.render import _render_audio_with_metadata
from rookery.render import _render_song_audio
from rookery.sampling import analyze, parse_title
from rookery.checks import check_audio
from rookery.service import Service


def _click_loop(path, bpm=100, bars=2, sr=16000, key="F major"):
    duration = bars * 4 * 60 / bpm
    count = round(duration * sr)
    time = np.arange(count) / sr
    audio = (0.01 * np.sin(2 * np.pi * 180 * time)).astype(np.float32)
    for beat in range(bars * 4):
        start = round(beat * 60 / bpm * sr)
        length = min(round(.012 * sr), count - start)
        if length > 0:
            audio[start:start + length] += .7 * np.exp(-np.arange(length, dtype=np.float32) / max(1, sr * .001))
    sf.write(path, audio, sr)


def test_parse_bpm_and_key_title_formats():
    assert parse_title("lofi emo guitar loop [100bpm] [f major]") == {"bpm": 100, "key": "F major"}
    assert parse_title("Warm Loop 100 BPM Fmin")["key"] == "F minor"
    assert parse_title("Guitar F#m 92bpm")["key"] == "F# minor"
    assert parse_title("bass Am")["key"] == "A minor"
    assert parse_title("lofi-emo-guitar-loop-100bpm-f-major")["key"] == "F major"
    assert parse_title("guitar-fmin-148-bpm-wav")["bpm"] == 148


def test_project_tempo_and_integer_bars_resolve_half_time_estimate_and_cache_context(tmp_path, monkeypatch):
    from rookery import sampling

    sr, bpm, bars = 16000, 140, 8
    count = round(bars * 4 * 60 / bpm * sr)
    audio = np.zeros(count, dtype=np.float32)
    for beat in range(bars * 4):
        start = round(beat * 60 / bpm * sr)
        audio[start:start + 64] = np.hanning(128)[32:96]
    library = tmp_path / "library"
    library.mkdir()
    path = library / "untagged-openverse-loop.flac"
    sf.write(path, audio, sr)
    monkeypatch.setattr(sampling, "_estimate_bpm", lambda *_args: (70.0, .6))

    at_project_tempo = analyze(path, project_bpm=140)
    assert at_project_tempo["bpm"] == pytest.approx(bars * 240 * sr / count)
    assert at_project_tempo["bars"] == bars
    assert at_project_tempo["bar_aligned"] is True

    # Analysis results depend on the project tempo. A cached 140 BPM decision
    # must not leak into a later project whose tempo favours the half-time read.
    at_other_tempo = analyze(path, project_bpm=90)
    assert at_other_tempo["bpm"] == pytest.approx(70, abs=.001)
    assert at_other_tempo["bars"] == 4


def test_estimates_synthetic_click_loop_tempo_within_one_bpm(tmp_path):
    path = tmp_path / "clicks.wav"
    _click_loop(path)
    result = analyze(path)
    assert abs(result["bpm"] - 100) <= 1


def test_duration_refines_noisy_tempo_estimate_for_exact_phrase(tmp_path):
    # The onset-envelope estimate is quantized to 10 ms and reads this exact
    # 2-bar 90 BPM phrase as 89.55 BPM. Exact phrase duration is more precise.
    path = tmp_path / "pulse.wav"
    _click_loop(path, bpm=90, bars=2, sr=44100, key=None)
    result = analyze(path)
    exact_bpm = 2 * 240 * 44100 / round(2 * 4 * 60 / 90 * 44100)
    assert result["bars"] == 2
    assert abs(result["bpm"] - exact_bpm) < 1e-9


def _render_clean_two_bar_loop(tmp_path, project_bpm, bars):
    sr, source_bpm, source_bars = 44100, 90, 2
    count = round(source_bars * 4 * 60 / source_bpm * sr)
    source = np.zeros((count, 2), dtype=np.float32)
    for beat in range(source_bars * 4):
        start = round(beat * 60 / source_bpm * sr)
        length = min(sr // 12, count - start)
        ping = (np.sin(2 * np.pi * 220 * np.arange(length) / sr)
                * .2 * np.exp(-np.arange(length) / (sr * .02))).astype(np.float32)
        source[start:start + length] += ping[:, None]
    edge = sr // 200
    ramp = np.linspace(0, 1, edge, dtype=np.float32)
    source[:edge] *= ramp[:, None]
    source[-edge:] *= ramp[::-1, None]
    path = tmp_path / "pulse.wav"
    sf.write(path, source, sr, subtype="PCM_24")

    project = validate_project(new_project("seam-grid", project_bpm, bars=bars))
    project["tracks"] = [{"id": "loop", "kind": "sample", "source": "user:pulse.wav",
                          "mode": "loop", "steps": "x" * bars, "key_lock": False}]
    audio, _, _ = _render_audio_with_metadata(project, sr, tmp_path)
    again, _, _ = _render_audio_with_metadata(project, sr, tmp_path)
    expected_samples = round(bars * 4 * 60 / project_bpm * sr)
    report = check_audio(audio, sr, expected_samples, deterministic=audio.tobytes() == again.tobytes())
    return audio, report, sr


@pytest.mark.parametrize("project_bpm", [84, 90, 100])
@pytest.mark.parametrize("bars", [4, 8])
def test_clean_two_bar_loop_seams_and_checks(tmp_path, project_bpm, bars):
    _, report, _ = _render_clean_two_bar_loop(tmp_path, project_bpm, bars)
    assert all(item["pass"] for item in report.values()), report


@pytest.mark.parametrize("project_bpm", [
    pytest.param(84, marks=pytest.mark.xfail(strict=True, reason="loop attacks land ~2.4-3.3 ms late at ratio <= 1 (constant latency offset); tracked")),
    pytest.param(90, marks=pytest.mark.xfail(strict=True, reason="loop attacks land ~2.4-3.3 ms late at ratio <= 1 (constant latency offset); tracked")),
    100,
])
@pytest.mark.parametrize("bars", [4, 8])
def test_clean_two_bar_loop_attacks_on_grid(tmp_path, project_bpm, bars):
    audio, _, sr = _render_clean_two_bar_loop(tmp_path, project_bpm, bars)

    # Locate each attack at the first 5%-of-peak crossing in the expected beat window.
    mono = audio.mean(axis=1)
    radius = round(.02 * sr)
    measured = []
    for beat in range(bars * 4):
        expected = round(beat * 60 / project_bpm * sr)
        lo, hi = max(1, expected - radius), min(len(mono) - 1, expected + radius)
        region = np.abs(mono[lo:hi])
        crossings = np.flatnonzero(region >= region.max() * .05)
        measured.append(lo + int(crossings[0]))
    offsets_ms = np.abs(np.asarray(measured) - np.asarray(
        [round(i * 60 / project_bpm * sr) for i in range(bars * 4)])) * 1000 / sr
    # Each beat piece is phase-aligned within the renderer's +/- 3 ms WSOLA search
    # (render.py _loop_sample), so attacks may move by up to that window, never more.
    assert float(offsets_ms.max()) <= 3.0, offsets_ms.tolist()


def test_analysis_returns_sources_downbeat_bars_and_size_keyed_cache(tmp_path):
    library = tmp_path / "library"
    library.mkdir()
    path = library / "100bpm F major.wav"
    _click_loop(path)
    result = analyze(path)
    cache = json.loads((library / "analysis.json").read_text())
    assert cache[path.name]["size"] == path.stat().st_size
    assert cache[path.name]["analysis"] == result
    assert result["bpm_source"] == result["key_source"] == "title"
    assert result["key"] == "F major" and result["bars"] == 2
    assert result["key_confidence"] == .85
    assert result["downbeat_s"] == 0
    assert result["profile"]["rhythm"] == "".join("9" if step % 4 == 0 else "0" for step in range(16))


def test_analysis_profiles_register_sustain_rhythm_and_role_from_synthesized_audio(tmp_path):
    sr, bpm, bars = 16000, 120, 2
    seconds = bars * 4 * 60 / bpm
    time = np.arange(round(seconds * sr), dtype=np.float32) / sr
    bed = sum(np.sin(2 * np.pi * frequency * time) for frequency in (293.66, 392.0, 493.88))
    bed_path = tmp_path / "bed.wav"
    sf.write(bed_path, (bed * .2).astype(np.float32), sr)
    bed_profile = analyze(bed_path, title="bed 120 bpm")["profile"]
    assert bed_profile["register"] == "low_mid"
    assert bed_profile["centroid_hz"] == pytest.approx((293.66 + 392 + 493.88) / 3, abs=8)
    assert len(bed_profile["bands"]) == 4 and sum(bed_profile["bands"]) == pytest.approx(1, abs=.001)
    assert bed_profile["sustain"] >= .95 and bed_profile["pitched"]
    assert bed_profile["role_hint"] == "bed"

    low_path = tmp_path / "low.wav"
    sf.write(low_path, (.2 * np.sin(2 * np.pi * 110 * time)).astype(np.float32), sr)
    low_profile = analyze(low_path, title="low 120 bpm")["profile"]
    assert low_profile["register"] == "low" and low_profile["role_hint"] == "counter"

    high_path = tmp_path / "high.wav"
    sf.write(high_path, (.2 * np.sin(2 * np.pi * 4000 * time)).astype(np.float32), sr)
    high_profile = analyze(high_path, title="high 120 bpm")["profile"]
    assert high_profile["register"] == "high" and high_profile["pitched"]

    lead = np.zeros_like(time)
    for step in (1, 5, 9, 13):
        start = round(step * 15 / bpm * sr)
        length = round(.07 * sr)
        local = np.arange(length, dtype=np.float32) / sr
        lead[start:start + length] += .8 * np.sin(2 * np.pi * 1200 * local) * np.exp(-local / .025)
        next_bar = start + round(2 * sr)
        if next_bar + length <= len(lead):
            lead[next_bar:next_bar + length] += .8 * np.sin(2 * np.pi * 1200 * local) * np.exp(-local / .025)
    lead_path = tmp_path / "lead.wav"
    sf.write(lead_path, lead, sr)
    lead_profile = analyze(lead_path, title="lead 120 bpm")["profile"]
    assert lead_profile["register"] == "mid"
    assert lead_profile["sustain"] < .55 and lead_profile["pitched"]
    assert lead_profile["role_hint"] == "lead"
    assert lead_profile["rhythm"][1] >= "5" and lead_profile["rhythm"][5] >= "5"
    assert lead_profile["rhythm"][0] == "0"

    drums = np.zeros(round(seconds * sr), dtype=np.float32)
    rng = np.random.default_rng(123)
    for bar in range(bars):
        for step in (0, 4, 8, 12):
            start = round((bar * 16 + step) * 15 / bpm * sr)
            length = round(.025 * sr)
            burst = rng.standard_normal(length).astype(np.float32) * np.exp(-np.arange(length) / (sr * .004))
            drums[start:start + length] += burst
    drums_path = tmp_path / "drums.wav"
    sf.write(drums_path, drums, sr)
    drums_profile = analyze(drums_path, title="drums 120 bpm")["profile"]
    assert drums_profile["rhythm"][0] == "9" and drums_profile["rhythm"][4] >= "5"
    assert drums_profile["density"] == 4 and drums_profile["busy_steps"] == 4
    assert not drums_profile["pitched"] and drums_profile["role_hint"] == "drums"

    sparse = np.zeros_like(drums)
    sparse[:320] = rng.standard_normal(320).astype(np.float32) * np.exp(-np.arange(320) / 35)
    sparse_path = tmp_path / "texture.wav"
    sf.write(sparse_path, sparse, sr)
    sparse_profile = analyze(sparse_path, title="texture 120 bpm")["profile"]
    assert sparse_profile["density"] < 4 and not sparse_profile["pitched"]
    assert sparse_profile["role_hint"] == "texture"


def test_declared_key_marks_diffuse_chroma_as_pitched_but_nokey_stays_unpitched(tmp_path):
    sr = 16000
    rng = np.random.default_rng(7)
    noise = (rng.standard_normal(sr) * .1).astype(np.float32)
    keyed, unpitched = tmp_path / "Amin-wide-loop.wav", tmp_path / "nokey-Amin-wide-loop.wav"
    sf.write(keyed, noise, sr)
    sf.write(unpitched, noise, sr)

    assert analyze(keyed)["profile"]["pitched"] is True
    assert analyze(unpitched)["profile"]["pitched"] is False


def test_vocal_title_marks_diffuse_chroma_as_pitched(tmp_path):
    sr = 16000
    rng = np.random.default_rng(9)
    path = tmp_path / "vocal-part.wav"
    sf.write(path, (rng.standard_normal(sr) * .1).astype(np.float32), sr)

    assert analyze(path)["profile"]["pitched"] is True


def test_unpitched_profile_disables_automatic_loop_key_lock(tmp_path, monkeypatch):
    import pedalboard
    from rookery import render, sampling

    sr, bpm, bars = 8000, 90, 4
    count = round(bars * 4 * 60 / bpm * sr)
    sf.write(tmp_path / "loop.wav", np.zeros(count, dtype=np.float32), sr)
    monkeypatch.setattr(sampling, "analyze", lambda *_args, **_kwargs: {
        "bpm": bpm, "key": "C major", "downbeat_s": 0.0, "bars": bars,
        "profile": {"pitched": False},
    })
    monkeypatch.setattr(render, "_stretch_latency", lambda *_args: 0)
    monkeypatch.setattr(pedalboard, "time_stretch", lambda audio, *_args, **_kwargs: np.asarray(audio))
    shifts = []
    monkeypatch.setattr(render, "_key_lock_interval",
                        lambda *args: shifts.append(args) or 0)
    project = validate_project(new_project("unpitched-lock", bpm, key="A", scale="major"))
    render._loop_sample("user:loop.wav", tmp_path, sr, project,
                        {"id": "loop", "key_lock": True})
    assert shifts == []


def test_low_confidence_audio_key_disables_automatic_loop_key_lock(tmp_path, monkeypatch):
    import pedalboard
    from rookery import render, sampling

    sr, bpm, bars = 8000, 90, 4
    count = round(bars * 4 * 60 / bpm * sr)
    sf.write(tmp_path / "loop.wav", np.zeros(count, dtype=np.float32), sr)
    monkeypatch.setattr(sampling, "analyze", lambda *_args, **_kwargs: {
        "bpm": bpm, "key": "C major", "key_source": "audio", "key_confidence": .2,
        "downbeat_s": 0.0, "bars": bars, "profile": {"pitched": True},
    })
    monkeypatch.setattr(render, "_stretch_latency", lambda *_args: 0)
    monkeypatch.setattr(pedalboard, "time_stretch", lambda audio, *_args, **_kwargs: np.asarray(audio))
    shifts = []
    monkeypatch.setattr(render, "_key_lock_interval",
                        lambda *args: shifts.append(args) or 0)
    project = validate_project(new_project("uncertain-lock", bpm, key="A", scale="major"))

    render._loop_sample("user:loop.wav", tmp_path, sr, project,
                        {"id": "loop", "key_lock": True})

    assert shifts == []


def test_old_analysis_cache_is_recomputed_to_add_profile(tmp_path):
    library = tmp_path / "library"
    library.mkdir()
    path = library / "old.wav"
    _click_loop(path, bpm=100, bars=2)
    (library / "analysis.json").write_text(json.dumps({
        path.name: {"size": path.stat().st_size,
                    "analysis": {"bpm": 100, "bars": 2}},
    }), encoding="utf-8")

    result = analyze(path)

    assert "profile" in result
    assert "profile" in json.loads((library / "analysis.json").read_text())[path.name]["analysis"]


def test_fetch_includes_analysis_and_project_fit_note(tmp_path, monkeypatch):
    audio = io.BytesIO()
    time = np.arange(8 * 8000, dtype=np.float32) / 8000
    source = (.25 * np.sin(2 * np.pi * 349.23 * time)).astype(np.float32)
    sf.write(audio, source, 8000, format="WAV")
    item = {"id": "sample123", "title": "Guitar loop 100 BPM F major", "creator": "maker",
            "license": "cc0", "license_url": "", "foreign_landing_url": "",
            "url": "https://cdn.freesound.org/audio.wav", "duration": 8000}
    monkeypatch.setattr(samples, "_json_response", lambda _url: item)
    monkeypatch.setattr(samples, "_response_body", lambda _url, _maximum: audio.getvalue())
    result = samples.fetch("sample123", tmp_path / "kit", 92, "D")
    assert result["analysis"]["bpm"] == 100
    assert result["analysis"]["key"] == "F major"
    assert result["profile"] == result["analysis"]["profile"]
    assert result["fit_note"] == (
        "100 BPM F major loop, 4 bars; in loop mode it plays at 92 in D. "
        "Key lock shift: -3 semitones."
    )


def test_unpitched_fetch_profile_recommends_disabling_key_lock(tmp_path, monkeypatch):
    sr, bpm = 16000, 120
    audio = np.zeros(round(2 * 4 * 60 / bpm * sr), dtype=np.float32)
    rng = np.random.default_rng(19)
    for beat in range(8):
        start = round(beat * 60 / bpm * sr)
        hit = rng.standard_normal(320).astype(np.float32) * np.exp(-np.arange(320) / 35)
        audio[start:start + len(hit)] += hit
    buffer = io.BytesIO()
    sf.write(buffer, audio, sr, format="WAV")
    item = {"id": "unpitched123", "title": "Texture loop 120 BPM", "creator": "maker",
            "license": "cc0", "license_url": "", "foreign_landing_url": "",
            "url": "https://cdn.freesound.org/texture.wav", "duration": 4000}
    monkeypatch.setattr(samples, "_json_response", lambda _url: item)
    monkeypatch.setattr(samples, "_response_body", lambda _url, _maximum: buffer.getvalue())

    result = samples.fetch("unpitched123", tmp_path / "kit", bpm, "A")

    assert result["profile"]["pitched"] is False
    assert result["profile"]["role_hint"] == "drums"
    assert result["key_lock_shift_semitones"] is None
    assert "key_lock=false" in result["hint"]


def test_openverse_fetch_warns_instead_of_using_low_confidence_audio_key(tmp_path, monkeypatch):
    from rookery import sampling

    sr, bpm = 44100, 90
    audio = (.2 * np.sin(2 * np.pi * 440 * np.arange(sr, dtype=np.float32) / sr)).astype(np.float32)
    raw = io.BytesIO()
    sf.write(raw, audio, sr, format="WAV")
    item = {"id": "uncertain123", "title": "Vocal loop", "creator": "maker",
            "license": "cc0", "license_url": "", "foreign_landing_url": "",
            "url": "https://cdn.freesound.org/uncertain.wav", "duration": 1000}
    monkeypatch.setattr(samples, "_json_response", lambda _url: item)
    monkeypatch.setattr(samples, "_response_body", lambda _url, _maximum: raw.getvalue())
    monkeypatch.setattr(sampling, "analyze", lambda *_args, **_kwargs: {
        "bpm": bpm, "bpm_source": "title", "key": "G minor", "key_source": "audio",
        "key_confidence": .2, "bars": 1, "downbeat_s": 0,
        "profile": {"pitched": True, "register": "mid", "rhythm": "0" * 16,
                    "sustain": .8, "bands": [0, 0, 1, 0], "role_hint": "bed"},
    })

    result = samples.fetch("uncertain123", tmp_path / "kit", bpm, "A")

    assert result["key_lock_shift_semitones"] is None
    assert "low-confidence key" in result["hint"]
    assert "low confidence" in result["fit_note"]


def test_loop_mode_locks_clicks_across_every_bar_seam_and_has_no_gap(tmp_path):
    path = tmp_path / "loop 100bpm F major.wav"
    _click_loop(path)
    project = new_project("loop-test", bpm=92, bars=4)
    project["tracks"] = [{"id": "loop", "kind": "sample", "source": f"user:{path.name}",
                          "mode": "loop", "steps": "xxxx", "pitch": 0}]
    project = validate_project(project)
    audio, _, _ = _render_audio_with_metadata(project, sample_rate=16000, user_kit_dir=tmp_path, fixed_gain=1)
    mono = audio.mean(axis=1)
    # Click peaks must stay close to the project beat grid, including the two-bar tile seam.
    expected = np.array([round(i * 60 / 92 * 16000) for i in range(16)])
    measured = []
    radius = round(.025 * 16000)
    for beat in expected:
        region = mono[max(0, beat - radius):min(len(mono), beat + radius)]
        measured.append(max(0, beat - radius) + int(np.argmax(np.abs(region))))
    assert np.max(np.abs(np.asarray(measured) - expected)) <= round(.005 * 16000)
    # The longest run of consecutive near-silent samples (a real gap), not the distance between
    # isolated zero crossings.
    silent = (np.abs(mono) < 1e-7).astype(np.int8)
    edges = np.diff(np.r_[0, silent, 0])
    runs = np.where(edges == -1)[0] - np.where(edges == 1)[0]
    assert not len(runs) or runs.max() / 16000 <= .02


def _loop_render(project, sr, kit_dir, *, song):
    if song:
        return _render_song_audio(project, sr, kit_dir, fixed_gain=1)[0]
    return _render_audio_with_metadata(project, sr, kit_dir, fixed_gain=1)[0]


def _tone_amplitude(signal, sr, frequency):
    time = np.arange(len(signal), dtype=np.float64) / sr
    phase = 2 * np.pi * frequency * time
    return 2 * np.hypot(np.dot(signal, np.sin(phase)), np.dot(signal, np.cos(phase))) / len(signal)


@pytest.mark.parametrize("song", [False, True], ids=["loop", "song"])
def test_new_project_loop_preserves_stereo_and_centers_sub_120_hz(tmp_path, monkeypatch, song):
    from rookery import sampling

    sr, bpm, bars = 8000, 90, 4
    count = round(bars * 4 * 60 / bpm * sr)
    time = np.arange(count, dtype=np.float64) / sr
    low = np.sin(2 * np.pi * 60 * time)
    high = np.sin(2 * np.pi * 450 * time)
    stereo = np.column_stack((.3 * low + .2 * high, .1 * low - .2 * high)).astype(np.float32)
    sf.write(tmp_path / "stereo.wav", stereo, sr, subtype="FLOAT")
    monkeypatch.setattr(sampling, "analyze", lambda *_args, **_kwargs: {
        "bpm": bpm, "key": "A minor", "downbeat_s": 0.0, "bars": bars, "confidence": .9,
    })
    import pedalboard
    monkeypatch.setattr(pedalboard, "time_stretch", lambda audio, *_args, **_kwargs: np.asarray(audio))

    project = new_project("stereo-loop", bpm, bars)
    project["mix_profile"] = "targets-v1"
    project["tracks"] = [{"id": "loop", "kind": "sample", "source": "user:stereo.wav",
                          "mode": "loop", "steps": "xxxx", "key_lock": False}]
    if song:
        project["arrangement"] = {"sections": [{"id": "A", "repeat": 1, "mute": []}]}
    audio = _loop_render(validate_project(project), sr, tmp_path, song=song)

    side = audio[:, 0] - audio[:, 1]
    low_side = _tone_amplitude(side, sr, 60)
    high_side = _tone_amplitude(side, sr, 450)
    assert high_side > .2  # stereo width above the crossover survives
    assert low_side < high_side * .15  # sub-120 Hz side content is strongly attenuated
    assert _tone_amplitude(audio.mean(axis=1), sr, 60) > .03  # the centered low end remains


@pytest.mark.parametrize("song", [False, True], ids=["loop", "song"])
def test_legacy_stereo_loop_pcm_matches_its_mono_projection(tmp_path, monkeypatch, song):
    from rookery import sampling
    from rookery.render import wav_bytes

    sr, bpm, bars = 8000, 90, 4
    count = round(bars * 4 * 60 / bpm * sr)
    time = np.arange(count, dtype=np.float64) / sr
    stereo = np.column_stack((.31 * np.sin(2 * np.pi * 110 * time),
                              .17 * np.cos(2 * np.pi * 330 * time))).astype(np.float32)
    mono = stereo.mean(axis=1, dtype=np.float64).astype(np.float32)
    sf.write(tmp_path / "legacy-stereo.wav", stereo, sr, subtype="FLOAT")
    sf.write(tmp_path / "legacy-mono.wav", mono, sr, subtype="FLOAT")
    monkeypatch.setattr(sampling, "analyze", lambda *_args, **_kwargs: {
        "bpm": bpm, "key": "A minor", "downbeat_s": 0.0, "bars": bars, "confidence": .9,
    })
    import pedalboard
    monkeypatch.setattr(pedalboard, "time_stretch", lambda audio, *_args, **_kwargs: np.asarray(audio))

    def project(source):
        value = new_project("legacy-stereo-loop", bpm, bars)
        value["tracks"] = [{"id": "loop", "kind": "sample", "source": f"user:{source}",
                            "mode": "loop", "steps": "xxxx", "key_lock": False}]
        if song:
            value["arrangement"] = {"sections": [{"id": "A", "repeat": 1, "mute": []}]}
        result = validate_project(value)
        assert "mix_profile" not in result
        return result

    stereo_render = _loop_render(project("legacy-stereo.wav"), sr, tmp_path, song=song)
    mono_render = _loop_render(project("legacy-mono.wav"), sr, tmp_path, song=song)
    assert wav_bytes(stereo_render, sr, "PCM_24") == wav_bytes(mono_render, sr, "PCM_24")


def test_loop_mode_conversion_defaults_legacy_sample_pattern_to_every_bar():
    project = new_project("loop-convert", 92, bars=4)
    project["tracks"] = [
        {"id": "loop", "kind": "sample", "source": "user:loop.wav", "steps": "x" + "." * 63, "mode": "loop"},
        {"id": "default", "kind": "sample", "source": "user:other.wav", "steps": ".", "mode": "loop"},
    ]
    normalized = validate_project(project)
    assert normalized["tracks"][0]["steps"] == normalized["tracks"][1]["steps"] == "xxxx"


def test_song_renderer_supports_loop_samples(tmp_path):
    path = tmp_path / "100bpm F major.wav"
    _click_loop(path)
    project = new_project("song-loop", 92, bars=4)
    project["tracks"] = [{"id": "loop", "kind": "sample", "source": f"user:{path.name}",
                          "mode": "loop", "steps": "xxxx", "duck": .4}]
    project["arrangement"] = {"sections": [{"id": "A", "repeat": 1, "mute": []}]}
    project = validate_project(project)
    audio, _, _, sections = _render_song_audio(project, 16000, tmp_path, fixed_gain=1)
    assert len(audio) == round(4 * 4 * 60 / 92 * 16000)
    assert sections[0]["id"] == "A"


def test_song_loop_sample_reads_audio_only_for_analysis_and_stretch(tmp_path, monkeypatch):
    import pedalboard
    from rookery import render

    sr, bpm, bars = 8000, 90, 4
    count = round(bars * 4 * 60 / bpm * sr)
    path = tmp_path / "loop.wav"
    sf.write(path, np.zeros(count, dtype=np.float32), sr)
    original_read = sf.read
    reads = []

    def counting_read(*args, **kwargs):
        reads.append(args[0])
        return original_read(*args, **kwargs)

    monkeypatch.setattr(render.sf, "read", counting_read)
    monkeypatch.setattr(render, "_stretch_latency", lambda *_args: 0)
    monkeypatch.setattr(pedalboard, "time_stretch", lambda audio, *_args, **_kwargs: np.asarray(audio))
    project = new_project("single-read-loop", bpm, bars=bars)
    project["tracks"] = [{"id": "loop", "kind": "sample", "source": "user:loop.wav",
                          "mode": "loop", "steps": "xxxx"}]
    project["arrangement"] = {"sections": [{"id": "A", "repeat": 1, "mute": []}]}

    _render_song_audio(validate_project(project), sr, tmp_path, fixed_gain=1)

    # One decode for analysis and one for the actual sample buffer. The song
    # renderer must not decode/resample a throwaway buffer before _loop_sample.
    assert len(reads) == 2


def test_loop_pitch_preserves_length_and_key_lock_selects_smallest_interval(tmp_path, monkeypatch):
    path = tmp_path / "100bpm F major.wav"
    _click_loop(path)
    project = new_project("pitch-test", bpm=92, bars=4)
    from rookery.flock.model import default_flock
    project["flock"] = default_flock()
    project["flock"]["key"] = "D"
    project["tracks"] = [{"id": "loop", "kind": "sample", "source": f"user:{path.name}",
                          "mode": "loop", "steps": "xxxx", "pitch": -1}]
    project = validate_project(project)
    import pedalboard
    calls = []
    original = pedalboard.time_stretch
    def checked_stretch(audio, sr, **kwargs):
        calls.append(kwargs["pitch_shift_in_semitones"])
        return original(audio, sr, **kwargs)
    monkeypatch.setattr(pedalboard, "time_stretch", checked_stretch)
    rendered, _, _ = _render_audio_with_metadata(project, 16000, tmp_path, fixed_gain=1)
    assert len(rendered) == round(4 * 4 * 60 / 92 * 16000)
    # F to D is -3 semitones; the analysis carries the source key and chosen project key.
    assert analyze(path)["key"] == "F major"
    # D dorian has C major's notes: F major moves down 5 to C, plus the explicit -1.
    assert calls[0] == -6
    again, _, _ = _render_audio_with_metadata(project, 16000, tmp_path, fixed_gain=1)
    assert rendered.tobytes() == again.tobytes()


def test_loop_state_shows_compact_tempo_and_key_fit(tmp_path):
    library = tmp_path / "library"
    library.mkdir()
    path = library / "100bpm F major.wav"
    _click_loop(path)
    service = Service(tmp_path / "data", user_kit_dir=tmp_path)
    service.new("state-loop", 92, bars=4)
    service.edit({"name": "state-loop", "op": "flock", "action": "harmony", "key": "D"})
    service.edit({"name": "state-loop", "op": "track", "action": "add", "id": "loop", "kind": "sample",
                  "source": "user:library/100bpm F major.wav", "mode": "loop", "steps": "xxxx"})
    state = service.state("state-loop")
    assert "loop · 100→92 BPM · F→D (−5) · 2 bars" in state
    assert "profile ·" in state and "rhythm" in state and "role" in state


def test_legacy_project_hash_is_unchanged_by_optional_loop_fields():
    project = new_project("legacy-hash", 92, bars=4)
    with_fields = json.loads(json.dumps(project))
    assert project_hash(project, "renderer") == project_hash(with_fields, "renderer")
    # Normalizing a one-shot sample does not inject loop defaults into its audio identity.
    sample = {"id": "sample", "kind": "sample", "source": "user:old.wav", "steps": "x", "slices": 1}
    before = {**project, "tracks": [sample]}
    after = {**project, "tracks": [{**sample, "mode": "oneshot"}]}
    assert project_hash(before, "renderer") == project_hash(after, "renderer")


def test_search_fit_ranks_tempo_and_key_match_first(monkeypatch):
    results = [
        {"id": "wrong1234", "title": "Loop 120 BPM A minor", "license": "cc0", "duration": 5000},
        {"id": "right1234", "title": "Loop 92 BPM F major", "license": "cc0", "duration": 5000},
    ]
    monkeypatch.setattr(samples, "_json_response", lambda _url: {"results": results})
    hits = samples.search("guitar loop", bpm=92, key="F")
    assert hits[0]["id"] == "right1234"
    assert 0 <= hits[0]["fit"] <= 1
    assert all(len(json.dumps(hit, separators=(",", ":")).encode()) < 170 for hit in hits)


def test_loop_mode_keeps_sustained_notes_level_across_beat_seams(tmp_path):
    # Stretching beat by beat used to fade each piece to silence: a dip on every beat.
    sr = 16000
    seconds = 2 * 4 * 60 / 100
    t = np.arange(round(seconds * sr)) / sr
    tone = (0.5 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)   # 5 ms period: steady 5 ms RMS
    path = tmp_path / "pad 100bpm C major.wav"
    sf.write(path, tone, sr)
    project = new_project("sustain", 92, bars=4)
    project["tracks"] = [{"id": "pad", "kind": "sample", "source": f"user:{path.name}",
                          "mode": "loop", "steps": "xxxx", "key_lock": False}]
    audio, _, _ = _render_audio_with_metadata(validate_project(project), sr, tmp_path, fixed_gain=1)
    from scipy.signal import hilbert
    mono = np.asarray(audio, dtype=np.float64).mean(axis=1)
    envelope = np.abs(hilbert(mono))
    k = round(sr * .002)
    envelope = np.convolve(envelope, np.ones(k) / k, "same")[400:-400]
    # Beat-by-beat fades measured -12 dB here; overlap-added, phase-aligned pieces stay near -3.
    assert 20 * np.log10(envelope.min() / np.median(envelope)) > -5.0


def test_key_lock_treats_relative_keys_as_the_same_notes():
    from rookery.render import _key_lock_interval
    assert _key_lock_interval("F major", "D", "minor") == 0      # F major = D minor's notes
    assert _key_lock_interval("A minor", "C", "major") == 0
    assert _key_lock_interval("F major", "D", "dorian") == -5    # D dorian = C major's notes
    assert _key_lock_interval("E minor", "D", "major") == -5     # E minor has G major's notes -> D major


def test_loop_key_lock_prefers_project_harmony_then_uses_flock_for_legacy(tmp_path, monkeypatch):
    import pedalboard
    from rookery import render, sampling
    from rookery.flock.model import default_flock

    sr = 8000
    seconds = 4 * 4 * 60 / 90
    audio = np.sin(2 * np.pi * 220 * np.arange(round(seconds * sr)) / sr).astype(np.float32)
    sf.write(tmp_path / "test-loop.wav", audio, sr)
    monkeypatch.setattr(sampling, "analyze", lambda *_args, **_kwargs: {
        "bpm": 90, "key": "C major", "downbeat_s": 0.0, "bars": 4, "confidence": .9,
    })
    monkeypatch.setattr(pedalboard, "time_stretch", lambda buffer, *_args, **_kwargs: np.asarray(buffer))
    targets = []
    monkeypatch.setattr(render, "_key_lock_interval",
                        lambda sample, key, scale: targets.append((sample, key, scale)) or 0)

    project = new_project("project-harmony", 90, bars=4, key="A", scale="major")
    project["flock"] = default_flock()  # D dorian must not override A major.
    track = {"id": "loop", "kind": "sample", "source": "user:test-loop.wav",
             "mode": "loop", "key_lock": True, "steps": "xxxx"}
    render._loop_sample(track["source"], tmp_path, sr, validate_project(project), track)
    assert targets and set(targets) == {("C major", "A", "major")}

    targets.clear()
    legacy = new_project("legacy-harmony", 90, bars=4)
    legacy["flock"] = default_flock()
    render._loop_sample(track["source"], tmp_path, sr, validate_project(legacy), track)
    assert targets and set(targets) == {("C major", "D", "dorian")}


def test_sample_tool_defaults_search_and_fetch_harmony_to_project(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from rookery.service import reset_services_for_tests

    monkeypatch.setenv("ROOKERY_DATA_DIR", str(tmp_path / "data"))
    reset_services_for_tests()
    tools.new(tmp_path / "data", "keyed", 92, key="Bb", scale="minor")
    seen = {}

    def search(*args, **kwargs):
        seen["search"] = (args, kwargs)
        return []

    def fetch(*args, **kwargs):
        seen["fetch"] = (args, kwargs)
        return {"source": "user:library/fake.flac"}

    monkeypatch.setattr(samples, "search", search)
    monkeypatch.setattr(samples, "fetch", fetch)
    engine = SimpleNamespace(tools=tools)
    handler = tools.make_handler(engine, "rookery_samples")
    handler({"action": "search", "query": "rhodes"})
    handler({"action": "fetch", "id": "sample-id"})
    assert seen["search"][0][4:] == (92, "A#")
    assert seen["fetch"][0][2:4] == (92, "A#")
    assert seen["fetch"][1]["project_scale"] == "minor"
    reset_services_for_tests()


def test_sample_tool_batches_queries_and_ids_with_per_item_validation(tmp_path, monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace
    from rookery.project import ValidationError
    from rookery.service import reset_services_for_tests

    monkeypatch.setenv("ROOKERY_DATA_DIR", str(tmp_path / "data"))
    reset_services_for_tests()
    tools.new(tmp_path / "data", "batch-keyed", 92, key="Bb", scale="minor")
    calls = {"search": [], "fetch": []}

    def search(query, *args, **kwargs):
        calls["search"].append((query, args, kwargs))
        return [{"id": f"{query}-hit"}]

    def fetch(identifier, *args, **kwargs):
        calls["fetch"].append((identifier, args, kwargs))
        if identifier == "rejected-id":
            raise ValidationError("sample failed the import quality gate")
        return {"source": f"user:library/{identifier}.flac"}

    monkeypatch.setattr(samples, "search", search)
    monkeypatch.setattr(samples, "fetch", fetch)
    handler = tools.make_handler(SimpleNamespace(tools=tools), "rookery_samples")

    groups = json.loads(handler({"action": "search", "queries": ["rhodes", "flute"],
                                 "source": "openverse", "limit": 3}))
    assert groups == [
        {"query": "rhodes", "results": [{"id": "rhodes-hit"}]},
        {"query": "flute", "results": [{"id": "flute-hit"}]},
    ]
    assert len(calls["search"]) == 2
    assert all(call[1] == (None, None, 3, 92, "A#") for call in calls["search"])
    assert all(call[2]["source"] == "openverse"
               and Path(call[2]["kit_dir"]) == tmp_path / "data" / "kits"
               for call in calls["search"])

    fetched = json.loads(handler({"action": "fetch", "ids": ["good-id", "rejected-id"],
                                  "source": "openverse"}))
    assert fetched == [
        {"id": "good-id", "source": "user:library/good-id.flac"},
        {"id": "rejected-id", "error": "sample failed the import quality gate"},
    ]
    assert len(calls["fetch"]) == 2
    assert all(Path(call[1][0]) == tmp_path / "data" / "kits" and call[1][1:] == (92, "A#")
               for call in calls["fetch"])
    assert all(call[2] == {"project_scale": "minor", "source": "openverse"}
               for call in calls["fetch"])

    too_many = json.loads(handler({"action": "search", "queries": ["a", "b", "c", "d", "e"]}))
    too_many_ids = json.loads(handler({"action": "fetch", "ids": ["a", "b", "c", "d", "e"]}))
    conflicting_queries = json.loads(handler({"action": "search", "query": "one", "queries": ["two"]}))
    conflict = json.loads(handler({"action": "fetch", "id": "one", "ids": ["two"]}))
    assert "1 to 4" in too_many["error"]
    assert "1 to 4" in too_many_ids["error"]
    assert "not both" in conflicting_queries["error"]
    assert "not both" in conflict["error"]
    properties = tools.SCHEMAS["rookery_samples"]["parameters"]["properties"]
    assert properties["queries"]["maxItems"] == properties["ids"]["maxItems"] == 4
    reset_services_for_tests()


def test_loop_mode_short_bar_gate_repeats_like_drum_steps():
    project = new_project("gate", 92, bars=8)
    project["tracks"] = [{"id": "a", "kind": "sample", "source": "user:a.wav", "mode": "loop", "steps": "x"},
                         {"id": "b", "kind": "sample", "source": "user:b.wav", "mode": "loop", "steps": "x."}]
    normalized = validate_project(project)
    assert normalized["tracks"][0]["steps"] == "x" * 8
    assert normalized["tracks"][1]["steps"] == "x." * 4


def test_nokey_in_the_name_stops_key_detection(tmp_path):
    """Importers mark unpitched loops "nokey" so loop-mode key lock leaves drums alone."""
    import numpy as np
    import soundfile as sf
    from rookery.sampling import analyze
    rate = 44100
    tone = np.sin(2 * np.pi * 440 * np.arange(rate * 2) / rate).astype(np.float32) * .5
    plain, marked = tmp_path / "a" / "loop.wav", tmp_path / "b" / "90bpm-nokey-loop.wav"
    for path in (plain, marked):
        path.parent.mkdir()
        sf.write(path, tone, rate)
    assert analyze(plain)["key"] is not None
    result = analyze(marked)
    assert result["key"] is None and result["key_source"] == "none" and result["bpm"] == 90
    assert result["key_confidence"] == 0
    assert result["profile"]["pitched"] is False


def test_audio_key_confidence_is_reported_separately_from_tempo(tmp_path, monkeypatch):
    from rookery import sampling

    path = tmp_path / "audio-key.wav"
    sf.write(path, np.zeros(16000, dtype=np.float32), 16000)
    monkeypatch.setattr(sampling, "_estimate_bpm", lambda *_args: (100.0, .9))
    monkeypatch.setattr(sampling, "_estimate_key_from_chroma", lambda *_args: ("A minor", .42))

    result = analyze(path)

    assert result["key"] == "A minor"
    assert result["key_confidence"] == .42
    assert result["confidence"] == .66


def test_bar_aligned_loop_keeps_its_opening_rest_on_the_downbeat(tmp_path):
    """A lead that answers on the "and" must not be pulled onto the beat."""
    sr = 44100
    library = tmp_path / "library"
    library.mkdir()
    t = np.arange(round(sr * 0.25)) / sr
    note = (0.6 * np.sin(2 * np.pi * 880 * t) * np.exp(-t * 12)).astype(np.float32)

    aligned = np.zeros(sr * 4, dtype=np.float32)  # exactly 2 bars at 120 BPM
    for start in (0.375, 2.375):  # step 3 of each bar
        i = round(start * sr)
        aligned[i:i + len(note)] += note
    path = library / "120bpm-Amin-answer-lead.flac"
    sf.write(path, aligned, sr)
    result = analyze(path)
    assert result["bar_aligned"] is True
    assert result["downbeat_s"] == 0.0

    loose = np.concatenate([np.zeros(round(sr * 0.6), dtype=np.float32), aligned[round(sr * 0.375):]])
    loose = np.concatenate([loose, np.zeros(round(sr * 0.3), dtype=np.float32)])
    path = library / "120bpm-Amin-untrimmed-take.flac"
    sf.write(path, loose, sr)
    result = analyze(path)
    assert result["bar_aligned"] is False
    assert result["downbeat_s"] > 0.5
