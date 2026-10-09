"""CASH_SHIFT_CLOSED handler — Treasury consumes cash-register cuts.

Caja owns the shift (apertura, arqueo, corte Z); Finance recognizes the
economic result: the cash that Sales booked into the register account moves
to general cash, and over/short differences are posted explicitly — never
silently absorbed.

CASH-26 (2026-10-07): la cuenta de la caja registradora SÓLO recibe lo que
Ventas asienta (cobros en efectivo, reembolsos y reversos). Fondo, ingresos,
retiros y retiros a bóveda son custodia entre la caja y el efectivo general y
no se asientan uno por uno. Hasta hoy este manejador acreditaba la caja por el
`expected_cash` entero (fondo y custodia incluidos): cada turno habría dejado
un residuo en la cuenta de la caja. Ahora acredita `sales_cash` y lleva al
efectivo general `sales_cash + diferencia`.
"""

from __future__ import annotations

from datetime import date

from backend.application.event_handlers.finance.handler_base import FinanceEventHandler
from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.enums import JournalType, PostingPurpose
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.posting_reference import PostingReference


class CashShiftClosedHandler(FinanceEventHandler):
    """Compatibility class now consuming the canonical Z-cut event."""
    event_name = "CASH_Z_CUT_GENERATED"

    def __init__(self, connection) -> None:
        super().__init__(connection)
        self._engine = PostingEngine()

    def _handle(self, uow, payload: dict) -> None:
        currency = self.currency(payload)
        shift_id = str(payload.get("shift_id") or "")
        if not shift_id:
            raise FinanceDomainError("CASH_SHIFT_CLOSED sin shift_id")
        # El día del turno (§33), no el día UTC del evento: un Z después de las
        # 18:00 en México caía al día siguiente (y a fin de mes, en otro periodo).
        business_date = str(payload.get("business_date") or "").strip()
        entry_date = (date.fromisoformat(business_date) if business_date
                      else self.event_date(payload))
        branch_id = payload.get("branch_id")

        expected_cash = self.money(payload, "expected_cash", currency)
        counted_cash = self.money(payload, "counted_cash", currency)
        sales_cash = self.money(payload, "sales_cash", currency)
        difference = counted_cash.subtract(expected_cash)
        to_general = sales_cash.add(difference)

        profile = self.resolve_profile(uow, "CASH_SHIFT", entry_date)
        register_account = profile.account_for("cash_account_id")       # POS register
        general_cash = self.resolve_profile(uow, "CAPITAL", entry_date).account_for("cash_account_id")

        lines: list[LineSpec] = []
        if to_general.is_positive():
            lines.append(LineSpec(general_cash, debit=to_general,
                                  description=f"Efectivo de ventas del corte {shift_id[:8]}"))
        if difference.is_negative():
            lines.append(LineSpec(profile.account_for("cash_over_short_account_id"),
                                  debit=difference.abs(), description="Faltante de caja"))
        if sales_cash.is_negative():
            lines.append(LineSpec(register_account, debit=sales_cash.abs(),
                                  description=f"Reembolsos netos del turno {shift_id[:8]}"))
        if sales_cash.is_positive():
            lines.append(LineSpec(register_account, credit=sales_cash,
                                  description=f"Vaciado de caja registradora {shift_id[:8]}"))
        if difference.is_positive():
            lines.append(LineSpec(profile.account_for("breakage_income_account_id"),
                                  credit=difference, description="Sobrante de caja"))
        if to_general.is_negative():
            lines.append(LineSpec(general_cash, credit=to_general.abs(),
                                  description=f"Efectivo general repone el turno {shift_id[:8]}"))
        if not lines:
            return

        self._engine.post(
            uow, JournalType.CASH, entry_date, f"Corte de caja {shift_id[:8]}",
            PostingReference("cash", shift_id, PostingPurpose.CASH_SHIFT_CLOSE,
                             str(payload["operation_id"])),
            lines, currency_code=currency, branch_id=branch_id,
        )
