"""Efectivo en poder de repartidores (SDLC-ORD-001).

Medido: el cobro a domicilio y la liquidación del repartidor emitían su evento
sin consumidor en Finanzas, y el efectivo en manos de un repartidor era
invisible para el mayor.

El ingreso NO se reconoce aquí: lo reconoce la venta (`SaleCompletedHandler`),
que lleva el efectivo a la caja registradora. Estos dos asientos sólo mueven ese
efectivo entre custodias, así que el mismo dinero nunca se cuenta dos veces:

    venta         Dr caja registradora      Cr ingresos
    cobro         Dr efectivo repartidores  Cr caja registradora
    liquidación   Dr caja general           Cr efectivo repartidores

La liquidación entra a caja general y no a la registradora porque esta sólo
recibe lo que el Corte Z le traslada después; lo que el repartidor entrega no
pasa por ningún turno. Si lo cobrado difiere de lo esperado, la diferencia se
ajusta contra la caja registradora (donde la venta dejó lo esperado) y va a
faltantes o sobrantes, las mismas cuentas de una diferencia de corte.

Sólo el efectivo genera custodia: un cobro con tarjeta o transferencia no queda
en manos del repartidor.
"""

from __future__ import annotations

from backend.application.event_handlers.finance.handler_base import FinanceEventHandler
from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.enums import JournalType, PostingPurpose
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.shared.ids import validate_uuidv7

_SOURCE_MODULE = "orders_delivery"


def _uuid(payload: dict, key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise FinanceDomainError(f"Evento de repartidor sin {key}")
    try:
        validate_uuidv7(value)
    except ValueError as exc:
        raise FinanceDomainError(f"Evento de repartidor con {key} inválido") from exc
    return value


class DriverCashCollectedHandler(FinanceEventHandler):
    event_name = "DELIVERY_CASH_COLLECTION_RECORDED"

    def __init__(self, connection) -> None:
        super().__init__(connection)
        self._engine = PostingEngine()

    def _handle(self, uow, payload: dict) -> None:
        if payload.get("payment_method") != "CASH":
            return
        currency = self.currency(payload)
        amount = self.money(payload, "collected_amount", currency)
        if not amount.is_positive():
            return   # cobro fallido: nadie recibió dinero
        collection_id = _uuid(payload, "collection_id")
        entry_date = self.event_date(payload)
        branch_id = payload.get("branch_id")
        custody = self.resolve_profile(uow, "DRIVER_CASH", entry_date, branch_id=branch_id)
        sale = self.resolve_profile(uow, "SALE", entry_date, branch_id=branch_id)
        self._engine.post(
            uow, JournalType.CASH, entry_date, f"Cobro de repartidor {collection_id[-8:]}",
            PostingReference(_SOURCE_MODULE, collection_id,
                             PostingPurpose.DRIVER_CASH_COLLECTION,
                             str(payload["operation_id"])),
            [LineSpec(custody.account_for("driver_cash_account_id"), debit=amount,
                      description="Efectivo en poder del repartidor"),
             LineSpec(sale.account_for("cash_account_id"), credit=amount,
                      description="Cobrado fuera del cajón")],
            currency_code=currency, branch_id=branch_id,
            source_document_type="DRIVER_CASH_COLLECTION")


class DriverSettlementClosedHandler(FinanceEventHandler):
    event_name = "DRIVER_SETTLEMENT_CLOSED"

    def __init__(self, connection) -> None:
        super().__init__(connection)
        self._engine = PostingEngine()

    def _handle(self, uow, payload: dict) -> None:
        settlement_id = _uuid(payload, "entity_id")
        currency = self.currency(payload)
        collected = self.money(payload, "cash_collected", currency)
        expected = self.money(payload, "cash_expected", currency)
        difference = collected.subtract(expected)
        if collected.is_zero() and difference.is_zero():
            return   # liquidación sin efectivo: nada cambió de custodia
        entry_date = self.event_date(payload)
        branch_id = payload.get("branch_id")
        custody = self.resolve_profile(uow, "DRIVER_CASH", entry_date, branch_id=branch_id)
        general = self.resolve_profile(uow, "CAPITAL", entry_date).account_for("cash_account_id")
        register = self.resolve_profile(
            uow, "SALE", entry_date, branch_id=branch_id).account_for("cash_account_id")
        shift = self.resolve_profile(uow, "CASH_SHIFT", entry_date)

        lines: list[LineSpec] = []
        if collected.is_positive():
            lines.append(LineSpec(general, debit=collected,
                                  description=f"Liquidación de repartidor {settlement_id[-8:]}"))
            lines.append(LineSpec(custody.account_for("driver_cash_account_id"),
                                  credit=collected,
                                  description="Efectivo entregado por el repartidor"))
        if difference.is_negative():
            lines.append(LineSpec(shift.account_for("cash_short_account_id"),
                                  debit=difference.abs(), description="Faltante de repartidor"))
            lines.append(LineSpec(register, credit=difference.abs(),
                                  description="Faltante de repartidor"))
        elif difference.is_positive():
            lines.append(LineSpec(register, debit=difference,
                                  description="Sobrante de repartidor"))
            lines.append(LineSpec(shift.account_for("cash_over_account_id"),
                                  credit=difference, description="Sobrante de repartidor"))
        self._engine.post(
            uow, JournalType.CASH, entry_date, f"Liquidación de repartidor {settlement_id[-8:]}",
            PostingReference(_SOURCE_MODULE, settlement_id,
                             PostingPurpose.DRIVER_CASH_SETTLEMENT,
                             str(payload["operation_id"])),
            lines, currency_code=currency, branch_id=branch_id,
            source_document_type="DRIVER_SETTLEMENT")
