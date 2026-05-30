from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.use_cases.venta import DatosPago, ItemCarrito, ProcesarVentaUC
from core.services.sales.sale_execution_result import (
    SaleExecutionResult,
    SaleExecutionItem,
    SaleLoyaltyResult,
    SalePaymentResult,
)
from core.services.sales_service import SalesService
from presentation.sales.workers.sale_checkout_worker_factory import SaleCheckoutWorkerFactory


def _result(**kw):
    base = dict(
        ok=True,
        venta_id=123,
        folio="F-123",
        operation_id="op-123",
        subtotal=100.0,
        descuento_total=0.0,
        total=100.0,
        items=[SaleExecutionItem(1, "Backend", 1, 100, 100, 0, 100)],
        payment=SalePaymentResult("Efectivo", 100, 100, 0, 0, 0, 0, 0, 0, {"efectivo": 100}),
        loyalty=SaleLoyaltyResult(1, 0, 0.0, None, None, None, "", "op-123", False),
        ticket_payload={},
        ticket_html="",
        warnings=[],
        error="",
    )
    base.update(kw)
    return SaleExecutionResult(**base)


def _uc_with_sales(rich, loyalty=None):
    sales = MagicMock()
    sales.execute_sale_result.return_value = rich
    inv = MagicMock()
    inv.get_stock.return_value = 999
    return ProcesarVentaUC(sales, inv, MagicMock(), loyalty, MagicMock()), sales


def test_no_ticket_from_uc_original_items():
    uc, _sales = _uc_with_sales(_result(ticket_payload={}, ticket_html=""))
    res = uc.ejecutar(
        [ItemCarrito(producto_id=1, cantidad=1, precio_unit=999.0, nombre="UI_ORIGINAL")],
        DatosPago(forma_pago="Efectivo", monto_pagado=100.0),
        1,
        "cajero",
    )
    assert res.ok is True
    assert res.ticket_html == ""
    assert "ticket_html_missing_from_sales_service" in res.warnings
    assert "UI_ORIGINAL" not in res.ticket_html


def test_ticket_requires_backend_payload():
    uc, _sales = _uc_with_sales(_result(ticket_payload={}, ticket_html="<html>legacy</html>"))
    res = uc.ejecutar([ItemCarrito(1, 1, 100, "A")], DatosPago(monto_pagado=100), 1, "u")
    assert res.ticket_payload == {}
    assert "ticket_html_missing_from_sales_service" in res.warnings


def test_ticket_payload_has_real_sale_id_and_total_matches_sale_result():
    payload = {"venta_id": 123, "folio": "F-123", "totales": {"total_final": 100.0}}
    uc, _sales = _uc_with_sales(_result(ticket_payload=payload, ticket_html="<html></html>"))
    res = uc.ejecutar([ItemCarrito(1, 1, 100, "A")], DatosPago(monto_pagado=100), 1, "u")
    assert res.ticket_payload["venta_id"] == res.venta_id == 123
    assert res.ticket_payload["totales"]["total_final"] == res.total


def test_loyalty_none_does_not_display_zero():
    loyalty = MagicMock()
    loyalty.enabled = True
    loyalty.saldo.side_effect = RuntimeError("down")
    uc, _sales = _uc_with_sales(_result(), loyalty=loyalty)
    res = uc.ejecutar([ItemCarrito(1, 1, 100, "A")], DatosPago(monto_pagado=100, cliente_id=1), 1, "u")
    assert res.puntos_totales is None
    assert "loyalty_balance_unavailable" in res.warnings


def test_loyalty_zero_only_if_service_confirms_zero():
    loyalty = MagicMock()
    loyalty.enabled = True
    loyalty.saldo.return_value = 0
    uc, _sales = _uc_with_sales(_result(), loyalty=loyalty)
    res = uc.ejecutar([ItemCarrito(1, 1, 100, "A")], DatosPago(monto_pagado=100, cliente_id=1), 1, "u")
    assert res.puntos_totales == 0
    loyalty.saldo.assert_called_once_with(1)




def test_ui_queries_saldo_when_result_points_missing():
    loyalty = MagicMock()
    loyalty.enabled = True
    loyalty.saldo.return_value = 45
    uc, _sales = _uc_with_sales(_result(), loyalty=loyalty)
    res = uc.ejecutar([ItemCarrito(1, 1, 100, "A")], DatosPago(monto_pagado=100, cliente_id=1), 1, "u")
    assert res.puntos_totales == 45
    assert res.loyalty_result["available"] is True
    loyalty.saldo.assert_called_once_with(1)


def test_untrusted_zero_loyalty_result_does_not_display_zero():
    loyalty = MagicMock()
    loyalty.enabled = True
    loyalty.saldo.return_value = 37
    rich = _result(loyalty=SaleLoyaltyResult(1, 0, 0.0, 0, 0, None, "", "op-123", False))
    uc, _sales = _uc_with_sales(rich, loyalty=loyalty)
    res = uc.ejecutar([ItemCarrito(1, 1, 100, "A")], DatosPago(monto_pagado=100, cliente_id=1), 1, "u")
    assert res.puntos_totales == 37
    assert res.loyalty_result["puntos_totales"] == 37


def test_ticket_does_not_print_fake_zero_points():
    from core.ticket_escpos_renderer import TicketESCPOSRenderer

    data = {
        "folio": "F-1",
        "items": [],
        "totales": {"total_final": 10},
        "pago": {"forma_pago": "Efectivo"},
        "puntos_ganados": 5,
        "puntos_totales": 0,
        "loyalty": {"available": False, "puntos_ganados": 5, "puntos_totales": 0},
        "layout_config": {"show_logo": False, "show_qr": False},
    }
    rendered = TicketESCPOSRenderer().render(data).decode("cp850", errors="ignore")
    assert "Puntos ganados: +5" in rendered
    assert "Saldo total: 0 puntos" not in rendered


def test_customer_cache_updated_only_with_real_balance_static():
    body = _source_between(
        "modulos/ventas.py",
        "    def _aplicar_resultado_venta",
        "    def _on_checkout_failed",
    )
    update_pos = body.index('self.cliente_actual["puntos"] = puntos_totales')
    reliable_pos = body.index("if saldo_confiable:")
    unavailable_pos = body.index('self.lbl_puntos_venta.setText("⭐ Saldo de puntos no disponible")')
    assert reliable_pos < update_pos < unavailable_pos




def test_loyalty_service_saldo_error_not_fake_zero():
    from core.services.loyalty_service import LoyaltyService

    svc = LoyaltyService.__new__(LoyaltyService)
    svc.db = object()
    with pytest.raises(RuntimeError, match="loyalty_balance_unavailable"):
        svc.saldo(1)


def test_payment_breakdown_preserved_to_ticket_payload():
    sales = SalesService.__new__(SalesService)
    sales._normalize_payment_method = lambda value: "Mixto" if value in {"Mixto", "Pago Mixto"} else value
    lines = sales._build_payment_breakdown("Mixto", 100.0, 0.0, {"efectivo": 40.0, "tarjeta": 60.0})
    assert lines == {"efectivo": 40.0, "tarjeta": 60.0, "transferencia": 0.0, "credito": 0.0, "mercado_pago": 0.0}


def test_pago_mixto_not_mapped_to_cash():
    sales = SalesService.__new__(SalesService)
    sales._normalize_payment_method = lambda value: "Mixto"
    with pytest.raises(ValueError, match="requiere payment_breakdown"):
        sales._build_payment_breakdown("Mixto", 100.0, 100.0, None)


def test_unknown_payment_method_fails():
    sales = SalesService.__new__(SalesService)
    sales._normalize_payment_method = lambda value: value
    with pytest.raises(ValueError, match="desconocido"):
        sales._build_payment_breakdown("Crypto", 100.0, 100.0, None)


def test_credit_sale_payment_payload_has_credit_total_and_cash_zero():
    sales = SalesService.__new__(SalesService)
    sales._normalize_payment_method = lambda value: "Crédito"
    lines = sales._build_payment_breakdown("Crédito", 250.0, 0.0, None)
    assert lines["credito"] == 250.0
    assert lines["efectivo"] == 0.0


def test_sale_checkout_factory_disabled_or_removed():
    with pytest.raises(RuntimeError, match="deshabilitado"):
        SaleCheckoutWorkerFactory(object()).build(object(), [], object(), 1, "u")


def test_mp_pending_requires_items_for_reservation():
    sales = SalesService.__new__(SalesService)
    sales.db = object()
    with pytest.raises(ValueError, match="requiere items"):
        sales.create_pending_payment_sale(1, "u", [], total=1.0)


def _source_between(path, start_marker, end_marker):
    repo_root = Path(__file__).resolve().parents[1]
    src = (repo_root / path).read_text(encoding="utf-8")
    start = src.index(start_marker)
    end = src.index(end_marker, start)
    return src[start:end]


def test_no_ticket_from_compra_actual_after_sale():
    body = _source_between(
        "modulos/ventas.py",
        "    def _aplicar_resultado_venta",
        "    def _on_checkout_failed",
    )
    assert "ticket_payload" in body
    assert "_imprimir_ticket_consolidado(datos_ticket)" in body
    assert "compra_actual" not in body
    assert "self.totales" not in body


def test_ui_does_not_cache_ticket_html_without_backend_payload_contract():
    body = _source_between(
        "modulos/ventas.py",
        "    def _aplicar_resultado_venta",
        "    def _on_checkout_failed",
    )
    branch_start = body.index("if (\n            not datos_ticket")
    missing_payload_branch = body[branch_start:body.index("        else:", branch_start)]
    assert 'self._ticket_html_cache = ""' in missing_payload_branch
    assert "_imprimir_ticket_consolidado" not in missing_payload_branch
    assert "Use reimpresión desde venta_id" in missing_payload_branch


def test_sales_service_ticket_payload_contract_has_backend_sale_id_total_and_payment():
    body = _source_between(
        "core/services/sales_service.py",
        "        ticket_payload = dict(datos_venta)",
        "        if return_details:",
    )
    assert 'ticket_payload["venta_id"] = sale_id' in body
    assert 'ticket_payload["sale_id"] = sale_id' in body
    assert 'ticket_payload["operation_id"] = operation_id' in body
    assert 'ticket_payload["folio"] = str(folio)' in body
    assert 'ticket_payload["items"] = list(carrito_final)' in body
    assert 'ticket_payload["total_final"] = round(float(total_a_pagar), 2)' in body
    assert 'ticket_payload["totales"]' in body
    assert 'ticket_payload["pago"]' in body
    assert 'ticket_payload["loyalty"]' in body


def test_tarjeta_not_modeled_as_cash_or_amount_paid_universal():
    sales = SalesService.__new__(SalesService)
    sales._normalize_payment_method = lambda value: "Tarjeta"
    lines = sales._build_payment_breakdown("Tarjeta", 180.0, 999.0, None)
    assert lines["tarjeta"] == 180.0
    assert lines["efectivo"] == 0.0
    assert sales._amount_paid_for_storage("Tarjeta", lines, 180.0) == 180.0


def test_credit_not_amount_paid_real():
    sales = SalesService.__new__(SalesService)
    sales._normalize_payment_method = lambda value: "Credito"
    lines = sales._build_payment_breakdown("Credito", 250.0, 999.0, None)
    assert lines["credito"] == 250.0
    assert lines["efectivo"] == 0.0
    assert sales._amount_paid_for_storage("Credito", lines, 250.0) == 0.0


def test_payment_validation_uses_breakdown_not_universal_amount_paid():
    sales = SalesService.__new__(SalesService)
    sales._normalize_payment_method = lambda value: value
    sales.customer_service = None
    lines = {"efectivo": 0.0, "tarjeta": 100.0, "transferencia": 0.0, "credito": 0.0, "mercado_pago": 0.0}
    sales._validate_payment("Tarjeta", 100.0, lines)
    with pytest.raises(ValueError, match="efectivo recibido"):
        sales._validate_payment("Efectivo", 100.0, {**lines, "tarjeta": 0.0})


def test_uc_preserves_payment_breakdown_to_sales_service():
    payload = {"venta_id": 123, "folio": "F-123", "totales": {"total_final": 100.0}}
    uc, sales = _uc_with_sales(_result(ticket_payload=payload, ticket_html="<html></html>"))
    res = uc.ejecutar(
        [ItemCarrito(1, 1, 100, "A")],
        DatosPago(
            forma_pago="Pago Mixto",
            monto_pagado=0.0,
            payment_breakdown={"efectivo": 40.0, "tarjeta": 60.0},
        ),
        1,
        "u",
    )
    assert res.ok is True
    assert sales.execute_sale_result.call_args.kwargs["payment_breakdown"] == {"efectivo": 40.0, "tarjeta": 60.0}
