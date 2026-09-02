"""SHELL-4 guardrail: main.py's database bootstrap must stay a single
canonical sequence — the SHELL-0 audit found three separate, overlapping
call sites (`_bootstrap_db`'s own `bootstrap_database()` call, an immediate
second unconditional call to that same function, and a third block with its
own connection calling `migrator.up`/`migrate_db`/`verificar_tablas`
directly) plus a bare `except Exception: continue anyway` after a migration
failure. This test fails if any of that shape reappears.
"""
from __future__ import annotations

from pathlib import Path

MAIN_PY = Path(__file__).resolve().parents[2] / "main.py"


def _source() -> str:
    return MAIN_PY.read_text(encoding="utf-8")


def test_main_calls_the_single_canonical_bootstrap_sequence():
    source = _source()
    assert "run_database_bootstrap_sequence" in source


def test_main_no_longer_defines_the_legacy_triplicated_bootstrap_path():
    source = _source()
    # The removed helper that had its own internal fallback re-implementing
    # migration-running logic separately from scripts/bootstrap_db.py.
    assert "def _bootstrap_db(" not in source
    # The removed helper whose "Ignore" button silently continued on a
    # database the code had just told the user was corrupted.
    assert "def _verificar_bd(" not in source


def test_main_does_not_call_migration_engine_directly():
    source = _source()
    # Nothing in main.py should reach into migrations.engine or
    # core.db.connection.migrate_db directly anymore — that's
    # run_database_bootstrap_sequence's job now, exclusively.
    assert "migrator.up(" not in source
    assert "migrate_db(" not in source


def test_main_does_not_silently_continue_after_a_migration_failure():
    source = _source()
    assert "continuando con repositorios como fallback" not in source


def test_main_does_not_offer_ignore_on_a_corrupted_database():
    source = _source()
    assert "QMessageBox.Ignore" not in source
