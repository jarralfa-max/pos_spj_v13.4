"""Settings and configuration module commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from backend.application.commands.base_command import BaseCommand


@dataclass(frozen=True)
class SaveCompanyProfileCommand(BaseCommand):
    branch_id: str = ""
    name: str = ""
    fiscal_name: str = ""
    rfc: str = ""
    address: str = ""
    phone: str = ""
    email: str = ""
    logo_path: str = ""
    extra: Mapping[str, Any] = field(default_factory=dict)

    def validate_context(self) -> None:
        super().validate_context()
        if not str(self.branch_id or "").strip():
            raise ValueError("branch_id is required")
        if not str(self.name or "").strip():
            raise ValueError("name is required")


@dataclass(frozen=True)
class SaveSystemSettingCommand(BaseCommand):
    key: str = ""
    value: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not str(self.key or "").strip():
            raise ValueError("key is required")


@dataclass(frozen=True)
class SaveSMTPSettingsCommand(BaseCommand):
    host: str = ""
    port: int = 0
    username: str = ""
    password: str = ""
    use_tls: bool = True
    from_email: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not str(self.host or "").strip():
            raise ValueError("host is required")


@dataclass(frozen=True)
class SaveHappyHourRuleCommand(BaseCommand):
    rule_id: str = ""
    name: str = ""
    start_time: str = ""
    end_time: str = ""
    discount_percent: float = 0.0
    days_of_week: tuple[int, ...] = field(default_factory=tuple)
    active: bool = True

    def validate_context(self) -> None:
        super().validate_context()
        if not str(self.name or "").strip():
            raise ValueError("name is required")
        if float(self.discount_percent or 0.0) <= 0:
            raise ValueError("discount_percent must be greater than zero")


@dataclass(frozen=True)
class SaveUserCommand(BaseCommand):
    user_id: str = ""
    username: str = ""
    full_name: str = ""
    role_id: str = ""
    employee_id: str = ""
    active: bool = True
    password_hash: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not str(self.username or "").strip():
            raise ValueError("username is required")
        if not str(self.role_id or "").strip():
            raise ValueError("role_id is required")


@dataclass(frozen=True)
class SaveRolePermissionsCommand(BaseCommand):
    role_id: str = ""
    permissions: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)

    def validate_context(self) -> None:
        super().validate_context()
        if not str(self.role_id or "").strip():
            raise ValueError("role_id is required")


@dataclass(frozen=True)
class ExecuteMonthlyClosingCommand(BaseCommand):
    period: str = ""
    branch_id: str = ""
    notes: str = ""

    def validate_context(self) -> None:
        super().validate_context()
        if not str(self.period or "").strip():
            raise ValueError("period is required")
        if not str(self.branch_id or "").strip():
            raise ValueError("branch_id is required")
