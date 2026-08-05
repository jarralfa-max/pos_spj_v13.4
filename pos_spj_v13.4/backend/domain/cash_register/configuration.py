"""CASH-5 configuration entities, hierarchy and effective dating."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import re

from backend.shared.ids import new_uuid, validate_uuidv7
from backend.domain.cash_register.value_objects.money import money


class ConfigurationScope(str, Enum):
    SYSTEM = "SYSTEM"
    COMPANY = "COMPANY"
    BRANCH = "BRANCH"
    REGISTER = "REGISTER"
    USER = "USER"


_PRECEDENCE = {scope: rank for rank, scope in enumerate(ConfigurationScope)}


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class CashScopedSetting:
    id: str
    key: str
    value: str
    scope: ConfigurationScope
    scope_id: str | None
    effective_from: datetime
    effective_to: datetime | None = None

    @classmethod
    def create(cls, key: str, value: str, scope: ConfigurationScope,
               scope_id: str | None, effective_from: datetime,
               effective_to: datetime | None = None) -> "CashScopedSetting":
        if not key.strip():
            raise ValueError("Setting key is required")
        if scope is ConfigurationScope.SYSTEM and scope_id is not None:
            raise ValueError("SYSTEM scope cannot have scope_id")
        if scope is not ConfigurationScope.SYSTEM:
            validate_uuidv7(scope_id)
        if effective_from.tzinfo is None or (effective_to and effective_to.tzinfo is None):
            raise ValueError("Configuration effective dates require timezone")
        if effective_to is not None and effective_to <= effective_from:
            raise ValueError("effective_to must be later than effective_from")
        return cls(new_uuid(), key.strip(), value, scope, scope_id, effective_from, effective_to)

    def is_effective(self, at: datetime) -> bool:
        return self.effective_from <= at and (self.effective_to is None or at < self.effective_to)


class CashConfigurationResolver:
    def __init__(self, settings: list[CashScopedSetting]) -> None:
        self._settings = tuple(settings)

    def resolve(self, key: str, *, at: datetime,
                scope_ids: dict[ConfigurationScope, str]) -> CashScopedSetting | None:
        candidates = []
        for setting in self._settings:
            expected_id = None if setting.scope is ConfigurationScope.SYSTEM else scope_ids.get(setting.scope)
            if setting.key == key and setting.scope_id == expected_id and setting.is_effective(at):
                candidates.append(setting)
        return max(candidates, key=lambda item: (_PRECEDENCE[item.scope], item.effective_from), default=None)


@dataclass(frozen=True, slots=True)
class CashDenomination:
    id: str
    currency_code: str
    value: Decimal
    display_name: str
    sort_order: int
    active: bool = True

    @classmethod
    def create(cls, currency_code: str, value: Decimal, display_name: str,
               sort_order: int) -> "CashDenomination":
        if len(currency_code.strip()) != 3 or not display_name.strip():
            raise ValueError("Currency and denomination name are required")
        if isinstance(sort_order, bool) or not isinstance(sort_order, int) or sort_order < 0:
            raise ValueError("sort_order must be a non-negative integer")
        return cls(new_uuid(), currency_code.upper(), money(value, allow_zero=False),
                   display_name.strip(), sort_order)


@dataclass(frozen=True, slots=True)
class CashPaymentMethod:
    id: str
    code: str
    display_name: str
    affects_physical_cash: bool
    active: bool = True

    @classmethod
    def create(cls, code: str, display_name: str, *, affects_physical_cash: bool) -> "CashPaymentMethod":
        if not code.strip() or not display_name.strip():
            raise ValueError("Payment method code and name are required")
        return cls(new_uuid(), code.strip().upper(), display_name.strip(), bool(affects_physical_cash))


@dataclass(frozen=True, slots=True)
class CashOperationLimit:
    id: str
    operation_type: str
    approval_threshold: Decimal
    hard_cap: Decimal

    @classmethod
    def create(cls, operation_type: str, approval_threshold: Decimal,
               hard_cap: Decimal) -> "CashOperationLimit":
        threshold, cap = money(approval_threshold), money(hard_cap)
        if not operation_type.strip() or cap < threshold:
            raise ValueError("Operation and ordered limits are required")
        return cls(new_uuid(), operation_type.strip().upper(), threshold, cap)


@dataclass(frozen=True, slots=True)
class CashMovementReason:
    id: str
    code: str
    display_name: str
    movement_type: str
    requires_authorization: bool
    active: bool = True

    @classmethod
    def create(cls, code: str, display_name: str, movement_type: str,
               *, requires_authorization: bool = False) -> "CashMovementReason":
        allowed = {"MANUAL_INCOME", "MANUAL_WITHDRAWAL", "SAFE_DROP"}
        normalized_type = movement_type.strip().upper()
        if not code.strip() or not display_name.strip() or normalized_type not in allowed:
            raise ValueError("Movement reason requires code, name and supported movement type")
        return cls(new_uuid(), code.strip().upper(), display_name.strip(), normalized_type,
                   bool(requires_authorization))


@dataclass(frozen=True, slots=True)
class CashAlertRule:
    id: str
    event_name: str
    severity: str
    channels: tuple[str, ...]

    @classmethod
    def create(cls, event_name: str, severity: str,
               channels: tuple[str, ...]) -> "CashAlertRule":
        allowed = {"IN_APP", "WHATSAPP", "EMAIL"}
        normalized = tuple(dict.fromkeys(channel.upper() for channel in channels))
        if not event_name.startswith("CASH_") or not normalized or not set(normalized) <= allowed:
            raise ValueError("Invalid cash alert rule")
        return cls(new_uuid(), event_name, severity.upper(), normalized)


@dataclass(frozen=True, slots=True)
class CashWhatsAppRecipient:
    id: str
    event_name: str
    phone_e164: str

    @classmethod
    def create(cls, event_name: str, phone_e164: str) -> "CashWhatsAppRecipient":
        if not event_name.startswith("CASH_") or not re.fullmatch(r"\+[1-9]\d{7,14}", phone_e164):
            raise ValueError("WhatsApp recipient requires event and E.164 phone")
        return cls(new_uuid(), event_name, phone_e164)


@dataclass(frozen=True, slots=True)
class CashPermissionProfile:
    id: str
    name: str
    permission_codes: tuple[str, ...]

    @classmethod
    def create(cls, name: str, permission_codes: tuple[str, ...]) -> "CashPermissionProfile":
        codes = tuple(dict.fromkeys(permission_codes))
        if not name.strip() or not codes or any(not code.startswith("CASH_") for code in codes):
            raise ValueError("Permission profile requires CASH_* permissions")
        return cls(new_uuid(), name.strip(), codes)
