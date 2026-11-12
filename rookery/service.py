"""Shared application service for Hermes tools and the Rookery REST API."""

from __future__ import annotations

import base64
import hashlib
import importlib.metadata
import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable

import soundfile as sf

from . import __version__, events
from .project import (
    ConflictError,
    NotFoundError,
    ProjectError,
    ProjectStore,
    ValidationError,
    _safe_name,
    _atomic_write,
    _locked,
    canonical_project,
)


_SERVICE_LOCK = threading.RLock()
_SERVICES: dict[tuple[str, str, str], "Service"] = {}
_LIFECYCLE_LOCKS: dict[str, threading.RLock] = {}
_SETTINGS_PROVIDER: Callable[[], dict[str, Any]] | None = None
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_RENDER_METADATA_FIELDS = ("flock_events", "kick_onsets", "flock_active_combos")


def _derived_render_metadata(project: dict[str, Any]) -> dict[str, Any]:
    """Recompute planner metadata from an exact rendered revision snapshot."""
    from .flock.synth import compile_events

    return compile_events(project)


def set_settings_provider(provider: Callable[[], dict[str, Any]] | None) -> None:
    """Install the Hermes context settings accessor for this engine namespace."""
    global _SETTINGS_PROVIDER
    _SETTINGS_PROVIDER = provider


def _ctx_settings() -> dict[str, Any]:
    provider = _SETTINGS_PROVIDER
    if provider is None:
        return {}
    try:
        value = provider()
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _data_dir() -> Path:
    override = os.environ.get("ROOKERY_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    try:
        from plugins.plugin_storage import plugin_data_dir

        return Path(plugin_data_dir("rookery")).expanduser().resolve()
    except (ImportError, ModuleNotFoundError):
        hermes_home = os.environ.get("HERMES_HOME")
        home = Path(hermes_home).expanduser() if hermes_home else Path.home() / ".hermes"
        return (home / "plugin-data" / "rookery").resolve()


def _setting_path(value: Any) -> str:
    if value is None or value == "":
        return ""
    return str(Path(value).expanduser().resolve())


def _renderer_version() -> str:
    from . import render

    return render.RENDERER_VERSION


def _check_identity() -> str:
    try:
        loudness = importlib.metadata.version("pyloudnorm")
    except importlib.metadata.PackageNotFoundError:
        loudness = "missing"
    return f"rookery-checks-1;pyloudnorm={loudness}"


class Service:
    """Project, render, and kit operations rooted in one Hermes plugin data directory."""

    def __init__(self, root=None, user_kit_dir=None, corvus_vst3_path=None):
        self.root = Path(root if root is not None else _data_dir()).expanduser().resolve()
        settings = _ctx_settings()
        selected_kit = user_kit_dir if user_kit_dir is not None else settings.get("user_kit_dir")
        selected_corvus = (
            corvus_vst3_path if corvus_vst3_path is not None else settings.get("corvus_vst3_path")
        )
        self.user_kit_dir = Path(selected_kit).expanduser().resolve() if selected_kit else self.root / "kits"
        self.corvus_vst3_path = str(selected_corvus) if selected_corvus else None
        self.store = ProjectStore(self.root)
        self.render_dir = self.root / "renders"

    def _lifecycle_lock(self, name: str) -> threading.RLock:
        key = f"{self.root}:{name}"
        with _SERVICE_LOCK:
            return _LIFECYCLE_LOCKS.setdefault(key, threading.RLock())

    def create_project(self, name=None, bpm=90, bars=4, swing=0, from_name=None) -> dict[str, Any]:
        return self.store.create_lifecycle(name, bpm=bpm, bars=bars, swing=swing, source_name=from_name)

    def rename_project(self, name: str, to: str) -> None:
        name, to = _safe_name(name), _safe_name(to, "to")
        with self._lifecycle_lock(name):
            old_records = self.render_dir / "projects" / name
            new_records = self.render_dir / "projects" / to
            if old_records.exists() and new_records.exists():
                raise ConflictError(f"render records already exist: {to}", 0)
            self.store.rename(name, to, emit_event=False)
            if old_records.exists():
                new_records.parent.mkdir(parents=True, exist_ok=True)
                try:
                    os.replace(old_records, new_records)
                    for record_path in new_records.glob("*.json"):
                        record = json.loads(record_path.read_text(encoding="utf-8"))
                        if isinstance(record, dict):
                            record["name"] = to
                            _atomic_write(record_path, record)
                except Exception:
                    if new_records.exists() and not old_records.exists():
                        os.replace(new_records, old_records)
                        for record_path in old_records.glob("*.json"):
                            record = json.loads(record_path.read_text(encoding="utf-8"))
                            if isinstance(record, dict):
                                record["name"] = name
                                _atomic_write(record_path, record)
                    self.store.rename(to, name, emit_event=False)
                    raise
            events.emit("project.renamed", {"from": name, "to": to})

    def delete_project(self, name: str) -> None:
        name = _safe_name(name)
        with self._lifecycle_lock(name):
            trash = self.store.delete(name, emit_event=False)
            records = self.render_dir / "projects" / name
            if records.exists():
                records.parent.mkdir(parents=True, exist_ok=True)
                os.replace(records, trash / "render-records")
            events.emit("project.deleted", {"name": name})

    def list_projects(self) -> list[dict[str, Any]]:
        return self.store.list_projects()

    def latest_project_name(self) -> str:
        projects = self.list_projects()
        if not projects:
            raise NotFoundError("no projects exist")
        return projects[0]["name"]

    def get_project(self, name: str | None, since=None) -> dict[str, Any]:
        project = self.store.read(name)
        rev = int(project["rev"])
        if since is not None:
            if isinstance(since, bool):
                raise ValidationError("since must be a non-negative integer")
            try:
                since_rev = int(since)
            except (TypeError, ValueError) as exc:
                raise ValidationError("since must be a non-negative integer") from exc
            if since_rev < 0 or str(since_rev) != str(since).strip():
                raise ValidationError("since must be a non-negative integer")
            if since_rev == rev:
                return {"changed": False, "rev": rev}
        render_view = self._render_view_for(project)
        return {
            "project": project,
            "rev": rev,
            "render": render_view,
            "agent_editing": events.is_editing(project["name"]),
        }

    def edit(self, body: dict[str, Any], source="user", tool=None) -> dict[str, Any]:
        if not isinstance(body, dict):
            raise ValidationError("edit body must be a JSON object")
        allowed = {"name", "rev", "op", "track", "steps", "velocity", "action", "id", "kind",
                    "source", "gain_db", "pan", "mute", "solo", "pitch", "notes", "slices",
                     "target", "fx", "bpm", "bars", "swing", "index", "param", "value",
                     "choke_group", "mode", "key_lock", "loop_bars", "duck", "role", "bird", "slot", "song", "on", "template", "key", "scale",
                     "progression", "weather", "humanize_ms", "sections"}
        extra = set(body) - allowed
        if extra:
            raise ValidationError(f"edit body has unknown fields: {', '.join(sorted(extra))}")
        if "name" not in body or "op" not in body:
            raise ValidationError("edit requires name and op")
        args = {key: value for key, value in body.items() if key not in {"name", "rev", "op"}}
        if body["op"] == "track" and args.get("action") == "add" and args.get("kind") == "sample":
            self._sample_add_defaults(args, self.store.read(body["name"]))
        if body["op"] == "track" and "source" in args:
            # ProjectStore reserves its ``source`` parameter for event origin.
            args["track_source"] = args.pop("source")
        return self.store.edit(
            body["name"], body["op"], rev=body.get("rev"), source=source, tool=tool, **args
        )

    def _sample_add_defaults(self, edit: dict[str, Any], project: dict[str, Any]) -> None:
        if edit.get("role"):
            return
        from .mix import add_track_defaults, cached_sample_role_hint

        role_hint = cached_sample_role_hint(edit, self.user_kit_dir)
        if role_hint:
            add_track_defaults(edit, project, role_hint=role_hint)

    def new(self, name, bpm, bars=4, genre=None, swing=0, seed=1337,
            source="agent", tool="rookery_new", key=None, scale=None) -> dict[str, Any]:
        return self.store.create(name, bpm=bpm, bars=bars, genre=genre, swing=swing, seed=seed,
                                 source=source, tool=tool, key=key, scale=scale)

    def undo(self, name=None, steps=1, source="agent", tool="rookery_undo") -> dict[str, Any]:
        return self.store.undo(name, steps=steps, source=source, tool=tool)

    def apply_ops(self, name, ops, rev=None, source="agent", tool="rookery_apply") -> dict[str, Any]:
        """Apply a batch of edits in one revision, expanding named grooves."""
        if not isinstance(ops, list) or not 1 <= len(ops) <= 64:
            raise ValidationError("ops must contain 1 to 64 edits")
        current_project = self.store.read(name)
        selected = current_project["name"]
        expanded: list[dict[str, Any]] = []
        for index, item in enumerate(ops):
            if not isinstance(item, dict) or not isinstance(item.get("op"), str):
                raise ValidationError(f"ops[{index}] must be an object with an op")
            if item["op"] == "groove":
                expanded.extend(self._groove_ops(selected, item))
            else:
                expanded.append(item)

        prepared = []
        for item in expanded:
            item = dict(item)
            if (item.get("op") == "track" and item.get("action") == "add"
                    and item.get("kind") == "sample"):
                self._sample_add_defaults(item, current_project)
            prepared.append(item)
        expanded = prepared

        def balance(project: dict[str, Any]) -> dict[str, Any]:
            from . import render

            _audio, _meters, metadata = render._render_audio_with_metadata(
                project, render.SAMPLE_RATE, self.user_kit_dir, include_balance=True,
            )
            return render._balance_response(project, metadata.get("_balance_layers", {}))

        return self.store.apply_batch(selected, expanded, rev=rev, source=source, tool=tool,
                                      balancer=balance)

    def _groove_ops(self, name: str, item: dict[str, Any]) -> list[dict[str, Any]]:
        groove_id = item.get("groove")
        if not isinstance(groove_id, str) or not groove_id:
            raise ValidationError("groove op requires a groove id")
        path = Path(__file__).resolve().parent.parent / "skills" / "rookery" / "grooves.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValidationError(f"could not read the groove catalog: {exc}") from exc
        template = next((entry for entry in data.get("templates", []) if entry.get("id") == groove_id), None)
        if template is None:
            raise ValidationError(f"unknown groove: {groove_id}")
        sources = {
            "kick": "factory:kick_punch", "snare": "factory:snare_snap",
            "clap": "factory:clap_stack", "hat": "factory:hat_tight",
            "hat_open": "factory:hat_open_short", "perc": "factory:perc",
        }
        project = self.store.read(name)
        existing = {track["id"]: track for track in project["tracks"]}
        ops: list[dict[str, Any]] = []
        for role, spec in template["tracks"].items():
            source = sources.get(role)
            if source is None:
                raise ValidationError(f"groove {groove_id} has an unknown role: {role}")
            track = existing.get(role)
            if track is None:
                fields: dict[str, Any] = {"op": "track", "action": "add", "id": role,
                                          "kind": "drum", "source": source}
                if role in {"hat", "hat_open"}:
                    fields["choke_group"] = "hats"
                ops.append(fields)
            elif role in {"hat", "hat_open"} and track.get("choke_group") != "hats":
                ops.append({"op": "track", "action": "set", "id": role, "choke_group": "hats"})
            ops.append({"op": "steps", "track": role, "steps": spec["steps"],
                        "velocity": spec["velocity"]})
        if "swing" in item:
            ops.append({"op": "meta", "swing": item["swing"]})
        return ops

    def state(self, name=None, since=None):
        project = self.store.read(name)
        if since is not None:
            try:
                since_rev = int(since)
                if isinstance(since, bool) or since_rev < 0 or str(since_rev) != str(since).strip():
                    raise ValueError
            except (TypeError, ValueError):
                raise ValidationError("since must be a non-negative integer") from None
            if since_rev == project["rev"]:
                return {"name": project["name"], "rev": project["rev"], "changes": []}
            history_dir = self.store.projects_dir / project["name"] / "history"
            cursor = project.get("_history_cursor")
            newer = []
            while cursor is not None:
                try:
                    snapshot = json.loads((history_dir / f"{int(cursor):08d}.json").read_text(encoding="utf-8"))
                except (OSError, ValueError, TypeError):
                    break
                if int(snapshot.get("rev", -1)) == since_rev:
                    relevant = [*newer, snapshot]
                    changes = [
                        {"source": entry.get("_history_change_source", "agent"),
                         "diff": entry.get("_history_change_diff", [])}
                        for entry in reversed(relevant)
                        if entry.get("_history_change_diff")
                    ]
                    return {"name": project["name"], "rev": project["rev"], "changes": changes}
                newer.append(snapshot)
                cursor = snapshot.get("_history_parent")
            return {"name": project["name"], "rev": project["rev"],
                    "note": f"revision {since_rev} is no longer in history", "state": self.state(name)}
        key_text = (f" | key {project['key']} {project.get('scale', 'major')}"
                    if "key" in project else "")
        lines = [
            f"{project['name']} | rev {project['rev']} | {project['bpm']:g} BPM | "
            f"{project['bars']} bars | swing {project['swing']:g}{key_text} | "
            f"humanize {project.get('humanize_ms', 0):g} ms",
        ]
        for track in project["tracks"]:
            pattern = track["steps"]
            groups = [pattern[i:i + 16] for i in range(0, len(pattern), 16)]
            lines.append(f"{track['id']} ({track['kind']}, {track['source']}) " + " | ".join(groups))
            if track.get("kind") == "sample":
                try:
                    from .sampling import analyze
                    sample_path = self.user_kit_dir / track["source"][len("user:"):]
                    analysis = analyze(sample_path, project_bpm=float(project["bpm"]))
                    profile = analysis.get("profile")
                    if isinstance(profile, dict):
                        pitched = "pitched" if profile.get("pitched") else "unpitched"
                        lines.append(
                            f"  profile · {profile['register']} · rhythm {profile['rhythm']} · "
                            f"sustain {profile['sustain']:.2f} · {pitched} · role {profile['role_hint']}"
                        )
                    if track.get("mode") == "loop":
                        source_bpm = analysis.get("bpm") or project["bpm"]
                        source_key = analysis.get("key")
                        flock = project.get("flock") or {}
                        target_key = project.get("key") or flock.get("key")
                        target_scale = (project.get("scale", "major") if project.get("key")
                                        else flock.get("scale", "major"))
                        key_note = ""
                        if source_key and target_key and track.get("key_lock", True):
                            from .render import _key_lock_interval
                            delta = _key_lock_interval(source_key, target_key, target_scale)
                            signed_delta = f"+{delta}" if delta > 0 else f"−{abs(delta)}" if delta < 0 else "0"
                            key_note = f" · {source_key.split()[0]}→{target_key} ({signed_delta})"
                        loop_bars = track.get("loop_bars", analysis.get("bars", 1))
                        lines.append(f"  loop · {source_bpm:g}→{project['bpm']:g} BPM{key_note} · {loop_bars} bars")
                except (OSError, ValueError, KeyError, TypeError):
                    if track.get("mode") == "loop":
                        lines.append(f"  loop · tempo/key unknown · {track.get('loop_bars', 1)} bars")
            velocity = track["velocity"]
            for cycle_length in range(1, len(velocity) + 1):
                if len(velocity) % cycle_length == 0 and all(
                    velocity[index] == velocity[index % cycle_length]
                    for index in range(len(velocity))
                ):
                    velocity = velocity[:cycle_length]
                    break
            controls = {key: track[key] for key in
                        ("gain_db", "pan", "mute", "solo", "pitch")}
            for key in ("mode", "key_lock", "loop_bars", "duck", "role"):
                if key in track:
                    controls[key] = track[key]
            controls["velocity"] = velocity
            controls["fx"] = track["fx"]
            if "choke_group" in track:
                controls["choke_group"] = track["choke_group"]
            lines.append("  controls: " + json.dumps(controls, separators=(",", ":")))
            if track.get("notes"):
                lines.append("  notes: " + json.dumps(track["notes"], separators=(",", ":")))
        lines.append("master fx: " + json.dumps(project["master"]["fx"], separators=(",", ":")))
        if "flock" in project:
            from .flock.model import state_lines

            lines.extend(state_lines(project["flock"]))
        if "arrangement" in project:
            summary = ", ".join(f"{item['id']}×{item['repeat']}"
                                 for item in project["arrangement"]["sections"])
            lines.append(f"Arrangement · {summary}")
        credits = self._sample_credit_line(project)
        if credits:
            lines.append(credits)
        return "\n".join(lines)

    def _sample_credit_line(self, project: dict[str, Any]) -> str:
        library_sources = {
            track["source"][len("user:library/"):]
            for track in project["tracks"]
            if isinstance(track.get("source"), str) and track["source"].startswith("user:library/")
        }
        if not library_sources:
            return ""
        try:
            credits = json.loads((self.user_kit_dir / "library" / "credits.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return ""
        if not isinstance(credits, dict):
            return ""

        entries = []
        seen = set()
        for credit in credits.values():
            if not isinstance(credit, dict) or credit.get("file") not in library_sources:
                continue
            key = credit.get("file")
            if key in seen:
                continue
            seen.add(key)
            fields = [credit.get("title"), credit.get("creator"), credit.get("license"),
                      credit.get("license_url"), credit.get("landing_url")]
            clean = [re.sub(r"\s+", " ", value).strip() for value in fields
                     if isinstance(value, str) and value.strip()]
            if clean:
                title = clean[0]
                creator = clean[1] if len(clean) > 1 else ""
                detail = "; ".join(clean[2:])
                attribution = f"{title} — {creator}" if creator else title
                entries.append(f"{attribution} ({detail})" if detail else attribution)
        return "Credits: " + " | ".join(entries) if entries else ""

    def flock_catalog(self) -> dict[str, Any]:
        """Return the shared, mutation-isolated Flock catalog for the page."""
        from .flock.model import load_catalog

        return load_catalog()

    def kits(self) -> dict[str, Any]:
        from .kit.factory import FACTORY_NAMES

        user_files = self._user_files()
        from . import fx

        corvus = fx.corvus_status(self.corvus_vst3_path)
        # The page shows a Soundza title, creator and credit from this map; a missing or
        # malformed credits.json means no credits, never an error.
        credits: dict[str, dict[str, Any]] = {}
        try:
            data = json.loads((self.user_kit_dir / "library" / "credits.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            data = {}
        if isinstance(data, dict):
            for entry in data.values():
                if not isinstance(entry, dict) or not isinstance(entry.get("file"), str) or not entry["file"]:
                    continue
                source = entry.get("source")
                credits[f"library/{entry['file']}"] = {
                    "source": source if isinstance(source, str) and source else "openverse",
                    "title": entry.get("title") if isinstance(entry.get("title"), str) else None,
                    "creator": entry.get("creator") if isinstance(entry.get("creator"), str) else None,
                    "landing_url": entry.get("landing_url") if isinstance(entry.get("landing_url"), str) else None,
                    "license_url": entry.get("license_url") if isinstance(entry.get("license_url"), str) else None,
                }
        return {"factory": list(FACTORY_NAMES), "user": user_files, "corvus": corvus, "credits": credits}

    def status(self) -> dict[str, Any]:
        kits = self.kits()
        return {
            "version": __version__,
            "corvus": kits["corvus"],
            "kits": {
                "factory": kits["factory"],
                "user_dir": str(self.user_kit_dir),
                "user": kits["user"],
                "credits": kits["credits"],
            },
        }

    def _user_files(self) -> list[str]:
        root = self.user_kit_dir
        if not root.is_dir():
            return []
        resolved_root = root.resolve()
        files = []
        for candidate in root.rglob("*"):
            try:
                resolved = candidate.resolve(strict=True)
                if candidate.is_file() and resolved.is_file() and resolved.is_relative_to(resolved_root):
                    files.append(candidate.relative_to(root).as_posix())
            except (OSError, RuntimeError):
                continue
        return sorted(files)

    def _render_record_path(self, name: str, rev: int) -> Path:
        return self.render_dir / "projects" / name / f"{rev}.json"

    def _render_view_for(self, project: dict[str, Any]) -> dict[str, Any] | None:
        record_path = self._render_record_path(project["name"], int(project["rev"]))
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
            content = json.loads((self.render_dir / f"{record['hash']}.json").read_text(encoding="utf-8"))
        except (OSError, KeyError, ValueError, TypeError):
            return None
        if record.get("rev") != project["rev"] or record.get("hash") != content.get("hash"):
            return None
        if record.get("project_key") != canonical_project(project):
            return None
        if content.get("renderer_version") != _renderer_version():
            return None
        if content.get("check_identity") != _check_identity():
            return None
        if content.get("wav_hash") is None:
            return None
        if not content.get("song") and "fit" not in content:
            return None
        if all(key in content for key in _RENDER_METADATA_FIELDS):
            metadata = {key: content[key] for key in _RENDER_METADATA_FIELDS}
        else:
            # Legacy records pre-date render metadata; the record's exact rev and
            # project key were just verified, so the planner can be rederived.
            try:
                metadata = _derived_render_metadata(project)
            except Exception:
                return None
        view = {
            "hash": content["hash"],
            "wav_hash": content["wav_hash"],
            "rev": int(project["rev"]),
            "audio_url": f"/audio/{content['hash']}",
            "report": content["report"],
            "meters": content["meters"],
            "mix": content.get("mix") or self._mix_for(content),
            "duration_samples": content["duration_samples"],
            "sample_rate": content["sample_rate"],
            "flock_events": metadata["flock_events"],
            "kick_onsets": metadata["kick_onsets"],
            "flock_active_combos": metadata["flock_active_combos"],
            **({"song": True, "sections": content["sections"]} if content.get("song") else {}),
        }
        if content.get("song"):
            from .arrangement import arrangement_variety
            view["variety"] = arrangement_variety(project)
        else:
            view.update({
                "balance": content.get("balance", {}),
                "mix_notes": content.get("mix_notes", []),
                "ref": content.get("ref", "none"),
                "fit": content.get("fit", []),
            })
        return view

    def _mix_for(self, content: dict[str, Any]) -> dict[str, Any] | None:
        """Recompute and cache the mix report for a legacy render record."""
        from . import checks

        try:
            path = self.render_dir / f"{content['hash']}.wav"
            audio, sample_rate = sf.read(str(path), dtype="float64", always_2d=True)
            mix = checks.mix_report(audio, sample_rate)
            content["mix"] = mix
            _atomic_write(self.render_dir / f"{content['hash']}.json", content)
            return mix
        except (OSError, KeyError, ValueError, TypeError, sf.SoundFileRuntimeError):
            return None

    def render(self, name=None, song=False) -> dict[str, Any]:
        selected_name = name if name is not None else self.latest_project_name()
        with self._lifecycle_lock(selected_name):
            return self._render_locked(name, song=song)

    def _render_locked(self, name=None, song=False) -> dict[str, Any]:
        snapshot = self.store.read(name)
        selected = snapshot["name"]
        rev = int(snapshot["rev"])
        events.emit("render.started", {"name": selected, "rev": rev})
        report_path = None
        try:
            from . import checks, render as renderer

            if song:
                if "arrangement" not in snapshot:
                    raise ValidationError("this project has no arrangement; add one with the arrange op")
                rendered = renderer.render_project(snapshot, self.render_dir, self.user_kit_dir, song=True)
                other_audio, _meters, _metadata, _timings = renderer.render_song_audio(
                    snapshot, renderer.SAMPLE_RATE, self.user_kit_dir)
                wav_data = Path(rendered["path"]).read_bytes()
                deterministic = wav_data == renderer.wav_bytes(other_audio, renderer.SAMPLE_RATE, "PCM_24")
                expected = rendered["duration_samples"]
                report = checks.evaluate_file(rendered["path"], expected, deterministic=deterministic)
                mix = rendered.get("mix")
                if mix is None:
                    mix = checks.mix_report(other_audio, renderer.SAMPLE_RATE)
                # A full content record plus the per-revision record, so the page's next
                # project load returns this song render (not the loop, not nothing).
                _atomic_write(self.render_dir / f"{rendered['hash']}.json", {
                    "hash": rendered["hash"], "renderer_version": renderer.RENDERER_VERSION,
                    "check_identity": _check_identity(), "wav_hash": rendered["wav_hash"],
                    "report": report, "meters": rendered["meters"], "mix": mix,
                    "duration_samples": rendered["duration_samples"],
                    "sample_rate": rendered["sample_rate"],
                    **{key: rendered[key] for key in _RENDER_METADATA_FIELDS},
                    "song": True, "sections": rendered["sections"],
                })
                self._record_revision(selected, rev, rendered["hash"], canonical_project(snapshot))
                song_view = {
                    "hash": rendered["hash"], "rev": rev,
                    "audio_url": f"/audio/{rendered['hash']}", "report": report,
                    "meters": rendered["meters"], "mix": mix,
                    "duration_samples": rendered["duration_samples"],
                    "sample_rate": rendered["sample_rate"],
                    "flock_events": rendered["flock_events"],
                    "kick_onsets": rendered["kick_onsets"],
                    "flock_active_combos": rendered["flock_active_combos"],
                    "song": True, "sections": rendered["sections"],
                    "variety": rendered["variety"],
                }
                result = {**song_view, "path": str(Path(rendered["path"]).resolve()),
                          "wav_hash": rendered["wav_hash"], "project": snapshot,
                          "snapshot": self._tool_snapshot(snapshot, song_view, Path(rendered["path"]))}
                events.emit("render.done", {"name": selected, "rev": rev,
                                             "hash": rendered["hash"], "report": report})
                return result

            content_hash = hashlib.sha256(
                (canonical_project(snapshot) + renderer.RENDERER_VERSION).encode("utf-8")
            ).hexdigest()
            expected = round(snapshot["bars"] * 4 * 60 / float(snapshot["bpm"])
                             * renderer.SAMPLE_RATE)
            wav_path = self.render_dir / f"{content_hash}.wav"
            report_path = self.render_dir / f"{content_hash}.json"
            self.render_dir.mkdir(parents=True, exist_ok=True)
            project_key = canonical_project(snapshot)
            with _locked(self.render_dir / ".locks", content_hash):
                cached = self._load_cache(report_path, wav_path, content_hash,
                                          renderer.RENDERER_VERSION, _check_identity(), expected)
                if cached is not None and not all(key in cached for key in _RENDER_METADATA_FIELDS):
                    # Legacy cache entries still have a valid, exact-revision WAV.
                    # Recompute the planner metadata rather than re-encoding bytes.
                    try:
                        cached = {**cached, **_derived_render_metadata(snapshot)}
                        _atomic_write(report_path, cached)
                    except Exception:
                        cached = None
                if cached is not None and "mix" not in cached:
                    mix = self._mix_for(cached)
                    if mix is None:
                        cached = None
                if cached is not None and not all(
                    key in cached for key in ("balance", "mix_notes", "ref", "fit")
                ):
                    # Pre-mix cache reports lack layer measurements. Re-render once
                    # to populate the new response fields; the deterministic WAV is unchanged.
                    cached = None
                if cached is None:
                    report_path.unlink(missing_ok=True)
                    rendered = renderer.render_project(snapshot, self.render_dir, self.user_kit_dir)
                    wav_path = Path(rendered["path"]).resolve()
                    wav_data = wav_path.read_bytes()
                    # A second render uses fresh DSP/FX instances. The encoded bytes, not file metadata,
                    # establish determinism on every cache miss.
                    other_audio, _other_meters = renderer.render_audio(
                        snapshot, renderer.SAMPLE_RATE, self.user_kit_dir
                    )
                    other_bytes = renderer.wav_bytes(other_audio, renderer.SAMPLE_RATE, "PCM_24")
                    deterministic = wav_data == other_bytes
                    report = checks.evaluate_file(wav_path, expected, deterministic=deterministic)
                    mix = rendered.get("mix")
                    if mix is None:
                        try:
                            mix = checks.mix_report(other_audio, renderer.SAMPLE_RATE)
                        except Exception:
                            mix = None
                    cached = {
                        "hash": content_hash,
                        "renderer_version": renderer.RENDERER_VERSION,
                        "check_identity": _check_identity(),
                        "wav_hash": hashlib.sha256(wav_data).hexdigest(),
                        "report": report,
                        "meters": rendered["meters"],
                        "mix": mix,
                        "balance": rendered.get("balance", {}),
                        "mix_notes": rendered.get("mix_notes", []),
                        "ref": rendered.get("ref", "none"),
                        "fit": rendered.get("fit", []),
                        "duration_samples": rendered["duration_samples"],
                        "sample_rate": rendered["sample_rate"],
                        "flock_events": rendered["flock_events"],
                        "kick_onsets": rendered["kick_onsets"],
                        "flock_active_combos": rendered["flock_active_combos"],
                    }
                    _atomic_write(report_path, cached)
                self._record_revision(selected, rev, content_hash, project_key)
            view = {
                "hash": content_hash,
                "rev": rev,
                "audio_url": f"/audio/{content_hash}",
                "report": cached["report"],
                "meters": cached["meters"],
                "mix": cached.get("mix"),
                "balance": cached["balance"],
                "mix_notes": cached["mix_notes"],
                "ref": cached["ref"],
                "fit": cached["fit"],
                "duration_samples": cached["duration_samples"],
                "sample_rate": cached["sample_rate"],
                "flock_events": cached["flock_events"],
                "kick_onsets": cached["kick_onsets"],
                "flock_active_combos": cached["flock_active_combos"],
            }
            result = {
                **view,
                "path": str(wav_path.resolve()),
                "wav_hash": cached["wav_hash"],
                "project": snapshot,
                "snapshot": self._tool_snapshot(snapshot, view, wav_path),
            }
            events.emit("render.done", {"name": selected, "rev": rev,
                                         "hash": content_hash, "report": cached["report"]})
            return result
        except Exception as exc:
            if report_path is not None:
                try:
                    report_path.unlink(missing_ok=True)
                except OSError:
                    pass
            message = str(exc).strip() or "render failed"
            events.emit("render.failed", {"name": selected, "rev": rev, "message": message})
            raise

    def _load_cache(self, report_path: Path, wav_path: Path, content_hash: str,
                    renderer_version: str, check_identity: str, expected: int) -> dict[str, Any] | None:
        try:
            record = json.loads(report_path.read_text(encoding="utf-8"))
            wav_data = wav_path.read_bytes()
        except (OSError, ValueError):
            return None
        if record.get("hash") != content_hash or record.get("renderer_version") != renderer_version:
            return None
        if record.get("check_identity") != check_identity:
            return None
        if record.get("duration_samples") != expected or record.get("wav_hash") != hashlib.sha256(wav_data).hexdigest():
            return None
        if not isinstance(record.get("report"), dict) or not isinstance(record.get("meters"), dict):
            return None
        return record

    def _record_revision(self, name: str, rev: int, content_hash: str, project_key: str) -> None:
        _atomic_write(self._render_record_path(name, rev), {
            "name": name, "rev": rev, "hash": content_hash, "project_key": project_key,
        })

    @staticmethod
    def _tool_snapshot(project: dict[str, Any], view: dict[str, Any], wav_path: Path) -> dict[str, Any]:
        tracks = [
            {"id": track["id"], "steps": track["steps"], "velocity": track["velocity"],
             "mute": track["mute"]}
            for track in project["tracks"][:8]
        ]
        snapshot = {
            "name": project["name"],
            "rev": project["rev"],
            "hash": view["hash"],
            "path": str(wav_path.resolve()),
            "bpm": project["bpm"],
            "bars": project["bars"],
            "swing": project["swing"],
            "duration_samples": view["duration_samples"],
            "report": view["report"],
            "meters": view["meters"],
            "mix": view.get("mix"),
            "tracks": tracks,
        }
        if "arrangement" in project:
            snapshot["arrangement"] = project["arrangement"]
        if view.get("song"):
            snapshot["song"] = True
            snapshot["sections"] = view["sections"]
            snapshot["variety"] = view["variety"]
        else:
            snapshot["balance"] = view.get("balance", {})
            snapshot["mix_notes"] = view.get("mix_notes", [])
            snapshot["ref"] = view.get("ref", "none")
            snapshot["fit"] = view.get("fit", [])
        flock = project.get("flock")
        if flock is not None:
            # Only the immutable rendered snapshot may source the chat card's wire.
            # In particular, never read perches from the shared hash-keyed cache.
            snapshot["flock"] = {
                "perches": [
                    None if perch is None else {
                        "bird": perch["bird"], "song": perch["song"],
                        "mute": perch["mute"], "solo": perch["solo"],
                        **{key: perch[key] for key in ("gain_db", "pan") if key in perch},
                    }
                    for perch in flock["perches"]
                ],
            }
        return snapshot

    def audio(self, audio_hash: str) -> dict[str, Any]:
        if not isinstance(audio_hash, str) or not _HASH_RE.fullmatch(audio_hash):
            raise NotFoundError("audio not found")
        wav_path = self.render_dir / f"{audio_hash}.wav"
        report_path = self.render_dir / f"{audio_hash}.json"
        try:
            record = json.loads(report_path.read_text(encoding="utf-8"))
            wav_data = wav_path.read_bytes()
        except (OSError, ValueError):
            raise NotFoundError("audio not found") from None
        if record.get("hash") != audio_hash or hashlib.sha256(wav_data).hexdigest() != record.get("wav_hash"):
            raise NotFoundError("audio not found")
        return {"hash": audio_hash, "mime": "audio/wav", "b64": base64.b64encode(wav_data).decode("ascii")}


def get_service(root=None, user_kit_dir=None, corvus_vst3_path=None) -> Service:
    """Get a service by the currently resolved data directory and settings."""
    settings = _ctx_settings()
    kit = user_kit_dir if user_kit_dir is not None else settings.get("user_kit_dir")
    corvus = corvus_vst3_path if corvus_vst3_path is not None else settings.get("corvus_vst3_path")
    resolved_root = Path(root if root is not None else _data_dir()).expanduser().resolve()
    key = (str(resolved_root), _setting_path(kit), str(corvus or ""))
    with _SERVICE_LOCK:
        service = _SERVICES.get(key)
        if service is None:
            service = Service(resolved_root, kit, corvus)
            _SERVICES[key] = service
        return service


def reset_services_for_tests() -> None:
    """Clear cached service objects; intended for isolated tests only."""
    with _SERVICE_LOCK:
        _SERVICES.clear()


__all__ = ["Service", "get_service", "set_settings_provider", "reset_services_for_tests"]
