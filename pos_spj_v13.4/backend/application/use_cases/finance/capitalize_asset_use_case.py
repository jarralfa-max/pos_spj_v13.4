"""CapitalizeAssetUseCase — CAPEX: alta de activo fijo (§17).

La compra de un activo NO es gasto operativo: se capitaliza.

    Pagado desde tesorería:  Dr Activo fijo / Cr Tesorería        (exige saldo)
    A crédito:               Dr Activo fijo / Cr Proveedores  + CxP en la MISMA transacción

Las cuentas salen de la categoría del activo (o del perfil FIXED_ASSET); la
vida útil se captura (nunca un número por omisión inventado).
"""

from __future__ import annotations

from datetime import date

from backend.application.services.finance.posting_engine import (
    PostingEngine,
    publish_finance_event,
)
from backend.application.use_cases.finance._support import (
    assert_available_funds,
    require_profile,
    require_treasury,
)
from backend.application.use_cases.finance.create_payable_use_case import create_payable_in
from backend.domain.finance.entities.fixed_asset import FixedAsset
from backend.domain.finance.enums import (
    AuditAction,
    FinancialDocumentType,
    JournalType,
    PostingPurpose,
    PurchaseDebitNature,
)
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName


class CapitalizeAssetUseCase:
    def __init__(self) -> None:
        self._engine = PostingEngine()

    def execute(self, connection, *, name: str, acquisition_cost: str,
                residual_value: str = "0.00", useful_life_months: int,
                capitalization_date: date, operation_id: str,
                paid_from_treasury_account_id: str | None = None,
                supplier_id: str | None = None, document_number: str = "",
                asset_code: str = "", asset_category_id: str | None = None,
                acquisition_date: date | None = None, project_id: str | None = None,
                branch_id: str | None = None, cost_center_id: str | None = None,
                currency_code: str = "MXN", created_by: str | None = None) -> FixedAsset:
        if bool(paid_from_treasury_account_id) == bool(supplier_id):
            raise FinanceDomainError(
                "Un activo se paga desde tesorería o queda a crédito de un proveedor "
                "(uno de los dos): su origen de fondos debe quedar identificado")
        with FinanceUnitOfWork(connection) as uow:
            duplicate = uow.fixed_assets.find_by_operation_id(operation_id)
            if duplicate is not None:
                return duplicate
            profile = require_profile(uow, "FIXED_ASSET", capitalization_date,
                                      branch_id=branch_id)
            category = None
            if asset_category_id:
                category = uow.fixed_assets.get_category(asset_category_id)
                if category is None:
                    raise FinanceDomainError("La categoría de activo no existe")
            if project_id and uow.dimensions.get_project(project_id) is None:
                raise FinanceDomainError("El proyecto CAPEX no existe")
            cost = Money.from_string(acquisition_cost, currency_code)
            asset = FixedAsset.create(
                name, cost, Money.from_string(residual_value, currency_code),
                useful_life_months, operation_id, asset_code=asset_code,
                asset_category_id=asset_category_id, acquisition_date=acquisition_date,
                supplier_id=supplier_id, project_id=project_id, branch_id=branch_id,
                cost_center_id=cost_center_id)
            asset.capitalize(
                capitalization_date,
                category.asset_account_id if category else profile.account_for("asset_account_id"),
                category.depreciation_expense_account_id if category
                else profile.account_for("depreciation_expense_account_id"),
                category.accumulated_depreciation_account_id if category
                else profile.account_for("accumulated_depreciation_account_id"))
            if paid_from_treasury_account_id:
                treasury = require_treasury(uow, paid_from_treasury_account_id,
                                            currency_code=cost.currency_code)
                assert_available_funds(uow, treasury, cost)
                credit_account = treasury.ledger_account_id
            else:
                payable = create_payable_in(
                    uow, supplier_id=supplier_id, amount=cost.to_string(),
                    currency_code=cost.currency_code,
                    document_number=document_number or f"CAPEX-{asset.id[-8:]}",
                    issue_date=capitalization_date, due_date=None, branch_id=branch_id,
                    source_module="finance", source_document_id=asset.id,
                    operation_id=f"{operation_id}:payable",
                    debit_nature=PurchaseDebitNature.FIXED_ASSET)
                asset.source_document_id = payable.financial_document_id
                credit_account = profile.account_for("payable_account_id")
            uow.fixed_assets.save(asset)
            self._engine.post(
                uow, JournalType.FIXED_ASSETS, capitalization_date,
                f"Capitalización de activo {name}",
                PostingReference("finance", asset.id, PostingPurpose.ASSET_CAPITALIZATION,
                                 operation_id),
                [LineSpec(asset.asset_account_id, debit=cost, description=f"Alta de activo {name}",
                          branch_id=branch_id, cost_center_id=cost_center_id,
                          project_id=project_id, supplier_id=supplier_id),
                 LineSpec(credit_account, credit=cost, description="Origen de fondos CAPEX",
                          branch_id=branch_id, supplier_id=supplier_id)],
                currency_code=currency_code, branch_id=branch_id, created_by=created_by,
                source_document_type=FinancialDocumentType.ASSET_ACQUISITION.value)
            uow.audit(AuditAction.ASSET_CAPITALIZED, entity_type="fixed_asset",
                      entity_id=asset.id, operation_id=operation_id, user_id=created_by,
                      after={"name": name, "cost": cost.to_string(),
                             "useful_life_months": useful_life_months,
                             "asset_code": asset.asset_code, "project_id": project_id},
                      branch_id=branch_id)
            publish_finance_event(uow, EventName.FIXED_ASSET_CAPITALIZED, {
                "asset_id": asset.id, "name": name, "cost": cost.to_string(),
                "project_id": project_id,
            }, operation_id=operation_id, entity_id=asset.id, branch_id=branch_id)
            return asset
