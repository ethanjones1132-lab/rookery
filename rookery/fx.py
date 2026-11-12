"""Fresh, deterministic pedalboard FX chains and optional Corvus discovery."""

from __future__ import annotations

import contextvars
import math
import os
import threading
import time
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

import numpy as np

_BUILTINS = {"compressor", "reverb", "delay", "distortion", "chorus", "limiter", "highpass", "lowpass"}
_RANGES = {
    "compressor": {"threshold_db": (-80, 0), "ratio": (1, 20), "attack_ms": (0.1, 500), "release_ms": (1, 5000)},
    "limiter": {"threshold_db": (-40, 0), "ceiling_db": (-40, 0), "release_ms": (1, 2000)},
    "reverb": {"room_size": (0, 1), "damping": (0, 1), "wet_level": (0, 1), "dry_level": (0, 1), "width": (0, 1)},
    "delay": {"delay_seconds": (0, 10), "feedback": (-0.99, 0.99), "mix": (0, 1)},
    "distortion": {"drive_db": (0, 48)},
    "chorus": {"rate_hz": (0, 20), "depth": (0, 1), "centre_delay_ms": (0, 50), "feedback": (-0.99, 0.99), "mix": (0, 1)},
    "highpass": {"cutoff_hz": (20, 20000)},
    "lowpass": {"cutoff_hz": (20, 20000)},
}
# The only VST3 Rookery will load: the user's configured corvus_vst3_path, set by the service around each
# render or export. With nothing configured, no plugin is loaded and there is no hard-coded fallback.
_CONFIGURED_VST3: contextvars.ContextVar[str | None] = contextvars.ContextVar("rookery_configured_vst3", default=None)
_NOT_CONFIGURED = ("Corvus FX is not configured: set corvus_vst3_path in Rookery's plugin settings to use the vst3 "
                   "effect. Rookery loads only that plugin and never downloads one.")
_CORVUS_TTL = 15.0
_corvus_cache = {}
_corvus_cache_lock = threading.RLock()


def _finite_number(value, label, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{label} must be a finite number between {low:g} and {high:g}")
    return float(value)


_MISSING = object()


def _parameter_map(plugin):
    parameters = getattr(plugin, "parameters", ())
    if isinstance(parameters, dict):
        return parameters
    return {getattr(param, "name", None): param for param in parameters}


def _is_boolean_parameter(param):
    return getattr(param, "type", None) is bool


def _plugin_param_info(plugin):
    values = []
    for name, param in _parameter_map(plugin).items():
        if not isinstance(name, str):
            continue
        param_type = getattr(param, "type", None)
        if param_type is str:
            continue
        is_bool = param_type is bool
        value = getattr(plugin, name, _MISSING)
        if value is _MISSING:
            continue
        if is_bool:
            value = int(bool(value))
            low, high = 0, 1
            default = getattr(param, "default", getattr(param, "default_value", value))
            default = int(bool(default)) if default is not None else value
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            bounds = getattr(param, "range", None)
            if isinstance(bounds, (tuple, list)) and len(bounds) >= 2:
                low, high = bounds[0], bounds[1]
            else:
                low = getattr(param, "min_value", None)
                high = getattr(param, "max_value", None)
            default = getattr(param, "default", getattr(param, "default_value", value))
        try:
            low, high, default, value = map(float, (low, high, default, value))
        except (TypeError, ValueError):
            continue
        if not all(map(math.isfinite, (low, high, default, value))) or low > high:
            continue
        values.append({"name": name, "min": low, "max": high, "default": default, "value": value})
    return values


def _plugin_path(path=None):
    if path:
        candidate = Path(path)
        if candidate.suffix.lower() != ".vst3":
            return None
        if candidate.is_file():
            return candidate
        if candidate.is_dir():
            modules = sorted(candidate.glob("Contents/x86_64-win/*.vst3"))
            if modules:
                return modules[0]
        return None
    return None


@contextmanager
def configured_vst3(path):
    """Run renders with ``path`` (the user's corvus_vst3_path, or None) as the only loadable VST3."""
    token = _CONFIGURED_VST3.set(str(path) if path else None)
    try:
        yield
    finally:
        _CONFIGURED_VST3.reset(token)


def _same_file(a: Path, b: Path) -> bool:
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def corvus_status(path=None) -> dict:
    """Report loadable Corvus controls; discovery never downloads or crashes callers."""
    selected = _plugin_path(path)
    try:
        stat = selected.stat() if selected else None
        file_stamp = (stat.st_mtime_ns, stat.st_size) if stat else None
    except OSError:
        file_stamp = None
    key = (str(path or "<default>"), str(selected) if selected else None, file_stamp)
    now = time.monotonic()
    with _corvus_cache_lock:
        cached = _corvus_cache.get(key)
        if cached and now - cached[0] < _CORVUS_TTL:
            return deepcopy(cached[1])
        if not path:
            result = {"found": False, "configured": False, "path": None, "params": [], "message": _NOT_CONFIGURED}
        elif selected is None:
            result = {"found": False, "configured": True, "path": None, "params": [],
                      "message": "the configured corvus_vst3_path is not a loadable .vst3 module"}
        else:
            try:
                from pedalboard import load_plugin
                plugin = load_plugin(os.fspath(selected))
                result = {"found": True, "configured": True, "path": str(selected), "params": _plugin_param_info(plugin)}
            except Exception as exc:
                result = {"found": False, "configured": True, "path": str(selected), "params": [], "message": str(exc)}
        _corvus_cache.clear()
        _corvus_cache[key] = (now, result)
        return deepcopy(result)


def _settings(effect, kind):
    if not isinstance(effect, dict) or effect.get("type") != kind:
        raise ValueError(f"{kind} effect must be an object with type={kind!r}")
    allowed = set(_RANGES[kind]) | {"type"}
    if kind in {"highpass", "lowpass"}:
        allowed.add("cutoff_frequency_hz")
    unknown = set(effect) - allowed
    if unknown:
        raise ValueError(f"unknown {kind} settings: {', '.join(sorted(unknown))}")
    settings = dict(effect)
    settings.pop("type")
    if "cutoff_frequency_hz" in settings:
        if "cutoff_hz" in settings:
            raise ValueError("provide only one cutoff_hz spelling")
        settings["cutoff_hz"] = settings.pop("cutoff_frequency_hz")
    for name, value in settings.items():
        low, high = _RANGES[kind][name]
        settings[name] = _finite_number(value, f"{kind}.{name}", low, high)
    return settings


def _make_plugin(effect):
    from pedalboard import (Chorus, Compressor, Delay, Distortion, HighpassFilter,
                            Limiter, LowpassFilter, Reverb)
    kind = effect["type"]
    opts = _settings(effect, kind)
    if kind == "compressor":
        return Compressor(**opts)
    if kind == "reverb":
        return Reverb(**opts)
    if kind == "delay":
        return Delay(**opts)
    if kind == "distortion":
        return Distortion(**opts)
    if kind == "chorus":
        return Chorus(**opts)
    if kind == "limiter":
        ceiling = opts.pop("ceiling_db", None)
        threshold = opts.pop("threshold_db", None)
        if ceiling is not None and threshold is not None:
            raise ValueError("limiter accepts ceiling_db or threshold_db, not both")
        if ceiling is not None:
            opts["threshold_db"] = ceiling
        elif threshold is not None:
            opts["threshold_db"] = threshold
        return Limiter(**opts)
    cls = HighpassFilter if kind == "highpass" else LowpassFilter
    return cls(cutoff_frequency_hz=opts.get("cutoff_hz", 20_000 if kind == "lowpass" else 20))


def _make_vst(effect):
    """Load the user's configured VST3 only; an effect may name it, but never another plugin."""
    if set(effect) - {"type", "path", "params"}:
        raise ValueError("unknown vst3 settings")
    params = effect.get("params", {})
    if not isinstance(params, dict):
        raise ValueError("vst3 params must be an object")
    requested = effect.get("path")
    if requested is not None and (not isinstance(requested, str) or not requested.lower().endswith(".vst3")):
        raise ValueError("vst3 path must name a .vst3 module or bundle")
    configured = _CONFIGURED_VST3.get()
    if not configured:
        raise ValueError(_NOT_CONFIGURED)
    candidate = _plugin_path(configured)
    if candidate is None:
        raise FileNotFoundError(f"the configured corvus_vst3_path is not a loadable .vst3 module: {configured}")
    if requested is not None:
        named = _plugin_path(requested)
        if named is None or not _same_file(named, candidate):
            raise ValueError("vst3 path is not the configured corvus_vst3_path; Rookery loads only the VST3 the "
                             "user configured in its plugin settings")
    from pedalboard import load_plugin
    plugin = load_plugin(os.fspath(candidate))
    parameters = _parameter_map(plugin)
    controls = {row["name"]: row for row in _plugin_param_info(plugin)}
    unknown = set(params) - set(controls)
    if unknown:
        raise ValueError(f"unknown or non-actionable VST3 parameters: {', '.join(sorted(unknown))}")
    for name, value in params.items():
        row = controls[name]
        numeric = _finite_number(value, f"vst3.params.{name}", row["min"], row["max"])
        is_bool = _is_boolean_parameter(parameters.get(name))
        if is_bool and numeric not in (0.0, 1.0):
            raise ValueError(f"vst3.params.{name} must be 0 or 1")
        try:
            setattr(plugin, name, bool(numeric) if is_bool else numeric)
        except Exception as exc:
            raise ValueError(f"could not set VST3 parameter {name}: {exc}") from exc
    return plugin


def apply_fx(audio, fx, sr) -> np.ndarray:
    """Apply a fresh pedalboard chain to frames×2 audio, preserving its exact length."""
    data = np.asarray(audio, dtype=np.float32)
    if data.ndim != 2 or data.shape[1] != 2 or not np.isfinite(data).all():
        raise ValueError("audio must be finite frames x 2")
    if isinstance(sr, bool) or not isinstance(sr, (int, np.integer)) or sr <= 0:
        raise ValueError("sr must be a positive integer")
    if not isinstance(fx, (list, tuple)):
        raise ValueError("fx must be a list")
    if not fx:
        return data.copy()
    from pedalboard import Pedalboard
    plugins = []
    for effect in fx:
        if not isinstance(effect, dict) or not isinstance(effect.get("type"), str):
            raise ValueError("each effect must be an object with a type")
        kind = effect["type"]
        if kind in _BUILTINS:
            plugins.append(_make_plugin(effect))
        elif kind == "vst3":
            plugins.append(_make_vst(effect))
        else:
            raise ValueError(f"unsupported effect type: {kind}")
    board = Pedalboard(plugins)
    processed = np.asarray(board(data.T, sample_rate=int(sr)), dtype=np.float32).T
    if processed.shape != data.shape or not np.isfinite(processed).all():
        raise ValueError("FX processing returned invalid audio")
    return processed
