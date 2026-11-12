"""Compatibility tool API shared by Hermes registrations and acceptance callers."""

from __future__ import annotations

from typing import Any

from . import samples
from .service import get_service


def new(data_dir, name, bpm, bars=4, swing=0, seed=1337, genre=None, key=None, scale=None):
    return get_service(data_dir).new(name, bpm, bars, genre, swing, seed, source="agent",
                                     tool="rookery_new", key=key, scale=scale)


def steps(data_dir, name, track, steps, velocity=None):
    body = {"name": name, "op": "steps", "track": track, "steps": steps}
    if velocity is not None:
        body["velocity"] = velocity
    return get_service(data_dir).edit(body, source="agent", tool="rookery_steps")


def track(data_dir, name, action, id, **fields):
    if id == "master":
        body = {"name": name, "op": "meta", **fields}
        if action != "set" or set(fields) - {"bpm", "bars", "swing", "humanize_ms"} or not fields:
            # Keep invalid master requests on the normal validator path; no project
            # mutation can occur unless this is a metadata-only set operation.
            body.update(action=action, id=id)
        return get_service(data_dir).edit(body, source="agent", tool="rookery_track")
    return get_service(data_dir).edit(
        {"name": name, "op": "track", "action": action, "id": id, **fields},
        source="agent", tool="rookery_track",
    )


def mix(data_dir, name, target, fx):
    return get_service(data_dir).edit(
        {"name": name, "op": "mix", "target": target, "fx": fx},
        source="agent", tool="rookery_mix",
    )


def apply(data_dir, name, ops):
    supported_ops = {"steps", "track", "mix", "meta", "clear", "groove", "arrange", "balance"}
    if isinstance(ops, list):
        for index, item in enumerate(ops):
            if not isinstance(item, dict) or not isinstance(item.get("op"), str):
                raise ValueError(
                    f"ops[{index}] must be an object with a string op; send an edit such as "
                    '{"op":"steps","track":"kick","steps":"x..."}'
                )
            op = item["op"]
            if op == "flock":
                raise ValueError(
                    "Flock is user-controlled and has no agent edit op; leave perched birds untouched. "
                    'For a drum pattern, send {"op":"steps","track":"kick","steps":"x..."}.'
                )
            if op not in supported_ops:
                choices = ", ".join(sorted(supported_ops))
                raise ValueError(
                    f"ops[{index}].op {op!r} is unsupported; send one of {choices}, for example "
                    '{"op":"steps","track":"kick","steps":"x..."}'
                )
    return get_service(data_dir).apply_ops(name, ops)


def render(data_dir, name, song=False):
    rendered = get_service(data_dir).render(name, song=song)
    # Keep the CHAT result itself a compact immutable render card payload.
    return {**rendered["snapshot"], "wav_hash": rendered["wav_hash"]}


def export(data_dir, name=None, song=None, stems=True, midi=True, fps=None):
    service = get_service(data_dir)
    project = service.store.read(name)
    from .export import export_project
    return export_project(project, data_dir, user_kit_dir=service.user_kit_dir,
                          song=song, stems=stems, midi=midi, fps=fps)


def state(data_dir, name, since=None):
    return get_service(data_dir).state(name, since=since)


def undo(data_dir, name, steps=1):
    return get_service(data_dir).undo(name, steps=steps, source="agent", tool="rookery_undo")


def kits(data_dir):
    return get_service(data_dir).kits()


_FX_SCHEMAS = [
    {
        "type": "object", "description": "Compressor settings.", "properties": {
            "type": {"const": "compressor"},
            "threshold_db": {"type": "number", "description": "Compression threshold in dB, from -80 to 0.", "minimum": -80, "maximum": 0},
            "ratio": {"type": "number", "description": "Compression ratio from 1 to 20.", "minimum": 1, "maximum": 20},
            "attack_ms": {"type": "number", "description": "Attack in milliseconds, from 0.1 to 500.", "minimum": 0.1, "maximum": 500},
            "release_ms": {"type": "number", "description": "Release in milliseconds, from 1 to 5000.", "minimum": 1, "maximum": 5000},
        }, "required": ["type"], "additionalProperties": False,
    },
    {
        "type": "object", "description": "Limiter settings.", "properties": {
            "type": {"const": "limiter"},
            "ceiling_db": {"type": "number", "description": "Output ceiling in dB, from -40 to 0.", "minimum": -40, "maximum": 0},
            "threshold_db": {"type": "number", "description": "Threshold in dB, from -40 to 0; use instead of ceiling_db.", "minimum": -40, "maximum": 0},
            "release_ms": {"type": "number", "description": "Release in milliseconds, from 1 to 2000.", "minimum": 1, "maximum": 2000},
        }, "required": ["type"], "additionalProperties": False,
    },
    {
        "type": "object", "description": "Reverb settings.", "properties": {
            "type": {"const": "reverb"},
            "room_size": {"type": "number", "description": "Room size from 0 to 1.", "minimum": 0, "maximum": 1},
            "damping": {"type": "number", "description": "High frequency damping from 0 to 1.", "minimum": 0, "maximum": 1},
            "wet_level": {"type": "number", "description": "Wet level from 0 to 1.", "minimum": 0, "maximum": 1},
            "dry_level": {"type": "number", "description": "Dry level from 0 to 1.", "minimum": 0, "maximum": 1},
            "width": {"type": "number", "description": "Stereo width from 0 to 1.", "minimum": 0, "maximum": 1},
        }, "required": ["type"], "additionalProperties": False,
    },
    {
        "type": "object", "description": "Delay settings.", "properties": {
            "type": {"const": "delay"},
            "delay_seconds": {"type": "number", "description": "Delay time in seconds, from 0 to 10.", "minimum": 0, "maximum": 10},
            "feedback": {"type": "number", "description": "Feedback from -0.99 to 0.99.", "minimum": -0.99, "maximum": 0.99},
            "mix": {"type": "number", "description": "Wet/dry mix from 0 to 1.", "minimum": 0, "maximum": 1},
        }, "required": ["type"], "additionalProperties": False,
    },
    {
        "type": "object", "description": "Distortion settings.", "properties": {
            "type": {"const": "distortion"},
            "drive_db": {"type": "number", "description": "Drive amount in dB, from 0 to 48.", "minimum": 0, "maximum": 48},
        }, "required": ["type"], "additionalProperties": False,
    },
    {
        "type": "object", "description": "Chorus settings.", "properties": {
            "type": {"const": "chorus"},
            "rate_hz": {"type": "number", "description": "Modulation rate from 0 to 20 Hz.", "minimum": 0, "maximum": 20},
            "depth": {"type": "number", "description": "Modulation depth from 0 to 1.", "minimum": 0, "maximum": 1},
            "centre_delay_ms": {"type": "number", "description": "Centre delay in milliseconds, from 0 to 50.", "minimum": 0, "maximum": 50},
            "feedback": {"type": "number", "description": "Feedback from -0.99 to 0.99.", "minimum": -0.99, "maximum": 0.99},
            "mix": {"type": "number", "description": "Wet/dry mix from 0 to 1.", "minimum": 0, "maximum": 1},
        }, "required": ["type"], "additionalProperties": False,
    },
    {
        "type": "object", "description": "High-pass filter settings.", "properties": {
            "type": {"const": "highpass"},
            "cutoff_hz": {"type": "number", "description": "Cutoff frequency in Hz, from 20 to 20000.", "minimum": 20, "maximum": 20000},
        }, "required": ["type"], "additionalProperties": False,
    },
    {
        "type": "object", "description": "Low-pass filter settings.", "properties": {
            "type": {"const": "lowpass"},
            "cutoff_hz": {"type": "number", "description": "Cutoff frequency in Hz, from 20 to 20000.", "minimum": 20, "maximum": 20000},
        }, "required": ["type"], "additionalProperties": False,
    },
    {
        "type": "object", "description": "Corvus VST3 effect and named parameters.", "properties": {
            "type": {"const": "vst3"},
            "path": {"type": "string", "description": "Installed VST3 module path; Rookery never downloads plugins."},
            "params": {"type": "object", "description": "Parameter names and numeric values exposed by the installed plugin.", "additionalProperties": {"type": "number"}},
        }, "required": ["type", "path"], "additionalProperties": False,
    },
]


def _schema(name: str, description: str, properties: dict[str, Any], required=()):
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "description": description,
            "properties": properties,
            "required": list(required),
            "additionalProperties": False,
        },
    }


_NAME = {"type": "string", "description": "Project name; omit to use the most recently updated project."}
_PROJECT_KEYS = ["C", "C#", "Db", "D", "D#", "Eb", "E", "F", "F#", "Gb", "G", "G#", "Ab", "A", "A#", "Bb", "B"]
_PROJECT_SCALES = ["major", "minor"]
_APPLY_OPS = {
    "type": "object",
    "description": "One edit. op selects the shape; the remaining fields match the single-edit tools.",
    "required": ["op"],
    "additionalProperties": False,
    "properties": {
        "op": {"type": "string", "description": "Edit kind; balance measures the current loop and sets each audible track role to its target midpoint (no other fields).", "enum": [
            "steps", "track", "mix", "meta", "clear", "groove", "arrange", "balance",
        ]},
        "track": {"type": "string", "description": "Track ID for a steps edit, or the track to clear."},
        "steps": {"type": "string", "description": "Pattern: x hit, . rest; length must divide the loop."},
        "velocity": {"type": "array", "description": "Repeating velocity list from 0 to 1.", "items": {"type": "number", "minimum": 0, "maximum": 1}},
        "action": {"type": "string", "description": "Track action.", "enum": ["add", "remove", "set"]},
        "id": {"type": "string", "description": "Track ID for a track edit."},
        "kind": {"type": "string", "description": "Track kind for add.", "enum": ["drum", "bass", "sample"]},
        "source": {"type": "string", "description": "Sound source such as factory:kick_boom or user:path.wav."},
        "gain_db": {"type": "number", "description": "Track gain in dB.", "minimum": -60, "maximum": 12},
        "pan": {"type": "number", "description": "Pan from -1 to 1.", "minimum": -1, "maximum": 1},
        "mute": {"type": "boolean", "description": "Mute this track."},
        "solo": {"type": "boolean", "description": "Solo this track."},
        "pitch": {"type": "number", "description": "Pitch offset in semitones.", "minimum": -48, "maximum": 48},
        "notes": {"type": "array", "description": "Bass notes with step, len, and pitch.", "items": {"type": "object", "properties": {
            "step": {"type": "integer", "description": "Zero-based loop step."},
            "len": {"type": "integer", "description": "Length in steps."},
            "pitch": {"oneOf": [{"type": "integer", "description": "MIDI note."}, {"type": "string", "description": "Note name."}]},
        }, "required": ["step", "len", "pitch"], "additionalProperties": False}},
        "slices": {"type": "integer", "description": "Sample slice count.", "minimum": 1, "maximum": 10},
        "mode": {"type": "string", "description": "Sample playback mode: one-shot or grid-locked loop.", "enum": ["oneshot", "loop"]},
        "key_lock": {"type": "boolean", "description": "Transpose a loop sample to the project key; set false for unpitched audio."},
        "loop_bars": {"type": "integer", "description": "Loop sample length in bars: 1, 2, 4, or 8.", "enum": [1, 2, 4, 8]},
        "choke_group": {"type": "string", "description": "Shared choke group for drum voices."},
        "role": {"type": "string", "description": "Mix role for a sample track; omitted roles use the fetched sample profile when available.", "enum": ["bed", "lead", "counter", "texture", "drums"]},
        "duck": {"type": "number", "description": "Kick duck depth for bass or loop sample.", "minimum": 0, "maximum": 1},
        "target": {"type": "string", "description": "master or a track ID for a mix edit."},
        "fx": {"type": "array", "description": "Ordered FX chain for a mix edit.", "items": {"oneOf": _FX_SCHEMAS}},
        "bpm": {"type": "number", "description": "Project tempo for a meta edit.", "minimum": 30, "maximum": 300},
        "bars": {"type": "integer", "description": "Project length for a meta edit.", "enum": [4, 8]},
        "swing": {"type": "number", "description": "Project swing for a meta or groove edit.", "minimum": 0, "maximum": 1},
        "humanize_ms": {"type": "number", "description": "Deterministic humanization amount in milliseconds, from 0 to 6.", "minimum": 0, "maximum": 6},
        "key": {"type": "string", "description": "Project tonic pitch class; flats and sharps use the note spellings.", "enum": _PROJECT_KEYS},
        "scale": {"type": "string", "description": "Project scale mode.", "enum": _PROJECT_SCALES},
        "groove": {"type": "string", "description": "Named drum groove from skills/rookery/grooves.json; applied in the same batch."},
        "sections": {"type": ["array", "null"], "description": "Arrangement sections for arrange; null removes arrangement.",
                       "minItems": 1, "maxItems": 16, "items": {"type": "object",
                           "properties": {"id": {"type": "string"},
                                          "repeat": {"type": "integer", "minimum": 1, "maximum": 8},
                                          "mute": {"type": "array", "items": {"type": "string"}},
                                          "steps": {"type": "object", "description": "Track step overrides.", "additionalProperties": {"type": "string"}},
                                          "velocity": {"type": "object", "description": "Track velocity overrides.", "additionalProperties": {"type": "array", "items": {"type": "number", "minimum": 0, "maximum": 1}}},
                                          "notes": {"type": "object", "description": "Bass note overrides.", "additionalProperties": {"type": "array", "items": {"type": "object", "properties": {
                                              "step": {"type": "integer"}, "len": {"type": "integer"},
                                              "pitch": {"oneOf": [{"type": "integer"}, {"type": "string"}]},
                                          }, "required": ["step", "len", "pitch"], "additionalProperties": False}}},
                                           "fill": {"type": "boolean", "description": "Add a deterministic last-repeat turnaround."}},
                           "required": ["id", "repeat", "mute"], "additionalProperties": False}},
    },
}
SCHEMAS = {
    "rookery_new": _schema("rookery_new", "Create a beat project, optionally seeded from a genre template and song key.", {
        "name": {"type": "string", "description": "New project name using letters, numbers, dot, underscore, or dash."},
        "bpm": {"type": "number", "description": "Tempo in beats per minute, from 30 to 300."},
        "bars": {"type": "integer", "description": "Loop length in bars.", "enum": [4, 8], "default": 4},
        "genre": {"type": "string", "description": "Optional ready-to-edit template.", "enum": ["boom-bap", "trap"]},
        "swing": {"type": "number", "description": "Swing amount from 0 (straight) to 1 (full).", "minimum": 0, "maximum": 1, "default": 0},
        "key": {"type": "string", "description": "Optional song tonic pitch class; flats and sharps use the note spellings.", "enum": _PROJECT_KEYS},
        "scale": {"type": "string", "description": "Optional song scale mode.", "enum": _PROJECT_SCALES},
    }, ("name", "bpm")),
    "rookery_steps": _schema("rookery_steps", "Replace a track's repeating step pattern and optional per-step velocities.", {
        "name": _NAME,
        "track": {"type": "string", "description": "Track ID to edit."},
        "steps": {"type": "string", "description": "Pattern using x for a hit and . for a rest; sample tracks may use slice digits. Length must divide the loop."},
        "velocity": {"type": "array", "description": "Optional repeating velocity values from 0 to 1.", "items": {"type": "number", "minimum": 0, "maximum": 1}},
    }, ("track", "steps")),
    "rookery_track": _schema("rookery_track", "Add, remove, or update a drum, bass, or sample track; set id master to edit tempo, bars, swing, or humanize_ms.", {
        "name": _NAME,
        "action": {"type": "string", "description": "Track operation.", "enum": ["add", "remove", "set"]},
        "id": {"type": "string", "description": "Track ID; use master with action set to edit project metadata."},
        "kind": {"type": "string", "description": "Track type for add.", "enum": ["drum", "bass", "sample"]},
        "source": {"type": "string", "description": "Sound source such as factory:kick_boom, factory:808, or user:relative/path.wav."},
        "steps": {"type": "string", "description": "Optional initial pattern: x hit, . rest; sample one-shots may use slice digits. Length must divide the loop."},
        "velocity": {"type": "array", "description": "Optional repeating per-step velocity values from 0 to 1.", "items": {"type": "number", "minimum": 0, "maximum": 1}},
        "fx": {"type": "array", "description": "Track FX chain; use rookery_mix to replace it later.", "items": {"oneOf": _FX_SCHEMAS}},
        "gain_db": {"type": "number", "description": "Track gain from -60 to 12 dB.", "minimum": -60, "maximum": 12},
        "pan": {"type": "number", "description": "Pan from -1 (left) to 1 (right).", "minimum": -1, "maximum": 1},
        "mute": {"type": "boolean", "description": "Mute this track."},
        "solo": {"type": "boolean", "description": "Solo this track."},
        "pitch": {"type": "number", "description": "Pitch offset in semitones from -48 to 48.", "minimum": -48, "maximum": 48},
        "choke_group": {"type": "string", "description": "Optional shared choke group for mutually exclusive drum voices; short string, drum tracks only."},
        "role": {"type": "string", "description": "Optional sample mix role; profile-derived when omitted.", "enum": ["bed", "lead", "counter", "texture", "drums"]},
        "mode": {"type": "string", "description": "Sample playback mode: one-shot (default) or grid-locked loop.", "enum": ["oneshot", "loop"]},
        "key_lock": {"type": "boolean", "description": "Transpose loop samples to the project key/scale when set, else the user's Flock harmony; defaults true in loop mode."},
        "loop_bars": {"type": "integer", "description": "Override analyzed loop length in bars; 1, 2, 4, or 8.", "enum": [1, 2, 4, 8]},
        "duck": {"type": "number", "description": "Kick duck depth for bass or loop sample.", "minimum": 0, "maximum": 1},
        "notes": {"type": "array", "description": "Bass notes; each item has a zero-based step, duration in steps, and MIDI pitch number or note name.", "items": {"type": "object", "properties": {
            "step": {"type": "integer", "description": "Zero-based loop step."},
            "len": {"type": "integer", "description": "Note duration in steps."},
            "pitch": {"oneOf": [{"type": "integer", "description": "MIDI note 0-127."}, {"type": "string", "description": "Note name such as C1 or F#2."}]},
        }, "required": ["step", "len", "pitch"], "additionalProperties": False}},
        "slices": {"type": "integer", "description": "Number of equal slices for a sample track, from 1 to 10.", "minimum": 1, "maximum": 10},
        "bpm": {"type": "number", "description": "Project tempo, master only, from 30 to 300 BPM.", "minimum": 30, "maximum": 300},
        "bars": {"type": "integer", "description": "Project loop length, master only; 4 or 8 bars.", "enum": [4, 8]},
        "swing": {"type": "number", "description": "Project swing, master only, from 0 (straight) to 1 (full).", "minimum": 0, "maximum": 1},
        "humanize_ms": {"type": "number", "description": "Project humanization amount, master only, from 0 to 6 ms.", "minimum": 0, "maximum": 6},
    }, ("action", "id")),
    "rookery_mix": _schema("rookery_mix", "Replace the FX chain on the master bus or one track.", {
        "name": _NAME,
        "target": {"type": "string", "description": "master or a track ID."},
        "fx": {"type": "array", "description": "Ordered FX chain using built-in effects or an installed Corvus VST3.", "items": {"oneOf": _FX_SCHEMAS}},
    }, ("target", "fx")),
    "rookery_apply": _schema("rookery_apply", "Apply a batch of edits in one revision, including a named drum groove, so a whole beat can land in one call.", {
        "name": _NAME,
        "ops": {"type": "array", "description": "Ordered edits; each item has an op and that op's fields.", "minItems": 1, "maxItems": 64, "items": _APPLY_OPS},
    }, ("ops",)),
    "rookery_render": _schema("rookery_render", "Render and check the project. Loop snapshots include role balance, pairwise sample fit, and mix notes; song snapshots omit these loop-only fields.", {
        "name": _NAME,
        "song": {"type": "boolean", "description": "Render the arranged song instead of one loop."},
    }),
    "rookery_export": _schema("rookery_export", "Export a creator-ready soundtrack, stems, MIDI, and beat/bar/hit cue sheet. Other video-making agents can call this to get a soundtrack and cue sheet for a video, including frame cues for Remotion or After Effects.", {
        "name": _NAME,
        "song": {"type": "boolean", "description": "Export the arranged song; defaults to true when the project has an arrangement, otherwise false."},
        "stems": {"type": "boolean", "description": "Include aligned per-track and Flock WAV stems.", "default": True},
        "midi": {"type": "boolean", "description": "Include a MIDI file with track and Flock notes.", "default": True},
        "fps": {"type": "integer", "description": "Add cue frame numbers at this frame rate, from 1 to 240.", "minimum": 1, "maximum": 240},
    }),
    "rookery_state": _schema("rookery_state", "Show the full human-readable project state, or changes since a retained revision.", {
        "name": _NAME,
        "since": {"type": "integer", "description": "Return changes since this revision if it remains in history."},
    }),
    "rookery_undo": _schema("rookery_undo", "Restore one or more history snapshots on a project.", {
        "name": _NAME,
        "steps": {"type": "integer", "description": "Number of history changes to undo, from 1 to 128.", "minimum": 1, "maximum": 128, "default": 1},
    }),
    "rookery_kits": _schema("rookery_kits", "List factory sounds, confined user-kit files, and Corvus availability.", {}),
    "rookery_samples": _schema(
        "rookery_samples",
        "Search Soundza for lossless WAV loops and one-shots tagged with tempo, key and seamless looping, then import one as a normalized FLAC. A free Soundza key is needed to fetch; Openverse stays available as the CC0 lossy-preview source.",
        {
            "action": {"type": "string", "description": "Search samples or fetch one by id, or batch up to four queries/ids.", "enum": ["search", "fetch"]},
            "source": {"type": "string", "description": "Where to search: Soundza (lossless, royalty-free, needs a free key to fetch) or Openverse (CC0 MP3 previews). Defaults to soundza.", "enum": ["soundza", "openverse"], "default": "soundza"},
            "query": {"type": "string", "description": "Words describing one sound to find; use instead of queries for a single search."},
            "queries": {"type": "array", "description": "Batch of 1 to 4 sound searches; results are returned in matching query groups.", "items": {"type": "string", "minLength": 1}, "minItems": 1, "maxItems": 4},
            "kind": {"type": "string", "description": "Optional sound kind: loop, one-shot, or texture. Soundza maps these to its form and type filters."},
            "max_seconds": {"type": "number", "description": "Optional maximum duration in seconds for search results.", "exclusiveMinimum": 0},
            "limit": {"type": "integer", "description": "Maximum number of compact search results, from 1 to 20.", "minimum": 1, "maximum": 20, "default": 8},
            "bpm": {"type": "number", "description": "Optional target project tempo; Soundza searches within 6% of it and ranks fit."},
            "key": {"type": "string", "description": "Optional target project key for fit ranking."},
            "id": {"type": "string", "description": "One sound id from a search result; use instead of ids for a single fetch."},
            "ids": {"type": "array", "description": "Batch of 1 to 4 sound ids; each is fetched and quality-gated independently.", "items": {"type": "string", "minLength": 1}, "minItems": 1, "maxItems": 4},
        }, ("action",)),
}


def make_handler(engine, name: str, *, compact_receipts: bool = True):
    """Make a Hermes handler over this engine's single tool/service implementation."""
    from .service import get_service
    from .project import ProjectError
    import json

    schema = SCHEMAS[name]["parameters"]
    allowed = set(schema["properties"])
    required = set(schema.get("required", ()))

    def diff_line(item):
        field = str(item.get("field", "edit"))
        track_id = item.get("track")
        if field == "track":
            action = {"add": "added", "remove": "removed"}.get(item.get("action"), "updated")
            return f"{track_id} {action}"[:48]
        if field in {"steps", "velocity"}:
            count = len(item.get("steps", []))
            return f"{track_id} {field} changed ({count} steps)"[:48]
        if field == "flock":
            detail = " ".join(str(item[key]) for key in ("change", "bird", "slot", "field") if key in item)
            return f"flock {detail or 'changed'}"[:48]
        if field == "arrangement":
            value = item.get("to")
            if value is None:
                return "Arrangement · removed"
            summary = ", ".join(f"{section['id']}×{section['repeat']}"
                                 for section in value["sections"])
            return f"Arrangement · {summary}"
        return f"{track_id + ' ' if track_id else ''}{field} changed"[:48]

    def receipt(result):
        changed = [diff_line(item) for item in result.get("diff", [])]
        if len(changed) > 20:
            changed = changed[:20] + [f"+{len(result['diff']) - 20} more"]
        response = {"name": result["project"]["name"], "rev": result["rev"], "changed": changed}
        if any(item.get("field") == "arrangement" for item in result.get("diff", [])):
            from .arrangement import arrangement_variety
            response["variety"] = arrangement_variety(result["project"])
        return response

    def state_changes(result):
        if "changes" in result:
            changes = []
            for change in result["changes"]:
                lines = [diff_line(item) for item in change["diff"]]
                if len(lines) > 20:
                    lines = lines[:20] + [f"+{len(lines) - 20} more"]
                changes.append({"source": change["source"], "changed": lines})
            return {"name": result["name"], "rev": result["rev"], "changes": changes}
        return result

    def handler(params, **kwargs):
        del kwargs
        try:
            if not isinstance(params, dict):
                raise ProjectError("tool input must be a JSON object")
            extra = set(params) - allowed
            missing = required - set(params)
            if extra:
                raise ProjectError(f"unknown tool parameter(s): {', '.join(sorted(extra))}")
            if missing:
                raise ProjectError(f"missing required parameter(s): {', '.join(sorted(missing))}")

            service = get_service()
            data_dir = service.root
            project_name = params.get("name")
            is_project_tool = name not in {"rookery_kits", "rookery_samples"}
            if name == "rookery_new":
                editing_name = project_name
            elif is_project_tool:
                editing_name = project_name or service.latest_project_name()
            else:
                editing_name = None

            def call():
                if name == "rookery_new":
                    return engine.tools.new(data_dir, params["name"], params["bpm"],
                                            bars=params.get("bars", 4), swing=params.get("swing", 0),
                                            genre=params.get("genre"), key=params.get("key"),
                                            scale=params.get("scale"))
                if name == "rookery_steps":
                    return engine.tools.steps(data_dir, editing_name, params["track"], params["steps"],
                                              params.get("velocity"))
                if name == "rookery_track":
                    fields = {key: value for key, value in params.items()
                              if key not in {"name", "action", "id"}}
                    return engine.tools.track(data_dir, editing_name, params["action"], params["id"], **fields)
                if name == "rookery_mix":
                    return engine.tools.mix(data_dir, editing_name, params["target"], params["fx"])
                if name == "rookery_apply":
                    return engine.tools.apply(data_dir, editing_name, params["ops"])
                if name == "rookery_render":
                    return engine.tools.render(data_dir, editing_name, song=params.get("song", False))
                if name == "rookery_export":
                    return engine.tools.export(data_dir, editing_name, song=params.get("song"),
                                               stems=params.get("stems", True), midi=params.get("midi", True),
                                               fps=params.get("fps"))
                if name == "rookery_state":
                    return engine.tools.state(data_dir, editing_name, params.get("since"))
                if name == "rookery_undo":
                    return engine.tools.undo(data_dir, editing_name, params.get("steps", 1))
                if name == "rookery_samples":
                    action = params["action"]
                    source = params.get("source", "soundza")
                    def batch_values(field):
                        values = params[field]
                        if (not isinstance(values, list) or not 1 <= len(values) <= 4
                                or any(not isinstance(value, str) or not value.strip() for value in values)):
                            raise ProjectError(f"{field} must contain 1 to 4 non-empty strings")
                        return [value.strip() for value in values]

                    def sample_project():
                        try:
                            return service.store.read(service.latest_project_name())
                        except ProjectError:
                            return None

                    if action == "search":
                        batched = "queries" in params
                        if ("query" in params) == batched or "id" in params or "ids" in params:
                            raise ProjectError("sample search requires query or queries (not both) and does not accept ids")
                        queries = batch_values("queries") if batched else [params["query"]]
                        if any(not isinstance(query, str) or not query.strip() for query in queries):
                            raise ProjectError("sample search queries must be non-empty strings")
                        queries = [query.strip() for query in queries]
                        project = sample_project()
                        flock = (project or {}).get("flock") or {}
                        project_key = ((project or {}).get("key") or flock.get("key"))
                        bpm = params.get("bpm", project.get("bpm") if project else None)
                        key = params.get("key") or project_key
                        if not batched:
                            return samples.search(queries[0], params.get("kind"),
                                                  params.get("max_seconds"), params.get("limit", 8),
                                                  bpm, key, source=source, kit_dir=service.user_kit_dir)
                        grouped = []
                        for query in queries:
                            try:
                                hits = samples.search(query, params.get("kind"),
                                                      params.get("max_seconds"), params.get("limit", 8),
                                                      bpm, key, source=source, kit_dir=service.user_kit_dir)
                                grouped.append({"query": query, "results": hits})
                            except ProjectError as exc:
                                grouped.append({"query": query, "error": str(exc)})
                        return grouped
                    if action == "fetch":
                        batched = "ids" in params
                        fetch_fields = {"action", "ids", "source"} if batched else {"action", "id", "source"}
                        if (set(params) - fetch_fields or ("id" in params) == batched):
                            raise ProjectError("sample fetch requires id or ids (not both) and accepts no search fields")
                        identifiers = batch_values("ids") if batched else [params["id"]]
                        if any(not isinstance(identifier, str) or not identifier.strip()
                               for identifier in identifiers):
                            raise ProjectError("sample fetch ids must be non-empty strings")
                        identifiers = [identifier.strip() for identifier in identifiers]
                        project = sample_project()
                        flock = (project or {}).get("flock") or {}
                        project_key = ((project or {}).get("key") or flock.get("key"))
                        project_scale = ((project or {}).get("scale", "major") if (project or {}).get("key")
                                         else flock.get("scale", "major"))
                        def fetch_one(identifier):
                            return samples.fetch(identifier, service.user_kit_dir,
                                                  project.get("bpm") if project else None,
                                                  project_key, project_scale=project_scale,
                                                  source=source)
                        if not batched:
                            return fetch_one(identifiers[0])
                        results = []
                        for identifier in identifiers:
                            try:
                                results.append({"id": identifier, **fetch_one(identifier)})
                            except ProjectError as exc:
                                results.append({"id": identifier, "error": str(exc)})
                        return results
                    raise ProjectError("sample action must be search or fetch")
                return engine.tools.kits(data_dir)

            if editing_name is None:
                result = call()
            else:
                with engine.events.editing(editing_name):
                    result = call()
            if compact_receipts and name in {"rookery_new", "rookery_steps", "rookery_track", "rookery_mix",
                                             "rookery_apply", "rookery_undo"}:
                result = receipt(result)
            elif name == "rookery_state" and isinstance(result, dict):
                result = state_changes(result)
            serialized = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
            if name == "rookery_render":
                return serialized + "\nMEDIA:" + result["path"]
            return serialized
        except Exception as exc:
            result = {"error": str(exc).strip() or "Rookery operation failed"}
            rev = getattr(exc, "rev", None)
            if isinstance(rev, int):
                result["rev"] = rev
            return json.dumps(result, ensure_ascii=False, separators=(",", ":"))

    return handler


__all__ = ["new", "steps", "track", "mix", "apply", "render", "export", "state", "undo", "kits", "SCHEMAS", "make_handler"]
