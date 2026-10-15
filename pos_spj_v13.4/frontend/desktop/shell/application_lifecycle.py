"""Process-level hand-over from the running desktop to the external updater.

Only `frontend/desktop/app.py` knows how to close the application cleanly
(background services, database connections, instance lock, Qt event loop),
so it registers the hand-over here once; the Configuración page and the
maintenance-window trigger only REQUEST it with the `LaunchRequest` their use
case returned.
"""
from __future__ import annotations

from typing import Callable

_handoff: Callable[[object], bool] | None = None


def set_update_handoff(handler: Callable[[object], bool] | None) -> None:
    global _handoff
    _handoff = handler


def request_update_handoff(launch_request) -> bool:
    """True when the desktop is closing to install. False when no host
    registered a hand-over (tests, embedded hosts) or it was refused."""
    if _handoff is None:
        return False
    return bool(_handoff(launch_request))
