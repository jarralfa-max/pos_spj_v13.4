"""SDLC-PAY-004 — ventas, devoluciones y compras con procesador usan el mismo
espejo.

Decisiones del responsable (2026-11-05): una sola cuenta de procesadores, la
venta carga directo a esa cuenta (no a la 1120 hasta la liquidación) y no hay
saldo histórico que reclasificar.
"""
from __future__ import annotations

import importlib
from decimal import Decimal

import pytest

from backend.application.event_handlers.finance.procurement_immediate_payment_bridge import (
    ProcurementImmediatePaymentBridgeHandler,
)
from backend.application.event_handlers.finance.sale_completed_handler import SaleCompletedHandler
from backend.application.event_handlers.finance.sale_returned_handler import SaleReturnedHandler
from backend.application.use_cases.finance.manage_treasury_account_use_case import (
    ManageTreasuryAccountUseCase,
)
from backend.domain.finance.entities.treasury_account import TreasuryAccount
from backend.domain.finance.enums import TreasuryAccountType
from backend.domain.finance.exceptions import FinanceDomainError
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.ids import new_uuid
from tests.integration.test_sales_checkout_settles_everything import (  # noqa: F401
    bus,
    conn,
    mostrador,
)


def _venta_evento(tipo, sale_id=None, monto="100"):
    return {"event_id": new_uuid(), "operation_id": new_uuid(), "branch_id": None,
            "occurred_at": "2026-11-06", "sale_id": sale_id or new_uuid(), "folio": "V-1",
            "gross_total": monto, "discount_total": "0", "net_total": monto, "tax_total": "0",
            "settlements": [{"type": tipo, "amount": monto}]}


def _devolucion_evento(tipo, monto="40"):
    return {"event_id": new_uuid(), "operation_id": new_uuid(), "branch_id": None,
            "occurred_at": "2026-11-06", "sale_id": new_uuid(), "return_id": new_uuid(),
            "folio": "V-1", "amount": monto, "gross_amount": monto, "tax_amount": "0",
            "cogs_amount": "0", "refunds": [{"type": tipo, "amount": monto}]}


def _compra_mercado_pago(conn, monto="300") -> str:
    document_id = new_uuid()
    ProcurementImmediatePaymentBridgeHandler(conn).handle({
        "source_module": "procurement", "document_id": document_id, "operation_id": new_uuid(),
        "document_number": "CD-1", "amount": monto, "currency_code": "MXN",
        "payment_source": "MERCADO_PAGO", "issue_date": "2026-11-06",
        "nature_subtotals": {"INVENTORY": monto}})
    return document_id


def _lineas(conn, source_id):
    return [(r[0], Decimal(r[1]), Decimal(r[2])) for r in conn.execute(
        "SELECT a.code, l.debit_amount, l.credit_amount FROM journal_lines l"
        " JOIN journal_entries e ON e.id=l.journal_entry_id"
        " JOIN accounts a ON a.id=l.account_id WHERE e.source_document_id=?"
        " ORDER BY l.line_index", (source_id,))]


def _balanceado(lineas):
    return sum(d for _, d, _ in lineas) == sum(c for _, _, c in lineas)


@pytest.mark.parametrize("tipo", ["PAYMENT_PROCESSOR", "CARD"])
def test_la_venta_carga_directo_la_cuenta_del_procesador(conn, tipo):
    evento = _venta_evento(tipo)
    SaleCompletedHandler(conn).handle(evento)
    lineas = _lineas(conn, evento["sale_id"])
    assert ("1115", Decimal("100"), Decimal("0")) in lineas
    assert not [l for l in lineas if l[0] == "1120"]
    assert _balanceado(lineas)


def test_la_venta_real_del_pos_tambien(conn, mostrador):
    presenter, pollo, _wh, _branch = mostrador
    sid = presenter.start_sale().entity_id
    assert presenter.add_line(sale_id=sid, product_id=pollo, quantity=Decimal("1"),
                              unit_price=Decimal("1"), product_snapshot={"name": "Pollo"}).success
    assert presenter.begin_checkout(sale_id=sid).success
    assert presenter.record_payment(sale_id=sid, method="MERCADO_PAGO", amount=Decimal("100"),
                                    reference="MP-778899").success
    assert presenter.checkout_sale(sale_id=sid).success
    lineas = _lineas(conn, sid)
    assert ("1115", Decimal("100"), Decimal("0")) in lineas
    assert not [l for l in lineas if l[0] == "1120"]


@pytest.mark.parametrize("tipo", ["PAYMENT_PROCESSOR", "CARD"])
def test_la_devolucion_abona_el_mismo_espejo(conn, tipo):
    evento = _devolucion_evento(tipo)
    SaleReturnedHandler(conn).handle(evento)
    lineas = _lineas(conn, evento["return_id"])
    assert ("1115", Decimal("0"), Decimal("40")) in lineas
    assert not [l for l in lineas if l[0] == "1120"]
    assert _balanceado(lineas)


def test_la_compra_con_mercado_pago_abona_el_mismo_espejo(conn):
    lineas = _lineas(conn, _compra_mercado_pago(conn))
    assert ("1115", Decimal("0"), Decimal("300")) in lineas
    assert _balanceado(lineas)


def test_venta_y_compra_netean_en_la_misma_cuenta(conn):
    _compra_mercado_pago(conn)
    SaleCompletedHandler(conn).handle(_venta_evento("PAYMENT_PROCESSOR", monto="500"))
    saldo = conn.execute(
        "SELECT SUM(CAST(l.debit_amount AS NUMERIC) - CAST(l.credit_amount AS NUMERIC))"
        " FROM journal_lines l JOIN accounts a ON a.id=l.account_id WHERE a.code='1115'"
    ).fetchone()[0]
    assert saldo == 200


def test_sin_cuenta_de_procesador_falla_a_la_vista_y_no_cae_en_la_puente(conn):
    conn.execute("UPDATE treasury_accounts SET active=0 WHERE account_type='PAYMENT_PROCESSOR'")
    conn.commit()
    evento = _venta_evento("PAYMENT_PROCESSOR")
    with pytest.raises(FinanceDomainError, match="procesador"):
        SaleCompletedHandler(conn).handle(evento)
    assert _lineas(conn, evento["sale_id"]) == []


def test_dos_cuentas_de_procesador_activas_no_se_adivinan(conn):
    with FinanceUnitOfWork(conn) as uow:
        espejo = next(a for a in uow.treasury.list_active()
                      if a.account_type is TreasuryAccountType.PAYMENT_PROCESSOR)
        uow.treasury.save(TreasuryAccount.create(
            "Otro", TreasuryAccountType.PAYMENT_PROCESSOR, espejo.ledger_account_id))
    with pytest.raises(FinanceDomainError, match="procesador"):
        SaleCompletedHandler(conn).handle(_venta_evento("CARD"))


def test_no_se_puede_dar_de_alta_una_segunda_cuenta_de_procesador(conn):
    with FinanceUnitOfWork(conn) as uow:
        espejo = next(a for a in uow.treasury.list_active()
                      if a.account_type is TreasuryAccountType.PAYMENT_PROCESSOR)
    with pytest.raises(FinanceDomainError, match="una sola"):
        ManageTreasuryAccountUseCase().create(
            conn, name="Mercado Pago 2", account_type=TreasuryAccountType.PAYMENT_PROCESSOR,
            ledger_account_id=espejo.ledger_account_id, operation_id=new_uuid(),
            created_by=new_uuid())


def test_la_cuenta_sembrada_dice_lo_que_es(conn):
    nombre = conn.execute("SELECT name FROM treasury_accounts"
                          " WHERE account_type='PAYMENT_PROCESSOR'").fetchone()[0]
    assert nombre == "Procesadores de pago (Mercado Pago y tarjetas)"


def test_migracion_renombra_la_cuenta_sembrada_y_es_idempotente(conn):
    conn.execute("UPDATE treasury_accounts SET name='Procesador de tarjetas'"
                 " WHERE account_type='PAYMENT_PROCESSOR'")
    conn.commit()
    migracion = importlib.import_module("migrations.standalone.385_single_processor_account")
    migracion.run(conn)
    migracion.run(conn)
    assert conn.execute("SELECT name FROM treasury_accounts WHERE"
                        " account_type='PAYMENT_PROCESSOR'").fetchone()[0].startswith(
        "Procesadores de pago")
