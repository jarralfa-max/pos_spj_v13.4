"""BackgroundService — SHELL-14.

The pluggable "what does running a background service actually do" port
`BackgroundServiceSupervisor` calls through — the same abstraction shape as
SHELL-13's `ModuleActivator`. `start()`/`stop()` are synchronous from the
supervisor's point of view; whether a concrete implementation spins up a
real `QThread`, a `QTimer`-driven poller, or something else entirely is
its own business. `stop()` must be safe to call on a service that was
never started or already stopped (idempotent) — the supervisor may call
it during teardown without first checking state.

A service that crashes *after* `start()` already returned (e.g. its
internal thread dies later) has no way to signal that through this
Protocol alone — it's expected to hold a reference to the supervisor (or a
callback closing over it) and call `supervisor.notify_crashed(service_id, error)`
itself. This Protocol only covers "make it go"/"make it stop," not an
ongoing health channel — reporting is push, not poll, matching how a real
crash is actually discovered (an exception/signal, not a timer).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class BackgroundService(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
