"""Application services for the Configuración module.

These services keep schema/default bootstrapping out of PyQt and provide an
explicit backend boundary for configuration reads and mutations.
"""

from __future__ import annotations

from typing import Any

from core.module_config import DEFAULT_TOGGLES
from repositories.config_repository import ConfigRepository


class SystemSettingsService:
    def __init__(self, repository: ConfigRepository) -> None:
        self._repository = repository

    def ensure_configuration_available(self) -> bool:
        try:
            self._repository.get_all_settings()
            return True
        except Exception:
            return False

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        return self._repository.get_setting(key, default or "")

    def get_many(self, keys: list[str], defaults: dict[str, str] | None = None) -> dict[str, str]:
        defaults = defaults or {}
        values = self._repository.get_settings(keys)
        return {key: str(values.get(key, defaults.get(key, ""))) for key in keys}

    def set_setting(self, key: str, value: Any) -> None:
        self._repository.save_setting(key, str(value))

    def save_many(self, settings: dict[str, Any]) -> None:
        for key, value in settings.items():
            self.set_setting(key, value)


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
        self._repository.set_module_toggle(self.normalize_key(module_key), enabled)

    def get_all(self) -> dict[str, bool]:
        toggles = dict(self._defaults)
        try:
            toggles.update(self._repository.get_module_toggles())
        except Exception:
            pass
        return toggles


class CompanyProfileService:
    def __init__(self, repository: ConfigRepository) -> None:
        self._repository = repository

    def get_branch(self, branch_id: int) -> dict | None:
        return self._repository.get_branch(branch_id)

    def save_branch(
        self,
        *,
        name: str,
        address: str | None,
        phone: str | None,
        active: bool,
        branch_id: int | None = None,
    ) -> int:
        return self._repository.save_branch(
            name=name,
            address=address,
            phone=phone,
            active=active,
            branch_id=branch_id,
        )

    def get_branch_delivery_profile(self, branch_id: int) -> dict | None:
        return self._repository.get_branch_delivery_profile(branch_id)

    def branches_for_company_settings(self) -> list[tuple[int, str]]:
        return self._repository.branches_for_company_settings()

    def list_branch_delivery_rows(self) -> list[tuple]:
        return self._repository.list_branch_delivery_rows()


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
        branch_id: int | None = None,
    ) -> int:
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
    """Application boundary for general configuration values."""

    def __init__(self, system_settings_service: SystemSettingsService) -> None:
        self._system_settings_service = system_settings_service

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

    def close_period(self, *, period: str, closed_by: str, totals: dict[str, float], branch_id: int) -> None:
        self._repository.save_monthly_close(period=period, closed_by=closed_by, totals=totals, branch_id=branch_id)

    def history(self, limit: int = 24) -> list[tuple]:
        return self._repository.get_monthly_closures(limit=limit)


class PermissionEventPublisher:
    """Small typed event publisher used by settings services."""

    def __init__(self, event_bus: Any | None = None) -> None:
        self._event_bus = event_bus
        self.published_events: list[Any] = []

    def publish(self, event_name: str, *, operation_id: str, entity_id: str, user_name: str, payload: dict[str, Any]) -> None:
        if not operation_id:
            raise ValueError("operation_id is required")
        event = {
            "event_name": event_name,
            "operation_id": operation_id,
            "entity_id": entity_id,
            "branch_id": str(payload.get("branch_id", "1")),
            "user_name": user_name,
            "source_module": "CONFIGURATION",
            "payload": payload,
        }
        self.published_events.append(event)
        if self._event_bus is not None:
            try:
                from backend.shared.events.event_contracts import create_domain_event
                from backend.shared.events.event_names import EventName

                self._event_bus.publish(create_domain_event(
                    event_name=EventName(event_name),
                    operation_id=operation_id,
                    entity_id=str(entity_id),
                    branch_id=str(event["branch_id"]),
                    user_name=user_name,
                    source_module="CONFIGURATION",
                    payload=payload,
                ))
            except Exception:
                self._event_bus.publish(event)


class UserManagementService:
    """Canonical user management boundary for Configuración."""

    def __init__(self, repository: ConfigRepository, event_publisher: PermissionEventPublisher | None = None) -> None:
        self._repository = repository
        self._events = event_publisher or PermissionEventPublisher()

    def list_users(self) -> list[tuple]:
        return self._repository.list_users_v13()

    def get_user_form_data(self, user_id: int) -> tuple | None:
        return self._repository.get_user_form_data(user_id)

    def save_user(
        self,
        *,
        user_id: int | None,
        username: str,
        name: str,
        email: str,
        role: str,
        branch_id: int,
        active: bool,
        employee_id: int | None,
        password_hash: str | None,
        operation_id: str,
        actor: str,
    ) -> None:
        self._repository.save_user_v13(
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
        self._events.publish(
            "USER_PERMISSIONS_UPDATED",
            operation_id=operation_id,
            entity_id=username,
            user_name=actor,
            payload={"user_id": user_id, "username": username, "role": role, "branch_id": branch_id},
        )

    def set_user_active(self, user_id: int, active: bool, *, operation_id: str, actor: str) -> None:
        self._repository.set_user_active(user_id, active)
        self._events.publish(
            "USER_PERMISSIONS_UPDATED",
            operation_id=operation_id,
            entity_id=str(user_id),
            user_name=actor,
            payload={"user_id": user_id, "active": active},
        )


class RoleManagementService:
    """Canonical role management boundary for Configuración."""

    def __init__(self, repository: ConfigRepository, event_publisher: PermissionEventPublisher | None = None) -> None:
        self._repository = repository
        self._events = event_publisher or PermissionEventPublisher()

    def list_roles(self) -> list[tuple]:
        return self._repository.list_roles_v13()

    def role_names(self) -> list[str]:
        return self._repository.role_names()

    def active_branches_for_selector(self) -> list[tuple[int, str]]:
        return self._repository.active_branches_for_selector()

    def active_employees_for_selector(self) -> list[tuple[int, str]]:
        return self._repository.active_employees_for_selector()

    def save_role(self, *, role_id: int | None, name: str, description: str, operation_id: str, actor: str) -> int:
        saved_id = self._repository.save_role(role_id=role_id, name=name, description=description)
        self._events.publish(
            "ROLE_PERMISSIONS_UPDATED",
            operation_id=operation_id,
            entity_id=str(saved_id),
            user_name=actor,
            payload={"role_id": saved_id, "role_name": name},
        )
        return saved_id


class PermissionQueryService:
    """Read model for role permissions and audit in Configuración."""

    def __init__(self, repository: ConfigRepository) -> None:
        self._repository = repository

    def role_permissions(self, role_id: int) -> dict[tuple[str, str], bool]:
        return self._repository.role_permissions(role_id)

    def audit_log_rows(self, limit: int = 200) -> list[tuple]:
        return self._repository.audit_log_rows(limit=limit)


class ModuleAccessService:
    """Canonical module permission mutator/query with event emission."""

    def __init__(self, repository: ConfigRepository, event_publisher: PermissionEventPublisher | None = None) -> None:
        self._repository = repository
        self._events = event_publisher or PermissionEventPublisher()
        self._cache: dict[int, dict[tuple[str, str], bool]] = {}

    def save_role_permissions(
        self,
        role_id: int,
        permissions: dict[tuple[str, str], bool],
        *,
        operation_id: str,
        actor: str,
    ) -> None:
        self._repository.save_role_permissions(role_id, permissions)
        self.invalidate_cache(role_id)
        self._events.publish(
            "ROLE_PERMISSIONS_UPDATED",
            operation_id=operation_id,
            entity_id=str(role_id),
            user_name=actor,
            payload={"role_id": role_id, "permissions": {f"{m}.{a}": v for (m, a), v in permissions.items()}},
        )
        self._events.publish(
            "MODULE_ACCESS_UPDATED",
            operation_id=operation_id,
            entity_id=str(role_id),
            user_name=actor,
            payload={"role_id": role_id},
        )

    def has_permission(self, role_id: int, module: str, action: str) -> bool:
        if role_id not in self._cache:
            self._cache[role_id] = self._repository.role_permissions(role_id)
        return self._cache[role_id].get((module, action), False)

    def invalidate_cache(self, role_id: int | None = None) -> None:
        if role_id is None:
            self._cache.clear()
        else:
            self._cache.pop(role_id, None)
