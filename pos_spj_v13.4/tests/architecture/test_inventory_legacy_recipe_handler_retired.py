"""P2 guardrail — the legacy purchase recipe-explosion handler is retired.

Buying a product with a recipe (transformation-on-purchase) must consume its
components only through the canonical ledger (CanonicalPurchaseRecipeExplosionHandler
→ ADJUSTMENT_OUT), never through the legacy handler that wrote 'salida' rows to the
legacy ``movimientos_inventario`` table. This guardrail keeps that path from
coming back.
"""

from pathlib import Path
from tests.architecture.architecture_guardrails import APP_ROOT

ROOT = APP_ROOT


def test_legacy_recipe_explosion_handler_file_is_removed():
    legacy = (ROOT / "backend/application/event_handlers/inventory/"
              "purchase_recipe_explosion_handler.py")
    assert not legacy.exists()


def test_nothing_imports_the_legacy_recipe_explosion_handler():
    offenders = []
    for folder in ("backend", "core", "frontend", "interfaz", "modulos", "tests"):
        base = ROOT / folder
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            text = path.read_text(errors="ignore")
            if ("from backend.application.event_handlers.inventory."
                    "purchase_recipe_explosion_handler import") in text:
                offenders.append(str(path))
    assert offenders == []


def test_canonical_recipe_bridge_is_the_wired_handler():
    """`core/events/wiring.py` (this test's original target) doesn't exist —
    `core/` was deleted wholesale in a legacy sweep well before the handler
    was actually connected. The real, current wiring call lives in
    `backend/bootstrap/wiring/event_wiring.py::wire_procurement_downstream_bridges`,
    called from `frontend/desktop/app.py::main()` — see
    `tests/integration/bootstrap/test_event_wiring.py` for the live-bus proof."""
    wiring = (ROOT / "backend/bootstrap/wiring/event_wiring.py").read_text(errors="ignore")
    assert "CanonicalPurchaseRecipeExplosionHandler" in wiring
    assert "PurchaseRecipeExplosionHandler," not in wiring.replace(
        "CanonicalPurchaseRecipeExplosionHandler,", "")
