"""Offline tests for the Soundza client: recorded keyless searches plus faked HTTP."""

import hashlib
import io
import json
from datetime import date, timedelta
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPSHandler, build_opener

import numpy as np
import pytest
import soundfile as sf

from rookery import soundza
from rookery.project import ValidationError


FIXTURES = Path(__file__).parent / "fixtures" / "soundza"
API = "https://api.soundza.com/v1"
STORAGE = "https://soundloft-packs.abc123.r2.cloudflarestorage.com/files/abc123?Expires=1700000000&Signature=xyz"
KEY = "sz_live_test_secret_value"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))["sounds"]


LOOPS = fixture("search_loop.json")
DETAIL = LOOPS[1]
SOUND_ID = DETAIL["id"]
ONES = fixture("search_one_shot.json")
KEYS = fixture("search_key_bpm.json")


class Page:
    """Minimal urllib response, including what HTTPErrorProcessor asks for."""

    def __init__(self, url, body=b"", *, status=200, headers=None):
        self.url = url
        self.body = body
        self.status = self.code = status
        self.msg = "OK" if status < 400 else "Error"
        self.headers = Message()
        for name, value in (headers or {}).items():
            self.headers[name] = value
        self.read_calls = 0

    def info(self):
        return self.headers

    def geturl(self):
        return self.url

    def read(self, size=-1):
        self.read_calls += 1
        return self.body if size < 0 else self.body[:size]

    def close(self):
        pass


def audio_bytes(seconds=1.0, sample_rate=44100, peak=0.2):
    """A clean, decaying broadband hit at CD quality, so it passes the sample quality gate."""
    count = round(seconds * sample_rate)
    noise = np.random.default_rng(7).standard_normal(count)
    audio = noise * np.exp(-np.arange(count) / (sample_rate * .25))
    audio = (audio / np.max(np.abs(audio)) * peak).astype(np.float32)
    buffer = io.BytesIO()
    sf.write(buffer, audio, sample_rate, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


def lossy_bytes(fmt):
    buffer = io.BytesIO()
    sf.write(buffer, np.zeros(800, dtype=np.float32), 8000, format=fmt)
    return buffer.getvalue()


def install(monkeypatch, *, sounds=None, detail=None, audio=None, audio_headers=None,
            removals=None, error=None):
    """Fake ``soundza._http_get`` the way test_samples fakes Openverse, and record calls."""
    detail = dict(DETAIL if detail is None else detail)
    audio = audio_bytes() if audio is None else audio
    calls = []

    def fake_http_get(url, *, timeout, bearer=None):
        calls.append({"url": url, "timeout": timeout, "bearer": bearer})
        if error is not None:
            error(url)
        if "/sounds/search" in url:
            return Page(url, json.dumps({"sounds": sounds or []}).encode())
        if "/removals" in url:
            payload = removals if removals is not None else {
                "since": "2026-01-01", "removals": [], "next_page": None}
            return Page(url, json.dumps(payload).encode())
        if url.endswith("/file?variant=original"):
            return Page(STORAGE, audio, headers=audio_headers)
        if url.startswith(API + "/sounds/"):
            return Page(url, json.dumps(detail).encode())
        raise AssertionError(f"unexpected HTTP request: {url}")

    monkeypatch.setattr(soundza, "_http_get", fake_http_get)
    return calls


@pytest.fixture(autouse=True)
def no_key(monkeypatch):
    monkeypatch.delenv("SOUNDZA_API_KEY", raising=False)


def params_of(call):
    return parse_qs(urlsplit(call["url"]).query)


def test_search_maps_kind_bpm_key_and_max_seconds(monkeypatch):
    calls = install(monkeypatch, sounds=LOOPS)

    hits = soundza.search("drum loop", kind="loop", bpm=90, key="D minor", max_seconds=12, limit=3)

    params = params_of(calls[0])
    assert params["q"] == ["drum loop"]
    assert params["type"] == ["MUSIC"]
    assert params["form"] == ["LOOP"]
    assert params["min_bpm"] == ["84.6"]
    assert params["max_bpm"] == ["95.4"]
    assert params["key"] == ["D minor"]
    assert params["max_duration"] == ["12.0"]
    assert params["per_page"] == ["9"]
    assert calls[0]["bearer"] is None
    assert calls[0]["timeout"] == 15
    assert [hit["id"] for hit in hits] == [
        "cmtnxqxmnbqk19hq396ql00bj", "cmtnwkxnzje29c61ep0isrgrw", "cmtlssff9vdg6cby24arzhn8i"]


@pytest.mark.parametrize("kind", ["one-shot", "oneshot", "hit"])
def test_one_shot_kinds_map_to_form(monkeypatch, kind):
    calls = install(monkeypatch, sounds=ONES)

    soundza.search("kick", kind=kind)

    params = params_of(calls[0])
    assert params["form"] == ["ONE_SHOT"]
    assert params["type"] == ["MUSIC"]
    assert params["q"] == ["kick"]


def test_texture_kind_searches_ambience(monkeypatch):
    calls = install(monkeypatch, sounds=LOOPS)

    soundza.search("rain", kind="texture")

    params = params_of(calls[0])
    assert params["type"] == ["AMBIENCE"]
    assert "form" not in params
    assert params["q"] == ["rain"]


def test_unknown_kind_becomes_query_terms(monkeypatch):
    calls = install(monkeypatch, sounds=LOOPS)

    soundza.search("riser", kind="sweep")

    params = params_of(calls[0])
    assert params["q"] == ["riser sweep"]
    assert "form" not in params
    assert params["type"] == ["MUSIC"]


def test_search_returns_the_compact_hit_shape_with_loop_and_license(monkeypatch):
    install(monkeypatch, sounds=KEYS)

    hits = soundza.search("lofi", bpm=86, key="D", limit=2)

    assert [hit["id"] for hit in hits] == ["cmudkglv2000009gmgye7860e", "cmudkiqaf000y0agm3h4n2753"]
    first = hits[0]
    assert set(first) <= {"id", "title", "creator", "seconds", "tags", "bpm", "key", "fit", "loop", "license"}
    assert {"id", "title", "creator", "seconds", "tags", "bpm", "key", "fit", "loop", "license"} <= set(first)
    assert first["license"] == "soundza"
    assert first["loop"] is False
    assert first["bpm"] == 86
    assert first["key"] == "D minor"
    assert first["fit"] == 1.0
    assert len(json.dumps(first, separators=(",", ":")).encode()) < 200


def test_search_drops_lossy_and_malformed_results(monkeypatch):
    good = dict(LOOPS[0])
    uppercase = {**LOOPS[0], "id": "cmtnxqxmnbqk19hq396ql00b2", "file_extension": "WAV"}
    mp3 = {**LOOPS[0], "id": "cmtnxqxmnbqk19hq396ql00b3", "file_extension": "mp3"}
    ogg = {**LOOPS[0], "id": "cmtnxqxmnbqk19hq396ql00b4", "file_extension": "ogg"}
    short_id = {**LOOPS[0], "id": "toolshort"}
    upper_id = {**LOOPS[0], "id": "CMTNXQXMNBQK19HQ396QL00B5"}
    install(monkeypatch, sounds=[good, mp3, ogg, short_id, upper_id, uppercase])

    hits = soundza.search("drum loop")

    assert [hit["id"] for hit in hits] == [good["id"], uppercase["id"]]


def test_search_filters_over_max_seconds(monkeypatch):
    install(monkeypatch, sounds=LOOPS)

    hits = soundza.search("drum loop", max_seconds=12)

    assert all(hit["seconds"] <= 12 for hit in hits)
    assert len(hits) == 3


def test_search_sends_the_key_when_it_is_set(monkeypatch):
    monkeypatch.setenv("SOUNDZA_API_KEY", KEY)
    calls = install(monkeypatch, sounds=LOOPS)

    soundza.search("drum loop")

    assert calls[0]["bearer"] == KEY


def test_fetch_without_a_key_explains_where_to_get_one(monkeypatch, tmp_path):
    calls = install(monkeypatch)

    with pytest.raises(ValidationError) as error:
        soundza.fetch(SOUND_ID, tmp_path / "kit")

    message = str(error.value)
    assert "free" in message
    assert "https://soundza.com/developers/keys" in message
    assert "SOUNDZA_API_KEY" in message
    assert "Hermes" in message
    assert calls == []


def test_fetch_rejects_ids_outside_the_soundza_shape(tmp_path):
    for bad in ("bad", "CMTNXQXMNBQK19HQ396QL00BJ", "../escape", "cmtnxqxmnbqk19hq396ql00bj\n"):
        with pytest.raises(ValidationError, match="invalid"):
            soundza.fetch(bad, tmp_path / "kit")


class FakeHTTPS(HTTPSHandler):
    """A transport that answers urllib's requests in-process, redirects included."""

    def __init__(self, route):
        self.route = route
        self.requests = []

    def https_open(self, request):
        self.requests.append(request)
        return self.route(request.full_url)


def test_fetch_follows_one_redirect_and_strips_the_key_from_the_storage_host(monkeypatch, tmp_path):
    monkeypatch.setenv("SOUNDZA_API_KEY", KEY)
    audio = audio_bytes(seconds=1, peak=0.25)

    def route(url):
        parts = urlsplit(url)
        if parts.netloc == "api.soundza.com":
            if parts.path == "/v1/removals":
                return Page(url, json.dumps({"since": "2026-01-01", "removals": [], "next_page": None}).encode())
            if parts.path == "/v1/sounds/" + SOUND_ID:
                return Page(url, json.dumps(DETAIL).encode())
            if parts.path == "/v1/sounds/" + SOUND_ID + "/file":
                assert parse_qs(parts.query)["variant"] == ["original"]
                return Page(url, b"", status=302, headers={"Location": STORAGE})
        if url == STORAGE:
            return Page(STORAGE, audio)
        raise AssertionError(f"unexpected HTTP request: {url}")

    transport = FakeHTTPS(route)
    monkeypatch.setattr(soundza, "build_opener", lambda *handlers: build_opener(transport, *handlers))
    kit_dir = tmp_path / "kit"

    result = soundza.fetch(SOUND_ID, kit_dir, 92, "D minor")

    api_requests = [request for request in transport.requests
                    if (urlsplit(request.full_url).hostname or "") == "api.soundza.com"]
    storage_requests = [request for request in transport.requests if request.full_url == STORAGE]
    assert api_requests and storage_requests
    assert all(request.get_header("Authorization") == f"Bearer {KEY}" for request in api_requests)
    assert all(request.get_header("Authorization") is None for request in storage_requests)
    assert all(not any(name.lower() == "authorization" for name in request.headers)
               for request in storage_requests)

    filename = "152bpm-nokey-jazz-drum-loop-szcmtlty4j.flac"
    path = kit_dir / "library" / filename
    assert result["source"] == f"user:library/{filename}"
    assert result["seconds"] == pytest.approx(1.0)
    assert set(result) == {"source", "seconds", "analysis", "profile", "fit_note", "hint", "credit", "quality",
                           "key_lock_shift_semitones"}
    assert result["key_lock_shift_semitones"] is None
    assert result["profile"] == result["analysis"]["profile"]
    assert result["credit"] == {
        "title": "Jazz Drum Loop",
        "creator": "wet paper",
        "landing_url": "https://soundza.com/sound/jazz-drum-loop",
        "license_url": "https://soundza.com/license",
    }
    # The keyless fixture has no ``form`` and isn't seamless, so it imports as a one-shot;
    # keyed metadata always carries ``form`` (see test_drum_loop_fetch_says_key_lock_false).
    assert "slices=1" in result["hint"] and result["fit_note"].startswith("one-shot")

    info = sf.info(path)
    assert info.format == "FLAC" and info.subtype == "PCM_24"
    audio_saved, _ = sf.read(path, dtype="float32")
    assert np.max(np.abs(audio_saved)) == pytest.approx(10 ** (-1 / 20), abs=1e-4)

    credits = json.loads((kit_dir / "library" / "credits.json").read_text(encoding="utf-8"))
    credit = credits["soundza:" + SOUND_ID]
    assert credit["id"] == SOUND_ID
    assert credit["source"] == "soundza"
    assert credit["file"] == filename
    assert credit["title"] == "Jazz Drum Loop"
    assert credit["creator"] == "wet paper"
    assert credit["creator_url"] == "https://soundza.com/creators/wet-paper"
    assert credit["license"] == "soundza-standard"
    assert credit["license_url"] == "https://soundza.com/license"
    assert credit["landing_url"] == "https://soundza.com/sound/jazz-drum-loop"
    assert credit["attribution"] == DETAIL["attribution"]
    assert credit["bpm"] == 152 and credit["key"] is None
    assert credit["loop_seamless"] is False
    assert credit["variant"] == "original"
    assert credit["source_sha256"] == hashlib.sha256(audio).hexdigest()
    assert credit["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert credit["fetched"] == date.today().isoformat()
    assert credit["removed"] is False
    assert credit["file_host"] == "soundloft-packs.abc123.r2.cloudflarestorage.com"

    transport.requests.clear()
    again = soundza.fetch(SOUND_ID, kit_dir)
    assert again["source"] == result["source"]
    assert [urlsplit(request.full_url).path for request in transport.requests] == ["/v1/sounds/" + SOUND_ID]


def test_fetch_rejects_an_mp3_body(monkeypatch, tmp_path):
    monkeypatch.setenv("SOUNDZA_API_KEY", KEY)
    install(monkeypatch, audio=lossy_bytes("MP3"))

    with pytest.raises(ValidationError, match="not lossless"):
        soundza.fetch(SOUND_ID, tmp_path / "kit")
    assert not (tmp_path / "kit" / "library" / "152bpm-nokey-jazz-drum-loop-szcmtlty4j.flac").exists()


def test_fetch_rejects_an_ogg_body(monkeypatch, tmp_path):
    monkeypatch.setenv("SOUNDZA_API_KEY", KEY)
    install(monkeypatch, audio=lossy_bytes("OGG"))

    with pytest.raises(ValidationError, match="lossy"):
        soundza.fetch(SOUND_ID, tmp_path / "kit")


def test_fetch_rejects_a_lossy_extension_before_downloading(monkeypatch, tmp_path):
    monkeypatch.setenv("SOUNDZA_API_KEY", KEY)
    calls = install(monkeypatch, detail={**DETAIL, "file_extension": "mp3"})

    with pytest.raises(ValidationError, match="not lossless"):
        soundza.fetch(SOUND_ID, tmp_path / "kit")
    assert not any(urlsplit(call["url"]).path.endswith("/file") for call in calls)


def test_fetch_rejects_a_file_longer_than_sixty_seconds(monkeypatch, tmp_path):
    monkeypatch.setenv("SOUNDZA_API_KEY", KEY)
    install(monkeypatch, detail={**DETAIL, "duration": 60},
            audio=audio_bytes(seconds=61))

    with pytest.raises(ValidationError) as error:
        soundza.fetch(SOUND_ID, tmp_path / "kit")

    assert "longer than 60 seconds" in str(error.value)
    assert not list((tmp_path / "kit").rglob("*.flac"))


def test_fetch_rejects_a_declared_duration_over_sixty_seconds(monkeypatch, tmp_path):
    monkeypatch.setenv("SOUNDZA_API_KEY", KEY)
    calls = install(monkeypatch, detail={**DETAIL, "duration": 61})

    with pytest.raises(ValidationError, match="longer than 60 seconds"):
        soundza.fetch(SOUND_ID, tmp_path / "kit")
    assert not any(urlsplit(call["url"]).path.endswith("/file") for call in calls)


def test_fetch_enforces_the_twenty_megabyte_cap(monkeypatch, tmp_path):
    monkeypatch.setenv("SOUNDZA_API_KEY", KEY)
    page = Page(STORAGE, b"should not read", headers={"Content-Length": str(20 * 1024 * 1024 + 1)})

    def fake_http_get(url, *, timeout, bearer=None):
        if "/removals" in url:
            return Page(url, json.dumps({"since": "2026-01-01", "removals": [], "next_page": None}).encode())
        if url.endswith("/file?variant=original"):
            return page
        return Page(url, json.dumps(DETAIL).encode())

    monkeypatch.setattr(soundza, "_http_get", fake_http_get)
    with pytest.raises(ValidationError, match="20 MB"):
        soundza.fetch(SOUND_ID, tmp_path / "kit")
    assert page.read_calls == 0


def test_fetch_reports_a_rejected_key(monkeypatch, tmp_path):
    monkeypatch.setenv("SOUNDZA_API_KEY", KEY)

    def unauthorized(url):
        raise HTTPError(url, 401, "Unauthorized", {}, None)

    install(monkeypatch, error=unauthorized)
    with pytest.raises(ValidationError) as error:
        soundza.fetch(SOUND_ID, tmp_path / "kit")
    assert str(error.value) == "the Soundza key was rejected"


def test_search_reports_a_rate_limit_with_the_wait(monkeypatch):
    def limited(url):
        raise HTTPError(url, 429, "Too Many Requests", {"Retry-After": "7"}, None)

    install(monkeypatch, error=limited)
    with pytest.raises(ValidationError) as error:
        soundza.search("drum loop")
    assert str(error.value) == "Soundza rate limit; retry after 7 s"


def test_search_falls_back_to_the_reset_header_for_a_rate_limit(monkeypatch):
    def limited(url):
        raise HTTPError(url, 429, "Too Many Requests", {"X-RateLimit-Reset": "42"}, None)

    install(monkeypatch, error=limited)
    with pytest.raises(ValidationError) as error:
        soundza.search("drum loop")
    assert str(error.value) == "Soundza rate limit; retry after 42 s"


def test_network_failure_reads_like_the_openverse_one(monkeypatch):
    def offline(url):
        raise TimeoutError("network unavailable")

    install(monkeypatch, error=offline)
    with pytest.raises(ValidationError) as error:
        soundza.search("drum loop")
    assert str(error.value) == "Soundza is unavailable; check the connection and try again"
    assert "\n" not in str(error.value)


def write_credits(kit_dir, entries):
    library = Path(kit_dir) / "library"
    library.mkdir(parents=True, exist_ok=True)
    (library / "credits.json").write_text(json.dumps(entries), encoding="utf-8")
    return library


def live_credit(identifier, filename="jazz-drum-loop-cmtlty4j.flac", **extra):
    return {"soundza:" + identifier: {
        "id": identifier, "source": "soundza", "file": filename, "title": "T",
        "creator": "", "creator_url": "", "license": "soundza-standard",
        "license_url": "https://soundza.com/license", "landing_url": "",
        "attribution": "", "bpm": None, "key": None, "loop_seamless": False,
        "variant": "original", "source_sha256": "0" * 64, "sha256": "1" * 64,
        "fetched": "2026-11-01", "removed": False, "file_host": "files.abc123.r2.cloudflarestorage.com",
        **extra}}


def test_removals_delete_the_file_mark_the_credit_and_reach_the_result(monkeypatch, tmp_path):
    monkeypatch.setenv("SOUNDZA_API_KEY", KEY)
    library = write_credits(tmp_path / "kit", live_credit(SOUND_ID))
    (library / "jazz-drum-loop-cmtlty4j.flac").write_bytes(b"audio")
    calls = install(monkeypatch, sounds=LOOPS,
                    removals={"since": "2026-01-01", "next_page": None,
                              "removals": [{"id": SOUND_ID, "removed_at": "2026-11-09T00:00:00Z"}]})

    result = soundza.search("drum loop", kit_dir=tmp_path / "kit")

    assert isinstance(result, dict)
    assert result["removed"] == [SOUND_ID]
    assert result["results"] and all(hit["license"] == "soundza" for hit in result["results"])
    credits = json.loads((library / "credits.json").read_text(encoding="utf-8"))
    assert credits["soundza:" + SOUND_ID]["removed"] is True
    assert not (library / "jazz-drum-loop-cmtlty4j.flac").exists()
    record = json.loads((library / "soundza-removals.json").read_text(encoding="utf-8"))
    assert record["last_check"] == date.today().isoformat()
    assert record["removed"] == [SOUND_ID]
    assert any("/removals" in call["url"] for call in calls)

    calls.clear()
    again = soundza.search("drum loop", kit_dir=tmp_path / "kit")
    assert isinstance(again, list)
    assert not any("/removals" in call["url"] for call in calls)


def test_removals_failure_is_swallowed_and_retried(monkeypatch, tmp_path):
    monkeypatch.setenv("SOUNDZA_API_KEY", KEY)
    write_credits(tmp_path / "kit", live_credit(SOUND_ID))

    def flaky(url):
        if "/removals" in url:
            raise TimeoutError("removals down")

    calls = install(monkeypatch, sounds=LOOPS, error=flaky)

    hits = soundza.search("drum loop", kit_dir=tmp_path / "kit")

    assert isinstance(hits, list) and hits
    assert any("/removals" in call["url"] for call in calls)
    assert not (tmp_path / "kit" / "library" / "soundza-removals.json").exists()


def test_fetch_refuses_a_sound_soundza_has_removed(monkeypatch, tmp_path):
    monkeypatch.setenv("SOUNDZA_API_KEY", KEY)
    library = write_credits(tmp_path / "kit", live_credit(SOUND_ID))
    calls = install(monkeypatch, removals={"since": "2026-01-01", "next_page": None,
                                           "removals": [{"id": SOUND_ID, "removed_at": "x"}]})

    with pytest.raises(ValidationError, match="removed this sound"):
        soundza.fetch(SOUND_ID, tmp_path / "kit")
    assert not any("/file" in call["url"] for call in calls)
    assert (library / "soundza-removals.json").exists()


def test_fetch_refuses_at_five_hundred_live_soundza_entries(monkeypatch, tmp_path):
    monkeypatch.setenv("SOUNDZA_API_KEY", KEY)
    entries = {}
    for index in range(500):
        entries.update(live_credit(f"cmsf4atna000604jla{index:05d}"))
    write_credits(tmp_path / "kit", entries)
    calls = install(monkeypatch)

    with pytest.raises(ValidationError, match="500"):
        soundza.fetch(SOUND_ID, tmp_path / "kit")
    assert not any(call["url"].startswith(API + "/sounds/") for call in calls)


def test_the_key_never_appears_in_results_or_errors(monkeypatch, tmp_path):
    monkeypatch.setenv("SOUNDZA_API_KEY", KEY)
    seen = []

    install(monkeypatch, sounds=LOOPS)
    seen.append(json.dumps(soundza.search("drum loop", kit_dir=tmp_path / "kit"), ensure_ascii=False))

    def unauthorized(url):
        raise HTTPError(url, 401, "Unauthorized", {}, None)

    install(monkeypatch, error=unauthorized)
    for call in (lambda: soundza.search("drum loop"),
                 lambda: soundza.fetch(SOUND_ID, tmp_path / "kit")):
        with pytest.raises(ValidationError) as error:
            call()
        seen.append(str(error.value))

    page = Page(STORAGE, b"x", headers={"Content-Length": str(20 * 1024 * 1024 + 1)})

    def capped(url, *, timeout, bearer=None):
        if "/removals" in url:
            return Page(url, json.dumps({"since": "2026-01-01", "removals": [], "next_page": None}).encode())
        return page if url.endswith("/file?variant=original") else Page(url, json.dumps(DETAIL).encode())

    monkeypatch.setattr(soundza, "_http_get", capped)
    with pytest.raises(ValidationError) as error:
        soundza.fetch(SOUND_ID, tmp_path / "kit")
    seen.append(str(error.value))

    assert all(KEY not in text for text in seen)


def test_audio_requests_use_the_plain_user_agent_and_a_fifteen_second_timeout(monkeypatch):
    seen = {}

    class Opener:
        def open(self, request, timeout):
            seen["agent"] = request.get_header("User-agent")
            seen["timeout"] = timeout
            raise OSError("stop here")

    monkeypatch.setattr(soundza, "build_opener", lambda *handlers: Opener())
    with pytest.raises(OSError):
        soundza._http_get(API + "/sounds/search?q=x", timeout=15)
    assert seen["agent"].startswith("Rookery/")
    assert "urllib" not in seen["agent"].lower()
    assert seen["timeout"] == 15


def test_api_urls_outside_the_allowlist_are_refused():
    for url in ("http://api.soundza.com/v1/sounds/search",
                "https://api.soundza.com.evil.example/v1/sounds/search",
                "https://user:pass@api.soundza.com/v1/sounds/search",
                "https://api.soundza.com:8443/v1/sounds/search"):
        with pytest.raises(ValidationError, match="api.soundza.com"):
            soundza._validate_api_url(url)


def test_a_second_redirect_is_refused():
    handler = soundza._SoundzaRedirectHandler()
    from urllib.request import Request

    with pytest.raises(ValidationError, match="more than once"):
        handler.redirect_request(Request("https://files.abc123.r2.cloudflarestorage.com/one"), None, 302, "Found", {},
                                 "https://files.abc123.r2.cloudflarestorage.com/two")


def test_removals_respect_the_seven_day_window(monkeypatch, tmp_path):
    monkeypatch.setenv("SOUNDZA_API_KEY", KEY)
    library = write_credits(tmp_path / "kit", {})
    record = library / "soundza-removals.json"
    calls = install(monkeypatch, sounds=LOOPS)

    record.write_text(json.dumps({"last_check": (date.today() - timedelta(days=6)).isoformat(),
                                  "removed": []}), encoding="utf-8")
    soundza.search("drum loop", kit_dir=tmp_path / "kit")
    assert not any("/removals" in call["url"] for call in calls)

    record.write_text(json.dumps({"last_check": (date.today() - timedelta(days=8)).isoformat(),
                                  "removed": []}), encoding="utf-8")
    calls.clear()
    soundza.search("drum loop", kit_dir=tmp_path / "kit")
    assert any("/removals" in call["url"] for call in calls)
    assert json.loads(record.read_text(encoding="utf-8"))["last_check"] == date.today().isoformat()


# --- Review fixes (Claude, after the live probe on 2026-11-10) -----------------------------

def test_storage_hop_is_pinned_to_soundzas_r2_host():
    soundza._validate_storage_url("https://soundloft-packs.8557d7ae.r2.cloudflarestorage.com/sounds/x.wav?sig=1")
    for bad in ("https://evil.example/sounds/x.wav", "https://r2.cloudflarestorage.com/x",
                "https://r2.cloudflarestorage.com.evil.example/x", "http://a.r2.cloudflarestorage.com/x",
                "https://user:pw@a.r2.cloudflarestorage.com/x", "https://a.r2.cloudflarestorage.com:8443/x"):
        with pytest.raises(ValidationError):
            soundza._validate_storage_url(bad)


def test_api_answers_must_come_from_the_api_host(monkeypatch):
    def fake_http_get(url, *, timeout, bearer=None):
        return Page("https://soundloft-packs.abc123.r2.cloudflarestorage.com/search.json", b'{"sounds": []}')

    monkeypatch.setattr(soundza, "_http_get", fake_http_get)
    with pytest.raises(ValidationError, match="api.soundza.com"):
        soundza.search("drums")


def test_filenames_carry_soundza_tempo_and_key_for_render():
    from rookery.sampling import parse_title, _NOKEY_RE
    keyed = soundza._filename("Skipit Horns", "cmudkgpuo000409gmjonfn7qq",
                              {"bpm": 86, "key": "D minor", "tags": ["brass"]})
    drums = soundza._filename("Bratz Drums", "cm5dkggd8000d0agmnhk4gm47",
                              {"bpm": 90, "key": None, "tags": ["kick", "snare"]})
    unknown = soundza._filename("Mystery Pad", "cmudkggd8000d0agmnhk4gm47",
                                {"bpm": 75.5, "key": None, "tags": ["pad"]})
    assert keyed == "86bpm-Dmin-skipit-horns-szcmudkgpu.flac"
    assert parse_title(keyed) == {"bpm": 86, "key": "D minor"}
    assert drums == "90bpm-nokey-bratz-drums-szcm5dkggd.flac"
    assert parse_title(drums)["key"] is None and _NOKEY_RE.search(drums)  # "cm5" never reads as C minor
    assert unknown == "mystery-pad-szcmudkggd.flac" and not _NOKEY_RE.search(unknown)


def test_drum_loop_fetch_says_key_lock_false(monkeypatch, tmp_path):
    monkeypatch.setenv("SOUNDZA_API_KEY", KEY)
    rate = 44100
    seconds = 4 * 4 * 60 / 90  # exactly 4 bars at 90 BPM
    count = round(seconds * rate)
    rng = np.random.default_rng(3)
    audio = np.zeros(count)
    for beat in range(16):
        start = round(beat * rate * 60 / 90)
        hit = rng.standard_normal(4000) * np.exp(-np.arange(4000) / 600)
        audio[start:start + 4000] += hit
    audio = (audio / np.max(np.abs(audio)) * .8).astype(np.float32)
    buffer = io.BytesIO()
    sf.write(buffer, audio, rate, format="WAV", subtype="PCM_16")
    detail = dict(DETAIL, title="Bratz Drums", bpm=90, key=None, form="loop", loop_seamless=True,
                  tags=["kick", "snare", "loop"], duration=round(seconds, 2), file_extension="wav")
    install(monkeypatch, detail=detail, audio=buffer.getvalue())

    result = soundza.fetch(SOUND_ID, tmp_path / "kit", 90, "D minor")

    assert "-nokey-" in result["source"] and result["source"].startswith("user:library/90bpm-")
    assert "key_lock=false" in result["hint"] and "mode=loop" in result["hint"]
    assert result["analysis"]["key"] is None and result["analysis"]["bars"] == 4
    assert result["quality"]["verdict"] in {"pass", "flag"}


def test_fetch_reports_key_lock_shift_and_warns_for_large_transpose(monkeypatch, tmp_path):
    monkeypatch.setenv("SOUNDZA_API_KEY", KEY)
    bpm = 90
    seconds = 4 * 4 * 60 / bpm
    rng = np.random.default_rng(41)
    audio = rng.standard_normal(round(seconds * 44100)).astype(np.float32)
    audio = (audio / np.max(np.abs(audio)) * .45).astype(np.float32)
    buffer = io.BytesIO()
    sf.write(buffer, audio, 44100, format="WAV", subtype="PCM_16")
    detail = dict(DETAIL, title="Pitched Loop", bpm=bpm, key="C major", form="loop",
                  loop_seamless=True, duration=seconds, file_extension="wav")
    install(monkeypatch, detail=detail, audio=buffer.getvalue())
    from rookery import sampling
    monkeypatch.setattr(sampling, "analyze", lambda *_args, **_kwargs: {
        "bpm": bpm, "key": "C major", "bpm_source": "title", "key_source": "title",
        "downbeat_s": 0.0, "bars": 4, "confidence": .9,
        "profile": {"register": "mid", "centroid_hz": 1200.0, "bands": [0, 0, 1, 0],
                    "rhythm": "9000900090009000", "density": 4.0, "busy_steps": 4,
                    "sustain": .2, "pitched": True, "role_hint": "lead"},
    })

    result = soundza.fetch(SOUND_ID, tmp_path / "kit", bpm, "F#", "major")

    assert result["key_lock_shift_semitones"] == -6
    assert "Key lock shift: -6 semitones" in result["fit_note"]
    assert "prefer another hit" in result["fit_note"]


def test_a_soundza_file_below_the_quality_gate_is_not_imported(monkeypatch, tmp_path):
    monkeypatch.setenv("SOUNDZA_API_KEY", KEY)
    install(monkeypatch, audio=audio_bytes(seconds=1, sample_rate=22050))
    with pytest.raises(ValidationError, match="quality gate.*22.05 kHz"):
        soundza.fetch(SOUND_ID, tmp_path / "kit")
    assert not list((tmp_path / "kit").rglob("*.flac"))
    credits = tmp_path / "kit" / "library" / "credits.json"
    assert not credits.exists() or "soundza:" + SOUND_ID not in json.loads(credits.read_text(encoding="utf-8"))
