from pathlib import Path

import pytest

from core.services.sales_service import SalesService
from core.services.sales.unified_sales_service import DatosPago, UnifiedSalesService

ROOT = Path(__file__).resolve().parents[1]
SALES_SRC = (ROOT / "core" / "services" / "sales_service.py").read_text(encoding="utf-8")
VENTAS_UI_SRC = (ROOT / "modulos" / "ventas.py").read_text(encoding="utf-8")
UNIFIED_SRC = (ROOT / "core" / "services" / "sales" / "unified_sales_service.py").read_text(encoding="utf-8")


class _Item:
    producto_id = 1
    cantidad = 1.0
    precio_unitario = 10.0
    nombre = "P"


def test_sales_service_procesar_venta_legacy_blocked_by_default(monkeypatch):
    monkeypatch.delenv("ALLOW_LEGACY_SALES_SERVICE_PROCESAR_VENTA", raising=False)
    svc = SalesService.__new__(SalesService)
    with pytest.raises(RuntimeError, match="ProcesarVentaUC"):
        svc.procesar_venta([_Item()], DatosPago(efectivo_recibido=10.0))


def test_legacy_unified_sales_service_blocked_by_default(monkeypatch):
    monkeypatch.delenv("ALLOW_LEGACY_UNIFIED_SALES_SERVICE", raising=False)
    svc = UnifiedSalesService(conn=None)
    with pytest.raises(RuntimeError, match="UnifiedSalesService.procesar_venta"):
        svc.procesar_venta([_Item()], DatosPago(efectivo_recibido=10.0))


def test_legacy_minimal_sale_write_blocked_by_default(monkeypatch):
    monkeypatch.delenv("ALLOW_LEGACY_MINIMAL_SALE_WRITE", raising=False)
    svc = SalesService.__new__(SalesService)
    with pytest.raises(RuntimeError, match="_procesar_venta_legacy_minimal"):
        svc._procesar_venta_legacy_minimal(
            items_payload=[{"product_id": 1, "qty": 1, "unit_price": 10}],
            payment_method="Efectivo",
            amount_paid=10.0,
            client_id=None,
            discount=0.0,
            usuario="u",
        )


def test_no_ui_direct_sale_write():
    assert "INSERT INTO ventas" not in VENTAS_UI_SRC
    assert "VentaRepository(" not in VENTAS_UI_SRC
    assert "create_sale(" not in VENTAS_UI_SRC
    assert "result = _uc.ejecutar" in VENTAS_UI_SRC


def test_no_legacy_ticket_path_active():
    assert "ALLOW_LEGACY_MINIMAL_SALE_WRITE" in SALES_SRC
    assert "_procesar_venta_legacy_minimal() está bloqueado por seguridad" in SALES_SRC
    assert "ticket_data={\"folio\": folio, \"total\": total, \"items\": items_payload}" in SALES_SRC
    assert "UnifiedSalesService.procesar_venta() está bloqueado por seguridad" in UNIFIED_SRC
