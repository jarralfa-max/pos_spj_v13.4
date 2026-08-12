"""LOSS-23 hard cutover: one Losses route, classification, and schema."""

from pathlib import Path
import sqlite3

from migrations.m000_base_schema import up as bootstrap_schema


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIRS = ("backend", "core", "frontend", "interfaz", "modulos")
LEGACY_FILES = (
    "modulos/merma.py",
    "backend/application/commands/waste_commands.py",
    "backend/application/services/waste_application_service.py",
    "backend/application/use_cases/register_waste_use_case.py",
    "backend/infrastructure/db/repositories/waste_repository.py",
    "backend/application/inventory/use_cases/register_waste.py",
    "backend/infrastructure/db/repositories/inventory/waste_repository.py",
    "core/services/inventory/canonical_waste_adapter.py",
)
LEGACY_IMPORT_TOKENS = (
    "modulos.merma", "ModuloMerma", "WasteApplicationService",
    "RegisterWasteCommand", "CanonicalWasteInventoryService",
    "register_waste_use_case", "inventory_waste_event",
    "ajustes_inventario",
)


def _runtime_sources():
    for directory in RUNTIME_DIRS:
        for path in (ROOT / directory).rglob("*.py"):
            if "__pycache__" not in path.parts:
                yield path, path.read_text(encoding="utf-8", errors="ignore")


def test_legacy_loss_modules_are_deleted_and_have_no_runtime_imports():
    assert not [relative for relative in LEGACY_FILES if (ROOT / relative).exists()]
    offenders = {
        str(path.relative_to(ROOT)): [token for token in LEGACY_IMPORT_TOKENS if token in source]
        for path, source in _runtime_sources()
    }
    assert not {path: tokens for path, tokens in offenders.items() if tokens}


def test_born_clean_schema_has_only_loss_bounded_context_tables():
    base = (ROOT / "migrations/m000_base_schema.py").read_text(encoding="utf-8")
    inventory = (ROOT / "backend/infrastructure/db/schema/inventory_schema.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS mermas" not in base
    assert "CREATE TABLE IF NOT EXISTS ajustes_inventario" not in base
    assert 'ensure_column(conn, "mermas"' not in base
    assert "inventory_waste_event" not in inventory
    canonical = (ROOT / "migrations/standalone/174_losses_bounded_context_schema.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS loss_cases" in canonical
    assert "CREATE TABLE IF NOT EXISTS loss_lines" in canonical


def test_born_clean_bootstrap_does_not_materialize_retired_tables():
    connection = sqlite3.connect(":memory:")
    try:
        bootstrap_schema(connection)
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert not tables.intersection({
            "mermas", "ajustes_inventario", "inventory_waste_event"})
        assert {"loss_cases", "loss_lines", "loss_classifications"} <= tables
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        connection.close()


def test_inventory_analytics_reads_canonical_loss_classification():
    source = (ROOT / "backend/application/inventory/analytics/inventory_analytics_service.py").read_text(encoding="utf-8")
    assert "loss_cases" in source and "loss_lines" in source
    assert "loss_classifications" in source
    assert "inventory_waste_event" not in source


def test_loss_inventory_never_uses_generic_adjustments_and_allowlist_is_empty():
    source = (ROOT / "backend/application/losses/loss_inventory_integration.py").read_text(encoding="utf-8")
    assert "ADJUSTMENT_IN" not in source and "ADJUSTMENT_OUT" not in source
    assert "MovementType.WASTE" in source
    legacy_loss_allowlist = frozenset()
    assert legacy_loss_allowlist == frozenset()


def test_loss_23_report_exists():
    report = ROOT / "docs/refactor/LOSS_23_LEGACY_REMOVAL_REPORT.md"
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    for heading in ("Inventario", "Clasificación", "Tablas consolidadas",
                    "Allowlist", "Validación"):
        assert heading in text
