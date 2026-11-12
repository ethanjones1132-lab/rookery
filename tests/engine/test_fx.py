import numpy as np
import pytest

from rookery.fx import apply_fx, corvus_status


def test_empty_and_builtin_chain_keep_stereo_length_and_reset_state():
    t = np.arange(2048, dtype=np.float32) / 44100
    audio = np.column_stack((0.2 * np.sin(2 * np.pi * 440 * t), 0.1 * np.sin(2 * np.pi * 660 * t)))
    assert np.array_equal(apply_fx(audio, [], 44100), audio)
    chain = [{"type": "delay", "delay_seconds": 0.01, "feedback": 0.2, "mix": 0.3},
             {"type": "limiter", "ceiling_db": -1.0}]
    first = apply_fx(audio, chain, 44100)
    second = apply_fx(audio, chain, 44100)
    assert first.shape == audio.shape and first.dtype == np.float32
    assert np.array_equal(first, second)


@pytest.mark.parametrize("fx", [
    [{"type": "highpass", "cutoff_frequency_hz": 100}],
    [{"type": "lowpass", "cutoff_hz": 1000}],
])
def test_cutoff_names_are_supported(fx):
    result = apply_fx(np.ones((1000, 2), dtype=np.float32) * 0.1, fx, 44100)
    assert result.shape == (1000, 2)


@pytest.mark.parametrize("fx", [
    [{"type": "unknown"}], [{"type": "highpass", "q": 0.7}],
    [{"type": "compressor", "threshold_db": float("nan")}],
])
def test_unknown_fx_settings_and_nonfinite_values_rejected(fx):
    with pytest.raises(ValueError):
        apply_fx(np.zeros((32, 2), dtype=np.float32), fx, 44100)


def test_corvus_status_is_safe_without_install():
    status = corvus_status(r"Z:\missing\DrippyFX.vst3")
    assert status["found"] is False
    assert "params" in status


def test_corvus_mapping_parameters_are_actionable_and_cache_is_deepcopied(monkeypatch, tmp_path):
    import sys
    import types

    class Descriptor:
        min_value, max_value, default_value = 0.0, 100.0, 50.0

    class Plugin:
        parameters = {"fatness": Descriptor()}

        def __init__(self):
            self.fatness = 25.0

    monkeypatch.setitem(sys.modules, "pedalboard", types.SimpleNamespace(load_plugin=lambda path: Plugin()))
    module = tmp_path / "plugin.vst3"
    module.touch()
    first = corvus_status(str(module))
    assert first["found"] is True
    assert first["params"] == [{"name": "fatness", "min": 0.0, "max": 100.0,
                                "default": 50.0, "value": 25.0}]
    first["params"][0]["value"] = -999
    assert corvus_status(str(module))["params"][0]["value"] == 25.0

    from rookery.fx import _plugin_param_info
    assert _plugin_param_info(Plugin())[0]["value"] == 25.0


class _WrappedBool:
    """Truthy wrapper like pedalboard's WrappedBool; deliberately not a bool subclass."""

    def __init__(self, value):
        self._value = value

    def __bool__(self):
        return self._value


def test_corvus_status_reports_numeric_and_boolean_controls(monkeypatch, tmp_path):
    import sys
    import types

    class Numeric:
        type = float
        min_value, max_value, default_value = 0.0, 100.0, 50.0
        range = (0.0, 100.0, None)

    class Boolean:
        type = bool
        min_value, max_value, default_value = False, True, True
        range = (False, True, 1)

    class Plugin:
        parameters = {"fatness": Numeric(), "distortion_bypass": Boolean()}

        def __init__(self):
            self.fatness = 10.0
            self.distortion_bypass = _WrappedBool(True)

    monkeypatch.setitem(sys.modules, "pedalboard", types.SimpleNamespace(load_plugin=lambda path: Plugin()))
    module = tmp_path / "plugin.vst3"
    module.touch()
    params = {row["name"]: row for row in corvus_status(str(module))["params"]}
    assert set(params) == {"fatness", "distortion_bypass"}
    assert params["fatness"] == {"name": "fatness", "min": 0.0, "max": 100.0,
                                 "default": 50.0, "value": 10.0}
    assert params["distortion_bypass"] == {"name": "distortion_bypass", "min": 0.0, "max": 1.0,
                                           "default": 1.0, "value": 1.0}


def test_make_vst_sets_boolean_controls_as_real_bools(monkeypatch, tmp_path):
    import sys
    import types

    class Numeric:
        type = float
        min_value, max_value, default_value = 0.0, 100.0, 50.0
        range = (0.0, 100.0, None)

    class Boolean:
        type = bool
        min_value, max_value, default_value = False, True, False
        range = (False, True, 1)

    class Plugin:
        parameters = {"fatness": Numeric(), "distortion_bypass": Boolean()}

        def __init__(self):
            self.fatness = 10.0
            self.distortion_bypass = _WrappedBool(False)

    monkeypatch.setitem(sys.modules, "pedalboard", types.SimpleNamespace(load_plugin=lambda path: Plugin()))
    module = tmp_path / "plugin.vst3"
    module.touch()
    from rookery.fx import _make_vst

    plugin = _make_vst({"type": "vst3", "path": str(module),
                        "params": {"distortion_bypass": 1, "fatness": 10}})
    assert plugin.distortion_bypass is True
    assert plugin.fatness == 10.0
    with pytest.raises(ValueError, match="0 or 1"):
        _make_vst({"type": "vst3", "path": str(module), "params": {"distortion_bypass": 0.3}})


def test_limiter_threshold_and_ceiling_are_forwarded(monkeypatch):
    import sys
    import types

    class Limiter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    module = types.SimpleNamespace(Chorus=object, Compressor=object, Delay=object, Distortion=object,
                                   HighpassFilter=object, Limiter=Limiter, LowpassFilter=object, Reverb=object)
    monkeypatch.setitem(sys.modules, "pedalboard", module)
    from rookery.fx import _make_plugin

    assert _make_plugin({"type": "limiter", "threshold_db": -3}).kwargs["threshold_db"] == -3
    assert _make_plugin({"type": "limiter", "ceiling_db": -8}).kwargs["threshold_db"] == -8
    with pytest.raises(ValueError, match="not both"):
        _make_plugin({"type": "limiter", "threshold_db": -3, "ceiling_db": -8})


@pytest.mark.parametrize("name", ["corvus.dll", "corvus.json", "corvus.txt"])
def test_corvus_status_rejects_non_vst3_explicit_paths_without_loading(monkeypatch, tmp_path, name):
    import sys
    import types

    calls = []
    monkeypatch.setitem(sys.modules, "pedalboard", types.SimpleNamespace(load_plugin=lambda path: calls.append(path)))
    module = tmp_path / name
    module.touch()

    status = corvus_status(str(module))
    assert status["found"] is False
    assert status["path"] is None
    assert calls == []


def test_plugin_path_rejects_invalid_explicit_suffix_without_fallback(tmp_path):
    from rookery.fx import _plugin_path

    dummy = tmp_path / "plugin.dll"
    dummy.touch()
    assert _plugin_path(str(dummy)) is None


def test_plugin_path_accepts_uppercase_vst3_suffix(tmp_path):
    from rookery.fx import _plugin_path

    module = tmp_path / "Plugin.VST3"
    module.touch()
    assert _plugin_path(str(module)) == module


def test_make_vst_rejects_non_vst3_path_before_loading(monkeypatch, tmp_path):
    import sys
    import types

    calls = []
    monkeypatch.setitem(sys.modules, "pedalboard", types.SimpleNamespace(load_plugin=lambda path: calls.append(path)))
    from rookery.fx import _make_vst

    dummy = tmp_path / "effect.json"
    dummy.touch()
    with pytest.raises(ValueError, match="vst3"):
        _make_vst({"type": "vst3", "path": str(dummy), "params": {}})
    assert calls == []


def test_distinct_limiter_thresholds_produce_distinct_audio():
    t = np.arange(4096, dtype=np.float32) / 44100
    signal = np.column_stack((0.95 * np.sin(2 * np.pi * 440 * t),) * 2)
    mild = apply_fx(signal, [{"type": "limiter", "threshold_db": -3}], 44100)
    strong = apply_fx(signal, [{"type": "limiter", "threshold_db": -20}], 44100)
    assert not np.array_equal(mild, strong)
