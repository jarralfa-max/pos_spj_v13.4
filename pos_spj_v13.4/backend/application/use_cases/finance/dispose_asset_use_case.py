"""DisposeAssetUseCase — baja, venta o castigo de un activo fijo (§17).

Se cancelan costo y depreciación acumulada; el valor en libros es pérdida
salvo en una venta, donde se compara con lo cobrado:

    Dr Depreciación acumulada
    Dr Tesorería (lo cobrado, sólo en venta)
    Dr Pérdida en baja/venta (si el valor en libros > lo cobrado)
        Cr Activo fijo (costo)
        Cr Utilidad en venta de activos (si lo cobrado > valor en libros)
"""

from __future__ import annotations

from datetime import date

from backend.application.services.finance.posting_engine import (
    PostingEngine,
    publish_finance_event,
)
from backend.application.use_cases.finance._support import require_profile, require_treasury
from backend.domain.finance.enums import (
    AuditAction,
    FinancialDocumentType,
    FixedAssetStatus,
    JournalType,
    PostingPurpose,
)
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName

_PURPOSE = {FixedAssetStatus.DISPOSED: PostingPurpose.ASSET_DISPOSAL,
            FixedAssetStatus.SOLD: PostingPurpose.ASSET_SALE,
            FixedAssetStatus.WRITTEN_OFF: PostingPurpose.ASSET_WRITE_OFF}
_LABEL = {FixedAssetStatus.DISPOSED: "Baja", FixedAssetStatus.SOLD: "Venta",
          FixedAssetStatus.WRITTEN_OFF: "Castigo"}


class DisposeAssetUseCase:
    def __init__(self) -> None:
        self._engine = PostingEngine()

    def execute(self, connection, *, asset_id: str, disposal_date: date, operation_id: str,
                outcome: FixedAssetStatus = FixedAssetStatus.DISPOSED,
                proceeds: str | None = None, treasury_account_id: str | None = None,
                reason: str = "", disposed_by: str | None = None) -> str:
        if outcome not in _PURPOSE:
            raise FinanceDomainError(f"{outcome.value} no es una forma de baja")
        if outcome is FixedAssetStatus.SOLD and not (proceeds and treasury_account_id):
            raise FinanceDomainError("Una venta indica lo cobrado y la cuenta que lo recibe")
        if outcome is not FixedAssetStatus.SOLD and proceeds:
            raise FinanceDomainError("Sólo una venta tiene importe cobrado")
        with FinanceUnitOfWork(connection) as uow:
            asset = uow.fixed_assets.get(asset_id)
            if asset is None:
                raise FinanceDomainError("El activo no existe")
            if asset.disposal_journal_entry_id:
                return asset.disposal_journal_entry_id
            profile = require_profile(uow, "FIXED_ASSET", disposal_date,
                                      branch_id=asset.branch_id)
            currency = asset.acquisition_cost.currency_code
            cash = Money.from_string(proceeds or "0", currency)
            book = asset.net_book_value()
            lines = []
            if asset.accumulated_depreciation.is_positive():
                lines.append(LineSpec(asset.accumulated_depreciation_account_id,
                                      debit=asset.accumulated_depreciation,
                                      description="Cancelación de depreciación acumulada",
                                      branch_id=asset.branch_id))
            if cash.is_positive():
                treasury = require_treasury(uow, treasury_account_id, currency_code=currency)
                lines.append(LineSpec(treasury.ledger_account_id, debit=cash,
                                      description=f"Cobro por venta de {asset.name}",
                                      branch_id=asset.branch_id))
            result = cash.subtract(book)
            if result.is_negative():
                lines.append(LineSpec(profile.account_for("asset_sale_loss_account_id"),
                                      debit=result.abs(),
                                      description=f"Pérdida por {_LABEL[outcome].lower()}",
                                      branch_id=asset.branch_id))
            lines.append(LineSpec(asset.asset_account_id, credit=asset.acquisition_cost,
                                  description=f"{_LABEL[outcome]} de activo {asset.name}",
                                  branch_id=asset.branch_id))
            if result.is_positive():
                lines.append(LineSpec(profile.account_for("asset_sale_gain_account_id"),
                                      credit=result, description="Utilidad en venta de activo",
                                      branch_id=asset.branch_id))
            entry = self._engine.post(
                uow, JournalType.FIXED_ASSETS, disposal_date,
                f"{_LABEL[outcome]} de activo {asset.name}",
                PostingReference("finance", asset.id, _PURPOSE[outcome], operation_id),
                lines, currency_code=currency, branch_id=asset.branch_id,
                created_by=disposed_by,
                source_document_type=FinancialDocumentType.ASSET_DISPOSAL.value)
            before = {"status": asset.status.value, "book_value": book.to_string()}
            asset.retire(outcome, disposal_date, entry.id, reason)
            uow.fixed_assets.update(asset)
            uow.audit(AuditAction.ASSET_CHANGED, entity_type="fixed_asset", entity_id=asset.id,
                      operation_id=operation_id, user_id=disposed_by, before=before,
                      after={"status": asset.status.value, "proceeds": cash.to_string(),
                             "result": result.to_string(), "journal_entry_id": entry.id},
                      reason=reason, branch_id=asset.branch_id)
            publish_finance_event(uow, EventName.FIXED_ASSET_DISPOSED, {
                "asset_id": asset.id, "outcome": outcome.value, "proceeds": cash.to_string(),
                "result": result.to_string(), "journal_entry_id": entry.id,
            }, operation_id=operation_id, entity_id=asset.id, branch_id=asset.branch_id)
            return entry.id


class ChangeAssetStatusUseCase:
    """Suspender (no deprecia mientras está fuera de servicio) o reanudar."""

    def suspend(self, connection, *, asset_id: str, reason: str, operation_id: str,
                actor: str) -> None:
        self._change(connection, asset_id, operation_id, actor, reason,
                     lambda asset: asset.suspend(reason))

    def resume(self, connection, *, asset_id: str, operation_id: str, actor: str) -> None:
        self._change(connection, asset_id, operation_id, actor, None,
                     lambda asset: asset.resume())

    @staticmethod
    def _change(connection, asset_id, operation_id, actor, reason, action) -> None:
        with FinanceUnitOfWork(connection) as uow:
            asset = uow.fixed_assets.get(asset_id)
            if asset is None:
                raise FinanceDomainError("El activo no existe")
            before = {"status": asset.status.value}
            action(asset)
            uow.fixed_assets.update(asset)
            uow.audit(AuditAction.ASSET_CHANGED, entity_type="fixed_asset", entity_id=asset.id,
                      operation_id=operation_id, user_id=actor, before=before,
                      after={"status": asset.status.value}, reason=reason,
                      branch_id=asset.branch_id)
