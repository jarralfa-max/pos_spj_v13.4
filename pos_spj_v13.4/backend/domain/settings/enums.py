"""Canonical enums for the Settings (Configuration Governance) bounded
context — SET-2. See docs/refactor/settings_refactor_execution_plan.md and
the master prompt §6-10.
"""

from __future__ import annotations

from enum import Enum


class ValueType(str, Enum):
    """How a `ConfigurationValue.value` is typed and validated. See §8."""

    BOOLEAN = "BOOLEAN"
    STRING = "STRING"
    INTEGER = "INTEGER"
    DECIMAL = "DECIMAL"
    MONEY = "MONEY"
    PERCENT = "PERCENT"
    DATE = "DATE"
    TIME = "TIME"
    DATETIME = "DATETIME"
    DURATION = "DURATION"
    ENUM = "ENUM"
    MULTI_ENUM = "MULTI_ENUM"
    JSON_SCHEMA = "JSON_SCHEMA"
    UUID_REFERENCE = "UUID_REFERENCE"
    SECRET_REFERENCE = "SECRET_REFERENCE"
    FILE_REFERENCE = "FILE_REFERENCE"
    COLOR_TOKEN = "COLOR_TOKEN"
    TEMPLATE_REFERENCE = "TEMPLATE_REFERENCE"
    DEVICE_REFERENCE = "DEVICE_REFERENCE"


# Value types whose python representation references an external UUIDv7
# entity (device, template, ...) rather than carrying a literal value.
UUID_REFERENCE_TYPES = frozenset({
    ValueType.UUID_REFERENCE, ValueType.TEMPLATE_REFERENCE, ValueType.DEVICE_REFERENCE,
})


class ScopeType(str, Enum):
    """Where a `ConfigurationValue` applies. See §6."""

    GLOBAL = "GLOBAL"
    COMPANY = "COMPANY"
    BRANCH = "BRANCH"
    WAREHOUSE = "WAREHOUSE"
    LOCATION = "LOCATION"
    WORKSTATION = "WORKSTATION"
    MODULE = "MODULE"
    DEVICE = "DEVICE"
    CHANNEL = "CHANNEL"
    USER = "USER"
    ROLE = "ROLE"
    CUSTOMER_SEGMENT = "CUSTOMER_SEGMENT"
    PRODUCT_CATEGORY = "PRODUCT_CATEGORY"
    PRODUCT = "PRODUCT"
    PROCESS = "PROCESS"
    DELIVERY_ZONE = "DELIVERY_ZONE"


# Scopes identified by a logical code (a module name, a channel key, a
# process name) rather than a UUIDv7 entity reference.
CODE_BASED_SCOPES = frozenset({ScopeType.MODULE, ScopeType.CHANNEL, ScopeType.PROCESS})


class ConfigurationValueStatus(str, Enum):
    """Lifecycle of one `ConfigurationValue` version. See §10."""

    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    SCHEDULED = "SCHEDULED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    ROLLED_BACK = "ROLLED_BACK"


class WorkstationType(str, Enum):
    """What a `Workstation` is used for. See §17."""

    POS = "POS"
    BACKOFFICE = "BACKOFFICE"
    WAREHOUSE = "WAREHOUSE"
    RECEIVING = "RECEIVING"
    PRODUCTION = "PRODUCTION"
    PROCESSING = "PROCESSING"
    DELIVERY_COORDINATION = "DELIVERY_COORDINATION"
    CUSTOMER_SERVICE = "CUSTOMER_SERVICE"
    ADMINISTRATION = "ADMINISTRATION"
    MOBILE = "MOBILE"
    KIOSK_FUTURE = "KIOSK_FUTURE"


class WorkstationStatus(str, Enum):
    """Lifecycle of a `Workstation`. See §17 — same five states already
    used by Cash Register's `cash_registers`/`pos_terminals`
    (`migrations/standalone/175_cash_register_bounded_context_schema.py`),
    kept identical on purpose for one shared vocabulary."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    MAINTENANCE = "MAINTENANCE"
    BLOCKED = "BLOCKED"
    RETIRED = "RETIRED"
