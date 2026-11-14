"""SDLC-PAY-003 — la referencia del procesador llega a Caja, Finanzas y ticket.

Se prueba por la composición REAL del POS: venta MP/tarjeta → Caja → Finanzas →
ticket, sin simular ninguna de las capas.
"""
from __future__ import annotations

from decimal import Decimal

from backend.application.sales.dto import SaleDTO
from backend.application.sales.integrations.finance_translator import sale_completed_to_finance
from backend.domain.sales.value_objects.sale_payment import mask_payment_reference
from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
from backend.infrastructure.integrations.sales_receipt_client import SalesReceiptClient
from backend.infrastructure.printing import sale_ticket_escpos_renderer as renderer
from backend.infrastructure.printing.ticket_template import (
    TicketTemplateEngine,
    default_ticket_template,
)
from tests.integration.test_sales_checkout_settles_everything import (  # noqa: F401
    bus,
    conn,
    mostrador,
)


def _venta(presenter, producto, *pagos):
    sid = presenter.start_sale().entity_id
    assert presenter.add_line(sale_id=sid, product_id=producto, quantity=Decimal("3"),
                              unit_price=Decimal("1"),
                              product_snapshot={"name": "Pollo"}).success
    assert presenter.begin_checkout(sale_id=sid).success
    for method, amount, reference in pagos:
        result = presenter.record_payment(sale_id=sid, method=method, amount=Decimal(amount),
                                          reference=reference)
        assert result.success, result.message
    result = presenter.checkout_sale(sale_id=sid)
    assert result.success, result.message
    return sid


def _asignaciones(conn, sid):
    return sorted(
        (r["method_type"], Decimal(r["amount"]), r["external_reference"] or "")
        for r in conn.execute(
            "SELECT a.method_type, a.amount, a.external_reference FROM payment_allocations a"
            " JOIN payment_records p ON p.id=a.payment_record_id WHERE p.sale_id=?", (sid,)))


def _lineas_debe(conn, sid):
    return sorted(
        (Decimal(r["debit_amount"]), r["description"]) for r in conn.execute(
            "SELECT l.debit_amount, l.description FROM journal_lines l"
            " JOIN journal_entries e ON e.id=l.journal_entry_id"
            " WHERE e.source_document_id=? AND e.description LIKE 'Venta %'"
            " AND CAST(l.debit_amount AS NUMERIC) > 0", (sid,)))


def test_una_asignacion_por_pago_con_su_referencia(conn, mostrador):
    presenter, pollo, _wh, _branch = mostrador
    sid = _venta(presenter, pollo, ("MERCADO_PAGO", "100", "MP-1000111"),
                 ("MERCADO_PAGO", "120", "MP-1000222"), ("CARD", "50", "AUT-345678"),
                 ("CASH", "30", None))

    assert _asignaciones(conn, sid) == [
        ("BANK_CARD", Decimal("50"), "AUT-345678"),
        ("CASH", Decimal("30"), ""),
        ("PAYMENT_PROCESSOR", Decimal("100"), "MP-1000111"),
        ("PAYMENT_PROCESSOR", Decimal("120"), "MP-1000222"),
    ]


def test_el_asiento_conserva_la_referencia_en_su_linea_y_cuadra(conn, mostrador):
    presenter, pollo, _wh, _branch = mostrador
    sid = _venta(presenter, pollo, ("MERCADO_PAGO", "100", "MP-2000111"),
                 ("MERCADO_PAGO", "120", "MP-2000222"), ("TRANSFER", "80", "RASTREO-778899"))

    debe = _lineas_debe(conn, sid)
    assert [monto for monto, _ in debe] == [Decimal("80"), Decimal("100"), Decimal("120")]
    assert "RASTREO-778899" in debe[0][1]
    assert "MP-2000111" in debe[1][1]
    assert "MP-2000222" in debe[2][1]
    entry = conn.execute("SELECT id FROM journal_entries WHERE source_document_id=?"
                         " AND description LIKE 'Venta %'", (sid,)).fetchone()
    totales = conn.execute(
        "SELECT SUM(CAST(debit_amount AS NUMERIC)), SUM(CAST(credit_amount AS NUMERIC))"
        " FROM journal_lines WHERE journal_entry_id=?", (entry[0],)).fetchone()
    assert totales[0] == totales[1] == 300


def test_el_ticket_imprime_la_referencia_enmascarada(conn, mostrador):
    presenter, pollo, _wh, _branch = mostrador
    sid = _venta(presenter, pollo, ("MERCADO_PAGO", "300", "MP-3000456"))
    sale = SaleDTO.from_entity(SaleRepository(conn).get(sid))

    receipt = SalesReceiptClient.build_receipt_data_from_sale(sale, cajero_nombre="Ana")
    payload = SalesReceiptClient._to_ticket_payload(receipt)

    assert payload["pago"]["referencias"] == [
        {"metodo": "MERCADO_PAGO", "referencia": "****0456"}]
    impreso = renderer.render_sale_ticket(payload)
    assert b"****0456" in impreso
    assert b"MP-3000456" not in impreso
    html = TicketTemplateEngine().generar_ticket(default_ticket_template(), payload)
    assert "****0456" in html
    assert "MP-3000456" not in html


def test_el_ticket_al_cobrar_tambien_la_lleva(conn, mostrador):
    presenter, pollo, _wh, _branch = mostrador
    sid = _venta(presenter, pollo, ("CARD", "300", "AUT-998877"))
    sale = SaleDTO.from_entity(SaleRepository(conn).get(sid))
    receipt = SalesReceiptClient.build_receipt_data(sale, forma_pago="CARD", cajero_nombre="Ana")
    assert receipt.payment_references == (("CARD", "****8877"),)


def test_efectivo_y_vales_no_imprimen_referencia(conn, mostrador):
    presenter, pollo, _wh, _branch = mostrador
    sid = _venta(presenter, pollo, ("CASH", "300", None))
    sale = SaleDTO.from_entity(SaleRepository(conn).get(sid))
    receipt = SalesReceiptClient.build_receipt_data_from_sale(sale, cajero_nombre="Ana")
    payload = SalesReceiptClient._to_ticket_payload(receipt)
    assert "referencias" not in payload["pago"]
    assert "****" not in TicketTemplateEngine().generar_ticket(
        default_ticket_template(), payload)


def test_mascara():
    assert mask_payment_reference("1234567890") == "****7890"
    assert mask_payment_reference("1234") == "****"
    assert mask_payment_reference("") == ""


def test_se_elimino_el_mapa_de_etiquetas_muerto():
    assert not hasattr(renderer, "PAYMENT_LABELS")


def test_el_traductor_reparte_por_referencia_y_tolera_eventos_viejos():
    base = {"total": "150", "tax_total": "0", "change": "0", "cogs_total": "0"}
    nuevo = sale_completed_to_finance({"payload": {
        **base, "payments": [{"method": "MERCADO_PAGO", "amount": "150"}],
        "payment_references": [
            {"method": "MERCADO_PAGO", "amount": "100", "reference": "A1111"},
            {"method": "MERCADO_PAGO", "amount": "50", "reference": "B2222"}]}})
    assert nuevo["settlements"] == [
        {"type": "PAYMENT_PROCESSOR", "amount": "100", "reference": "A1111"},
        {"type": "PAYMENT_PROCESSOR", "amount": "50", "reference": "B2222"}]
    viejo = sale_completed_to_finance({"payload": {
        **base, "payments": [{"method": "MERCADO_PAGO", "amount": "150"}]}})
    assert viejo["settlements"] == [{"type": "PAYMENT_PROCESSOR", "amount": "150"}]
