"""P2 guardrail — purchase traceability lots are canonical only.

The legacy PurchaseLotEntryHandler wrote the legacy ``lotes`` / ``movimientos_lote``
tables. After P2 the wired CanonicalPurchaseStockEntryHandler creates the lot in
canonical ``inventory_lots`` (via _ensure_lot). This guardrail keeps the legacy
handler gone and stops any inventory event handler from writing the legacy lot
tables again.
"""

from pathlib import Path
from tests.architecture.architecture_guardrails import APP_ROOT

ROOT = APP_ROOT
HANDLERS = ROOT / "backend/application/event_handlers/inventory"


def test_legacy_purchase_lot_entry_handler_file_is_removed():
    assert not (HANDLERS / "purchase_lot_entry_handler.py").exists()


def test_nothing_imports_the_legacy_purchase_lot_entry_handler():
    offenders = []
    for folder in ("backend", "core", "frontend", "interfaz", "modulos", "tests"):
        base = ROOT / folder
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            text = path.read_text(errors="ignore")
            if ("from backend.application.event_handlers.inventory."
                    "purchase_lot_entry_handler import") in text:
                offenders.append(str(path))
    assert offenders == []


def test_inventory_handlers_do_not_write_legacy_lot_tables():
    offenders = []
    for path in HANDLERS.rglob("*.py"):
        text = path.read_text(errors="ignore")
        for legacy in ("INTO lotes", "INTO movimientos_lote",
                       "INTO movimientos_inventario"):
            if legacy in text:
                offenders.append(f"{path}: {legacy}")
    assert offenders == []
