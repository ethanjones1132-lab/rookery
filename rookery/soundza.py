"""Soundza sample search and import: lossless loops and one-shots with full metadata.

The API is free but downloading needs a key (``SOUNDZA_API_KEY``). Searching works
without one. Files are WAV/FLAC/AIFF only: lossy results are dropped before the
agent ever sees them, and every downloaded file is re-encoded to a normalized
24-bit FLAC next to the Openverse credits. A sound is saved once and reused by id,
and sounds Soundza lists in ``/removals`` are deleted from the library.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
from datetime import date
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import numpy as np
import soundfile as sf

from .project import ValidationError
from .samples import _TARGET_PEAK, _clean_text, _read_credits, _slug, _write_atomic


_API = "https://api.soundza.com/v1"
_API_HOSTS = {"api.soundza.com"}
# Soundza's /file redirect lands on its Cloudflare R2 bucket (observed live on 2026-11-10:
# soundloft-packs.<account>.r2.cloudflarestorage.com). Only that storage suffix is accepted.
_STORAGE_SUFFIX = ".r2.cloudflarestorage.com"
_TIMEOUT_SECONDS = 15
_MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
_MAX_API_BYTES = 2 * 1024 * 1024
_MAX_SECONDS = 60
_STORE_LIMIT = 500
_REMOVALS_DAYS = 7
_REMOVALS_START = "2026-01-01"
_LICENSE = "soundza-standard"
_LICENSE_URL = "https://soundza.com/license"
_KEYS_URL = "https://soundza.com/developers/keys"
_HEADERS = {"User-Agent": "Rookery/0.1 (Hermes plugin sample search)", "Accept": "*/*"}
_ID_RE = re.compile(r"[a-z0-9]{20,40}")
_LOSSLESS_EXTENSIONS = {"wav", "flac", "aif", "aiff"}
# libsndfile majors that are containers of uncompressed or losslessly compressed samples.
_LOSSLESS_FORMATS = {"WAV", "WAVEX", "W64", "RF64", "FLAC", "AIFF", "CAF"}
_LOSSLESS_SUBTYPES = {"PCM_S8", "PCM_U8", "PCM_16", "PCM_24", "PCM_32", "FLOAT", "DOUBLE"}
_KIND_FORM = {"loop": "LOOP", "one-shot": "ONE_SHOT", "oneshot": "ONE_SHOT", "hit": "ONE_SHOT"}


def _api_key() -> str | None:
    """Read ``SOUNDZA_API_KEY`` at call time. The value is never logged or echoed."""
    value = os.environ.get("SOUNDZA_API_KEY")
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _missing_key_error() -> ValidationError:
    return ValidationError(
        "Soundza needs a free API key to download; get one at "
        f"{_KEYS_URL} and set it in Hermes's env as SOUNDZA_API_KEY"
    )


def _validate_api_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        hostname = (parsed.hostname or "").lower()
        port = parsed.port
    except (TypeError, ValueError):
        raise ValidationError("Soundza API URL must use https on api.soundza.com") from None
    if (parsed.scheme != "https" or hostname not in _API_HOSTS
            or parsed.username is not None or parsed.password is not None
            or port not in (None, 443)):
        raise ValidationError("Soundza API URL must use https on api.soundza.com")
    return url


def _validate_storage_url(url: str) -> str:
    """The single signed hop: https on Soundza's R2 storage, port 443, no credentials in the URL."""
    try:
        parsed = urlsplit(url)
        hostname = (parsed.hostname or "").lower()
        port = parsed.port
    except (TypeError, ValueError):
        raise ValidationError("Soundza file link must use https on Soundza's storage host") from None
    if (parsed.scheme != "https" or not hostname.endswith(_STORAGE_SUFFIX)
            or hostname == _STORAGE_SUFFIX.lstrip(".")
            or parsed.username is not None or parsed.password is not None
            or port not in (None, 443)):
        raise ValidationError("Soundza file link must use https on Soundza's storage host")
    return url


class _SoundzaRedirectHandler(HTTPRedirectHandler):
    """Follow exactly one hop off the API host, and never carry the key across it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if (urlsplit(req.full_url).hostname or "").lower() not in _API_HOSTS:
            raise ValidationError("Soundza file link redirected more than once")
        _validate_storage_url(newurl)
        new_request = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_request is not None:
            # urllib copies request headers onto the redirect; the storage host must not
            # receive the bearer key (the signed link carries its own credentials).
            new_request.remove_header("Authorization")
            new_request.remove_header("authorization")
        return new_request


def _http_get(url: str, *, timeout: int = _TIMEOUT_SECONDS, bearer: str | None = None):
    """Open one allowlisted HTTPS URL; kept as a seam for offline tests."""
    _validate_api_url(url)
    headers = dict(_HEADERS)
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    opener = build_opener(_SoundzaRedirectHandler())
    return opener.open(Request(url, headers=headers), timeout=timeout)


def _retry_seconds(headers) -> int | None:
    for name in ("Retry-After", "X-RateLimit-Reset"):
        value = headers.get(name) if hasattr(headers, "get") else None
        if value is None:
            continue
        try:
            seconds = float(str(value).strip())
        except ValueError:
            continue
        if math.isfinite(seconds) and seconds >= 0:
            return int(math.ceil(seconds))
    return None


def _http_error(exc: HTTPError) -> ValidationError:
    code = getattr(exc, "code", None)
    headers = getattr(exc, "headers", None) or {}
    if code == 401:
        return ValidationError("the Soundza key was rejected")
    if code == 429:
        wait = _retry_seconds(headers)
        if wait is None:
            return ValidationError("Soundza rate limit; try again shortly")
        return ValidationError(f"Soundza rate limit; retry after {wait} s")
    return ValidationError(f"Soundza returned HTTP {code}")


def _response_body(url: str, maximum: int, *, bearer: str | None = None) -> bytes:
    _validate_api_url(url)
    try:
        response = _http_get(url, timeout=_TIMEOUT_SECONDS, bearer=bearer)
    except ValidationError:
        raise
    except HTTPError as exc:
        raise _http_error(exc) from None
    except Exception:
        raise ValidationError("Soundza is unavailable; check the connection and try again") from None
    try:
        final_url = response.geturl() if callable(getattr(response, "geturl", None)) else url
        _validate_api_url(final_url)  # API answers come from the API host, never a redirect
        status = getattr(response, "status", 200)
        if status < 200 or status >= 300:
            raise ValidationError(f"Soundza returned HTTP {status}")
        headers = getattr(response, "headers", {}) or {}
        content_length = headers.get("Content-Length") if hasattr(headers, "get") else None
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except (TypeError, ValueError):
                declared_length = None
            if declared_length is not None and declared_length > maximum:
                raise ValidationError("Soundza download exceeds the 20 MB size limit")
        body = response.read(maximum + 1)
        if len(body) > maximum:
            raise ValidationError("Soundza download exceeds the 20 MB size limit")
        return body
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()


def _json_get(url: str, *, bearer: str | None = None) -> dict:
    try:
        data = json.loads(_response_body(url, _MAX_API_BYTES, bearer=bearer).decode("utf-8"))
    except ValidationError:
        raise
    except Exception:
        raise ValidationError("Soundza returned an invalid response") from None
    if not isinstance(data, dict):
        raise ValidationError("Soundza returned an invalid response")
    return data


def _sound_id(value) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ValidationError("Soundza sound id is invalid")
    return value


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _bpm_value(value) -> int | float | None:
    number = _number(value)
    if number is None or number <= 0:
        return None
    return int(number) if number.is_integer() else round(number, 1)


def _lossless(item: dict) -> bool:
    extension = item.get("file_extension")
    return isinstance(extension, str) and extension.strip().lower() in _LOSSLESS_EXTENSIONS


def _soundza_url(value, host: str = "soundza.com") -> str:
    text = _clean_text(value, 1000)
    try:
        parsed = urlsplit(text)
    except (TypeError, ValueError):
        return ""
    if parsed.scheme == "https" and (parsed.hostname or "").lower() == host:
        return text
    return ""


def _compact_hit(item: dict, seconds: float, bpm_target, key_target) -> dict | None:
    identifier = item.get("id")
    if not isinstance(identifier, str) or not _ID_RE.fullmatch(identifier):
        return None
    creator = item.get("creator") if isinstance(item.get("creator"), dict) else {}
    hit = {
        "id": identifier,
        "title": _clean_text(item.get("title"), 48),
        "creator": _clean_text(creator.get("name"), 32),
        "seconds": round(seconds, 1),
        "tags": [name for name in (_clean_text(tag, 20) for tag in (item.get("tags") or [])) if name][:5],
        "license": "soundza",
    }
    bpm = _bpm_value(item.get("bpm"))
    if bpm is not None:
        hit["bpm"] = bpm
    key = _clean_text(item.get("key"), 12)
    if key:
        hit["key"] = key
    hit["loop"] = bool(item.get("loop_seamless"))
    if bpm is not None or key:
        from .sampling import key_fit
        tempo_score = .5
        if bpm_target and bpm:
            ratio = float(bpm) / float(bpm_target)
            tempo_score = 1.0 if abs(ratio - 1) <= .08 else (
                .8 if min(abs(ratio * 2 - 1), abs(ratio / 2 - 1)) <= .04 else .1)
        harmonic_score = key_fit(key or None, key_target)
        hit["fit"] = round((tempo_score + harmonic_score) / 2, 2)
    else:
        hit["fit"] = .5
    while len(json.dumps(hit, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) >= 200:
        if hit["tags"]:
            hit["tags"].pop()
        elif hit["creator"]:
            hit["creator"] = hit["creator"][:-1]
        elif hit["title"]:
            hit["title"] = hit["title"][:-1]
        else:
            return None
    return hit


def _search_params(query, kind, max_seconds, limit, bpm, key) -> dict:
    params = {"q": query, "type": "MUSIC"}
    if isinstance(kind, str) and kind.strip():
        lowered = kind.strip().lower()
        if lowered in _KIND_FORM:
            params["form"] = _KIND_FORM[lowered]
        elif lowered == "texture":
            params["type"] = "AMBIENCE"
        else:
            params["q"] = f"{query} {kind.strip()}"
    if bpm is not None:
        params["min_bpm"] = round(float(bpm) * .94, 1)
        params["max_bpm"] = round(float(bpm) * 1.06, 1)
    if isinstance(key, str) and key.strip():
        params["key"] = key.strip()
    if max_seconds is not None:
        params["max_duration"] = float(max_seconds)
    params["per_page"] = min(50, max(limit, limit * 3))
    return params


def search(query, kind=None, max_seconds=None, limit=8, bpm=None, key=None, kit_dir=None):
    """Return compact lossless Soundza hits ranked by tempo/key fit."""
    if not isinstance(query, str) or not query.strip():
        raise ValidationError("sample search query must be a non-empty string")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ValidationError("sample search limit must be an integer from 1 to 20")
    if max_seconds is not None:
        if isinstance(max_seconds, bool) or not isinstance(max_seconds, (int, float)) \
                or not math.isfinite(max_seconds) or max_seconds <= 0:
            raise ValidationError("max_seconds must be a positive number")
    if bpm is not None and (isinstance(bpm, bool) or not isinstance(bpm, (int, float))
                            or not math.isfinite(bpm) or bpm <= 0):
        raise ValidationError("bpm must be a positive number")
    if key is not None and (not isinstance(key, str) or not key.strip()):
        raise ValidationError("key must be a non-empty string")

    api_key = _api_key()
    removed = _removals(kit_dir, api_key)
    payload = _json_get(_API + "/sounds/search?" + urlencode(_search_params(
        query.strip(), kind, max_seconds, limit, bpm, key)), bearer=api_key)
    results = payload.get("sounds")
    if not isinstance(results, list):
        raise ValidationError("Soundza returned an invalid sound list")

    hits = []
    for item in results:
        if not isinstance(item, dict) or not _lossless(item):
            continue
        seconds = _number(item.get("duration"))
        if seconds is None or seconds < 0:
            continue
        if max_seconds is not None and seconds > max_seconds:
            continue
        hit = _compact_hit(item, seconds, bpm, key)
        if hit is not None:
            hits.append(hit)
    hits.sort(key=lambda hit: hit.get("fit", 0), reverse=True)
    hits = hits[:limit]
    if removed:
        return {"results": hits, "removed": removed}
    return hits


def _read_lossless(raw: bytes):
    try:
        with sf.SoundFile(io.BytesIO(raw)) as source:
            if str(source.format).upper() not in _LOSSLESS_FORMATS \
                    or str(source.subtype).upper() not in _LOSSLESS_SUBTYPES:
                raise ValidationError(
                    "Soundza sample is not lossless audio; MP3, OGG and other lossy files are not imported")
            sample_rate = int(source.samplerate)
            channels = int(source.channels)
            if sample_rate < 1 or channels not in (1, 2):
                raise ValidationError("Soundza sample must be mono or stereo audio")
            frames = int(source.frames)
            if frames / sample_rate > _MAX_SECONDS:
                raise ValidationError(
                    f"Soundza sample is longer than {_MAX_SECONDS} seconds; loops must stay whole bars")
            data = source.read(frames=frames, dtype="float32", always_2d=True)
    except ValidationError:
        raise
    except Exception:
        raise ValidationError("Soundza sample could not be decoded as audio") from None
    if not len(data):
        raise ValidationError("Soundza sample contains no audio")
    return data, sample_rate


def _removals_path(kit_dir) -> Path:
    return Path(kit_dir).expanduser().resolve() / "library" / "soundza-removals.json"


def _last_check(path: Path) -> date | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = data.get("last_check") if isinstance(data, dict) else None
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _removals(kit_dir, api_key: str | None) -> list[str]:
    """Check Soundza removals when the record is stale; never fail the caller."""
    if not api_key or kit_dir is None:
        return []
    try:
        return _check_removals(kit_dir, api_key)
    except Exception:
        return []


def _check_removals(kit_dir, api_key: str) -> list[str]:
    library = Path(kit_dir).expanduser().resolve() / "library"
    path = _removals_path(kit_dir)
    last = _last_check(path)
    today = date.today()
    if last is not None and (today - last).days <= _REMOVALS_DAYS:
        return []
    since = last.isoformat() if last is not None else _REMOVALS_START
    payload = _json_get(_API + "/removals?" + urlencode({"since": since}), bearer=api_key)
    listed = payload.get("removals")
    if not isinstance(listed, list):
        raise ValidationError("Soundza returned an invalid removals list")

    credits_path = library / "credits.json"
    credits = _read_credits(credits_path)
    removed = []
    changed = False
    for entry in listed:
        identifier = entry.get("id") if isinstance(entry, dict) else None
        if not isinstance(identifier, str):
            continue
        credit = credits.get("soundza:" + identifier)
        if not isinstance(credit, dict):
            continue
        name = credit.get("file")
        if isinstance(name, str) and name and name == Path(name).name:
            try:
                (library / name).unlink()
            except OSError:
                pass
        credit["removed"] = True
        removed.append(identifier)
        changed = True
    if changed:
        _write_atomic(credits_path, (json.dumps(
            credits, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        record = {}
    if not isinstance(record, dict):
        record = {}
    previous = record.get("removed")
    record = {
        "last_check": today.isoformat(),
        "removed": sorted({*(previous if isinstance(previous, list) else []), *removed}),
    }
    library.mkdir(parents=True, exist_ok=True)
    _write_atomic(path, (json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return removed


def _live_count(credits: dict) -> int:
    return sum(1 for entry in credits.values()
               if isinstance(entry, dict) and entry.get("source") == "soundza" and not entry.get("removed"))


def _metadata(identifier: str, api_key: str) -> dict:
    item = _json_get(_API + "/sounds/" + quote(identifier, safe=""), bearer=api_key)
    if item.get("id") != identifier:
        raise ValidationError("Soundza returned a different sound id")
    return item


def _download(identifier: str, api_key: str) -> tuple[bytes, str]:
    url = _API + "/sounds/" + quote(identifier, safe="") + "/file?" + urlencode({"variant": "original"})
    _validate_api_url(url)
    try:
        response = _http_get(url, timeout=_TIMEOUT_SECONDS, bearer=api_key)
    except ValidationError:
        raise
    except HTTPError as exc:
        raise _http_error(exc) from None
    except Exception:
        raise ValidationError("Soundza could not download this sample; check the connection and try again") from None
    try:
        final_url = response.geturl() if callable(getattr(response, "geturl", None)) else url
        _validate_storage_url(final_url)
        status = getattr(response, "status", 200)
        if status < 200 or status >= 300:
            raise ValidationError(f"Soundza returned HTTP {status}")
        headers = getattr(response, "headers", {}) or {}
        content_length = headers.get("Content-Length") if hasattr(headers, "get") else None
        if content_length is not None:
            try:
                declared = int(content_length)
            except (TypeError, ValueError):
                declared = None
            if declared is not None and declared > _MAX_DOWNLOAD_BYTES:
                raise ValidationError("Soundza download exceeds the 20 MB size limit")
        raw = response.read(_MAX_DOWNLOAD_BYTES + 1)
        if len(raw) > _MAX_DOWNLOAD_BYTES:
            raise ValidationError("Soundza download exceeds the 20 MB size limit")
        return raw, (urlsplit(final_url).hostname or "")
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()


_UNPITCHED = re.compile(
    r"(?<![a-z])(drums?|drum ?loop|percussion|perc|kick|snare|hi ?hats?|hats?|cymbals?|"
    r"claps?|shakers?|breaks?|breakbeat|rims?|toms?|beat)(?![a-z])", re.I)


def _key_token(key) -> str | None:
    """Soundza's "D minor" as a filename token ("Dmin") that sampling.parse_title reads back."""
    if not isinstance(key, str):
        return None
    match = re.fullmatch(r"\s*([A-Ga-g])\s*([#b]?)\s*(major|minor|maj|min)\s*", key, re.I)
    if not match:
        return None
    letter, accidental, mode = match.groups()
    return letter.upper() + accidental + ("min" if mode.lower().startswith("min") else "maj")


def _unpitched(item: dict) -> bool:
    """No stated key and drum-like words: key lock would only detune it."""
    if _key_token(item.get("key")):
        return False
    words = " ".join([_clean_text(item.get("title"), 300),
                      *(_clean_text(tag, 40) for tag in (item.get("tags") or []))])
    return bool(_UNPITCHED.search(words))


def _filename(title: str, identifier: str, item: dict) -> str:
    """Encode Soundza's tempo and key where render's analysis reads them: the file name.

    Render re-analyses a loop from its path alone, so "86bpm-Dmin-..." carries the stated
    tempo and key, and "nokey" tells it not to key-lock drums (sampling.analyze honours it).
    The id gets an "sz" prefix so its letters never read as a key ("cm5..." is not C minor).
    """
    parts = []
    bpm = _bpm_value(item.get("bpm"))
    if isinstance(bpm, int) and 30 <= bpm <= 300:
        parts.append(f"{bpm}bpm")
    token = _key_token(item.get("key"))
    if token:
        parts.append(token)
    elif _unpitched(item):
        parts.append("nokey")
    parts.append(_slug(title)[:40].strip("-") or "sample")
    parts.append("sz" + identifier[:8])
    return "-".join(parts) + ".flac"


def _gate_kind(item: dict) -> str:
    form = str(item.get("form") or "").lower()
    return "loop" if form == "loop" or (not form and item.get("loop_seamless")) else "one-shot"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _credit(item: dict, identifier: str, filename: str, *, source_sha256: str, sha256: str,
            fetched: str, file_host: str) -> dict:
    creator = item.get("creator") if isinstance(item.get("creator"), dict) else {}
    title = _clean_text(item.get("title"), 300) or "Untitled sample"
    creator_name = _clean_text(creator.get("name"), 300)
    landing_url = _soundza_url(item.get("url"))
    creator_url = _soundza_url(creator.get("url"), host="soundza.com")
    attribution = _clean_text(item.get("attribution"), 500) or (
        f'"{title}" by {creator_name} on Soundza ({landing_url})' if creator_name
        else f'"{title}" on Soundza ({landing_url})')
    return {
        "id": identifier,
        "source": "soundza",
        "file": filename,
        "title": title,
        "creator": creator_name,
        "creator_url": creator_url,
        "license": _LICENSE,
        "license_url": _LICENSE_URL,
        "landing_url": landing_url,
        "attribution": attribution,
        "bpm": _bpm_value(item.get("bpm")),
        "key": _clean_text(item.get("key"), 32) or None,
        "loop_seamless": bool(item.get("loop_seamless")),
        "variant": "original",
        "source_sha256": source_sha256,
        "sha256": sha256,
        "fetched": fetched,
        "removed": False,
        "file_host": file_host,
    }


def fetch(soundza_id, kit_dir, project_bpm=None, project_key=None, project_scale="major"):
    """Re-read a Soundza sound, then save a normalized 24-bit FLAC and its credit."""
    identifier = _sound_id(soundza_id)
    api_key = _api_key()
    if api_key is None:
        raise _missing_key_error()

    library = Path(kit_dir).expanduser().resolve() / "library"
    credits_path = library / "credits.json"

    # Soundza's API terms: delete anything it lists as removed, then look at the
    # refreshed credits so a removed sound is never re-imported.
    removed = _removals(kit_dir, api_key)
    credits = _read_credits(credits_path)
    key = "soundza:" + identifier
    existing = credits.get(key) if isinstance(credits.get(key), dict) else None
    if identifier in removed or (existing is not None and existing.get("removed")):
        raise ValidationError("Soundza removed this sound; it is no longer available")
    if existing is None and _live_count(credits) >= _STORE_LIMIT:
        raise ValidationError(
            f"Soundza store limit reached: {_STORE_LIMIT} saved sounds; remove one before fetching another")

    item = _metadata(identifier, api_key)
    if not _lossless(item):
        raise ValidationError(
            "Soundza sample is not lossless audio; MP3, OGG and other lossy files are not imported")
    declared = _number(item.get("duration"))
    if declared is not None and declared > _MAX_SECONDS:
        raise ValidationError(
            f"Soundza sample is longer than {_MAX_SECONDS} seconds; loops must stay whole bars")

    title = _clean_text(item.get("title"), 300) or "Untitled sample"
    known = existing.get("file") if existing is not None else None
    filename = known if isinstance(known, str) and known and known == Path(known).name         else _filename(title, identifier, item)
    gate_kind = _gate_kind(item)
    quality = None
    library.mkdir(parents=True, exist_ok=True)
    destination = library / filename

    reused = False
    file_host = ""
    source_sha256 = ""
    if existing is not None and destination.is_file() and destination.stat().st_size > 0:
        try:
            saved_sha256 = _sha256_file(destination)
        except OSError:
            raise ValidationError("existing imported sample could not be read") from None
        if existing.get("sha256") == saved_sha256:
            reused = True
            source_sha256 = str(existing.get("source_sha256") or "")
            file_host = str(existing.get("file_host") or "")

    if reused:
        fetched = str(existing.get("fetched") or date.today().isoformat())
        credit = _credit(item, identifier, filename, source_sha256=source_sha256,
                         sha256=existing.get("sha256"), fetched=fetched, file_host=file_host)
    else:
        raw, file_host = _download(identifier, api_key)
        source_sha256 = hashlib.sha256(raw).hexdigest()
        data, sample_rate = _read_lossless(raw)
        from .sample_gate import assess_bytes
        stated_bpm = _bpm_value(item.get("bpm"))
        verdict = assess_bytes(raw, "." + str(item.get("file_extension") or "wav").lower(),
                               kind=gate_kind, bpm=stated_bpm if gate_kind == "loop" else None)
        if verdict["verdict"] == "reject":
            raise ValidationError("Soundza sample failed Rookery's quality gate: " + "; ".join(verdict["reasons"]))
        quality = {"verdict": verdict["verdict"], "warnings": verdict["warnings"]}
        peak = float(np.max(np.abs(data)))
        if peak > 0:
            data = (data * (_TARGET_PEAK / peak)).astype(np.float32, copy=False)
        try:
            encoded = io.BytesIO()
            sf.write(encoded, data, sample_rate, format="FLAC", subtype="PCM_24")
            _write_atomic(destination, encoded.getvalue())
        except Exception:
            raise ValidationError("could not write the imported sample") from None
        credit = _credit(item, identifier, filename, source_sha256=source_sha256,
                         sha256=_sha256_file(destination), fetched=date.today().isoformat(),
                         file_host=file_host)

    credits_path.parent.mkdir(parents=True, exist_ok=True)
    credits[key] = credit
    _write_atomic(credits_path, (json.dumps(
        credits, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))

    try:
        info = sf.info(destination)
        length = info.frames / info.samplerate
    except Exception:
        raise ValidationError("existing imported sample could not be read") from None

    source = f"user:library/{filename}"
    from .sampling import analyze, has_confident_key, key_lock_shift
    # Analyse by file name, exactly as render will (and as the analysis cache stores it):
    # the name carries Soundza's stated tempo and key, or "nokey" for drums.
    analysis = analyze(destination, project_bpm=project_bpm)
    profile = analysis["profile"]
    unpitched = "-nokey-" in f"-{filename}" or not profile["pitched"]
    confident_key = has_confident_key(analysis)
    shift = (key_lock_shift(analysis.get("key"), project_key, project_scale)
             if gate_kind == "loop" and not unpitched and confident_key else None)
    tempo = f"{analysis['bpm']:g} BPM" if analysis.get("bpm") else "unknown tempo"
    key_text = f" {analysis['key']}" if not unpitched and analysis.get("key") else ""
    length_text = f"{analysis['bars']} {'bar' if analysis['bars'] == 1 else 'bars'}"
    target_tempo = f"{project_bpm:g}" if project_bpm else "the project tempo"
    target_key = f" in {project_key}" if project_key and not unpitched else ""
    if gate_kind == "loop":
        lock = ("key_lock=false (no key: drums stay at their own pitch)" if unpitched else
                "key is unknown; set key_lock=false" if not analysis.get("key") else
                "verify the low-confidence key or set key_lock=false" if not confident_key else
                "loop mode locks to the project grid and key")
        fit_note = (f"{tempo}{key_text} loop, {length_text}; in loop mode it plays at "
                    f"{target_tempo}{target_key}.")
        if shift is not None:
            fit_note += f" Key lock shift: {shift:+d} semitones."
            if abs(shift) > 5:
                fit_note += f" Warning: {shift:+d} semitones sounds artificial; prefer another hit."
        elif not unpitched and analysis.get("key") and not confident_key:
            fit_note += " Key estimate has low confidence; verify it or set key_lock=false."
        hint = f"add with rookery_track action=add kind=sample source={source} mode=loop; {lock}"
    else:
        fit_note = f"one-shot, {round(length, 2):g} s{key_text if not unpitched else ''}."
        hint = (f"add with rookery_track action=add kind=sample source={source} slices=1; "
                "each hit plays the whole sound")
    result = {
        "source": source,
        "seconds": round(length, 3),
        "analysis": analysis,
        "profile": profile,
        "key_lock_shift_semitones": shift,
        "fit_note": fit_note,
        "hint": hint,
        "credit": {
            "title": credit["title"],
            "creator": credit["creator"],
            "landing_url": credit["landing_url"],
            "license_url": credit["license_url"],
        },
    }
    if quality is not None:
        result["quality"] = quality
    if removed:
        result["removed"] = removed
    return result


__all__ = ["search", "fetch"]
