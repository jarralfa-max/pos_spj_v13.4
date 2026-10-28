"""Configuración financiera (§13, §22, §23, §24, §28) — cada cambio auditado.

- Parámetros (``FinanceSettings``): segregación, umbrales de doble
  autorización, tolerancias de conciliación, moneda base, cuenta de redondeo.
- Perfiles contables: se versionan por vigencia; un cambio crea la versión
  nueva desde una fecha y cierra la anterior. Nunca reexpresa asientos pasados.
- Dimensiones: centros de costo y de utilidad, proyectos (CAPEX) y departamentos.
- Impuestos: códigos, tasas con vigencia, reglas y cuenta contable.
- Monedas y tipos de cambio con vigencia.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import date, timedelta

from backend.application.services.finance.posting_engine import publish_finance_event
from backend.domain.finance.entities.cost_center import CostCenter
from backend.domain.finance.entities.currency import Currency, ExchangeRateRecord
from backend.domain.finance.entities.dimension import Department, Project
from backend.domain.finance.entities.finance_settings import FinanceSettings
from backend.domain.finance.entities.posting_profile import PostingProfile
from backend.domain.finance.entities.profit_center import ProfitCenter
from backend.domain.finance.entities.tax import TaxCode, TaxPostingProfile, TaxRate, TaxRule
from backend.domain.finance.enums import AuditAction, TaxDirection, TaxKind
from backend.domain.finance.exceptions import (
    AccountNotFoundError,
    FinanceDomainError,
    PostingProfileNotFoundError,
)
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName


class UpdateFinanceSettingsUseCase:
    def execute(self, connection, *, changes: dict, operation_id: str, updated_by: str,
                reason: str | None = None):
        with FinanceUnitOfWork(connection) as uow:
            before = uow.settings
            after = before.with_changes(**changes)
            if after.rounding_account_id and uow.accounts.get(after.rounding_account_id) is None:
                raise AccountNotFoundError("La cuenta de redondeo no existe")
            uow.settings_store.save(after, updated_by=updated_by)
            uow.audit(AuditAction.SETTINGS_UPDATED, entity_type="finance_settings",
                      entity_id="finance_settings", operation_id=operation_id,
                      user_id=updated_by, before=before.as_storage(), after=after.as_storage(),
                      reason=reason)
            publish_finance_event(uow, EventName.FINANCE_SETTINGS_UPDATED, {
                "changed": sorted(k for k in changes
                                  if getattr(before, k) != getattr(after, k)),
            }, operation_id=operation_id, entity_id=operation_id)
            return after


class UpdatePostingProfileUseCase:
    """Nueva versión del perfil desde ``effective_from`` con las cuentas dadas."""

    def execute(self, connection, *, profile_id: str, accounts: dict[str, str],
                effective_from: date, operation_id: str, updated_by: str,
                reason: str | None = None) -> PostingProfile:
        with FinanceUnitOfWork(connection) as uow:
            current = uow.posting_profiles.get(profile_id)
            if current is None:
                raise PostingProfileNotFoundError("El perfil contable no existe")
            if effective_from <= current.effective_from:
                raise FinanceDomainError(
                    "La nueva versión debe empezar después de la vigente; el pasado no se "
                    "reexpresa")
            merged = dict(current.accounts)
            for role, account_id in accounts.items():
                account = uow.accounts.get(account_id)
                if account is None:
                    raise AccountNotFoundError(f"La cuenta para {role} no existe")
                account.assert_postable()
                merged[role] = account_id
            successor = PostingProfile.create(
                current.profile_key, current.description, merged, effective_from,
                effective_to=current.effective_to, instrument_type=current.instrument_type,
                program_id=current.program_id, campaign_id=current.campaign_id,
                branch_id=current.branch_id, customer_type=current.customer_type,
                currency_code=current.currency_code, funding_party=current.funding_party)
            current.effective_to = effective_from - timedelta(days=1)
            uow.posting_profiles.update(current)
            uow.posting_profiles.save(successor)
            uow.audit(AuditAction.SETTINGS_UPDATED, entity_type="posting_profile",
                      entity_id=successor.id, operation_id=operation_id, user_id=updated_by,
                      before={"profile_id": current.id, "accounts": current.accounts},
                      after={"profile_id": successor.id, "accounts": merged,
                             "effective_from": effective_from.isoformat()}, reason=reason,
                      branch_id=current.branch_id)
            return successor


class ManageDimensionsUseCase:
    def create(self, connection, *, kind: str, code: str, name: str, operation_id: str,
               created_by: str, branch_id: str | None = None, parent_id: str | None = None,
               is_capex: bool = False, org_unit_id: str | None = None):
        with FinanceUnitOfWork(connection) as uow:
            if kind == "COST_CENTER":
                if uow.cost_centers.get_by_code(code.strip().upper()) is not None:
                    raise FinanceDomainError(f"Ya existe el centro de costo {code}")
                item = CostCenter.create(code.strip().upper(), name, parent_id=parent_id,
                                         branch_id=branch_id, org_unit_id=org_unit_id)
                uow.cost_centers.save(item)
            elif kind == "PROFIT_CENTER":
                if uow.profit_centers.get_by_code(code.strip().upper()) is not None:
                    raise FinanceDomainError(f"Ya existe el centro de utilidad {code}")
                item = ProfitCenter.create(code.strip().upper(), name, branch_id=branch_id,
                                           org_unit_id=org_unit_id)
                uow.profit_centers.save(item)
            elif kind == "PROJECT":
                if uow.dimensions.get_project_by_code(code.strip().upper()) is not None:
                    raise FinanceDomainError(f"Ya existe el proyecto {code}")
                item = Project.create(code, name, branch_id=branch_id, is_capex=is_capex)
                uow.dimensions.save_project(item)
            elif kind == "DEPARTMENT":
                if uow.dimensions.get_department_by_code(code.strip().upper()) is not None:
                    raise FinanceDomainError(f"Ya existe el departamento {code}")
                item = Department.create(code, name)
                uow.dimensions.save_department(item)
            else:
                raise FinanceDomainError(f"Dimensión desconocida: {kind}")
            uow.audit(AuditAction.SETTINGS_UPDATED, entity_type=kind.lower(), entity_id=item.id,
                      operation_id=operation_id, user_id=created_by,
                      after={"code": item.code, "name": item.name,
                             "org_unit_id": getattr(item, "org_unit_id", None)},
                      branch_id=branch_id)
            return item


class ManageTaxConfigurationUseCase:
    def create_code(self, connection, *, code: str, name: str, kind: TaxKind,
                    direction: TaxDirection, rate_percent: str, effective_from: date,
                    account_id: str, operation_id: str, created_by: str) -> TaxCode:
        with FinanceUnitOfWork(connection) as uow:
            if uow.taxes.get_code_by_code(code) is not None:
                raise FinanceDomainError(f"Ya existe el impuesto {code}")
            if uow.accounts.get(account_id) is None:
                raise AccountNotFoundError("La cuenta del impuesto no existe")
            tax_code = TaxCode.create(code, name, kind, direction)
            uow.taxes.save_code(tax_code)
            uow.taxes.save_rate(TaxRate.create(tax_code.id, rate_percent, effective_from))
            uow.taxes.save_posting_profile(TaxPostingProfile.create(tax_code.id, account_id,
                                                                    effective_from))
            uow.audit(AuditAction.TAX_CONFIGURED, entity_type="tax_code", entity_id=tax_code.id,
                      operation_id=operation_id, user_id=created_by,
                      after={"code": tax_code.code, "rate_percent": rate_percent,
                             "effective_from": effective_from.isoformat()})
            return tax_code

    def set_rate(self, connection, *, tax_code_id: str, rate_percent: str, effective_from: date,
                 operation_id: str, created_by: str) -> TaxRate:
        with FinanceUnitOfWork(connection) as uow:
            if uow.taxes.get_code(tax_code_id) is None:
                raise FinanceDomainError("El impuesto no existe")
            rate = TaxRate.create(tax_code_id, rate_percent, effective_from)
            uow.taxes.save_rate(rate)
            uow.audit(AuditAction.TAX_CONFIGURED, entity_type="tax_rate", entity_id=rate.id,
                      operation_id=operation_id, user_id=created_by,
                      after={"tax_code_id": tax_code_id, "rate_percent": rate_percent,
                             "effective_from": effective_from.isoformat()})
            return rate

    def add_rule(self, connection, *, tax_code_id: str, scope: str, scope_id: str | None,
                 effective_from: date, operation_id: str, created_by: str,
                 effective_to: date | None = None) -> TaxRule:
        with FinanceUnitOfWork(connection) as uow:
            if uow.taxes.get_code(tax_code_id) is None:
                raise FinanceDomainError("El impuesto no existe")
            rule = TaxRule.create(tax_code_id, scope, scope_id, effective_from, effective_to)
            uow.taxes.save_rule(rule)
            uow.audit(AuditAction.TAX_CONFIGURED, entity_type="tax_rule", entity_id=rule.id,
                      operation_id=operation_id, user_id=created_by,
                      after={"tax_code_id": tax_code_id, "scope": rule.scope,
                             "scope_id": rule.scope_id})
            return rule


class ManageCurrencyUseCase:
    def add_currency(self, connection, *, code: str, name: str, decimal_places: int,
                     operation_id: str, created_by: str) -> Currency:
        currency = Currency.create(code, name, decimal_places=decimal_places)
        with FinanceUnitOfWork(connection) as uow:
            if uow.currencies.get_by_code(currency.code) is not None:
                raise FinanceDomainError(f"La moneda {currency.code} ya existe")
            uow.currencies.save(currency)
            uow.audit(AuditAction.SETTINGS_UPDATED, entity_type="currency",
                      entity_id=currency.id, operation_id=operation_id, user_id=created_by,
                      after={"code": currency.code, "decimal_places": decimal_places})
        return currency

    def register_rate(self, connection, *, from_currency: str, to_currency: str, rate: str,
                      effective_date: date, operation_id: str, created_by: str,
                      source: str = "") -> ExchangeRateRecord:
        record = ExchangeRateRecord.create(from_currency, to_currency, rate, effective_date,
                                           source=source, created_by=created_by)
        with FinanceUnitOfWork(connection) as uow:
            for code in (record.from_currency, record.to_currency):
                if uow.currencies.get_by_code(code) is None:
                    raise FinanceDomainError(f"La moneda {code} no está dada de alta")
            uow.currencies.save_rate(record)
            uow.audit(AuditAction.SETTINGS_UPDATED, entity_type="exchange_rate",
                      entity_id=record.id, operation_id=operation_id, user_id=created_by,
                      after={"pair": f"{record.from_currency}/{record.to_currency}",
                             "rate": format(record.rate, "f"),
                             "effective_date": effective_date.isoformat()})
        return record


#: Parámetros editables desde la pantalla de configuración.
EDITABLE_SETTINGS = tuple(f.name for f in fields(FinanceSettings))
