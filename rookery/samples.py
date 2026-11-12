"""CC0 sample search and import through Openverse, or lossless Soundza samples."""

from __future__ import annotations

import io
import json
import math
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import numpy as np
import soundfile as sf

from .project import ValidationError


_SOURCES = {"openverse", "soundza"}
_API = "https://api.openverse.org/v1/audio/"
_ALLOWED_HOSTS = {"api.openverse.org", "cdn.freesound.org"}
_TIMEOUT_SECONDS = 15
_MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
_MAX_API_BYTES = 2 * 1024 * 1024
_MAX_SECONDS = 30
_TARGET_PEAK = 10 ** (-1 / 20)
# Openverse answers 403 to urllib's default User-Agent; identify the plugin plainly.
_HEADERS = {"User-Agent": "Rookery/0.1 (Hermes plugin sample search)", "Accept": "*/*"}


def _validate_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        hostname = (parsed.hostname or "").lower()
        port = parsed.port
    except (TypeError, ValueError):
        raise ValidationError("sample URL must use an allowlisted host") from None
    if (parsed.scheme != "https" or hostname not in _ALLOWED_HOSTS
            or parsed.username is not None or parsed.password is not None
            or port not in (None, 443)):
        raise ValidationError("sample URL must use https on an allowlisted host")
    return url


class _AllowlistedRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _http_get(url: str, *, timeout: int):
    """Open one allowlisted HTTPS URL; kept as a seam for offline tests."""
    _validate_url(url)
    opener = build_opener(_AllowlistedRedirectHandler())
    return opener.open(Request(url, headers=_HEADERS), timeout=timeout)


def _response_body(url: str, maximum: int) -> bytes:
    _validate_url(url)
    response = _http_get(url, timeout=_TIMEOUT_SECONDS)
    try:
        final_url = response.geturl() if callable(getattr(response, "geturl", None)) else url
        _validate_url(final_url)
        status = getattr(response, "status", 200)
        if status < 200 or status >= 300:
            raise ValidationError(f"Openverse returned HTTP {status}")
        headers = getattr(response, "headers", {}) or {}
        content_length = headers.get("Content-Length") if hasattr(headers, "get") else None
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except ValueError:
                declared_length = None
            if declared_length is not None and declared_length > maximum:
                raise ValidationError("sample download exceeds the 20 MB size limit")
        body = response.read(maximum + 1)
        if len(body) > maximum:
            raise ValidationError("sample download exceeds the 20 MB size limit")
        return body
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()


def _json_response(url: str) -> dict:
    try:
        raw = _response_body(url, _MAX_API_BYTES)
        data = json.loads(raw.decode("utf-8"))
    except ValidationError:
        raise
    except HTTPError as exc:
        raise ValidationError(f"Openverse returned HTTP {exc.code}") from None
    except Exception:
        raise ValidationError("Openverse is unavailable; check the connection and try again") from None
    if not isinstance(data, dict):
        raise ValidationError("Openverse returned an invalid response")
    return data


def _clean_text(value, maximum: int) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", "".join(char for char in value if ord(char) >= 32)).strip()[:maximum]


def _is_cc0(value) -> bool:
    return isinstance(value, str) and value.strip().lower() in {"cc0", "cc0-1.0"}


def _compact_hit(item: dict, seconds: float) -> dict | None:
    identifier = item.get("id")
    if not isinstance(identifier, str) or not identifier:
        return None
    hit = {
        "id": identifier,
        "title": _clean_text(item.get("title"), 48),
        "creator": _clean_text(item.get("creator"), 32),
        "seconds": round(seconds, 1),
        "tags": [name for name in (_clean_text(tag.get("name") if isinstance(tag, dict) else tag, 20)
                                   for tag in (item.get("tags") or [])) if name][:5],
        "license": "cc0",
    }
    while len(json.dumps(hit, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) >= 150:
        if hit["tags"]:
            hit["tags"].pop()
        elif hit["creator"]:
            hit["creator"] = hit["creator"][:-1]
        elif hit["title"]:
            hit["title"] = hit["title"][:-1]
        else:
            return None
    return hit


def search(query, kind=None, max_seconds=None, limit=8, bpm=None, key=None, *,
           source="openverse", kit_dir=None):
    """Route a sample search to Soundza or Openverse.

    The ``rookery_samples`` tool defaults to ``soundza``; this helper keeps
    ``openverse`` as its own default so existing callers are unchanged.
    """
    if source not in _SOURCES:
        raise ValidationError('sample source must be "soundza" or "openverse"')
    if source == "soundza":
        from . import soundza
        return soundza.search(query, kind=kind, max_seconds=max_seconds, limit=limit,
                              bpm=bpm, key=key, kit_dir=kit_dir)
    return _search_openverse(query, kind, max_seconds, limit, bpm, key)


def _search_openverse(query, kind=None, max_seconds=None, limit=8, bpm=None, key=None):
    """Return compact CC0-only Openverse audio hits for a query."""
    if not isinstance(query, str) or not query.strip():
        raise ValidationError("sample search query must be a non-empty string")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ValidationError("sample search limit must be an integer from 1 to 20")
    if max_seconds is not None:
        if isinstance(max_seconds, bool) or not isinstance(max_seconds, (int, float)) \
                or not math.isfinite(max_seconds) or max_seconds <= 0:
            raise ValidationError("max_seconds must be a positive number")
    if bpm is not None and (isinstance(bpm, bool) or not isinstance(bpm, (int, float)) or not math.isfinite(bpm) or bpm <= 0):
        raise ValidationError("bpm must be a positive number")
    if key is not None and (not isinstance(key, str) or not key.strip()):
        raise ValidationError("key must be a non-empty string")
    terms = [query.strip()]
    if kind is not None:
        if not isinstance(kind, str) or not kind.strip():
            raise ValidationError("kind must be a non-empty string when provided")
        terms.append(kind.strip())
    url = _API + "?" + urlencode({
        "q": " ".join(terms),
        "license": "cc0",
        "page_size": min(20, max(limit, limit * 2)),
    })
    payload = _json_response(url)
    results = payload.get("results")
    if not isinstance(results, list):
        raise ValidationError("Openverse returned an invalid audio list")
    from .sampling import key_fit, parse_title
    hits = []
    for item in results:
        if not isinstance(item, dict) or not _is_cc0(item.get("license")):
            continue
        try:
            seconds = float(item.get("duration")) / 1000
        except (TypeError, ValueError):
            continue
        if not math.isfinite(seconds) or seconds < 0:
            continue
        if max_seconds is not None and seconds > max_seconds:
            continue
        hit = _compact_hit(item, seconds)
        if hit is not None:
            raw_tags = [tag.get("name") if isinstance(tag, dict) else tag for tag in (item.get("tags") or [])]
            parsed = parse_title(" ".join([_clean_text(item.get("title"), 300),
                                           *(_clean_text(tag, 64) for tag in raw_tags)]))
            if parsed["bpm"] is not None:
                hit["bpm"] = parsed["bpm"]
            if parsed["key"] is not None:
                hit["key"] = parsed["key"]
            tempo_score = .5
            if bpm and parsed["bpm"]:
                ratio = parsed["bpm"] / float(bpm)
                tempo_score = 1.0 if abs(ratio - 1) <= .08 else (.8 if min(abs(ratio * 2 - 1), abs(ratio / 2 - 1)) <= .04 else .1)
            harmonic_score = key_fit(parsed["key"], key)
            hit["fit"] = round((tempo_score + harmonic_score) / 2, 2)
            hits.append(hit)
    hits.sort(key=lambda hit: hit.get("fit", 0), reverse=True)
    for hit in hits:
        while len(json.dumps(hit, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) >= 150:
            if hit.get("tags"):
                hit["tags"].pop()
            elif hit.get("creator"):
                hit["creator"] = hit["creator"][:-1]
            elif hit.get("title"):
                hit["title"] = hit["title"][:-1]
            else:
                break
    return hits[:limit]


def _safe_id(value) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value):
        raise ValidationError("Openverse audio id is invalid")
    return value


def _slug(title: str) -> str:
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")[:48].strip("-")
    return slug or "sample"


def _read_audio(raw: bytes):
    try:
        with sf.SoundFile(io.BytesIO(raw)) as source:
            sample_rate = int(source.samplerate)
            channels = int(source.channels)
            if sample_rate < 1 or channels not in (1, 2):
                raise ValidationError("Openverse sample must be mono or stereo audio")
            data = source.read(frames=sample_rate * _MAX_SECONDS, dtype="float32", always_2d=True)
    except ValidationError:
        raise
    except Exception:
        raise ValidationError("Openverse sample could not be decoded as audio") from None
    if not len(data):
        raise ValidationError("Openverse sample contains no audio")
    return data, sample_rate


def _write_atomic(path: Path, data: bytes) -> None:
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".sample-", suffix=".tmp", delete=False) as temp:
            temp_name = temp.name
            temp.write(data)
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(temp_name, path)
    finally:
        if temp_name:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass


def _read_credits(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValidationError("sample credits file is unreadable") from None
    if not isinstance(data, dict):
        raise ValidationError("sample credits file is malformed")
    return data


def fetch(sample_id, kit_dir, project_bpm=None, project_key=None, *,
          project_scale="major", source="openverse"):
    """Route a sample fetch to Soundza or Openverse; the tool defaults to Soundza."""
    if source not in _SOURCES:
        raise ValidationError('sample source must be "soundza" or "openverse"')
    if source == "soundza":
        from . import soundza
        return soundza.fetch(sample_id, kit_dir, project_bpm, project_key,
                             project_scale=project_scale)
    return _fetch_openverse(sample_id, kit_dir, project_bpm, project_key, project_scale)


def _fetch_openverse(sample_id, kit_dir, project_bpm=None, project_key=None, project_scale="major"):
    """Re-lookup a CC0 Openverse result, then save a normalized local FLAC."""
    identifier = _safe_id(sample_id)
    detail_url = _API + quote(identifier, safe="") + "/"
    item = _json_response(detail_url)
    if item.get("id") != identifier:
        raise ValidationError("Openverse returned a different audio id")
    if not _is_cc0(item.get("license")):
        raise ValidationError("only CC0 samples can be fetched")
    audio_url = item.get("url")
    if not isinstance(audio_url, str):
        raise ValidationError("Openverse sample has no preview URL")
    _validate_url(audio_url)

    title = _clean_text(item.get("title"), 300) or "Untitled sample"
    creator = _clean_text(item.get("creator"), 300)
    token = re.sub(r"[^a-zA-Z0-9]", "", identifier)[:8].lower()
    if len(token) < 8:
        token = (token + "00000000")[:8]
    filename = f"{_slug(title)}-{token}.flac"
    library = Path(kit_dir).expanduser().resolve() / "library"
    destination = library / filename
    library.mkdir(parents=True, exist_ok=True)

    quality = None
    if destination.is_file() and destination.stat().st_size > 0:
        length = _existing_length(destination)
    else:
        try:
            raw = _response_body(audio_url, _MAX_DOWNLOAD_BYTES)
        except ValidationError:
            raise
        except Exception:
            raise ValidationError("Openverse could not download this sample; check the connection and try again") from None
        data, sample_rate = _read_audio(raw)
        length = len(data) / sample_rate
        # Openverse is the keyless fallback and serves lossy previews, so the gate is
        # advisory here: the agent hears what failed and can prefer a Soundza sound.
        try:
            from .sample_gate import assess_bytes
            verdict = assess_bytes(raw, Path(urlsplit(audio_url).path).suffix or ".mp3")
            quality = {"verdict": verdict["verdict"], "warnings": verdict["reasons"] + verdict["warnings"],
                       "note": "Openverse previews are lossy; imported as a fallback. Prefer source=soundza."}
        except Exception:
            quality = None
        peak = float(np.max(np.abs(data)))
        if peak > 0:
            data = (data * (_TARGET_PEAK / peak)).astype(np.float32, copy=False)
        try:
            encoded = io.BytesIO()
            sf.write(encoded, data, sample_rate, format="FLAC", subtype="PCM_24")
            _write_atomic(destination, encoded.getvalue())
        except Exception:
            raise ValidationError("could not write the imported sample") from None

    license_url = _clean_text(item.get("license_url"), 1000)
    landing_url = _clean_text(item.get("foreign_landing_url"), 1000)
    credit = {
        "id": identifier,
        "file": filename,
        "title": title,
        "creator": creator,
        "license": "cc0",
        "license_url": license_url,
        "landing_url": landing_url,
    }
    credits_path = library / "credits.json"
    credits = _read_credits(credits_path)
    credits[identifier] = credit
    _write_atomic(credits_path, (json.dumps(credits, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))

    source = f"user:library/{filename}"
    from .sampling import analyze, has_confident_key, key_lock_shift
    analysis = analyze(destination, title=title, project_bpm=project_bpm)
    profile = analysis["profile"]
    confident_key = has_confident_key(analysis)
    shift = (key_lock_shift(analysis.get("key"), project_key, project_scale)
             if profile["pitched"] and confident_key else None)
    tempo = f"{analysis['bpm']:g} BPM" if analysis.get("bpm") else "unknown tempo"
    key_text = f" {analysis['key']}" if profile["pitched"] and analysis.get("key") else ""
    length_text = f"{analysis['bars']} {'bar' if analysis['bars'] == 1 else 'bars'}"
    target_tempo = f"{project_bpm:g}" if project_bpm else "the project tempo"
    target_key = f" in {project_key}" if project_key and profile["pitched"] else ""
    key_lock_hint = ("set key_lock=false for unpitched audio" if not profile["pitched"] else
                     "key is unknown; set key_lock=false" if not analysis.get("key") else
                     "verify the low-confidence key or set key_lock=false" if not confident_key else
                     "loop mode locks to the project grid and key")
    result = {
        "source": source,
        "seconds": round(length, 3),
        "analysis": analysis,
        "profile": profile,
        "fit_note": f"{tempo}{key_text} loop, {length_text}; in loop mode it plays at {target_tempo}{target_key}."
                    + (f" Key lock shift: {shift:+d} semitones." if shift is not None else "")
                    + (f" Warning: {shift:+d} semitones sounds artificial; prefer another hit."
                       if shift is not None and abs(shift) > 5 else "")
                    + (" Key estimate has low confidence; verify it or set key_lock=false."
                       if profile["pitched"] and analysis.get("key") and not confident_key else ""),
        "key_lock_shift_semitones": shift,
        "hint": f"add with rookery_track action=add kind=sample source={source} mode=loop; {key_lock_hint}",
    }
    if quality is not None:
        result["quality"] = quality
    return result


def _existing_length(path: Path) -> float:
    try:
        info = sf.info(path)
        return min(info.frames / info.samplerate, _MAX_SECONDS)
    except Exception:
        raise ValidationError("existing imported sample could not be read") from None


__all__ = ["search", "fetch"]
