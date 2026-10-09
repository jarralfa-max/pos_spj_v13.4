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
    CashMovementReason,
    CashOperationLimit,
    CashPaymentMethod,
    CashScopedSetting,
    CashWhatsAppRecipient,
    ConfigurationScope,
)
from backend.domain.cash_register.difference_policy import CashDifferencePolicy
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


@dataclass(frozen=True, slots=True)
class ConfigureCashMovementReasonCommand:
    """§14/§15: el motivo de un ingreso, retiro o retiro a bóveda."""
    code: str
    display_name: str
    movement_type: str
    requires_authorization: bool = False
    window: CashConfigurationWindow = CashConfigurationWindow()


@dataclass(frozen=True, slots=True)
class ConfigureCashDifferencePolicyCommand:
    """§21: tolerancias de diferencias. Sin una vigente el Corte Z no procede
    si hay faltante o sobrante."""
    tolerance: Decimal
    critical_threshold: Decimal
    recurrence_window_days: int
    recurrence_threshold: int
    channels: tuple[str, ...]
    scope: CashConfigurationScope
    window: CashConfigurationWindow = CashConfigurationWindow()


CashConfigurationCommand = (
    ConfigureCashSettingCommand
    | ConfigureCashDenominationCommand
    | ConfigureCashPaymentMethodCommand
    | ConfigureCashOperationLimitCommand
    | ConfigureCashAlertRuleCommand
    | ConfigureCashMovementReasonCommand
    | ConfigureCashDifferencePolicyCommand
)

#: Secciones cuyas filas se pueden dar de baja (cerrar su vigencia).
DEACTIVATABLE_SECTIONS = {
    "denominations": "cash_denominations",
    "payment_methods": "cash_payment_methods",
    "limits": "cash_operation_limits",
    "alerts": "cash_alert_rules",
    "reasons": "cash_movement_reasons",
    "tolerances": "cash_difference_policies",
}


class ConfigureCashRegisterUseCase:
    """Create one effective configuration entry in the canonical Caja schema."""

    def __init__(self, authorization: CashAuthorizationPolicy) -> None:
        self._authorization = authorization

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
        if isinstance(command, ConfigureCashMovementReasonCommand):
            return "reasons", command.code.strip().upper(), None, command.window
        if isinstance(command, ConfigureCashDifferencePolicyCommand):
            return "tolerances", "DIFFERENCE_POLICY", command.scope, command.window
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
            uow.configuration.close_previous_denomination(
                currency_code=denomination.currency_code, value=str(denomination.value),
                effective_from=effective_from)
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
            uow.configuration.close_previous_limit(
                operation_type=limit.operation_type,
                scope_type=command.scope.scope_type.value, scope_id=command.scope.scope_id,
                effective_from=effective_from)
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
            uow.configuration.supersede_alert_rule(
                new_rule_id=entity_id, event_name=alert.event_name,
                scope_type=command.scope.scope_type.value, scope_id=command.scope.scope_id,
                effective_from=effective_from)
            return
        if isinstance(command, ConfigureCashMovementReasonCommand):
            reason = CashMovementReason.create(
                command.code, command.display_name, command.movement_type,
                requires_authorization=command.requires_authorization)
            uow.configuration.close_previous_reason(
                code=reason.code, effective_from=effective_from)
            uow.configuration.add_movement_reason(
                row_id=entity_id, code=reason.code, display_name=reason.display_name,
                movement_type=reason.movement_type,
                requires_authorization=reason.requires_authorization,
                effective_from=effective_from, effective_to=effective_to)
            return
        if isinstance(command, ConfigureCashDifferencePolicyCommand):
            if int(command.recurrence_window_days) < 1:
                raise ValueError("La ventana de reincidencia debe ser de al menos un dia")
            policy = CashDifferencePolicy(
                tolerance=Decimal(command.tolerance),
                critical_threshold=Decimal(command.critical_threshold),
                recurrence_threshold=int(command.recurrence_threshold),
                channels=tuple(command.channels))
            uow.configuration.close_previous_difference_policy(
                scope_type=command.scope.scope_type.value, scope_id=command.scope.scope_id,
                effective_from=effective_from)
            uow.configuration.add_difference_policy(
                row_id=entity_id, tolerance=str(policy.tolerance),
                critical_threshold=str(policy.critical_threshold),
                recurrence_window_days=int(command.recurrence_window_days),
                recurrence_threshold=policy.recurrence_threshold, channels=policy.channels,
                scope_type=command.scope.scope_type.value, scope_id=command.scope.scope_id,
                effective_from=effective_from, effective_to=effective_to)
            return
        raise TypeError("Comando de configuracion de Caja no soportado")


class DeactivateCashConfigurationUseCase:
    """Da de baja una fila de catálogo cerrando su vigencia (nunca la borra:
    cortes y conteos pasados siguen apuntando a ella)."""

    def __init__(self, authorization: CashAuthorizationPolicy) -> None:
        self._authorization = authorization

    def execute(self, connection, *, section: str, row_id: str, actor_user_id: str,
                branch_id: str, operation_id: str) -> CashConfigurationResult:
        self._authorization.require(
            user_id=actor_user_id, permission_code=CashPermissions.SETTINGS_MANAGE,
            branch_id=branch_id)
        table = DEACTIVATABLE_SECTIONS.get(section)
        if table is None:
            raise ValueError("Esta seccion no admite baja de registros")
        validate_uuidv7(row_id)
        now = _now()
        with CashRegisterUnitOfWork(connection) as uow:
            if not uow.configuration.end_validity(table=table, row_id=row_id, at=now):
                raise ValueError("El registro ya no esta vigente o no existe")
            event = cash_event_payload(
                "CASH_CONFIGURATION_CHANGED", operation_id=operation_id, entity_id=row_id,
                branch_id=branch_id, user_id=actor_user_id, section=section,
                name="DEACTIVATED", scope_type="SYSTEM", scope_id=None)
            uow.audit.record(
                audit_id=new_uuid(), action="CASH_CONFIGURATION_DEACTIVATED",
                actor_user_id=actor_user_id, entity_id=row_id, branch_id=branch_id,
                operation_id=operation_id, reason=f"{section}:baja",
                occurred_at=event["timestamp"])
            uow.events.add(event)
            uow.outbox.enqueue(event)
        return CashConfigurationResult(row_id, "Registro dado de baja")


def _parse_effective(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Las vigencias de configuracion requieren zona horaria")
    return parsed


def build_cash_catalog_command(section: str, fields: dict) -> CashConfigurationCommand:
    """Comando tipado a partir de los campos de la pantalla (ya `Decimal`/`int`).

    Alcance SYSTEM: los catálogos de Caja aplican a toda la instalación; un
    alcance por sucursal o caja se agregará cuando exista quien lo lea.
    """
    system = CashConfigurationScope(ConfigurationScope.SYSTEM)
    if section == "denominations":
        return ConfigureCashDenominationCommand(
            currency_code=str(fields["currency_code"]), value=Decimal(fields["value"]),
            display_name=str(fields["display_name"]), sort_order=int(fields["sort_order"]))
    if section == "reasons":
        return ConfigureCashMovementReasonCommand(
            code=str(fields["code"]), display_name=str(fields["display_name"]),
            movement_type=str(fields["movement_type"]),
            requires_authorization=bool(fields.get("requires_authorization")))
    if section == "limits":
        return ConfigureCashOperationLimitCommand(
            operation_type=str(fields["operation_type"]),
            approval_threshold=Decimal(fields["approval_threshold"]),
            hard_cap=Decimal(fields["hard_cap"]), scope=system)
    if section == "tolerances":
        return ConfigureCashDifferencePolicyCommand(
            tolerance=Decimal(fields["tolerance"]),
            critical_threshold=Decimal(fields["critical_threshold"]),
            recurrence_window_days=int(fields["recurrence_window_days"]),
            recurrence_threshold=int(fields["recurrence_threshold"]),
            channels=tuple(fields["channels"]), scope=system)
    if section == "alerts":
        return ConfigureCashAlertRuleCommand(
            event_name=str(fields["event_name"]), severity=str(fields["severity"]),
            channels=tuple(fields["channels"]), scope=system)
    raise ValueError(f"Seccion de configuracion sin alta tipada: {section}")


class ManageCashAlertRecipientUseCase:
    """Destinatarios de los avisos de Caja (CASH-26 bloque 2, 2026-10-07).

    Las reglas de aviso tenían escritor y sus destinatarios NO: ningún aviso
    llegaba a nadie. Un destinatario es un usuario activo (aviso en el
    sistema) o un teléfono E.164 (WhatsApp); sólo en un canal que la regla use.
    """

    def __init__(self, authorization: CashAuthorizationPolicy) -> None:
        self._authorization = authorization

    def add(self, connection, *, alert_rule_id: str, channel: str, address: str,
            display_name: str, actor_user_id: str, branch_id: str,
            operation_id: str) -> CashConfigurationResult:
        self._authorization.require(
            user_id=actor_user_id, permission_code=CashPermissions.SETTINGS_MANAGE,
            branch_id=branch_id)
        validate_uuidv7(alert_rule_id)
        channel = channel.upper()
        address = address.strip()
        with CashRegisterUnitOfWork(connection) as uow:
            rule = uow.configuration.active_alert_rule(alert_rule_id, at=_now())
            if rule is None:
                raise ValueError("El aviso seleccionado ya no esta vigente")
            if channel not in rule["channels"]:
                raise ValueError("Ese aviso no se envia por el canal elegido")
            if channel == "IN_APP":
                validate_uuidv7(address)
                name = uow.configuration.user_display_name(address)
                if name is None:
                    raise ValueError("El usuario no existe o esta inactivo")
                display_name = display_name.strip() or name
            elif channel == "WHATSAPP":
                CashWhatsAppRecipient.create(rule["event_name"], address)
                if not display_name.strip():
                    raise ValueError("Escribe el nombre de quien recibe el WhatsApp")
            else:
                raise ValueError("Canal de aviso no soportado")
            row_id = uow.configuration.add_alert_recipient(
                row_id=new_uuid(), alert_rule_id=alert_rule_id, channel=channel,
                address=address, display_name=display_name.strip())
            self._record(uow, row_id=row_id, action="CASH_ALERT_RECIPIENT_ADDED",
                         actor_user_id=actor_user_id, branch_id=branch_id,
                         operation_id=operation_id, detail=f"{channel}:{rule['event_name']}")
        return CashConfigurationResult(row_id, "Destinatario agregado")

    def deactivate(self, connection, *, row_id: str, actor_user_id: str, branch_id: str,
                   operation_id: str) -> CashConfigurationResult:
        self._authorization.require(
            user_id=actor_user_id, permission_code=CashPermissions.SETTINGS_MANAGE,
            branch_id=branch_id)
        validate_uuidv7(row_id)
        with CashRegisterUnitOfWork(connection) as uow:
            if not uow.configuration.deactivate_alert_recipient(row_id):
                raise ValueError("El destinatario ya estaba dado de baja o no existe")
            self._record(uow, row_id=row_id, action="CASH_ALERT_RECIPIENT_REMOVED",
                         actor_user_id=actor_user_id, branch_id=branch_id,
                         operation_id=operation_id, detail="baja")
        return CashConfigurationResult(row_id, "Destinatario dado de baja")

    @staticmethod
    def _record(uow, *, row_id: str, action: str, actor_user_id: str, branch_id: str,
                operation_id: str, detail: str) -> None:
        event = cash_event_payload(
            "CASH_CONFIGURATION_CHANGED", operation_id=operation_id, entity_id=row_id,
            branch_id=branch_id, user_id=actor_user_id, section="recipients",
            name=action, scope_type="SYSTEM", scope_id=None)
        uow.audit.record(
            audit_id=new_uuid(), action=action, actor_user_id=actor_user_id,
            entity_id=row_id, branch_id=branch_id, operation_id=operation_id,
            reason=detail, occurred_at=event["timestamp"])
        uow.events.add(event)
        uow.outbox.enqueue(event)
