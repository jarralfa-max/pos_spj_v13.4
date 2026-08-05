"""P2 guardrail — the legacy inventory DROP stays deferred, guarded and complete.

Dropping ``lotes`` / ``movimientos_lote`` / ``movimientos_inventario`` is unsafe
while live consumers remain (LoteService cárnico/FIFO, delivery reservation
adapter, API router, analytics, reconcile scripts, inventory_repository…). The
DROP is therefore a deferred, env-guarded migration that must NOT be auto-run.
This guardrail keeps that safety in place until the consumers reach zero.
"""

from pathlib import Path

ROOT = Path("pos_spj_v13.4")
DROP = ROOT / "migrations/deferred/legacy_inventory_drop.py"


def test_deferred_drop_migration_exists():
    assert DROP.exists()


def test_deferred_drop_is_not_registered_in_engine():
    engine = (ROOT / "migrations/engine.py").read_text(errors="ignore")
    assert "legacy_inventory_drop" not in engine


def test_deferred_drop_is_env_guarded():
    src = DROP.read_text(errors="ignore")
    assert 'INVENTORY_ALLOW_LEGACY_DROP' in src
    # refuses to run unless the guard is explicitly set to "1"
    assert '!= "1"' in src and "raise RuntimeError" in src


def test_deferred_drop_covers_the_three_legacy_tables():
    src = DROP.read_text(errors="ignore")
    for table in ("lotes", "movimientos_lote", "movimientos_inventario"):
        assert f'"{table}"' in src
