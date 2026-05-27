from unittest.mock import MagicMock

from core.services.sales_service import SalesService


def _build_service():
    db = MagicMock()
    db.cursor.return_value = MagicMock()

    sales_repo = MagicMock()
    sales_repo.create_sale.return_value = (10, "F-10")
    sales_repo.save_sale_item.return_value = None

    customer = MagicMock()
    customer.get_customer.return_value = {"id": 1}
    customer.validate_credit.return_value = (True, "")

    loyalty = MagicMock()
    loyalty.compute_redemption_discount.return_value = 0.0

    finance = MagicMock()

    svc = SalesService(
        db_conn=db,
        sales_repo=sales_repo,
        recipe_repo=MagicMock(),
        inventory_service=MagicMock(),
        finance_service=finance,
        loyalty_service=loyalty,
        promotion_engine=None,
        sync_service=None,
        ticket_template_engine=MagicMock(),
        whatsapp_service=MagicMock(),
        config_service=MagicMock(get=MagicMock(return_value="<html>{{folio}}</html>")),
        feature_flag_service=MagicMock(),
        growth_engine=MagicMock(),
        notification_service=MagicMock(),
        customer_service=customer,
    )
    svc._validate_stock_pre_sale = MagicMock()
    svc._resolve_sale_items = MagicMock(return_value=[])
    svc._comisiones_svc = MagicMock()
    return svc, loyalty, finance


def test_sales_service_publishes_single_flow_and_loyalty_processed_once_before_ticket():
    svc, loyalty, finance = _build_service()

    from core.events import event_bus
    bus = event_bus.get_bus()
    published = []
    original = bus.publish

    def _capture(event, payload, **kwargs):
        published.append(event)

    bus.publish = _capture
    try:
        folio, ticket = svc.execute_sale(
            branch_id=1,
            user="cajero",
            items=[{"product_id": 1, "qty": 2, "unit_price": 50.0}],
            payment_method="Efectivo",
            amount_paid=100.0,
            client_id=1,
            client_phone="5551112222",
        )
    finally:
        bus.publish = original

    assert folio == "F-10"
    assert ticket is not None
    assert published.count("sale_items_process") == 1
    assert published.count("VENTA_COMPLETADA") == 1

    loyalty.process_loyalty_for_sale.assert_called_once()
    finance.registrar_ingreso.assert_not_called()
    svc._comisiones_svc.registrar_comision.assert_not_called()
    svc.notification_service.notificar_venta_cliente.assert_not_called()
    svc.whatsapp_service.send_message.assert_not_called()


def test_sale_with_active_raffle_includes_snapshot_in_event_and_ticket_data():
    svc, loyalty, _finance = _build_service()
    loyalty.process_raffles_for_sale.return_value = [
        {"raffle": "Navidad SPJ", "numero_boleto": "1-100-1"},
        {"raffle": "Navidad SPJ", "numero_boleto": "1-100-2"},
    ]

    from core.events import event_bus
    bus = event_bus.get_bus()
    payloads = []
    original = bus.publish

    def _capture(event, payload, **kwargs):
        if event == "VENTA_COMPLETADA":
            payloads.append(payload)

    bus.publish = _capture
    try:
        svc.execute_sale(
            branch_id=1,
            user="cajero",
            items=[{"product_id": 1, "qty": 2, "unit_price": 50.0}],
            payment_method="Efectivo",
            amount_paid=100.0,
            client_id=1,
        )
    finally:
        bus.publish = original

    assert payloads
    assert payloads[0]["raffle_tickets_snapshot"]
    assert len(payloads[0]["raffle_tickets_snapshot"]) == 2

    args, _kwargs = svc.ticket_template_engine.generar_ticket.call_args
    datos_venta = args[1]
    assert "raffle_tickets_snapshot" in datos_venta
    assert len(datos_venta["raffle_tickets_snapshot"]) == 2
    assert "raffle_tickets_lines" in datos_venta


def test_sale_without_active_raffle_does_not_break_ticket_generation():
    svc, loyalty, _finance = _build_service()
    loyalty.process_raffles_for_sale.return_value = []

    folio, ticket = svc.execute_sale(
        branch_id=1,
        user="cajero",
        items=[{"product_id": 1, "qty": 1, "unit_price": 100.0}],
        payment_method="Efectivo",
        amount_paid=100.0,
        client_id=1,
    )

    assert folio == "F-10"
    assert ticket is not None
    args, _kwargs = svc.ticket_template_engine.generar_ticket.call_args
    datos_venta = args[1]
    assert datos_venta.get("raffle_tickets_snapshot") == []
