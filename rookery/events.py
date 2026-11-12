"""Optional Hermes plugin events with a safe no-op fallback."""

from __future__ import annotations

import logging
import sys
import threading
from contextlib import contextmanager
from typing import Any, Callable, Iterator

_LOGGER = logging.getLogger(__name__)

# Tests and embedders can install a publisher without importing Hermes.
publisher: Callable[[str, str, dict[str, Any]], Any] | None = None
_COUNTS: dict[str, int] = {}
# Reentrant so a publisher may query or nest editing() on the same thread while
# a transition is being emitted; transitions for a name stay ordered.
_COUNTS_LOCK = threading.RLock()
# One WARNING per detached episode: a broken publisher must be visible in the
# log without one traceback per edit. A delivered event re-arms it.
_DETACHED_WARNED = False


def emit(event: str, payload: dict[str, Any]) -> None:
    """Publish a Rookery event if Hermes is available; otherwise do nothing."""
    global _DETACHED_WARNED
    target = publisher
    if target is None and "tui_gateway.server" not in sys.modules:
        # No live gateway in this process (a CLI tool run, tests, a plugin-only host): nobody to deliver to.
        # Importing the gateway here would pull in Hermes's process bootstrap, which can relaunch the process.
        _LOGGER.debug("Rookery event %s not broadcast: no gateway in this process", event)
        return
    try:
        if target is None:
            from hermes_cli.plugin_events import broadcast_plugin_event
            target = broadcast_plugin_event
        target("rookery", event, payload)
    except Exception:
        with _COUNTS_LOCK:
            first = not _DETACHED_WARNED
            _DETACHED_WARNED = True
        if first:
            _LOGGER.warning(
                "Rookery UI events cannot reach the page (%s): the event publisher failed, so the "
                "page will only update by polling until it recovers",
                event, exc_info=True,
            )
        else:
            _LOGGER.debug("Rookery event publisher unavailable for %s", event, exc_info=True)
    else:
        with _COUNTS_LOCK:
            _DETACHED_WARNED = False


def is_editing(name: str) -> bool:
    with _COUNTS_LOCK:
        return _COUNTS.get(name, 0) > 0


def _emit_state(name: str, editing_state: bool) -> None:
    try:
        emit("agent.editing", {"name": name, "editing": editing_state})
    except Exception:
        # A publisher failure must never strand the in-memory editing count.
        _LOGGER.debug("Rookery editing event publisher unavailable for %s", name, exc_info=True)


@contextmanager
def editing(name: str) -> Iterator[None]:
    """Emit editing state at overlap-safe 0→1 and 1→0 transitions."""
    if not isinstance(name, str) or not name:
        raise ValueError("editing project name must be a non-empty string")
    with _COUNTS_LOCK:
        count = _COUNTS.get(name, 0)
        _COUNTS[name] = count + 1
        if count == 0:
            try:
                _emit_state(name, True)
            except BaseException:
                if _COUNTS.get(name) == 1:
                    _COUNTS.pop(name, None)
                else:
                    _COUNTS[name] -= 1
                raise
    try:
        yield
    finally:
        with _COUNTS_LOCK:
            count = _COUNTS.get(name, 0)
            if count <= 1:
                _COUNTS.pop(name, None)
                _emit_state(name, False)
            else:
                _COUNTS[name] = count - 1


__all__ = ["emit", "editing", "is_editing", "publisher"]
