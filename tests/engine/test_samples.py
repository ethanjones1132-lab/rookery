import io
import json
from urllib.parse import parse_qs, urlsplit

import numpy as np
import pytest
import soundfile as sf

from rookery import samples
from rookery.project import ValidationError
from rookery.service import Service


OPENVERSE = "https://api.openverse.org/v1/audio/"
PREVIEW = "https://cdn.freesound.org/previews/123/123456_1-hq.mp3"
SAMPLE_ID = "12345678-1234-1234-1234-123456789abc"


class FakeResponse:
    def __init__(self, url, body=b"", *, status=200, headers=None):
        self.url = url
        self.body = body
        self.status = status
        self.headers = headers or {}
        self.read_calls = 0

    def read(self, size=-1):
        self.read_calls += 1
        return self.body if size < 0 else self.body[:size]

    def geturl(self):
        return self.url

    def close(self):
        pass


def audio_bytes(seconds=1.0, sample_rate=8000, peak=0.2):
    audio = np.full((round(seconds * sample_rate),), peak, dtype=np.float32)
    buffer = io.BytesIO()
    sf.write(buffer, audio, sample_rate, format="WAV")
    return buffer.getvalue()


def detail(*, url=PREVIEW, license="cc0", title="Vinyl crackle", creator="Sample maker"):
    return {
        "id": SAMPLE_ID,
        "title": title,
        "creator": creator,
        "license": license,
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "foreign_landing_url": "https://freesound.org/people/example/sounds/123456/",
        "url": url,
        "duration": 1200,
        "filetype": "mp3",
        "tags": ["vinyl", "crackle", "noise", "record", "dust", "extra"],
    }


def install_fake(monkeypatch, *, audio=None, item=None, audio_headers=None):
    item = item or detail()
    audio = audio if audio is not None else audio_bytes()
    calls = []

    def fake_http_get(url, *, timeout):
        calls.append((url, timeout))
        if url.startswith(OPENVERSE):
            if urlsplit(url).path.rstrip("/") == "/v1/audio":
                payload = {"results": [item]}
            else:
                payload = item
            return FakeResponse(url, json.dumps(payload).encode())
        if url == item["url"]:
            return FakeResponse(url, audio, headers=audio_headers)
        raise AssertionError(f"unexpected HTTP request: {url}")

    monkeypatch.setattr(samples, "_http_get", fake_http_get)
    return calls


def test_search_queries_openverse_for_cc0_and_returns_compact_hits(monkeypatch):
    calls = install_fake(monkeypatch)

    hits = samples.search("vinyl crackle", kind="texture", max_seconds=4, limit=3)

    params = parse_qs(urlsplit(calls[0][0]).query)
    assert params["q"] == ["vinyl crackle texture"]
    assert params["license"] == ["cc0"]
    assert hits[0]["id"] == SAMPLE_ID
    assert hits[0]["license"] == "cc0"
    assert len(hits[0]["tags"]) <= 5
    assert len(json.dumps(hits[0], separators=(",", ":")).encode()) < 150


def test_search_filters_duration_and_non_cc0_results(monkeypatch):
    item = detail()
    other = {**detail(), "id": "87654321-1234-1234-1234-123456789abc", "duration": 5000}
    unlicensed = {**detail(), "id": "abcdefab-1234-1234-1234-123456789abc", "license": "by"}

    def fake_http_get(url, *, timeout):
        return FakeResponse(url, json.dumps({"results": [item, other, unlicensed]}).encode())

    monkeypatch.setattr(samples, "_http_get", fake_http_get)
    assert [hit["id"] for hit in samples.search("crackle", max_seconds=2)] == [SAMPLE_ID]


def test_fetch_rejects_audio_urls_outside_allowlist(monkeypatch, tmp_path):
    calls = install_fake(monkeypatch, item=detail(url="https://evil.example/audio.wav"))

    with pytest.raises(ValidationError, match="allowlisted host"):
        samples.fetch(SAMPLE_ID, tmp_path / "kit")

    assert len(calls) == 1


def test_fetch_enforces_twenty_megabyte_download_cap(monkeypatch, tmp_path):
    response = FakeResponse(PREVIEW, b"should not read", headers={"Content-Length": str(20 * 1024 * 1024 + 1)})
    calls = []

    def fake_http_get(url, *, timeout):
        calls.append(url)
        if url.startswith(OPENVERSE):
            return FakeResponse(url, json.dumps(detail()).encode())
        return response

    monkeypatch.setattr(samples, "_http_get", fake_http_get)
    with pytest.raises(ValidationError, match="20 MB"):
        samples.fetch(SAMPLE_ID, tmp_path / "kit")
    assert response.read_calls == 0


def test_fetch_trims_to_thirty_seconds_and_peak_normalizes_flac(monkeypatch, tmp_path):
    install_fake(monkeypatch, audio=audio_bytes(seconds=35, sample_rate=8000, peak=0.2))

    result = samples.fetch(SAMPLE_ID, tmp_path / "kit")
    path = tmp_path / "kit" / "library" / result["source"].split("/")[-1]
    audio, sample_rate = sf.read(path, dtype="float32", always_2d=True)

    assert result["seconds"] == pytest.approx(30)
    assert len(audio) == 30 * sample_rate
    assert np.max(np.abs(audio)) == pytest.approx(10 ** (-1 / 20), abs=1e-4)
    assert path.suffix == ".flac"


def test_fetched_flac_renders_through_a_sample_track(monkeypatch, tmp_path):
    kit_dir = tmp_path / "kit"
    install_fake(monkeypatch, audio=audio_bytes(seconds=0.25))
    result = samples.fetch(SAMPLE_ID, kit_dir)
    service = Service(tmp_path / "data", user_kit_dir=kit_dir)
    service.new("sample-beat", 90, bars=4)
    service.edit({"name": "sample-beat", "op": "track", "action": "add", "id": "chop",
                  "kind": "sample", "source": result["source"], "steps": "x"})

    rendered = service.render("sample-beat")

    assert rendered["duration_samples"] == 44100 * 4 * 4 * 60 // 90
    assert rendered["wav_hash"]


def test_fetch_records_credit_and_state_shows_only_matched_library_credit(monkeypatch, tmp_path):
    kit_dir = tmp_path / "kit"
    install_fake(monkeypatch)
    result = samples.fetch(SAMPLE_ID, kit_dir)
    credits = json.loads((kit_dir / "library" / "credits.json").read_text())
    assert credits[SAMPLE_ID]["title"] == "Vinyl crackle"
    assert credits[SAMPLE_ID]["creator"] == "Sample maker"
    assert credits[SAMPLE_ID]["license"] == "cc0"
    assert credits[SAMPLE_ID]["license_url"].startswith("https://")
    assert credits[SAMPLE_ID]["landing_url"].startswith("https://")

    service = Service(tmp_path / "data", user_kit_dir=kit_dir)
    service.new("credits", 90, bars=4)
    service.edit({"name": "credits", "op": "track", "action": "add", "id": "credited",
                  "kind": "sample", "source": result["source"]})
    service.edit({"name": "credits", "op": "track", "action": "add", "id": "uncredited",
                  "kind": "sample", "source": "user:other.flac"})

    state = service.state("credits")

    assert state.endswith("Credits: Vinyl crackle — Sample maker (cc0; "
                          "https://creativecommons.org/publicdomain/zero/1.0/; "
                          "https://freesound.org/people/example/sounds/123456/)")
    assert state.count("Credits:") == 1


def test_fetch_same_id_reuses_audio_file(monkeypatch, tmp_path):
    calls = install_fake(monkeypatch)
    kit_dir = tmp_path / "kit"

    first = samples.fetch(SAMPLE_ID, kit_dir)
    audio_calls_before = sum(url == PREVIEW for url, _ in calls)
    second = samples.fetch(SAMPLE_ID, kit_dir)

    assert second["source"] == first["source"]
    assert sum(url == PREVIEW for url, _ in calls) == audio_calls_before == 1


def test_fetch_rejects_non_cc0_metadata(monkeypatch, tmp_path):
    install_fake(monkeypatch, item=detail(license="by"))

    with pytest.raises(ValidationError, match="CC0"):
        samples.fetch(SAMPLE_ID, tmp_path / "kit")


def test_search_reports_offline_error_as_one_validation_line(monkeypatch):
    def offline(*args, **kwargs):
        raise TimeoutError("network unavailable")

    monkeypatch.setattr(samples, "_http_get", offline)
    with pytest.raises(ValidationError) as error:
        samples.search("vinyl crackle")
    assert str(error.value) == "Openverse is unavailable; check the connection and try again"
    assert "\n" not in str(error.value)


def test_requests_send_a_plain_user_agent(monkeypatch):
    # Openverse answers 403 to urllib's default User-Agent (seen live 2026-11-09).
    seen = {}

    class Opener:
        def open(self, request, timeout):
            seen["agent"] = request.get_header("User-agent")
            seen["timeout"] = timeout
            raise OSError("stop here")

    monkeypatch.setattr(samples, "build_opener", lambda *handlers: Opener())
    with pytest.raises(OSError):
        samples._http_get("https://api.openverse.org/v1/audio/?q=x", timeout=15)
    assert seen["agent"].startswith("Rookery/")
    assert "urllib" not in seen["agent"].lower()


def test_search_reads_openverse_tag_objects(monkeypatch):
    # Openverse sends tags as objects ({"name": ...}), not strings.
    item = {"id": "abc12345", "title": "Crackle", "creator": "x", "license": "cc0", "duration": 2000,
            "tags": [{"name": "vinyl", "accuracy": None}, {"name": "dust"}]}
    monkeypatch.setattr(samples, "_json_response", lambda url: {"results": [item]})
    assert samples.search("crackle")[0]["tags"] == ["vinyl", "dust"]


def test_search_routes_to_soundza_with_the_project_fit_fields(monkeypatch):
    from rookery import soundza
    seen = {}

    def fake_search(query, **kwargs):
        seen["query"] = query
        seen.update(kwargs)
        return [{"id": "cmudkglv2000009gmgye7860e", "license": "soundza"}]

    monkeypatch.setattr(soundza, "search", fake_search)
    hits = samples.search("lofi keys", kind="loop", max_seconds=20, limit=3,
                          bpm=86, key="D minor", source="soundza", kit_dir="kit")

    assert hits[0]["license"] == "soundza"
    assert seen == {"query": "lofi keys", "kind": "loop", "max_seconds": 20, "limit": 3,
                    "bpm": 86, "key": "D minor", "kit_dir": "kit"}


def test_fetch_routes_to_soundza(monkeypatch, tmp_path):
    from rookery import soundza
    seen = {}

    def fake_fetch(identifier, kit_dir, bpm=None, key=None, project_scale="major"):
        seen.update(identifier=identifier, kit_dir=kit_dir, bpm=bpm, key=key,
                    project_scale=project_scale)
        return {"source": "user:library/x.flac", "credit": {}}

    monkeypatch.setattr(soundza, "fetch", fake_fetch)
    result = samples.fetch("cmudkglv2000009gmgye7860e", tmp_path, 86, "D minor", source="soundza")

    assert result["source"].startswith("user:library/")
    assert seen == {"identifier": "cmudkglv2000009gmgye7860e", "kit_dir": tmp_path,
                    "bpm": 86, "key": "D minor", "project_scale": "major"}


def test_unknown_sample_source_is_refused(tmp_path):
    with pytest.raises(ValidationError, match="soundza.*openverse"):
        samples.search("crackle", source="freesound")
    with pytest.raises(ValidationError, match="soundza.*openverse"):
        samples.fetch("1234", tmp_path, source="freesound")


def test_rookery_samples_tool_defaults_to_soundza_and_offers_openverse():
    from rookery.tools import SCHEMAS

    properties = SCHEMAS["rookery_samples"]["parameters"]["properties"]
    assert properties["source"]["enum"] == ["soundza", "openverse"]
    assert properties["source"]["default"] == "soundza"
    assert set(SCHEMAS["rookery_samples"]["parameters"]["required"]) == {"action"}
