"""Planeación de Compras: la pantalla PyQt no ejecuta SQL (usa QueryService)."""
from __future__ import annotations

from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]


def test_planning_screen_has_no_sql():
    text = (APP_ROOT / "modulos" / "planeacion_compras.py").read_text(encoding="utf-8")
    code = "\n".join(l for l in text.splitlines() if not l.strip().startswith("#"))
    for banned in (".cursor(", ".execute(", "SELECT id, nombre FROM productos",
                   "detalles_compra"):
        assert banned not in code, f"SQL directo en planeacion_compras.py: {banned!r}"
    assert "PurchasePlanningReadService" in code


def test_planning_read_service_provides_required_reads():
    from backend.application.queries.purchase_planning_query_service import (
        PurchasePlanningReadService,
    )

    for method in ("list_forecastable_products", "last_purchase_cost",
                   "sales_history", "current_stock"):
        assert callable(getattr(PurchasePlanningReadService, method))
