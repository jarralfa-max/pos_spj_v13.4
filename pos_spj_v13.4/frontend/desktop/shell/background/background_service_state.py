"""BackgroundServiceState — SHELL-14."""
from __future__ import annotations

from enum import Enum


class BackgroundServiceState(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    CRASHED = "CRASHED"
    RESTARTING = "RESTARTING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"
