"""Activos que Compras ya reconoció en el mayor (SDLC-FIN-002).

El puente de Compras carga la cuenta de activo contra CxP o tesorería: el costo y
su origen de fondos ya están contabilizados. Aquí sólo se lleva ese hecho al
auxiliar, sin otro asiento:

- ``register_purchased_asset_in``: alta automática, en la unidad de trabajo del
  puente. Nace en DRAFT porque Compras no sabe la vida útil.
- ``CompletePurchasedAssetUseCase``: se actualiza hasta completar (decisión del
  responsable, 2026-11-05). Con vida útil queda ACTIVO y empieza a depreciar.
- ``reduce_purchased_asset_in``: una devolución o reverso de Compras alcanza al
  auxiliar para que no siga depreciando lo que ya salió del mayor.
"""

from __future__ import annotations

import logging
from datetime import date

from backend.application.services.finance.posting_engine import publish_finance_event
from backend.application.use_cases.finance._support import require_profile
from backend.domain.finance.entities.fixed_asset import FixedAsset
from backend.domain.finance.enums import AuditAction, FixedAssetStatus
from backend.domain.finance.exceptions import AssetNotActiveError, FinanceDomainError
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName

logger = logging.getLogger("spj.finance.purchased_asset")

#: Naturaleza de Compras que se reconoce en la cuenta de activo fijo.
ASSET_NATURE = "ASSET"


def register_purchased_asset_in(uow: FinanceUnitOfWork, profile, payload: dict, *,
                                document_id: str, document_number: str, issue_date: date,
                                currency_code: str, operation_id: str,
                                branch_id: str | None) -> FixedAsset | None:
    """Alta en el auxiliar del subtotal ASSET de un documento. Idempotente por
    documento. El costo es el mismo importe que el puente cargó a la cuenta."""
    subtotal = (payload.get("nature_subtotals") or {}).get(ASSET_NATURE)
    if subtotal is None:
        return None
    cost = Money.from_string(str(subtotal), currency_code)
    if not cost.is_positive():
        return None
    existing = uow.fixed_assets.find_by_source_document(document_id)
    if existing is not None:
        return existing
    asset = FixedAsset.from_recognized_purchase(
        f"Activo de compra {document_number}", cost, f"{operation_id}:asset",
        asset_account_id=profile.account_for("asset_account_id"),
        source_document_id=document_id, source_document_number=document_number,
        acquisition_date=issue_date, supplier_id=payload.get("supplier_id") or None,
        branch_id=branch_id)
    uow.fixed_assets.save(asset)
    uow.audit(AuditAction.ASSET_CHANGED, entity_type="fixed_asset", entity_id=asset.id,
              operation_id=asset.operation_id, user_id=payload.get("user_id"),
              after={"status": asset.status.value, "cost": cost.to_string(),
                     "source_document_number": document_number},
              reason="Alta automática de un activo reconocido por Compras",
              branch_id=branch_id)
    return asset


def reduce_purchased_asset_in(uow: FinanceUnitOfWork, source_document_ids: list[str],
                              amount: Money | None, *, on_date: date, journal_entry_id: str,
                              reason: str, operation_id: str, actor: str | None) -> None:
    """Descuenta del auxiliar lo que Compras devolvió o revirtió (``amount`` nulo:
    todo el activo). No revierte el asiento de Compras por un activo ya depreciado:
    el mayor ya bajó, así que el activo queda para una baja formal y se avisa."""
    remaining = amount
    for document_id in source_document_ids:
        if remaining is not None and not remaining.is_positive():
            return
        asset = uow.fixed_assets.find_by_source_document(document_id)
        if asset is None:
            continue
        cost = asset.acquisition_cost
        applied = cost if remaining is None or remaining > cost else remaining
        before = {"status": asset.status.value, "cost": cost.to_string()}
        try:
            asset.reverse_recognition(applied, on_date, journal_entry_id, reason)
        except (AssetNotActiveError, FinanceDomainError) as exc:
            logger.error("Activo %s no ajustado tras la devolución de Compras: %s", asset.id, exc)
            continue
        uow.fixed_assets.update(asset)
        uow.audit(AuditAction.ASSET_CHANGED, entity_type="fixed_asset", entity_id=asset.id,
                  operation_id=operation_id, user_id=actor, before=before,
                  after={"status": asset.status.value,
                         "cost": asset.acquisition_cost.to_string(),
                         "journal_entry_id": journal_entry_id},
                  reason=reason, branch_id=asset.branch_id)
        if remaining is not None:
            remaining = remaining.subtract(applied)


class CompletePurchasedAssetUseCase:
    """Guarda lo capturado; con vida útil activa el activo. Nunca asienta."""

    def execute(self, connection, *, asset_id: str, operation_id: str,
                name: str | None = None, asset_code: str | None = None,
                asset_category_id: str | None = None, residual_value: str | None = None,
                useful_life_months: int | None = None,
                capitalization_date: date | None = None, project_id: str | None = None,
                cost_center_id: str | None = None,
                completed_by: str | None = None) -> FixedAsset:
        with FinanceUnitOfWork(connection) as uow:
            asset = uow.fixed_assets.get(asset_id)
            if asset is None:
                raise FinanceDomainError("El activo no existe")
            category = None
            if asset_category_id:
                category = uow.fixed_assets.get_category(asset_category_id)
                if category is None:
                    raise FinanceDomainError("La categoría de activo no existe")
            if project_id and uow.dimensions.get_project(project_id) is None:
                raise FinanceDomainError("El proyecto CAPEX no existe")
            if not useful_life_months and category is not None:
                useful_life_months = category.default_useful_life_months
            currency = asset.acquisition_cost.currency_code
            before = {"status": asset.status.value, "name": asset.name,
                      "useful_life_months": asset.useful_life_months}
            asset.update_pending_data(
                name=name, asset_code=asset_code, asset_category_id=asset_category_id,
                residual_value=(Money.from_string(residual_value, currency)
                                if residual_value not in (None, "") else None),
                useful_life_months=useful_life_months or None,
                project_id=project_id, cost_center_id=cost_center_id)
            activated = asset.useful_life_months > 0
            if activated:
                start = capitalization_date or asset.acquisition_date
                profile = require_profile(uow, "FIXED_ASSET", start, branch_id=asset.branch_id)
                asset.capitalize(
                    start, asset.asset_account_id,
                    category.depreciation_expense_account_id if category
                    else profile.account_for("depreciation_expense_account_id"),
                    category.accumulated_depreciation_account_id if category
                    else profile.account_for("accumulated_depreciation_account_id"))
            uow.fixed_assets.update(asset)
            uow.audit(AuditAction.ASSET_CAPITALIZED if activated else AuditAction.ASSET_CHANGED,
                      entity_type="fixed_asset", entity_id=asset.id, operation_id=operation_id,
                      user_id=completed_by, before=before,
                      after={"status": asset.status.value, "name": asset.name,
                             "useful_life_months": asset.useful_life_months,
                             "asset_code": asset.asset_code},
                      branch_id=asset.branch_id)
            if activated:
                publish_finance_event(uow, EventName.FIXED_ASSET_CAPITALIZED, {
                    "asset_id": asset.id, "name": asset.name,
                    "cost": asset.acquisition_cost.to_string(),
                    "project_id": asset.project_id,
                }, operation_id=operation_id, entity_id=asset.id, branch_id=asset.branch_id)
            return asset
