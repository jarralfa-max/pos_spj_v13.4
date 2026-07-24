"""PROD-19 paso 9 (prep) — ratchet de consumidores legacy de `productos`.

Congela el conjunto de archivos que aún leen/escriben la tabla legacy `productos`
por SQL directo. Mientras el corte de Productos avanza, este guardrail impide
**agregar nuevos** consumidores legacy: la allowlist sólo puede **decrecer**. El
objetivo del paso 10 es allowlist **vacía** → entonces el DROP de `productos` es
seguro.

Escanea literales SQL (AST) en el código de aplicación (no migraciones/tests/docs).
Cuando un archivo se repunta al maestro canónico `products` (o a
`ProductCatalogService`/`PricingReadFacade`/`inventory_balances`), se elimina de la
allowlist; si vuelve a aparecer, el test falla.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SCAN_DIRS = ("backend", "core", "modulos", "frontend", "integrations", "services",
              "repositories", "application", "interfaz", "sync")
_FROM_PRODUCTOS = re.compile(r"\b(from|into|update|join)\s+productos\b", re.IGNORECASE)


def _sql_literals(tree: ast.AST) -> list[str]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            up = node.value.upper()
            if any(k in up for k in ("SELECT ", "INSERT ", "UPDATE ", "DELETE ",
                                     "JOIN ", " FROM ")):
                out.append(node.value)
    return out


def _current_consumers() -> set[str]:
    hits: set[str] = set()
    for d in _SCAN_DIRS:
        base = _ROOT / d
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            if any(_FROM_PRODUCTOS.search(sql) for sql in _sql_literals(tree)):
                hits.add(str(path.relative_to(_ROOT)))
    return hits


# Allowlist congelada (PROD-19 paso 9). SÓLO puede reducirse: repuntar un archivo al
# maestro canónico y borrarlo de aquí. Objetivo del paso 10: conjunto vacío.
_ALLOWLIST: frozenset[str] = frozenset({
    "backend/application/event_handlers/inventory/purchase_stock_entry_handler.py",
    "backend/application/procurement/queries/purchase_template_read_service.py",
    "backend/application/procurement/queries/qr_traceability_read_service.py",
    "backend/application/queries/bi_dashboard_query_service.py",
    "backend/application/queries/bi_inventory_query_service.py",
    "backend/application/queries/bi_sales_query_service.py",
    "backend/application/queries/inventory_balance_service.py",
    "backend/application/queries/inventory_query_service.py",
    "backend/application/queries/product_query_service.py",
    "backend/application/queries/purchase_planning_query_service.py",
    "backend/application/queries/transfer_query_service.py",
    "backend/application/services/product_catalog_service.py",
    "backend/infrastructure/db/repositories/branch_product_repository.py",
    "backend/infrastructure/db/repositories/compras_read_repository.py",
    "backend/infrastructure/db/repositories/compras_write_repository.py",
    "backend/infrastructure/db/repositories/product_repository.py",
    "backend/infrastructure/db/repositories/qr_containers_read_repository.py",
    "backend/infrastructure/db/repositories/sales_read_repository.py",
    "backend/infrastructure/db/repositories/waste_repository.py",
    "core/app_container.py",
    "core/delivery/application/query_service.py",
    "core/forecast/replenishment_engine.py",
    "core/health/health_server.py",
    "core/migration_validator.py",
    "core/production/cost_allocator.py",
    "core/production/production_engine.py",
    "core/services/actionable_forecast.py",
    "core/services/alert_engine.py",
    "core/services/alertas_service.py",
    "core/services/analytics/analytics_engine.py",
    "core/services/cfdi_service.py",
    "core/services/cotizacion_service.py",
    "core/services/decision_engine.py",
    "core/services/delivery_service.py",
    "core/services/discount_guard.py",
    "core/services/enterprise/demand_forecasting.py",
    "core/services/enterprise/finance_service.py",
    "core/services/enterprise/report_engine.py",
    "core/services/enterprise/report_engine_v2.py",
    "core/services/erp_application_service.py",
    "core/services/export_service.py",
    "core/services/finance/production_cost_service.py",
    "core/services/finance/treasury_service.py",
    "core/services/financial_simulator.py",
    "core/services/forecast_engine.py",
    "core/services/forecast_service.py",
    "core/services/franchise_manager.py",
    "core/services/inventory/unified_inventory_service.py",
    "core/services/inventory_balance_service.py",
    "core/services/lote_service.py",
    "core/services/printer_service.py",
    "core/services/product_catalog_query_service.py",
    "core/services/production_query_service.py",
    "core/services/recepcion_qr_service.py",
    "core/services/recipe_engine.py",
    "core/services/recipes/recipe_resolver.py",
    "core/services/recipes/recipe_service.py",
    "core/services/reporte_email_service.py",
    "core/services/sales/product_catalog_query_service.py",
    "core/services/sales_fulfillment_service.py",
    "core/services/sales_service.py",
    "core/services/transfer_suggestion_engine.py",
    "core/use_cases/venta.py",
    "integrations/cfdi/cfdi_service.py",
    "integrations/pos_adapter.py",
    "repositories/bi_repository.py",
    "repositories/config_repository.py",
    "repositories/inventory_repository.py",
    "repositories/main_window_repository.py",
    "repositories/productos.py",
    "repositories/proveedor_repository.py",
    "repositories/purchase_repository.py",
    "repositories/recetas.py",
    "repositories/sales_repository.py",
    "repositories/transferencias.py",
    "repositories/ventas.py",
    "services/bot_pedidos.py",
    "services/qr_service.py",
})


def test_no_new_legacy_productos_consumers():
    current = _current_consumers()
    new = current - _ALLOWLIST
    assert not new, (
        "Nuevos consumidores de la tabla legacy `productos` (repunta a `products` "
        "canónico / ProductCatalogService / PricingReadFacade / inventory_balances):\n"
        + "\n".join(sorted(new)))


def test_allowlist_has_no_stale_entries():
    """La allowlist no debe listar archivos que ya NO leen `productos` (mantiene el
    ratchet honesto: al repuntar un archivo, se borra de la allowlist)."""
    current = _current_consumers()
    stale = _ALLOWLIST - current
    assert not stale, ("Entradas obsoletas en la allowlist (bórralas, ya no leen "
                       "`productos`):\n" + "\n".join(sorted(stale)))
