"""Hermes plugin entry point for Rookery.

Importing this module and calling ``register()`` stays cheap: the engine (and its
numpy, scipy, soundfile, pyloudnorm and pedalboard stack) is imported on the first
tool call, so Hermes can load the plugin inside its 10 s import timeout.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from .rookery.bootstrap import load_engine

PLUGIN_ROOT = Path(__file__).resolve().parent

# Keep in step with rookery/tool_schemas.json and plugin.yaml provides_tools;
# tests/engine/test_plugin.py fails if any of the three drifts.
TOOL_NAMES = (
    "rookery_new",
    "rookery_steps",
    "rookery_track",
    "rookery_mix",
    "rookery_apply",
    "rookery_render",
    "rookery_export",
    "rookery_state",
    "rookery_undo",
    "rookery_kits",
    "rookery_samples",
)

_LOCK = threading.Lock()
_ENGINE = None
_HANDLERS: dict[str, object] = {}
_SETTINGS_PROVIDER = None


def _register_skills(ctx, plugin_root):
    register_skill = getattr(ctx, "register_skill", None)
    skill_root = plugin_root / "skills"
    if not callable(register_skill) or not skill_root.is_dir():
        return
    for skill_file in sorted(skill_root.rglob("SKILL.md")):
        skill_name = skill_file.parent.name
        try:
            register_skill(skill_name, skill_file, f"{skill_name.replace('-', ' ').capitalize()} beat-making guidance.")
        except Exception:
            # Skill discovery is optional; a malformed/missing bundled skill must not hide tools.
            continue


def _settings_provider(ctx):
    get_config = getattr(ctx, "get_config", None)
    if not callable(get_config):
        return None

    def provider():
        values = {}
        for key in ("user_kit_dir", "corvus_vst3_path"):
            try:
                values[key] = get_config(key)
            except Exception:
                values[key] = None
        return values

    return provider


def _engine():
    """Load the engine once, on first use, under a lock."""
    global _ENGINE
    engine = _ENGINE
    if engine is not None:
        return engine
    with _LOCK:
        if _ENGINE is None:
            engine = load_engine(PLUGIN_ROOT)
            if _SETTINGS_PROVIDER is not None:
                engine.service.set_settings_provider(_SETTINGS_PROVIDER)
            _ENGINE = engine
        return _ENGINE


def _lazy_handler(name):
    """Return a Hermes handler that builds the real one on its first call."""

    def handler(params, **kwargs):
        cached = _HANDLERS.get(name)
        if cached is None:
            engine = _engine()
            with _LOCK:
                cached = _HANDLERS.get(name)
                if cached is None:
                    cached = engine.tools.make_handler(engine, name)
                    _HANDLERS[name] = cached
        return cached(params, **kwargs)

    return handler


def register(ctx):
    """Register the public tools and any bundled skills supported by Hermes."""
    global _SETTINGS_PROVIDER
    provider = _settings_provider(ctx)
    _SETTINGS_PROVIDER = provider
    engine = _ENGINE
    if engine is not None and provider is not None:
        # A later registration may carry a fresh Hermes config lookup.
        engine.service.set_settings_provider(provider)

    schemas = json.loads((PLUGIN_ROOT / "rookery" / "tool_schemas.json").read_text(encoding="utf-8"))
    for name in TOOL_NAMES:
        ctx.register_tool(name=name, toolset="rookery", schema=schemas[name],
                          handler=_lazy_handler(name))
    _register_skills(ctx, PLUGIN_ROOT)
