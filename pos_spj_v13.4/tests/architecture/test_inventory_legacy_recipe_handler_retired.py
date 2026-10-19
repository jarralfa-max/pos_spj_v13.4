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


def test_purchases_do_not_explode_recipes():
    """2026-10-16 (decisión del usuario, auditoría de Producción 32cfbf): Compras
    registra lo recibido y nada más. El puente canónico que consumía los
    componentes de cualquier producto comprado con receta activa (de cualquier
    tipo y con negativo permitido) se retiró; toda transformación se registra
    una sola vez en Producción, con referencia a la recepción."""
    bridge = (ROOT / "backend/application/event_handlers/inventory/"
              "purchase_recipe_explosion_bridge.py")
    assert not bridge.exists()
    wiring = (ROOT / "backend/bootstrap/wiring/event_wiring.py").read_text(encoding="utf-8")
    assert "RecipeExplosionHandler(" not in wiring
