"""Inventory-domain handlers: adjustments, waste and production."""

from __future__ import annotations

from backend.application.event_handlers.finance.handler_base import FinanceEventHandler
from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.enums import JournalType, PostingPurpose
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.posting_reference import PostingReference


class InventoryAdjustmentHandler(FinanceEventHandler):
    """INVENTORY_ADJUSTMENT_REGISTERED — values positive/negative adjustments."""

    event_name = "INVENTORY_ADJUSTMENT_REGISTERED"

    def __init__(self, connection) -> None:
        super().__init__(connection)
        self._engine = PostingEngine()

    def _handle(self, uow, payload: dict) -> None:
        currency = self.currency(payload)
        adjustment_id = str(payload.get("adjustment_id") or "")
        if not adjustment_id:
            raise FinanceDomainError("Evento de ajuste sin adjustment_id")
        entry_date = self.event_date(payload)
        amount = self.money(payload, "amount", currency)
        direction = str(payload.get("direction") or "").upper()
        if direction not in ("INCREASE", "DECREASE"):
            raise FinanceDomainError("direction debe ser INCREASE o DECREASE")

        profile = self.resolve_profile(uow, "INVENTORY", entry_date)
        inventory = profile.account_for("inventory_account_id")
        adjustment = profile.account_for("inventory_adjustment_account_id")
        if direction == "INCREASE":
            lines = [LineSpec(inventory, debit=amount, description="Ajuste de inventario (+)"),
                     LineSpec(adjustment, credit=amount, description="Contrapartida de ajuste")]
        else:
            lines = [LineSpec(adjustment, debit=amount, description="Ajuste de inventario (-)"),
                     LineSpec(inventory, credit=amount, description="Salida por ajuste")]
        self._engine.post(
            uow, JournalType.INVENTORY, entry_date, f"Ajuste de inventario {adjustment_id[:8]}",
            PostingReference("inventory", adjustment_id, PostingPurpose.INVENTORY_ADJUSTMENT,
                             str(payload["operation_id"])),
            lines, currency_code=currency, branch_id=payload.get("branch_id"),
        )


class WasteRegisteredHandler(FinanceEventHandler):
    """WASTE_REGISTERED — waste is a cost, never a cash movement."""

    event_name = "WASTE_REGISTERED"

    def __init__(self, connection) -> None:
        super().__init__(connection)
        self._engine = PostingEngine()

    def _handle(self, uow, payload: dict) -> None:
        currency = self.currency(payload)
        waste_id = str(payload.get("waste_id") or "")
        if not waste_id:
            raise FinanceDomainError("WASTE_REGISTERED sin waste_id")
        entry_date = self.event_date(payload)
        amount = self.money(payload, "amount", currency)
        profile = self.resolve_profile(uow, "INVENTORY", entry_date)
        self._engine.post(
            uow, JournalType.INVENTORY, entry_date, f"Merma {waste_id[:8]}",
            PostingReference("inventory", waste_id, PostingPurpose.WASTE,
                             str(payload["operation_id"])),
            [
                LineSpec(profile.account_for("waste_expense_account_id"), debit=amount,
                         description="Costo de merma"),
                LineSpec(profile.account_for("inventory_account_id"), credit=amount,
                         description="Salida de inventario por merma"),
            ],
            currency_code=currency, branch_id=payload.get("branch_id"),
        )


class ProductionCompletedHandler(FinanceEventHandler):
    """MEAT_PRODUCTION_COMPLETED — consumes inputs into finished inventory,
    recognizing yield loss (merma de producción) when outputs are worth less."""

    event_name = "MEAT_PRODUCTION_COMPLETED"

    def __init__(self, connection) -> None:
        super().__init__(connection)
        self._engine = PostingEngine()

    def _handle(self, uow, payload: dict) -> None:
        currency = self.currency(payload)
        production_id = str(payload.get("production_id") or "")
        if not production_id:
            raise FinanceDomainError("Evento de producción sin production_id")
        entry_date = self.event_date(payload)
        input_cost = self.money(payload, "input_cost", currency)
        output_value = self.money(payload, "output_value", currency)
        if output_value > input_cost:
            raise FinanceDomainError(
                "El valor de salida no puede exceder el costo de insumos; "
                "la producción no genera utilidad contable directa"
            )
        yield_loss = input_cost.subtract(output_value)

        profile = self.resolve_profile(uow, "INVENTORY", entry_date)
        lines = [
            LineSpec(profile.account_for("inventory_account_id"), debit=output_value,
                     description="Producto terminado"),
        ]
        if yield_loss.is_positive():
            lines.append(LineSpec(profile.account_for("waste_expense_account_id"),
                                  debit=yield_loss, description="Merma de producción"))
        lines.append(LineSpec(profile.account_for("inventory_account_id"), credit=input_cost,
                              description="Consumo de insumos"))
        self._engine.post(
            uow, JournalType.INVENTORY, entry_date, f"Producción {production_id[:8]}",
            PostingReference("production", production_id, PostingPurpose.PRODUCTION,
                             str(payload["operation_id"])),
            lines, currency_code=currency, branch_id=payload.get("branch_id"),
        )
