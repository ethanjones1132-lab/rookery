"""Standalone Hermes dashboard adapter sharing the plugin's private engine package."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse


_PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def _bootstrap_module():
    bootstrap_path = (_PLUGIN_ROOT / "rookery" / "bootstrap.py").resolve(strict=True)
    digest = hashlib.sha256(str(_PLUGIN_ROOT).casefold().encode("utf-8")).hexdigest()[:24]
    name = f"_rookery_bootstrap_{digest}"
    module = sys.modules.get(name)
    if module is not None:
        if Path(module.__file__).resolve() != bootstrap_path:
            raise ImportError(f"Rookery bootstrap origin mismatch: {name}")
        return module
    spec = importlib.util.spec_from_file_location(name, bootstrap_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load Rookery bootstrap from {bootstrap_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


_bootstrap = _bootstrap_module()
_ENGINE = None
_ENGINE_LOCK = threading.Lock()
router = APIRouter()


def _get_engine():
    """Load the shared engine once, on the first request, under a lock."""
    global _ENGINE
    engine = _ENGINE
    if engine is not None:
        return engine
    with _ENGINE_LOCK:
        if _ENGINE is None:
            _ENGINE = _bootstrap.load_engine(_PLUGIN_ROOT)
        return _ENGINE


def __getattr__(name):
    # Keep ``plugin_api._engine`` working for existing callers without loading at import.
    if name == "_engine":
        return _get_engine()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


async def _run(method: str, *args, **kwargs):
    service = await run_in_threadpool(_get_engine().service.get_service)
    return await run_in_threadpool(getattr(service, method), *args, **kwargs)


def _error_response(exc: Exception):
    message = str(exc).strip() or "Rookery request failed"
    try:
        engine = _get_engine()
        ConflictError = engine.project.ConflictError
        NotFoundError = engine.project.NotFoundError
        ProjectError = engine.project.ProjectError
        ValidationError = engine.project.ValidationError
    except Exception as load_error:
        detail = str(load_error).strip()
        return JSONResponse(
            {"message": f"Rookery engine unavailable: {detail or 'failed to load'}"},
            status_code=503,
        )

    if isinstance(exc, ConflictError):
        return JSONResponse({"message": message, "rev": exc.rev}, status_code=409)
    if isinstance(exc, NotFoundError):
        return JSONResponse({"message": message}, status_code=404)
    if isinstance(exc, (ValidationError, ProjectError)):
        return JSONResponse({"message": message}, status_code=422)
    return JSONResponse({"message": message}, status_code=500)


@router.get("/projects")
async def projects():
    try:
        return await _run("list_projects")
    except Exception as exc:
        return _error_response(exc)


@router.get("/project/{name}")
async def project(name: str, since: str | None = None):
    try:
        return await _run("get_project", name, since)
    except Exception as exc:
        return _error_response(exc)


@router.post("/project")
async def create_project(body: Any = Body(default={} )):
    try:
        engine = _get_engine()
        if not isinstance(body, dict) or set(body) - {"name", "bpm", "bars", "swing", "from"}:
            raise engine.project.ValidationError("project create accepts name, bpm, bars, swing, and from")
        if ("name" in body and body["name"] is None) or ("from" in body and body["from"] is None):
            raise engine.project.ValidationError("name and from must be omitted or strings")
        return await _run("create_project", body.get("name"), body.get("bpm", 90),
                          body.get("bars", 4), body.get("swing", 0), body.get("from"))
    except Exception as exc:
        return _error_response(exc)


@router.post("/project/{name}/rename")
async def rename_project(name: str, body: Any = Body(...)):
    try:
        engine = _get_engine()
        if not isinstance(body, dict) or set(body) != {"to"}:
            raise engine.project.ValidationError("rename requires a JSON object with to")
        await _run("rename_project", name, body["to"])
        return await _run("get_project", body["to"])
    except Exception as exc:
        return _error_response(exc)


@router.delete("/project/{name}")
async def delete_project(name: str):
    try:
        await _run("delete_project", name)
        return {"deleted": name}
    except Exception as exc:
        return _error_response(exc)


@router.get("/status")
async def status():
    try:
        return await _run("status")
    except Exception as exc:
        return _error_response(exc)


@router.get("/flock/catalog")
async def flock_catalog():
    try:
        return await _run("flock_catalog")
    except Exception as exc:
        return _error_response(exc)


@router.post("/edit")
async def edit(body: Any = Body(...)):
    try:
        return await _run("edit", body, source="user", tool=None)
    except Exception as exc:
        return _error_response(exc)


@router.post("/undo")
async def undo(body: Any = Body(...)):
    try:
        engine = _get_engine()
        if not isinstance(body, dict) or "name" not in body:
            raise engine.project.ValidationError("undo requires a JSON object with name")
        if set(body) - {"name", "steps"}:
            raise engine.project.ValidationError("undo body accepts only name and steps")
        return await _run("undo", body["name"], body.get("steps", 1), source="user", tool="rookery_undo")
    except Exception as exc:
        return _error_response(exc)


@router.post("/render")
async def render(body: Any = Body(...)):
    try:
        engine = _get_engine()
        if not isinstance(body, dict) or set(body) - {"name", "song"} or "name" not in body:
            raise engine.project.ValidationError("render requires name and optional song")
        if "song" in body and not isinstance(body["song"], bool):
            raise engine.project.ValidationError("song must be a boolean")
        result = (await _run("render", body["name"], song=True) if body.get("song", False)
                  else await _run("render", body["name"]))
        return {key: result.get(key) for key in (
            "hash", "wav_hash", "rev", "audio_url", "report", "meters", "mix", "balance", "mix_notes", "fit",
            "ref", "duration_samples", "sample_rate", "flock_events", "kick_onsets", "flock_active_combos",
            "song", "sections", "variety",
        )}
    except Exception as exc:
        return _error_response(exc)


@router.post("/export")
async def export(body: Any = Body(...)):
    try:
        engine = _get_engine()
        allowed = {"name", "song", "stems", "midi", "fps"}
        if not isinstance(body, dict) or set(body) - allowed:
            raise engine.project.ValidationError("export accepts name, song, stems, midi, and fps")
        if "name" in body and (not isinstance(body["name"], str) or not body["name"]):
            raise engine.project.ValidationError("name must be a non-empty string")
        for key in ("song", "stems", "midi"):
            if key in body and not isinstance(body[key], bool):
                raise engine.project.ValidationError(f"{key} must be a boolean")
        fps = body.get("fps")
        if fps is not None and (isinstance(fps, bool) or not isinstance(fps, int) or not 1 <= fps <= 240):
            raise engine.project.ValidationError("fps must be an integer from 1 to 240")
        service = await run_in_threadpool(engine.service.get_service)
        name = body.get("name") or await run_in_threadpool(service.latest_project_name)
        project = await run_in_threadpool(service.store.read, name)
        from_engine = engine.export.export_project
        result = await run_in_threadpool(
            from_engine, project, service.root, user_kit_dir=service.user_kit_dir,
            song=body.get("song"), stems=body.get("stems", True),
            midi=body.get("midi", True), fps=fps, corvus_vst3_path=service.corvus_vst3_path,
        )
        return result
    except Exception as exc:
        return _error_response(exc)


@router.get("/audio/{audio_hash}")
async def audio(audio_hash: str):
    try:
        return await _run("audio", audio_hash)
    except Exception as exc:
        return _error_response(exc)


__all__ = ["router"]
