import numpy as np

from rookery import events, tools
from rookery.kit import FACTORY_NAMES, synthesize
from rookery.render import render_audio
from rookery.service import Service


NEW_RECIPES = {
    "kick": ("kick_punch", "kick_thump", "kick_sub", "kick_snap", "kick_rumble"),
    "snare": ("snare_crack_wide", "snare_snap_dry", "snare_body", "snare_burst", "snare_dust"),
    "clap": ("clap_stack", "clap_wide", "clap_sharp", "clap_dust", "clap_tail"),
    "hat_closed": (
        "hat_closed_tight_tick", "hat_closed_bright", "hat_closed_dark",
        "hat_closed_dust", "hat_closed_metal",
    ),
    "hat_open": ("hat_open_wash", "hat_open_sizzle", "hat_open_bright", "hat_open_dark", "hat_open_long"),
    "perc": ("perc_tom_low", "perc_tom_high", "perc_woodblock", "perc_rimshot", "perc_bongo"),
    "808": ("808_sub_clean", "808_long_glide", "808_drop", "808_bloom", "808_grit"),
}


def test_new_factory_voices_are_registered_and_deterministic_audible_unclipped():
    recipe_ids = [name for names in NEW_RECIPES.values() for name in names]
    assert len(recipe_ids) == 35
    assert set(recipe_ids) <= set(FACTORY_NAMES)

    for name in recipe_ids:
        first = synthesize(name, sr=16000, seed=71)
        second = synthesize(name, sr=16000, seed=71)
        assert np.array_equal(first, second), name
        assert np.isfinite(first).all(), name
        assert np.max(np.abs(first)) > 0.05, name
        assert np.max(np.abs(first)) <= 1.0, name


def test_new_factory_voices_are_listed_addable_and_renderable(tmp_path, monkeypatch):
    monkeypatch.setattr(events, "publisher", lambda *args, **kwargs: None)
    catalog = Service(tmp_path).status()["kits"]["factory"]
    recipe_ids = [name for names in NEW_RECIPES.values() for name in names]
    assert set(recipe_ids) <= set(catalog)

    render_tracks = []
    for category, names in NEW_RECIPES.items():
        project_name = f"recipes-{category}"
        tools.new(tmp_path, project_name, 240)
        for name in names:
            kind = "bass" if category == "808" else "drum"
            fields = {"notes": [{"step": 0, "len": 16, "pitch": "C1"}]} if kind == "bass" else {"steps": "x"}
            tools.track(
                tmp_path, project_name, "add", name, kind=kind, source=f"factory:{name}",
                gain_db=-36, **fields,
            )
            track = {"id": name, "kind": kind, "source": f"factory:{name}", "gain_db": -36}
            track.update(fields)
            render_tracks.append(track)

    audio, _ = render_audio({
        "schema": "rookery.project/1", "name": "new-factory-voices", "bpm": 240,
        "bars": 4, "steps_per_bar": 16, "swing": 0, "seed": 1337,
        "tracks": render_tracks,
    })
    assert np.isfinite(audio).all()
    assert np.max(np.abs(audio)) > 0.01
    assert np.max(np.abs(audio)) <= 1.0
