from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_MIGRATION = PACKAGE_ROOT / "migrations" / "standalone" / "099_archive_legacy_inventory_sources.py"
ENGINE = PACKAGE_ROOT / "migrations" / "engine.py"
MIGRATED_OPERATIONAL_FILES = [
    PACKAGE_ROOT / "backend" / "application" / "services" / "waste_application_service.py",
    PACKAGE_ROOT / "backend" / "infrastructure" / "db" / "repositories" / "waste_repository.py",
    PACKAGE_ROOT / "core" / "services" / "purchase_service.py",
    PACKAGE_ROOT / "application" / "purchases" / "receive_po_adapter.py",
]


def test_legacy_inventory_archive_migration_is_noop_under_plan_b() -> None:
    """Plan B born-clean: 099 sigue registrada (ledger estable) pero es un no-op
    documentado — una BD nueva no debe nacer con tablas legacy_* muertas."""
    engine_source = ENGINE.read_text(encoding="utf-8")
    migration_source = ARCHIVE_MIGRATION.read_text(encoding="utf-8")

    assert "099_archive_legacy_inventory_sources" in engine_source
    assert "NO-OP" in migration_source and "Plan B" in migration_source
    assert "ALTER TABLE" not in migration_source

    import sqlite3
    import sys
    sys.path.insert(0, str(PACKAGE_ROOT))
    import migrations.m000_base_schema as base
    from migrations import engine as migrator
    conn = sqlite3.connect(":memory:")
    base.up(conn)
    conn.commit()
    migrator.up(conn)
    conn.commit()
    legacy = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'legacy_%'"
    ).fetchall()]
    assert legacy == [], f"una BD nueva no debe tener tablas legacy_*: {legacy}"


def test_migrated_operational_inventory_flows_do_not_reference_legacy_sources() -> None:
    forbidden = [
        "inventario_actual",
        "branch_inventory",
        "movimientos_inventario",
        "UPDATE productos SET existencia",
        "INSERT INTO inventario_actual",
        "UPDATE inventario_actual",
        "INSERT INTO branch_inventory",
        "UPDATE branch_inventory",
        ".add_stock(",
        ".deduct_stock(",
    ]
    violations = {
        str(path.relative_to(PACKAGE_ROOT)): [token for token in forbidden if token in path.read_text(encoding="utf-8")]
        for path in MIGRATED_OPERATIONAL_FILES
    }
    assert {path: tokens for path, tokens in violations.items() if tokens} == {}
