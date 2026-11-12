"""Pure arrangement views shared by song rendering, export, and receipts."""

from __future__ import annotations

from typing import Any

from .flock.model import validate_flock
from .kit.factory import is_kick_source


def _expand(value: str, size: int, default: str = ".") -> str:
    text = str(value or default) or default
    return (text * ((size + len(text) - 1) // len(text)))[:size]


def _fill_view(steps: str, velocity: list[float], track: dict[str, Any], bars: int) -> tuple[str, list[float]]:
    """Return deterministic last-bar fill patterns without modifying inputs."""
    if track.get("kind") == "bass" or (track.get("kind") == "sample" and track.get("mode") == "loop"):
        return steps, velocity

    source = str(track.get("source", "")).split(":", 1)[-1].lower()
    total = bars * 16
    bar_start = total - 16
    if "snare" in source or "clap" in source:
        pattern = list(_expand(steps, total))
        values = (velocity * ((total + len(velocity) - 1) // len(velocity)))[:total]
        pattern[total - 4:total] = "xxxx"
        values[total - 4:total] = [0.35, 0.55, 0.75, 0.95]
        return "".join(pattern), values
    if is_kick_source(track.get("source")):
        pattern = list(_expand(steps, total))
        values = (velocity * ((total + len(velocity) - 1) // len(velocity)))[:total]
        pattern[total - 4:total] = "...."
        pattern[total - 4] = "x"
        values[total - 4:total] = [0.8, 0.0, 0.0, 0.0]
        return "".join(pattern), values
    is_closed_hat = (("hat" in source and "closed" in source)
                     or source in {"hat_tight", "hat_bright"})
    if is_closed_hat:
        pattern = list(_expand(steps, total))
        pattern[bar_start + 14:bar_start + 16] = ".."
        return "".join(pattern), velocity
    return steps, velocity


def section_track_view(project: dict[str, Any], section: dict[str, Any], track: dict[str, Any],
                       repeat_index: int) -> tuple[str, list[float], list[dict[str, Any]]]:
    """Resolve (steps, velocity, notes) for one track in one section iteration."""
    track_id = track["id"]
    steps = section.get("steps", {}).get(track_id, track.get("steps", "."))
    velocity = list(section.get("velocity", {}).get(track_id, track.get("velocity", [1.0])) or [1.0])
    notes = [dict(note) for note in section.get("notes", {}).get(track_id, track.get("notes", [])) or []]
    if section.get("fill") and repeat_index == section["repeat"] - 1:
        steps, velocity = _fill_view(steps, velocity, track, int(project["bars"]))
    return steps, velocity, notes


def section_flock(project: dict[str, Any], section: dict[str, Any]) -> dict[str, Any] | None:
    """Return this section's flock, applying its perch-song overrides."""
    if "flock" not in project:
        return None
    flock = validate_flock(project["flock"])
    for reference, song in section.get("songs", {}).items():
        slot = int(reference[5:])
        flock["perches"][slot]["song"] = song
    return validate_flock(flock)


def _signature(project: dict[str, Any], section: dict[str, Any], repeat_index: int) -> dict[str, Any]:
    tracks = []
    for track in project.get("tracks", []):
        steps, velocity, notes = section_track_view(project, section, track, repeat_index)
        tracks.append((track["id"], track["kind"], steps, tuple(velocity),
                       tuple((note["step"], note["len"], note["pitch"]) for note in notes)))
    flock = section_flock(project, section)
    songs = tuple((slot, perch["song"]) for slot, perch in enumerate(flock["perches"]) if perch) if flock else ()
    return {
        "mute": tuple(sorted(section.get("mute", []))),
        "tracks": tuple(tracks),
        "songs": songs,
        "fill": bool(section.get("fill") and repeat_index == section["repeat"] - 1),
    }


def _change_kinds(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    changes: set[str] = set()
    if before["mute"] != after["mute"]:
        changes.add("mute")
    old_tracks = {item[0]: item for item in before["tracks"]}
    new_tracks = {item[0]: item for item in after["tracks"]}
    for track_id in old_tracks.keys() | new_tracks.keys():
        old, new = old_tracks.get(track_id), new_tracks.get(track_id)
        if old == new:
            continue
        kind = (new or old)[1]
        if kind == "bass":
            changes.add("bass")
        else:
            changes.add("drums")
    old_songs, new_songs = dict(before["songs"]), dict(after["songs"])
    for slot in old_songs.keys() | new_songs.keys():
        if old_songs.get(slot) != new_songs.get(slot):
            changes.add(f"birds:{slot}")
    ordered = [kind for kind in ("drums", "bass") if kind in changes]
    ordered.extend(sorted(item for item in changes if item.startswith("birds:")))
    if "mute" in changes:
        ordered.append("mute")
    return ordered


def arrangement_variety(project: dict[str, Any]) -> dict[str, Any]:
    """Summarize section changes and the longest run of identical loop iterations."""
    sections = project.get("arrangement", {}).get("sections", [])
    bars = int(project.get("bars", 4))
    if not sections:
        return {"longest_unchanged_bars": 0, "sections": []}

    baseline = {"mute": (), "tracks": tuple(
        (track["id"], track["kind"], track.get("steps", "."), tuple(track.get("velocity", [1.0])),
         tuple((note["step"], note["len"], note["pitch"]) for note in track.get("notes", [])))
        for track in project.get("tracks", [])),
        "songs": tuple((slot, perch["song"]) for slot, perch in
                       enumerate(project.get("flock", {}).get("perches", [])) if perch),
        "fill": False}
    result_sections = []
    loop_signatures = []
    previous = baseline
    for section in sections:
        first = _signature(project, section, 0)
        changes = _change_kinds(previous, first)
        if section.get("fill"):
            changes.append("fill")
        result_sections.append({"id": section["id"], "bars": bars * section["repeat"], "changes": changes})
        for repeat_index in range(section["repeat"]):
            signature = _signature(project, section, repeat_index)
            loop_signatures.append(signature)
        previous = loop_signatures[-1]

    longest = run = 0
    previous_signature = None
    for signature in loop_signatures:
        same = (previous_signature is not None and not previous_signature["fill"] and not signature["fill"]
                and previous_signature["mute"] == signature["mute"]
                and previous_signature["tracks"] == signature["tracks"]
                and previous_signature["songs"] == signature["songs"])
        run = run + bars if same else bars
        longest = max(longest, run)
        previous_signature = signature
    return {"longest_unchanged_bars": longest, "sections": result_sections}


__all__ = ["arrangement_variety", "section_flock", "section_track_view"]
