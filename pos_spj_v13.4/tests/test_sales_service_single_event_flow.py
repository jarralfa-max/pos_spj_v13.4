from unittest.mock import MagicMock

from core.services.sales_service import SalesService


def _build_service(printer_service=None, auto_print="1"):
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

    def _config_get(key, default=None):
        values = {
            "ticket_template_html": "<html>{{folio}}</html>",
            "raffle_ticket_print_auto": auto_print,
            "imprimir_automatico_boletos_sorteo": auto_print,
        }
        return values.get(key, default)

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
        config_service=MagicMock(get=MagicMock(side_effect=_config_get)),
        feature_flag_service=MagicMock(),
        growth_engine=MagicMock(),
        notification_service=MagicMock(),
        customer_service=customer,
        printer_service=printer_service,
    )
    svc._validate_stock_pre_sale = MagicMock()
    svc._resolve_sale_items = MagicMock(return_value=[])
    svc._comisiones_svc = MagicMock()
    svc._loyalty_policy = MagicMock(return_value=None)

    from core.events.domain_events import SALE_ITEMS_PROCESS
    from core.events import event_bus
    bus = event_bus.get_bus()
    bus.subscribe(SALE_ITEMS_PROCESS, lambda payload: None, priority=100, label="sale_inventory_test")
    bus.subscribe(SALE_ITEMS_PROCESS, lambda payload: None, priority=90, label="sale_finance_test")
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


def test_sale_prints_raffle_ticket_when_raffle_active():
    printer = MagicMock()
    printer.print_raffle_ticket.return_value = "job-raffle-1"
    svc, loyalty, _finance = _build_service(printer_service=printer)
    ticket_payload = {
        "ticket_type": "raffle_ticket",
        "raffle_id": 1,
        "raffle_name": "Navidad SPJ",
        "numero_boleto": "1-10-1",
        "folio_venta": "F-10",
        "venta_id": 10,
        "barcode": "1-10-1",
    }
    loyalty.process_raffles_for_sale.return_value = [
        {"raffle": "Navidad SPJ", "numero_boleto": "1-10-1", "raffle_ticket": ticket_payload}
    ]

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
    printer.print_raffle_ticket.assert_called_once_with(ticket_payload)


def test_sale_does_not_print_raffle_ticket_when_not_eligible():
    printer = MagicMock()
    svc, loyalty, _finance = _build_service(printer_service=printer)
    loyalty.process_raffles_for_sale.return_value = []

    svc.execute_sale(
        branch_id=1,
        user="cajero",
        items=[{"product_id": 1, "qty": 1, "unit_price": 100.0}],
        payment_method="Efectivo",
        amount_paid=100.0,
        client_id=1,
    )

    printer.print_raffle_ticket.assert_not_called()


def test_sale_does_not_cancel_if_raffle_ticket_print_fails():
    printer = MagicMock()
    printer.print_raffle_ticket.side_effect = [RuntimeError("printer offline"), "job-raffle-2"]
    svc, loyalty, _finance = _build_service(printer_service=printer)
    first = {"ticket_type": "raffle_ticket", "numero_boleto": "1-10-1", "raffle_id": 1}
    second = {"ticket_type": "raffle_ticket", "numero_boleto": "1-10-2", "raffle_id": 1}
    loyalty.process_raffles_for_sale.return_value = [
        {"raffle": "Navidad SPJ", "numero_boleto": "1-10-1", "raffle_ticket": first},
        {"raffle": "Navidad SPJ", "numero_boleto": "1-10-2", "raffle_ticket": second},
    ]

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
    assert printer.print_raffle_ticket.call_count == 2


def test_sale_does_not_duplicate_raffle_ticket_prints_when_retry_returns_existing_snapshot_once():
    printer = MagicMock()
    printer.print_raffle_ticket.return_value = "job-raffle-1"
    svc, loyalty, _finance = _build_service(printer_service=printer)
    payload = {"ticket_type": "raffle_ticket", "numero_boleto": "1-10-1", "raffle_id": 1}
    loyalty.process_raffles_for_sale.side_effect = [
        [{"raffle": "Navidad SPJ", "numero_boleto": "1-10-1", "raffle_ticket": payload}],
        [],
    ]

    for _ in range(2):
        svc.execute_sale(
            branch_id=1,
            user="cajero",
            items=[{"product_id": 1, "qty": 1, "unit_price": 100.0}],
            payment_method="Efectivo",
            amount_paid=100.0,
            client_id=1,
        )

    printer.print_raffle_ticket.assert_called_once_with(payload)


def test_sale_respects_raffle_ticket_auto_print_config():
    printer = MagicMock()
    svc, loyalty, _finance = _build_service(printer_service=printer, auto_print="0")
    payload = {"ticket_type": "raffle_ticket", "numero_boleto": "1-10-1", "raffle_id": 1}
    loyalty.process_raffles_for_sale.return_value = [
        {"raffle": "Navidad SPJ", "numero_boleto": "1-10-1", "raffle_ticket": payload}
    ]

    svc.execute_sale(
        branch_id=1,
        user="cajero",
        items=[{"product_id": 1, "qty": 1, "unit_price": 100.0}],
        payment_method="Efectivo",
        amount_paid=100.0,
        client_id=1,
    )

    printer.print_raffle_ticket.assert_not_called()
