"""Bootstrap failure classification — SHELL-3.

Encodes the master refactor plan's §9 taxonomy as executable code instead of
leaving it to each step's judgment: a step picks a `BootstrapFailureReason`,
and `severity_for()` — not the step — decides whether that reason is FATAL,
DEGRADED, or WARNING. This is what makes "no convertir una excepción de
migración crítica en warning" structural rather than a convention someone
can quietly violate in one step's `except` block.
"""
from __future__ import annotations

from enum import Enum


class BootstrapSeverity(str, Enum):
    FATAL = "FATAL"
    DEGRADED = "DEGRADED"
    WARNING = "WARNING"
    INFO = "INFO"  # no problem — a successful step reports this


class BootstrapFailureReason(str, Enum):
    # ── Fatal — must stop the boot (§9 "Fatal") ─────────────────────────────
    DATABASE_CORRUPTED_UNRECOVERABLE = "DATABASE_CORRUPTED_UNRECOVERABLE"
    SCHEMA_INCOMPLETE = "SCHEMA_INCOMPLETE"
    IDENTITY_NOT_UUIDV7 = "IDENTITY_NOT_UUIDV7"
    BOOTSTRAP_INVALID = "BOOTSTRAP_INVALID"
    REQUIRED_DEPENDENCY_MISSING = "REQUIRED_DEPENDENCY_MISSING"
    DEPENDENCY_GRAPH_INVALID = "DEPENDENCY_GRAPH_INVALID"
    INSTALLATION_LOCKED = "INSTALLATION_LOCKED"
    CRITICAL_CONFIGURATION_MISSING = "CRITICAL_CONFIGURATION_MISSING"

    # ── Degraded — an optional capability is unavailable (§9 "Degradado") ──
    WHATSAPP_UNAVAILABLE = "WHATSAPP_UNAVAILABLE"
    PRINTER_DISCONNECTED = "PRINTER_DISCONNECTED"
    GEOCODING_UNAVAILABLE = "GEOCODING_UNAVAILABLE"
    UPDATE_CHECKER_FAILED = "UPDATE_CHECKER_FAILED"
    OPTIONAL_INTEGRATION_INACTIVE = "OPTIONAL_INTEGRATION_INACTIVE"

    # ── Warning — non-blocking, worth surfacing (§9 "Advertencia") ─────────
    BACKUP_OVERDUE = "BACKUP_OVERDUE"
    OPTIONAL_DEVICE_DISCONNECTED = "OPTIONAL_DEVICE_DISCONNECTED"
    CAMPAIGN_NOT_SYNCED = "CAMPAIGN_NOT_SYNCED"
    SECONDARY_SERVICE_PAUSED = "SECONDARY_SERVICE_PAUSED"
    SCHEMA_COVERAGE_INCOMPLETE = "SCHEMA_COVERAGE_INCOMPLETE"


_FATAL_REASONS = frozenset({
    BootstrapFailureReason.DATABASE_CORRUPTED_UNRECOVERABLE,
    BootstrapFailureReason.SCHEMA_INCOMPLETE,
    BootstrapFailureReason.IDENTITY_NOT_UUIDV7,
    BootstrapFailureReason.BOOTSTRAP_INVALID,
    BootstrapFailureReason.REQUIRED_DEPENDENCY_MISSING,
    BootstrapFailureReason.DEPENDENCY_GRAPH_INVALID,
    BootstrapFailureReason.INSTALLATION_LOCKED,
    BootstrapFailureReason.CRITICAL_CONFIGURATION_MISSING,
})

_DEGRADED_REASONS = frozenset({
    BootstrapFailureReason.WHATSAPP_UNAVAILABLE,
    BootstrapFailureReason.PRINTER_DISCONNECTED,
    BootstrapFailureReason.GEOCODING_UNAVAILABLE,
    BootstrapFailureReason.UPDATE_CHECKER_FAILED,
    BootstrapFailureReason.OPTIONAL_INTEGRATION_INACTIVE,
})

_WARNING_REASONS = frozenset({
    BootstrapFailureReason.BACKUP_OVERDUE,
    BootstrapFailureReason.OPTIONAL_DEVICE_DISCONNECTED,
    BootstrapFailureReason.CAMPAIGN_NOT_SYNCED,
    BootstrapFailureReason.SECONDARY_SERVICE_PAUSED,
    BootstrapFailureReason.SCHEMA_COVERAGE_INCOMPLETE,
})


def severity_for(reason: BootstrapFailureReason) -> BootstrapSeverity:
    if reason in _FATAL_REASONS:
        return BootstrapSeverity.FATAL
    if reason in _DEGRADED_REASONS:
        return BootstrapSeverity.DEGRADED
    if reason in _WARNING_REASONS:
        return BootstrapSeverity.WARNING
    raise ValueError(f"Razón de fallo sin clasificar: {reason!r}")
