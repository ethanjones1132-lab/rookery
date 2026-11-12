"""The event bridge: a detached UI must be visible in the log, once."""

import logging

import pytest

from rookery import events


@pytest.fixture(autouse=True)
def reset_events(monkeypatch):
    old_publisher = events.publisher
    monkeypatch.setattr(events, "_DETACHED_WARNED", False)
    yield
    events.publisher = old_publisher


def warnings(caplog):
    return [record for record in caplog.records if record.levelno == logging.WARNING]


def test_a_dropped_event_warns_once_not_per_event(caplog):
    attempts = []

    def broken_publisher(_plugin, _event, _payload):
        attempts.append(1)
        raise RuntimeError("no tui_gateway in this process")

    events.publisher = broken_publisher

    with caplog.at_level(logging.WARNING, logger=events.__name__):
        events.emit("project.updated", {"name": "beat", "rev": 2})
        events.emit("project.updated", {"name": "beat", "rev": 3})
        events.emit("render.done", {"name": "beat"})

    assert len(attempts) == 3
    caught = warnings(caplog)
    assert len(caught) == 1
    assert "cannot reach the page" in caught[0].getMessage()
    assert caught[0].exc_info is not None


def test_a_delivered_event_rearms_the_warning(caplog):
    broken = {"on": True}

    def flaky_publisher(_plugin, _event, _payload):
        if broken["on"]:
            raise RuntimeError("publisher unavailable")

    events.publisher = flaky_publisher

    with caplog.at_level(logging.WARNING, logger=events.__name__):
        events.emit("project.updated", {})
        broken["on"] = False
        events.emit("project.updated", {})
        broken["on"] = True
        events.emit("project.updated", {})

    assert len(warnings(caplog)) == 2


def test_editing_state_survives_a_dead_publisher():
    def broken_publisher(_plugin, _event, _payload):
        raise RuntimeError("publisher unavailable")

    events.publisher = broken_publisher

    with events.editing("beat"):
        assert events.is_editing("beat") is True
    assert events.is_editing("beat") is False



def test_emit_without_a_gateway_in_process_never_imports_the_gateway(monkeypatch):
    import builtins
    import sys

    from rookery import events

    monkeypatch.setattr(events, "publisher", None)
    monkeypatch.delitem(sys.modules, "tui_gateway.server", raising=False)
    real_import = builtins.__import__
    imported = []

    def spy(name, *args, **kwargs):
        if name.startswith(("hermes_cli.plugin_events", "tui_gateway")):
            imported.append(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", spy)
    events.emit("project.updated", {"name": "beat", "rev": 1})
    assert imported == []
