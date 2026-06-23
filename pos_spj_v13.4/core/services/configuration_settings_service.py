"""Application services for the Configuración module.

These services keep schema/default bootstrapping out of PyQt and provide an
explicit backend boundary for configuration reads and mutations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

CONFIGURATION_EVENT_SCHEMA_VERSION = 1

from backend.application.dto.configuracion_dtos import (
    BranchDeliveryRowDTO,
    HappyHourRuleDTO,
    MonthlyClosingSummaryDTO,
    RoleSettingsDTO,
    UserSettingsDTO,
)
from backend.infrastructure.db.unit_of_work import ConnectionUnitOfWork
from backend.shared.ids import new_uuid
from core.module_config import DEFAULT_TOGGLES
from repositories.config_repository import ConfigRepository


class SystemSettingsService:
    def __init__(self, repository: ConfigRepository) -> None:
        self._repository = repository

    def ensure_configuration_available(self) -> bool:
        return self._repository.settings_schema_is_ready()

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        return self._repository.get_setting(key, default or "")

    def get_many(self, keys: list[str], defaults: dict[str, str] | None = None) -> dict[str, str]:
        defaults = defaults or {}
        values = self._repository.get_settings(keys)
        return {key: str(values.get(key, defaults.get(key, ""))) for key in keys}

    def set_setting(self, key: str, value: Any) -> None:
        with ConnectionUnitOfWork(self._repository.connection):
            self._repository.save_setting(key, str(value))

    def save_many(self, settings: dict[str, Any]) -> None:
        with ConnectionUnitOfWork(self._repository.connection):
            for key, value in settings.items():
                self._repository.save_setting(key, str(value))


class ModuleSettingsService:
    def __init__(self, repository: ConfigRepository) -> None:
        self._repository = repository
        self._defaults = dict(DEFAULT_TOGGLES)

    def normalize_key(self, module_key: str) -> str:
        return module_key if module_key.endswith("_enabled") else f"{module_key}_enabled"

    def is_enabled(self, module_key: str) -> bool:
        key = self.normalize_key(module_key)
        return self.get_all().get(key, self._defaults.get(key, True))

    def set_enabled(self, module_key: str, enabled: bool) -> None:
        with ConnectionUnitOfWork(self._repository.connection):
            self._repository.set_module_toggle(self.normalize_key(module_key), enabled)

    def get_all(self) -> dict[str, bool]:
        toggles = dict(self._defaults)
        toggles.update(self._repository.get_module_toggles())
        return toggles


class CompanyProfileService:
    def __init__(self, repository: ConfigRepository) -> None:
        self._repository = repository

    def get_branch(self, branch_id: str) -> dict | None:
        return self._repository.get_branch(branch_id)

    def save_branch(
        self,
        *,
        name: str,
        address: str | None,
        phone: str | None,
        active: bool,
        branch_id: str | None = None,
    ) -> str:
        with ConnectionUnitOfWork(self._repository.connection):
            return self._repository.save_branch(
                name=name,
                address=address,
                phone=phone,
                active=active,
                branch_id=branch_id,
            )

    def get_branch_delivery_profile(self, branch_id: str) -> dict | None:
        return self._repository.get_branch_delivery_profile(branch_id)

    def branches_for_company_settings(self) -> list[tuple[str, str]]:
        return self._repository.branches_for_company_settings()

    def list_branch_delivery_rows(self) -> list[BranchDeliveryRowDTO]:
        return [BranchDeliveryRowDTO.from_row(row) for row in self._repository.list_branch_delivery_rows()]

    def save_branch_delivery_profile(
        self,
        *,
        name: str,
        address: str | None,
        phone: str | None,
        opening_time: str,
        closing_time: str,
        operation_days: str,
        accepts_after_hours_orders: bool,
        after_hours_message: str,
        branch_id: str | None = None,
    ) -> str:
        with ConnectionUnitOfWork(self._repository.connection):
            return self._repository.save_branch_delivery_profile(
                name=name,
                address=address,
                phone=phone,
                opening_time=opening_time,
                closing_time=closing_time,
                operation_days=operation_days,
                accepts_after_hours_orders=accepts_after_hours_orders,
                after_hours_message=after_hours_message,
                branch_id=branch_id,
            )


class SettingsApplicationService:
    """Application boundary for settings readiness and shared configuration values."""

    def __init__(self, system_settings_service: SystemSettingsService) -> None:
        self._system_settings_service = system_settings_service

    def assert_ready(self) -> None:
        if not self._system_settings_service.ensure_configuration_available():
            raise RuntimeError("Migraciones de configuración pendientes. Ejecute migrations antes de abrir Configuración.")

    def get_general_settings(self) -> dict[str, str]:
        return self._system_settings_service.get_many(
            ["impuesto_por_defecto", "requerir_admin"],
            {"impuesto_por_defecto": "0", "requerir_admin": "False"},
        )

    def save_tax_rate(self, tax_percent: float) -> None:
        self._system_settings_service.set_setting("impuesto_por_defecto", str(tax_percent))

    def save_security_requirement(self, require_admin: bool) -> None:
        self._system_settings_service.set_setting("requerir_admin", "True" if require_admin else "False")


class EmailSettingsService:
    """Application boundary for SMTP settings."""

    KEYS = ["smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_tls", "email_gerente"]

    def __init__(self, system_settings_service: SystemSettingsService) -> None:
        self._system_settings_service = system_settings_service

    def get_settings(self) -> dict[str, str]:
        return self._system_settings_service.get_many(self.KEYS, {"smtp_port": "0", "smtp_tls": "0"})

    def save_settings(self, settings: dict[str, Any]) -> None:
        self._system_settings_service.save_many({key: settings.get(key, "") for key in self.KEYS})


class PaymentProviderSettingsService:
    """Application boundary for payment provider settings."""

    MERCADO_PAGO_KEYS = ["mp_access_token", "mp_webhook_url", "mp_return_url"]

    def __init__(self, system_settings_service: SystemSettingsService) -> None:
        self._system_settings_service = system_settings_service

    def get_mercado_pago_settings(self) -> dict[str, str]:
        return self._system_settings_service.get_many(self.MERCADO_PAGO_KEYS)

    def save_mercado_pago_settings(self, settings: dict[str, Any]) -> None:
        self._system_settings_service.save_many({key: settings.get(key, "") for key in self.MERCADO_PAGO_KEYS})


class ClosingPeriodService:
    """Application boundary for monthly closing operations."""

    def __init__(self, repository: ConfigRepository) -> None:
        self._repository = repository

    def period_exists(self, period: str) -> bool:
        return self._repository.monthly_close_exists(period)

    def calculate_totals(self, start_date: str, end_date: str) -> dict[str, float]:
        return self._repository.calculate_monthly_close_totals(start_date, end_date)

    def close_period(self, *, period: str, closed_by: str, totals: dict[str, float], branch_id: str) -> None:
        with ConnectionUnitOfWork(self._repository.connection):
            self._repository.save_monthly_close(period=period, closed_by=closed_by, totals=totals, branch_id=branch_id)

    def history(self, limit: int = 24) -> list[MonthlyClosingSummaryDTO]:
        return [MonthlyClosingSummaryDTO.from_row(row) for row in self._repository.get_monthly_closures(limit=limit)]


class HappyHourSettingsService:
    """Canonical settings boundary for Happy Hour rule administration."""

    def __init__(self, repository: ConfigRepository) -> None:
        self._repository = repository

    def list_rules(self) -> list[HappyHourRuleDTO]:
        return [HappyHourRuleDTO.from_repository_dict(rule) for rule in self._repository.list_happy_hour_rules()]

    def get_rule(self, rule_id: str) -> HappyHourRuleDTO | None:
        rule = self._repository.get_happy_hour_rule(rule_id)
        return HappyHourRuleDTO.from_repository_dict(rule) if rule else None

    def save_rule(self, rule: dict[str, Any]) -> str:
        prepared = dict(rule)
        if "message" in prepared:
            prepared["mensaje_wa"] = prepared.pop("message")
        with ConnectionUnitOfWork(self._repository.connection):
            return self._repository.save_happy_hour_rule(prepared)

    def set_rule_active(self, rule_id: str, active: bool) -> None:
        with ConnectionUnitOfWork(self._repository.connection):
            self._repository.set_happy_hour_rule_active(rule_id, active)


class PermissionEventPublisher:
    """Small typed event publisher used by settings services."""

    def __init__(self, event_bus: Any | None = None) -> None:
        self._event_bus = event_bus
        self.published_events: list[Any] = []

    def _branch_id_for_event(self, payload: dict[str, Any]) -> str:
        branch_id = str(payload.get("branch_id") or payload.get("sucursal_id") or "").strip()
        if branch_id:
            return self._require_uuidv7(branch_id, "branch_id")
        return new_uuid()

    def _require_uuidv7(self, value: str, field_name: str) -> str:
        normalized = str(value or "").strip().lower()
        try:
            parsed = UUID(normalized)
        except ValueError as exc:
            raise ValueError(f"{field_name} must be a canonical lowercase UUIDv7") from exc
        if parsed.version != 7 or normalized != str(parsed):
            raise ValueError(f"{field_name} must be a canonical lowercase UUIDv7")
        return normalized

    def publish(self, event_name: str, *, operation_id: str, entity_id: str, user_name: str, payload: dict[str, Any]) -> None:
        if not operation_id:
            raise ValueError("operation_id is required")
        operation_id = self._require_uuidv7(operation_id, "operation_id")
        entity_id = self._require_uuidv7(entity_id, "entity_id")
        event = {
            "event_id": new_uuid(),
            "event_name": event_name,
            "operation_id": operation_id,
            "entity_id": entity_id,
            "branch_id": self._branch_id_for_event(payload),
            "user_name": user_name,
            "source_module": "CONFIGURATION",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "schema_version": CONFIGURATION_EVENT_SCHEMA_VERSION,
            "payload": payload,
        }
        self.published_events.append(event)
        if self._event_bus is not None:
            try:
                from backend.shared.events.event_contracts import create_domain_event
                from backend.shared.events.event_names import EventName

                self._event_bus.publish(
                    create_domain_event(
                        event_name=EventName(event_name),
                        operation_id=operation_id,
                        entity_id=entity_id,
                        branch_id=str(event["branch_id"]),
                        user_name=user_name,
                        source_module="CONFIGURATION",
                        payload=payload,
                    )
                )
            except Exception:
                self._event_bus.publish(event)


class UserManagementService:
    """Canonical user management boundary for Configuración."""

    def __init__(self, repository: ConfigRepository, event_publisher: PermissionEventPublisher | None = None) -> None:
        self._repository = repository
        self._events = event_publisher or PermissionEventPublisher()

    def list_users(self) -> list[UserSettingsDTO]:
        return [UserSettingsDTO.from_list_row(row) for row in self._repository.list_users_v13()]

    def get_user_form_data(self, user_id: str) -> UserSettingsDTO | None:
        row = self._repository.get_user_form_data(user_id)
        return UserSettingsDTO.from_form_row(user_id, row) if row else None

    def save_user(
        self,
        *,
        user_id: str | None,
        username: str,
        name: str,
        email: str,
        role: str,
        branch_id: str,
        active: bool,
        employee_id: int | None,
        password_hash: str | None,
        operation_id: str,
        actor: str,
    ) -> str:
        with ConnectionUnitOfWork(self._repository.connection) as uow:
            persisted_user_id = self._repository.save_user_v13(
                user_id=user_id,
                username=username,
                name=name,
                email=email,
                role=role,
                branch_id=branch_id,
                active=active,
                employee_id=employee_id,
                password_hash=password_hash,
            )
            uow.commit()
        self._events.publish(
            "USER_PERMISSIONS_UPDATED",
            operation_id=operation_id,
            entity_id=persisted_user_id,
            user_name=actor,
            payload={"username": username, "role": role, "branch_id": branch_id},
        )
        return persisted_user_id

    def set_user_active(self, user_id: str, active: bool, *, operation_id: str, actor: str) -> None:
        with ConnectionUnitOfWork(self._repository.connection) as uow:
            self._repository.set_user_active(user_id, active)
            username = self._repository.username_for_uuid(user_id) or ""
            uow.commit()
        self._events.publish(
            "USER_PERMISSIONS_UPDATED",
            operation_id=operation_id,
            entity_id=user_id,
            user_name=actor,
            payload={"username": username, "active": active},
        )


class RoleManagementService:
    """Canonical role management boundary for Configuración."""

    def __init__(self, repository: ConfigRepository, event_publisher: PermissionEventPublisher | None = None) -> None:
        self._repository = repository
        self._events = event_publisher or PermissionEventPublisher()

    def list_roles(self) -> list[RoleSettingsDTO]:
        return [RoleSettingsDTO.from_row(row) for row in self._repository.list_roles_v13()]

    def role_names(self) -> list[str]:
        return self._repository.role_names()

    def active_branches_for_selector(self) -> list[tuple[str, str]]:
        return self._repository.active_branches_for_selector()

    def active_employees_for_selector(self) -> list[tuple[int, str]]:
        return self._repository.active_employees_for_selector()

    def save_role(self, *, role_id: str | None, name: str, description: str, operation_id: str, actor: str) -> str:
        with ConnectionUnitOfWork(self._repository.connection) as uow:
            persisted_role_id = self._repository.save_role(role_id=role_id, name=name, description=description)
            uow.commit()
        self._events.publish(
            "ROLE_PERMISSIONS_UPDATED",
            operation_id=operation_id,
            entity_id=persisted_role_id,
            user_name=actor,
            payload={"role_name": name},
        )
        return persisted_role_id


class PermissionQueryService:
    """Read model for role permissions and audit in Configuración."""

    def __init__(self, repository: ConfigRepository) -> None:
        self._repository = repository

    def role_permissions(self, role_id: str) -> dict[tuple[str, str], bool]:
        return self._repository.role_permissions(role_id)

    def permission_codes_for_role_name(self, role_name: str) -> set[str]:
        return self._repository.permission_codes_for_role_name(role_name)

    def permission_codes_for_user(self, user_id: str, branch_id: str | None = None) -> set[str]:
        return self._repository.permission_codes_for_user(user_id, branch_id)

    def permission_matrix(self) -> list[tuple[str, list[str]]]:
        return self._repository.permission_matrix()

    def audit_log_rows(self, limit: int = 200) -> list[tuple]:
        return self._repository.audit_log_rows(limit=limit)


class ModuleAccessService:
    """Canonical module permission mutator/query with event emission."""

    def __init__(self, repository: ConfigRepository, event_publisher: PermissionEventPublisher | None = None) -> None:
        self._repository = repository
        self._events = event_publisher or PermissionEventPublisher()
        self._cache: dict[str, dict[tuple[str, str], bool]] = {}
        self._processed_operations: set[str] = set()

    def save_role_permissions(
        self,
        role_id: str,
        permissions: dict[tuple[str, str], bool],
        *,
        operation_id: str,
        actor: str,
    ) -> None:
        # operation_id idempotency: a replayed command is a no-op (no second
        # mutation, no duplicate event).
        if operation_id in self._processed_operations:
            return
        with ConnectionUnitOfWork(self._repository.connection) as uow:
            self._repository.save_role_permissions(role_id, permissions)
            role_name = self._repository.role_name_for_id(role_id) or ""
            uow.commit()
        self.invalidate_cache(role_id)
        payload = {"role_name": role_name, "permissions": {f"{m}.{a}": v for (m, a), v in permissions.items()}}
        self._events.publish(
            "ROLE_PERMISSIONS_UPDATED",
            operation_id=operation_id,
            entity_id=role_id,
            user_name=actor,
            payload=payload,
        )
        self._events.publish(
            "MODULE_ACCESS_UPDATED",
            operation_id=operation_id,
            entity_id=role_id,
            user_name=actor,
            payload={"role_name": role_name},
        )
        self._processed_operations.add(operation_id)

    def has_permission(self, role_id: str, module: str, action: str) -> bool:
        if role_id not in self._cache:
            self._cache[role_id] = self._repository.role_permissions(role_id)
        return self._cache[role_id].get((module, action), False)

    def invalidate_cache(self, role_id: str | None = None) -> None:
        if role_id is None:
            self._cache.clear()
        else:
            self._cache.pop(role_id, None)


@dataclass
class SettingsModuleServices:
    settings_application_service: SettingsApplicationService
    system_settings_service: SystemSettingsService
    company_profile_service: CompanyProfileService
    email_settings_service: EmailSettingsService
    payment_provider_settings_service: PaymentProviderSettingsService
    closing_period_service: ClosingPeriodService
    happy_hour_settings_service: HappyHourSettingsService
    user_management_service: UserManagementService
    role_management_service: RoleManagementService
    permission_query_service: PermissionQueryService
    module_access_service: ModuleAccessService
    permission_event_publisher: PermissionEventPublisher

    @classmethod
    def from_connection(cls, connection: Any, event_bus: Any | None = None) -> "SettingsModuleServices":
        repository = ConfigRepository(connection)
        system_settings_service = SystemSettingsService(repository)
        settings_application_service = SettingsApplicationService(system_settings_service)
        permission_event_publisher = PermissionEventPublisher(event_bus)
        return cls(
            settings_application_service=settings_application_service,
            system_settings_service=system_settings_service,
            company_profile_service=CompanyProfileService(repository),
            email_settings_service=EmailSettingsService(system_settings_service),
            payment_provider_settings_service=PaymentProviderSettingsService(system_settings_service),
            closing_period_service=ClosingPeriodService(repository),
            happy_hour_settings_service=HappyHourSettingsService(repository),
            user_management_service=UserManagementService(repository, permission_event_publisher),
            role_management_service=RoleManagementService(repository, permission_event_publisher),
            permission_query_service=PermissionQueryService(repository),
            module_access_service=ModuleAccessService(repository, permission_event_publisher),
            permission_event_publisher=permission_event_publisher,
        )
