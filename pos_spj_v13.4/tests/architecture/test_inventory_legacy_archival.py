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


def test_legacy_inventory_archive_migration_is_registered() -> None:
    engine_source = ENGINE.read_text(encoding="utf-8")
    migration_source = ARCHIVE_MIGRATION.read_text(encoding="utf-8")

    assert "099_archive_legacy_inventory_sources" in engine_source
    assert "legacy_inventario_actual" in migration_source
    assert "legacy_branch_inventory" in migration_source
    assert "legacy_movimientos_inventario" in migration_source


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
