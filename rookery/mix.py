"""Shared mix-role classification and targets for defaults and render guidance."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .kit.factory import is_kick_source

_MIX_PROFILE = "targets-v1"
SAMPLE_ROLES = frozenset({"bed", "lead", "counter", "texture", "drums"})


@lru_cache(maxsize=1)
def mix_targets() -> dict[str, Any]:
    return json.loads(Path(__file__).with_name("mix_targets.json").read_text(encoding="utf-8"))


def mix_genre(project: dict[str, Any] | None) -> str:
    targets = mix_targets()
    genre = project.get("genre") if isinstance(project, dict) else None
    return genre if genre in targets["roles"]["kick"]["targets"] else targets["default_genre"]


def track_role(track: dict[str, Any], role_hint: str | None = None) -> str | None:
    kind = track.get("kind", "drum")
    source = str(track.get("source", "")).lower()
    name = source.split(":", 1)[-1].rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if kind == "bass":
        return "bass"
    if kind == "sample":
        role = track.get("role") or role_hint
        if role in SAMPLE_ROLES:
            return "texture" if role == "texture" else f"sample_{role}"
        return "sample_loop"
    if kind != "drum":
        return None
    if is_kick_source(source):
        return "kick"
    if "snare" in name or "clap" in name:
        return "snare_clap"
    if "hat" in name and "open" in name:
        return "hat_open"
    if "hat" in name:
        return "hat"
    if "perc" in name or "rim" in name:
        return "perc_rim"
    return None


def cached_sample_role_hint(track: dict[str, Any], user_kit_dir: str | Path | None = None) -> str | None:
    """Read a fetched library sample's compact role hint, if its cache is current."""
    source = track.get("source")
    if not isinstance(source, str) or not source.startswith("user:") or user_kit_dir is None:
        return None
    sample_path = Path(user_kit_dir).expanduser() / source[len("user:"):]
    if sample_path.parent.name.lower() != "library":
        return None
    try:
        from .sampling import analyze
        profile = analyze(sample_path).get("profile")
    except (OSError, RuntimeError, ValueError, TypeError):
        return None
    role_hint = profile.get("role_hint") if isinstance(profile, dict) else None
    return role_hint if role_hint in SAMPLE_ROLES else None


def bird_role(role: str) -> str:
    return f"flock_{role}"


def role_target(role: str, genre: str) -> list[float] | None:
    item = mix_targets()["roles"].get(role)
    if item is None:
        return None
    return item["targets"].get(genre, item["targets"][mix_targets()["default_genre"]])


def add_track_defaults(track: dict[str, Any], project: dict[str, Any],
                       role_hint: str | None = None) -> dict[str, Any]:
    """Set just the absent add-time gain/pan fields; render defaults remain unchanged."""
    role = track_role(track, role_hint=role_hint)
    item = mix_targets()["roles"].get(role) if role else None
    if item is None:
        return track
    genre = mix_genre(project)
    if "gain_db" not in track and role != "kick":
        # Factory sources differ by up to 16 LU within a role, so land each one at
        # its role's target midpoint from its measured level instead of one number.
        source = str(track.get("source", ""))
        level = mix_targets().get("source_level_lu", {}).get(source.split(":", 1)[1]) \
            if source.startswith("factory:") else None
        target = role_target(role, genre)
        if isinstance(level, (int, float)) and target is not None:
            track["gain_db"] = min(12.0, max(-60.0, round((target[0] + target[1]) / 2 - level, 1)))
    for field in ("gain_db", "pan"):
        if field in track:
            continue
        value = item.get("default_gain_db" if field == "gain_db" else "default_pan")
        if isinstance(value, dict):
            value = value.get(genre, value.get(mix_targets()["default_genre"]))
        if value is not None:
            track[field] = value
    return track


def mix_profile_enabled(project: dict[str, Any]) -> bool:
    """Enable calibrated Flock trims for projects carrying the explicit marker."""
    return project.get("mix_profile") == _MIX_PROFILE


__all__ = [
    "add_track_defaults", "bird_role", "cached_sample_role_hint", "mix_genre",
    "mix_profile_enabled", "mix_targets", "role_target", "SAMPLE_ROLES", "track_role",
]
