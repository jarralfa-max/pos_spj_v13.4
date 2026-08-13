"""CASH-5 configuration commands for born-clean Caja catalogs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.permissions import CashPermissions
from backend.domain.cash_register.events import cash_event_payload
from backend.infrastructure.db.repositories.cash_register.unit_of_work import CashRegisterUnitOfWork
from backend.shared.ids import new_uuid, validate_uuidv7


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class CashConfigurationResult:
    entity_id: str
    message: str


class ConfigureCashRegisterUseCase:
    """Create one effective configuration entry in the canonical Caja schema."""

    _SCOPES = {"SYSTEM", "COMPANY", "BRANCH", "REGISTER", "USER"}

    def __init__(self, authorization: CashAuthorizationPolicy) -> None:
        self._authorization = authorization

    def execute(
        self,
        connection,
        *,
        section: str,
        name: str,
        value: str,
        scope_type: str,
        scope_id: str | None,
        actor_user_id: str,
        branch_id: str,
        operation_id: str,
        effective_from: str | None = None,
        effective_to: str | None = None,
    ) -> CashConfigurationResult:
        self._authorization.require(
            user_id=actor_user_id,
            permission_code=CashPermissions.SETTINGS_MANAGE,
            branch_id=branch_id,
        )
        validate_uuidv7(actor_user_id)
        validate_uuidv7(branch_id)
        validate_uuidv7(operation_id)
        scope_type = scope_type.strip().upper()
        if scope_type not in self._SCOPES:
            raise ValueError("Alcance de configuracion de Caja invalido")
        if scope_type == "SYSTEM":
            scope_id = None
        elif not scope_id:
            raise ValueError("El alcance seleccionado requiere scope_id UUIDv7")
        else:
            validate_uuidv7(scope_id)
        name = name.strip().upper()
        value = value.strip()
        if not name or not value:
            raise ValueError("Nombre y valor de configuracion son requeridos")
        effective_from = effective_from or _now()
        entity_id = new_uuid()
        with CashRegisterUnitOfWork(connection) as uow:
            self._insert(
                uow,
                section=section,
                entity_id=entity_id,
                name=name,
                value=value,
                scope_type=scope_type,
                scope_id=scope_id,
                effective_from=effective_from,
                effective_to=effective_to,
                actor_user_id=actor_user_id,
            )
            event = cash_event_payload(
                "CASH_CONFIGURATION_CHANGED",
                operation_id=operation_id,
                entity_id=entity_id,
                branch_id=branch_id,
                user_id=actor_user_id,
                section=section,
                name=name,
                scope_type=scope_type,
                scope_id=scope_id,
            )
            uow.audit.record(
                audit_id=new_uuid(),
                action="CASH_CONFIGURATION_CHANGED",
                actor_user_id=actor_user_id,
                entity_id=entity_id,
                branch_id=branch_id,
                operation_id=operation_id,
                reason=f"{section}:{name}",
                occurred_at=event["timestamp"],
            )
            uow.events.add(event)
            uow.outbox.enqueue(event)
        return CashConfigurationResult(entity_id, "Configuracion de Caja guardada")

    def _insert(self, uow, *, section: str, entity_id: str, name: str,
                value: str, scope_type: str, scope_id: str | None,
                effective_from: str, effective_to: str | None,
                actor_user_id: str) -> None:
        if section in {"hierarchy", "validity"}:
            uow.configuration.add_setting(
                row_id=entity_id,
                setting_key=name,
                setting_value=value,
                scope_type=scope_type,
                scope_id=scope_id,
                effective_from=effective_from,
                effective_to=effective_to,
                created_by=actor_user_id,
            )
            return
        if section == "denominations":
            amount = Decimal(value)
            uow.configuration.add_denomination(
                row_id=entity_id,
                currency_code=scope_id or "MXN",
                value=str(amount),
                label=f"{scope_id or 'MXN'} {amount}",
                sort_order=0,
                effective_from=effective_from,
                effective_to=effective_to,
            )
            return
        if section == "payment_methods":
            uow.configuration.add_payment_method(
                row_id=entity_id,
                code=name,
                display_name=value,
                affects_physical_cash=name == "CASH",
                effective_from=effective_from,
                effective_to=effective_to,
            )
            return
        if section == "limits":
            threshold, _, cap = value.partition("/")
            threshold = str(Decimal(threshold.strip()))
            cap = str(Decimal((cap or threshold).strip()))
            uow.configuration.add_operation_limit(
                row_id=entity_id,
                operation_type=name,
                approval_threshold=threshold,
                hard_cap=cap,
                scope_type=scope_type,
                scope_id=scope_id,
                effective_from=effective_from,
                effective_to=effective_to,
                created_by=actor_user_id,
            )
            return
        if section == "alerts":
            uow.configuration.add_alert_rule(
                row_id=entity_id,
                event_name=name,
                severity=value.upper(),
                channels=("IN_APP",),
                scope_type=scope_type,
                scope_id=scope_id,
                effective_from=effective_from,
                effective_to=effective_to,
            )
            return
        raise ValueError(f"Seccion de configuracion no mutable en este flujo: {section}")
