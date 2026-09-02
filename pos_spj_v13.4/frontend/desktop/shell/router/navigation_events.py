"""Canonical navigation event names — SHELL-10.

Same audit/event-publishing pattern as `ApplicationContextService`
(SHELL-6, `application_context_events.py`): a plain string catalog, emitted
through an injected callable rather than a hard EventBus dependency.
"""
from __future__ import annotations

NAVIGATION_REQUESTED = "NAVIGATION_REQUESTED"
NAVIGATION_SUCCEEDED = "NAVIGATION_SUCCEEDED"
NAVIGATION_DENIED = "NAVIGATION_DENIED"
NAVIGATION_BACK = "NAVIGATION_BACK"
NAVIGATION_FORWARD = "NAVIGATION_FORWARD"
