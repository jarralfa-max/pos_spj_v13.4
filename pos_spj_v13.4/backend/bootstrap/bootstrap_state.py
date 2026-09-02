"""BootstrapState — SHELL-3 §7 state list, verbatim.

Not every state is reachable yet: COMPOSITION_BUILDING/COMPOSITION_READY
(SHELL-5), AUTHENTICATION_READY (SHELL-7), SHELL_READY (SHELL-11),
BACKGROUND_SERVICES_STARTING (SHELL-14) belong to steps that don't exist
yet. `DesktopApplicationBootstrapper` only ever reaches as far as the last
state whose step is actually registered; RUNNING is used today as "every
registered step succeeded," and will be reinterpreted as "all phases
including the shell are up" once those steps land.
"""
from __future__ import annotations

from enum import Enum


class BootstrapState(str, Enum):
    CREATED = "CREATED"
    ENVIRONMENT_VALIDATING = "ENVIRONMENT_VALIDATING"
    INSTANCE_LOCKING = "INSTANCE_LOCKING"
    LOGGING_READY = "LOGGING_READY"
    PATHS_READY = "PATHS_READY"
    DATABASE_CHECKING = "DATABASE_CHECKING"
    DATABASE_READY = "DATABASE_READY"
    SCHEMA_VALIDATED = "SCHEMA_VALIDATED"
    COMPOSITION_BUILDING = "COMPOSITION_BUILDING"
    COMPOSITION_READY = "COMPOSITION_READY"
    INSTALLATION_RESOLVING = "INSTALLATION_RESOLVING"
    AUTHENTICATION_READY = "AUTHENTICATION_READY"
    SHELL_READY = "SHELL_READY"
    BACKGROUND_SERVICES_STARTING = "BACKGROUND_SERVICES_STARTING"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
