"""Crédito del proveedor en Compras (2026-10-15).

MEDIDO en la base real: la compra rápida dejaba elegir «Crédito de proveedor» con
cualquier proveedor, no miraba su límite y no nacía ninguna cuenta por pagar —
4 compras a crédito recibidas ($9,066) y 0 CxP. Este servicio es el ÚNICO lugar
donde Compras decide:

* si el proveedor tiene crédito (``supplier_commercial_terms.is_credit``, de la
  pestaña «Condiciones» de Proveedores; sin condiciones = contado);
* cuánto crédito está usado (exposición) = saldo de sus CxP abiertas + compras
  rápidas a crédito comprometidas que aún no tienen CxP + órdenes de compra
  abiertas aún sin CxP (decisión del usuario, 2026-10-15);
* si una compra cabe en el límite. Límite 0 = sin límite definido.

Lee Proveedores y Finanzas por sus servicios de consulta (no sus tablas).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

#: Compras rápidas que ya comprometen crédito (borradores y pendientes de
#: autorización todavía no).
COMMITTED_DIRECT_STATUSES = ("CONFIRMED", "PARTIALLY_RECEIVED", "RECEIVED")
#: Órdenes de compra vivas (aprobadas en adelante, sin cerrar ni cancelar).
OPEN_ORDER_STATUSES = ("APPROVED", "SENT", "ACKNOWLEDGED", "PARTIALLY_LOADED", "LOADED",
                       "PARTIALLY_RECEIVED", "RECEIVED", "PARTIALLY_INVOICED", "ON_HOLD")


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else "0"))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _money(value: Decimal) -> str:
    return f"${value.quantize(Decimal('0.01')):,.2f}"


@dataclass(frozen=True, slots=True)
class SupplierCreditTerms:
    is_credit: bool
    credit_days: int
    credit_limit: Decimal
    currency_code: str

    @property
    def has_limit(self) -> bool:
        return self.credit_limit > 0


@dataclass(frozen=True, slots=True)
class CreditEvaluation:
    allowed: bool                 # el proveedor da crédito
    within_limit: bool            # la compra cabe (o no hay límite)
    terms: SupplierCreditTerms | None
    exposure: Decimal
    amount: Decimal

    @property
    def available(self) -> Decimal | None:
        if self.terms is None or not self.terms.has_limit:
            return None
        return self.terms.credit_limit - self.exposure

    def problem(self) -> str | None:
        if not self.allowed:
            return ("El proveedor no tiene crédito autorizado en sus condiciones "
                    "comerciales: compre de contado o configure el crédito en "
                    "Proveedores → Condiciones")
        if not self.within_limit:
            return (f"Excede el límite de crédito del proveedor: límite "
                    f"{_money(self.terms.credit_limit)}, usado {_money(self.exposure)}, "
                    f"esta compra {_money(self.amount)}, disponible "
                    f"{_money(max(Decimal('0'), self.available))}")
        return None

    def summary(self) -> str:
        if self.terms is None or not self.terms.is_credit:
            return "Sin crédito: sólo contado"
        text = f"Crédito {self.terms.credit_days} día(s)"
        if self.terms.has_limit:
            text += (f" · límite {_money(self.terms.credit_limit)} · usado "
                     f"{_money(self.exposure)} · disponible "
                     f"{_money(max(Decimal('0'), self.available))}")
        else:
            text += " · sin límite definido"
        return text


class SupplierCreditService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def _query(self, sql: str, params: tuple = ()) -> list[dict]:
        try:
            cursor = self._conn.execute(sql, params)
        except sqlite3.OperationalError:
            return []
        columns = [c[0] for c in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    # ── condiciones ─────────────────────────────────────────────────────────
    def terms(self, supplier_id: str) -> SupplierCreditTerms | None:
        from backend.application.suppliers.queries.supplier_read_services import (
            SupplierDetailQueryService,
        )
        try:
            row = SupplierDetailQueryService(self._conn).commercial_terms(supplier_id)
        except sqlite3.OperationalError:
            return None
        if not row:
            return None
        try:
            days = max(0, int(row.get("credit_days") or 0))
        except (TypeError, ValueError):
            days = 0
        return SupplierCreditTerms(is_credit=bool(row.get("is_credit")), credit_days=days,
                                   credit_limit=_decimal(row.get("credit_limit")),
                                   currency_code=str(row.get("currency_code") or "MXN"))

    # ── exposición ──────────────────────────────────────────────────────────
    def _payables(self):
        from backend.application.queries.finance.finance_read_services import (
            PayableQueryService,
        )
        return PayableQueryService(self._conn)

    def _recognized(self, source_ids) -> Decimal:
        try:
            return self._payables().recognized_for_sources("procurement", source_ids)
        except sqlite3.OperationalError:
            return Decimal("0")

    def exposure(self, supplier_id: str, *, currency_code: str = "MXN",
                 exclude_direct_purchase_id: str | None = None) -> Decimal:
        try:
            open_payables = self._payables().open_payables(supplier_id=supplier_id)
        except sqlite3.OperationalError:
            open_payables = []
        total = sum((_decimal(p["outstanding_amount"]) for p in open_payables), Decimal("0"))

        marks = ",".join("?" for _ in COMMITTED_DIRECT_STATUSES)
        for dp in self._query(
                "SELECT id, total, currency_code FROM direct_purchases WHERE supplier_id=?"
                f" AND payment_condition='SUPPLIER_CREDIT' AND status IN ({marks})",
                (supplier_id, *COMMITTED_DIRECT_STATUSES)):
            if dp["id"] == exclude_direct_purchase_id or \
                    (dp["currency_code"] or "MXN") != currency_code:
                continue
            sources = [r["id"] for r in self._query(
                "SELECT id FROM goods_receipts WHERE direct_purchase_id=?", (dp["id"],))]
            sources += [r["id"] for r in self._query(
                "SELECT id FROM supplier_invoices WHERE direct_purchase_id=?", (dp["id"],))]
            total += max(Decimal("0"), _decimal(dp["total"]) - self._recognized(sources))

        marks = ",".join("?" for _ in OPEN_ORDER_STATUSES)
        for po in self._query(
                "SELECT id, total, currency_code FROM purchase_orders WHERE supplier_id=?"
                f" AND status IN ({marks})", (supplier_id, *OPEN_ORDER_STATUSES)):
            if (po["currency_code"] or "MXN") != currency_code:
                continue
            invoices = [r["id"] for r in self._query(
                "SELECT id FROM supplier_invoices WHERE purchase_order_id=?", (po["id"],))]
            total += max(Decimal("0"), _decimal(po["total"]) - self._recognized(invoices))
        return total.quantize(Decimal("0.01"))

    # ── evaluación ──────────────────────────────────────────────────────────
    def evaluate(self, supplier_id: str, amount, *, currency_code: str = "MXN",
                 exclude_direct_purchase_id: str | None = None) -> CreditEvaluation:
        amount = _decimal(amount)
        terms = self.terms(supplier_id)
        if terms is None or not terms.is_credit:
            return CreditEvaluation(False, False, terms, Decimal("0"), amount)
        exposure = self.exposure(supplier_id, currency_code=currency_code,
                                 exclude_direct_purchase_id=exclude_direct_purchase_id)
        within = (not terms.has_limit) or exposure + amount <= terms.credit_limit
        return CreditEvaluation(True, within, terms, exposure, amount)
