"""PUR-13.21 — the procurement legacy allowlist is well-formed and only shrinks.

Guards the controlled-elimination contract: every allowlisted legacy path must
carry a full justification (reason, owner, created_at, removal_condition), the
listed paths must actually still exist, and the allowlist must never grow
(MAX_ENTRIES ratchets down). The phase is "done" only when the allowlist is empty.
"""

from __future__ import annotations

from pathlib import Path

from tests.architecture.procurement_legacy_allowlist import (
    LEGACY_ALLOWLIST,
    MAX_ENTRIES,
)

REPO = Path(__file__).resolve().parents[2]
_VALID_CLASSES = {"WRAP_TEMPORARILY", "BLOCKED", "REWRITE"}


def test_every_entry_is_fully_justified():
    for e in LEGACY_ALLOWLIST:
        assert e.path and e.reason and e.owner and e.created_at and e.removal_condition, (
            f"Entrada de allowlist incompleta: {e.path}")
        assert e.classification in _VALID_CLASSES, (
            f"Clasificación inválida para {e.path}: {e.classification}")


def test_allowlisted_paths_exist():
    for e in LEGACY_ALLOWLIST:
        assert (REPO / e.path).exists(), (
            f"La allowlist referencia una ruta inexistente: {e.path} "
            "(elimínala de la allowlist cuando borres el archivo).")


def test_allowlist_only_shrinks():
    assert len(LEGACY_ALLOWLIST) <= MAX_ENTRIES, (
        f"La allowlist creció ({len(LEGACY_ALLOWLIST)} > {MAX_ENTRIES}); "
        "sólo puede reducirse. Baja MAX_ENTRIES al eliminar legacy, nunca lo subas.")


def test_no_duplicate_entries():
    paths = [e.path for e in LEGACY_ALLOWLIST]
    assert len(paths) == len(set(paths)), "Hay rutas duplicadas en la allowlist."
