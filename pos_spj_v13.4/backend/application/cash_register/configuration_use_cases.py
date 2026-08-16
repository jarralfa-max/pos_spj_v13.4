"""CASH-5 configuration commands for born-clean Caja catalogs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.permissions import CashPermissions
from backend.domain.cash_register.configuration import (
    CashAlertRule,
    CashDenomination,
    CashOperationLimit,
    CashPaymentMethod,
    CashScopedSetting,
    ConfigurationScope,
)
from backend.domain.cash_register.events import cash_event_payload
from backend.infrastructure.db.repositories.cash_register.unit_of_work import CashRegisterUnitOfWork
from backend.shared.ids import new_uuid, validate_uuidv7


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class CashConfigurationResult:
    entity_id: str
    message: str


@dataclass(frozen=True, slots=True)
class CashConfigurationScope:
    scope_type: ConfigurationScope
    scope_id: str | None = None

    @classmethod
    def from_values(cls, scope_type: str,
                    scope_id: str | None = None) -> "CashConfigurationScope":
        try:
            scope = ConfigurationScope(scope_type.strip().upper())
        except ValueError as exc:
            raise ValueError("Alcance de configuracion de Caja invalido") from exc
        if scope is ConfigurationScope.SYSTEM:
            if scope_id is not None and str(scope_id).strip():
                raise ValueError("El alcance SYSTEM no acepta scope_id")
            return cls(scope_type=scope, scope_id=None)
        if not scope_id:
            raise ValueError("El alcance seleccionado requiere scope_id UUIDv7")
        validate_uuidv7(scope_id)
        return cls(scope_type=scope, scope_id=scope_id)


@dataclass(frozen=True, slots=True)
class CashConfigurationWindow:
    effective_from: str | None = None
    effective_to: str | None = None


@dataclass(frozen=True, slots=True)
class ConfigureCashSettingCommand:
    section: str
    key: str
    value: str
    scope: CashConfigurationScope
    window: CashConfigurationWindow = CashConfigurationWindow()


@dataclass(frozen=True, slots=True)
class ConfigureCashDenominationCommand:
    currency_code: str
    value: Decimal
    display_name: str
    sort_order: int = 0
    window: CashConfigurationWindow = CashConfigurationWindow()


@dataclass(frozen=True, slots=True)
class ConfigureCashPaymentMethodCommand:
    code: str
    display_name: str
    affects_physical_cash: bool
    window: CashConfigurationWindow = CashConfigurationWindow()


@dataclass(frozen=True, slots=True)
class ConfigureCashOperationLimitCommand:
    operation_type: str
    approval_threshold: Decimal
    hard_cap: Decimal
    scope: CashConfigurationScope
    window: CashConfigurationWindow = CashConfigurationWindow()


@dataclass(frozen=True, slots=True)
class ConfigureCashAlertRuleCommand:
    event_name: str
    severity: str
    channels: tuple[str, ...]
    scope: CashConfigurationScope
    window: CashConfigurationWindow = CashConfigurationWindow()


CashConfigurationCommand = (
    ConfigureCashSettingCommand
    | ConfigureCashDenominationCommand
    | ConfigureCashPaymentMethodCommand
    | ConfigureCashOperationLimitCommand
    | ConfigureCashAlertRuleCommand
)


class ConfigureCashRegisterUseCase:
    """Create one effective configuration entry in the canonical Caja schema."""

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
        command = self._legacy_payload_to_command(
            section=section,
            name=name,
            value=value,
            scope_type=scope_type,
            scope_id=scope_id,
            effective_from=effective_from,
            effective_to=effective_to,
        )
        return self.execute_typed(
            connection,
            command=command,
            actor_user_id=actor_user_id,
            branch_id=branch_id,
            operation_id=operation_id,
        )

    def execute_typed(
        self,
        connection,
        *,
        command: CashConfigurationCommand,
        actor_user_id: str,
        branch_id: str,
        operation_id: str,
    ) -> CashConfigurationResult:
        self._authorization.require(
            user_id=actor_user_id,
            permission_code=CashPermissions.SETTINGS_MANAGE,
            branch_id=branch_id,
        )
        validate_uuidv7(actor_user_id)
        validate_uuidv7(branch_id)
        validate_uuidv7(operation_id)
        section, name, scope, window = self._describe(command)
        effective_from = window.effective_from or _now()
        entity_id = new_uuid()
        with CashRegisterUnitOfWork(connection) as uow:
            self._insert_typed(
                uow,
                command=command,
                entity_id=entity_id,
                effective_from=effective_from,
                effective_to=window.effective_to,
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
                scope_type=scope.scope_type.value if scope else "SYSTEM",
                scope_id=scope.scope_id if scope else None,
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

    def _legacy_payload_to_command(
        self,
        *,
        section: str,
        name: str,
        value: str,
        scope_type: str,
        scope_id: str | None,
        effective_from: str | None,
        effective_to: str | None,
    ) -> CashConfigurationCommand:
        section = section.strip().lower()
        name = name.strip().upper()
        value = value.strip()
        if not name or not value:
            raise ValueError("Nombre y valor de configuracion son requeridos")
        scope = CashConfigurationScope.from_values(scope_type, scope_id)
        window = CashConfigurationWindow(effective_from, effective_to)
        if section in {"hierarchy", "validity"}:
            return ConfigureCashSettingCommand(section, name, value, scope, window)
        if section == "denominations":
            currency_code = name if len(name) == 3 else "MXN"
            amount = Decimal(value)
            return ConfigureCashDenominationCommand(
                currency_code=currency_code,
                value=amount,
                display_name=f"{currency_code} {amount}",
                window=window,
            )
        if section == "payment_methods":
            return ConfigureCashPaymentMethodCommand(
                code=name,
                display_name=value,
                affects_physical_cash=name == "CASH",
                window=window,
            )
        if section == "limits":
            threshold, _, cap = value.partition("/")
            return ConfigureCashOperationLimitCommand(
                operation_type=name,
                approval_threshold=Decimal(threshold.strip()),
                hard_cap=Decimal((cap or threshold).strip()),
                scope=scope,
                window=window,
            )
        if section == "alerts":
            return ConfigureCashAlertRuleCommand(
                event_name=name,
                severity=value.upper(),
                channels=("IN_APP",),
                scope=scope,
                window=window,
            )
        raise ValueError(f"Seccion de configuracion no mutable en este flujo: {section}")

    def _describe(
        self,
        command: CashConfigurationCommand,
    ) -> tuple[str, str, CashConfigurationScope | None, CashConfigurationWindow]:
        if isinstance(command, ConfigureCashSettingCommand):
            return command.section, command.key.strip().upper(), command.scope, command.window
        if isinstance(command, ConfigureCashDenominationCommand):
            return "denominations", command.currency_code.strip().upper(), None, command.window
        if isinstance(command, ConfigureCashPaymentMethodCommand):
            return "payment_methods", command.code.strip().upper(), None, command.window
        if isinstance(command, ConfigureCashOperationLimitCommand):
            return "limits", command.operation_type.strip().upper(), command.scope, command.window
        if isinstance(command, ConfigureCashAlertRuleCommand):
            return "alerts", command.event_name.strip().upper(), command.scope, command.window
        raise TypeError("Comando de configuracion de Caja no soportado")

    def _insert_typed(self, uow, *, command: CashConfigurationCommand,
                      entity_id: str, effective_from: str,
                      effective_to: str | None, actor_user_id: str) -> None:
        if isinstance(command, ConfigureCashSettingCommand):
            section = command.section.strip().lower()
            if section not in {"hierarchy", "validity"}:
                raise ValueError("Ajuste tipado de Caja requiere seccion hierarchy o validity")
            effective_start = _parse_effective(effective_from)
            effective_end = _parse_effective(effective_to) if effective_to else None
            setting = CashScopedSetting.create(
                command.key,
                command.value,
                command.scope.scope_type,
                command.scope.scope_id,
                effective_start,
                effective_end,
            )
            uow.configuration.add_setting(
                row_id=entity_id,
                setting_key=setting.key.strip().upper(),
                setting_value=setting.value,
                scope_type=setting.scope.value,
                scope_id=setting.scope_id,
                effective_from=effective_from,
                effective_to=effective_to,
                created_by=actor_user_id,
            )
            return
        if isinstance(command, ConfigureCashDenominationCommand):
            denomination = CashDenomination.create(
                command.currency_code,
                command.value,
                command.display_name,
                command.sort_order,
            )
            uow.configuration.add_denomination(
                row_id=entity_id,
                currency_code=denomination.currency_code,
                value=str(denomination.value),
                label=denomination.display_name,
                sort_order=denomination.sort_order,
                effective_from=effective_from,
                effective_to=effective_to,
            )
            return
        if isinstance(command, ConfigureCashPaymentMethodCommand):
            method = CashPaymentMethod.create(
                command.code,
                command.display_name,
                affects_physical_cash=command.affects_physical_cash,
            )
            uow.configuration.add_payment_method(
                row_id=entity_id,
                code=method.code,
                display_name=method.display_name,
                affects_physical_cash=method.affects_physical_cash,
                effective_from=effective_from,
                effective_to=effective_to,
            )
            return
        if isinstance(command, ConfigureCashOperationLimitCommand):
            limit = CashOperationLimit.create(
                command.operation_type,
                command.approval_threshold,
                command.hard_cap,
            )
            uow.configuration.add_operation_limit(
                row_id=entity_id,
                operation_type=limit.operation_type,
                approval_threshold=str(limit.approval_threshold),
                hard_cap=str(limit.hard_cap),
                scope_type=command.scope.scope_type.value,
                scope_id=command.scope.scope_id,
                effective_from=effective_from,
                effective_to=effective_to,
                created_by=actor_user_id,
            )
            return
        if isinstance(command, ConfigureCashAlertRuleCommand):
            alert = CashAlertRule.create(
                command.event_name,
                command.severity,
                command.channels,
            )
            uow.configuration.add_alert_rule(
                row_id=entity_id,
                event_name=alert.event_name,
                severity=alert.severity,
                channels=alert.channels,
                scope_type=command.scope.scope_type.value,
                scope_id=command.scope.scope_id,
                effective_from=effective_from,
                effective_to=effective_to,
            )
            return
        raise TypeError("Comando de configuracion de Caja no soportado")


def _parse_effective(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Las vigencias de configuracion requieren zona horaria")
    return parsed
