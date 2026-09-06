"""TRF-23 final, zero-allowlist architecture audit."""
import sqlite3
from pathlib import Path

from backend.application.transfers.permissions import ALL_TRANSFER_PERMISSIONS
from backend.domain.transfers.events import ALL_TRANSFER_EVENTS
from backend.infrastructure.db.schema.transfers_schema import (
    TRANSFER_TABLES, create_transfers_schema,
)
from tests.architecture.architecture_guardrails import APP_ROOT


ROOT = APP_ROOT


def test_transfer_schema_is_uuid_text_decimal_text_and_not_duplicated():
    connection = sqlite3.connect(":memory:")
    create_transfers_schema(connection)
    actual = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert actual == set(TRANSFER_TABLES)
    for table in TRANSFER_TABLES:
        columns = connection.execute(f"PRAGMA table_info({table})").fetchall()
        for _, name, kind, *_ in columns:
            if name == "id" or name.endswith("_id"):
                assert kind == "TEXT", f"{table}.{name} must carry UUIDv7 as TEXT"
            if (not name.endswith("_required") and any(
                    token in name for token in ("quantity", "weight", "temperature",
                                                "tolerance", "score", "days_of_supply"))):
                assert kind == "TEXT", f"{table}.{name} must carry Decimal as TEXT"
        assert all(kind not in {"REAL", "FLOAT", "DOUBLE"} for _, _, kind, *_ in columns)


def test_transfer_ui_has_no_sql_or_transaction_control():
    sources = "\n".join(path.read_text(errors="ignore").lower() for path in
                        (ROOT / "frontend/desktop/modules/transfers").rglob("*.py"))
    for forbidden in ("select ", "insert ", "update ", "delete ", "create table",
                      ".commit(", ".rollback(", "sqlite3"):
        assert forbidden not in sources


def test_transfer_events_permissions_offline_inventory_and_legacy_are_canonical():
    assert ALL_TRANSFER_EVENTS
    assert all(name.startswith("TRANSFER_") for name in ALL_TRANSFER_EVENTS)
    assert ALL_TRANSFER_PERMISSIONS
    assert all(code.startswith("TRANSFERS_") for code in ALL_TRANSFER_PERMISSIONS)
    inventory = (ROOT / "backend/application/transfers/integrations/inventory_gateway.py").read_text()
    offline = (ROOT / "backend/application/transfers/offline_sync.py").read_text()
    assert "InventoryEngine" not in inventory and "sqlite3" not in inventory
    assert "OfflineTransferPolicy" in offline and "local_sequence" in offline
    assert not (ROOT / "modulos/transferencias.py").exists()
    assert not (ROOT / "repositories/transferencias.py").exists()
