"""Explicit DTOs for the CONFIGURACION module.

Repositories return persistent rows/dicts; the application/query services
translate them into these typed DTOs so the UI consumes attributes instead of
positional tuples, ``sqlite3.Row`` objects or ambiguous dictionaries.

Identity fields carry the canonical UUIDv7 string (REGLA CERO).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BranchSettingsDTO:
    """Company branch identity/contact settings."""

    id: str
    name: str
    address: str = ""
    phone: str = ""
    active: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> "BranchSettingsDTO":
        return cls(
            id=str(data.get("id") or data.get("uuid") or ""),
            name=str(data.get("nombre") or ""),
            address=str(data.get("direccion") or ""),
            phone=str(data.get("telefono") or ""),
            active=bool(data.get("activa", True)),
        )


@dataclass(frozen=True)
class BranchDeliveryRowDTO:
    """A branch row as shown in the delivery-profile table."""

    id: str
    name: str
    address: str = ""
    opening_time: str = ""
    closing_time: str = ""
    operation_days: str = ""
    active: bool = True

    @classmethod
    def from_row(cls, row) -> "BranchDeliveryRowDTO":
        return cls(
            id=str(row[0] or ""),
            name=str(row[1] or ""),
            address=str(row[2] or ""),
            opening_time=str(row[3] or ""),
            closing_time=str(row[4] or ""),
            operation_days=str(row[5] or ""),
            active=bool(row[6]),
        )


@dataclass(frozen=True)
class UserSettingsDTO:
    """A system user. ``id`` is the canonical UUIDv7 identity."""

    id: str
    username: str
    name: str = ""
    email: str = ""
    role: str = ""
    branch_id: str = ""
    branch_name: str = ""
    active: bool = True
    employee_id: Any = None

    @classmethod
    def from_list_row(cls, row) -> "UserSettingsDTO":
        # list_users_v13: id, usuario, nombre, rol, sucursal, activo, ...
        return cls(
            id=str(row[0] or ""),
            username=str(row[1] or ""),
            name=str(row[2] or ""),
            role=str(row[3] or ""),
            branch_name=str(row[4] or ""),
            active=bool(row[5]),
        )

    @classmethod
    def from_form_row(cls, user_id: str, row) -> "UserSettingsDTO":
        # get_user_form_data: usuario, nombre, email, rol, branch, activo, empleado_id
        return cls(
            id=str(user_id or ""),
            username=str(row[0] or ""),
            name=str(row[1] or ""),
            email=str(row[2] or ""),
            role=str(row[3] or ""),
            branch_id="" if row[4] is None else str(row[4]),
            active=bool(row[5]),
            employee_id=row[6],
        )


@dataclass(frozen=True)
class RoleSettingsDTO:
    """A security role. ``id`` is the canonical UUIDv7 identity."""

    id: str
    name: str
    description: str = ""
    user_count: int = 0

    @classmethod
    def from_row(cls, row) -> "RoleSettingsDTO":
        # list_roles_v13: id, nombre, descripcion, num_usuarios
        return cls(
            id=str(row[0] or ""),
            name=str(row[1] or ""),
            description=str(row[2] or ""),
            user_count=int(row[3] or 0),
        )


@dataclass(frozen=True)
class HappyHourRuleDTO:
    """A Happy Hour pricing rule. ``id`` is the canonical UUIDv7 identity."""

    id: str
    name: str
    start_time: str = ""
    end_time: str = ""
    days_of_week: str = ""
    discount_type: str = ""
    value: float = 0.0
    applies_to: str = ""
    applies_value: str = ""
    message: str = ""
    active: bool = False
    branch_id: str = ""

    @classmethod
    def from_repository_dict(cls, data: dict) -> "HappyHourRuleDTO":
        return cls(
            id=str(data.get("id") or ""),
            name=str(data.get("nombre") or ""),
            start_time=str(data.get("hora_inicio") or ""),
            end_time=str(data.get("hora_fin") or ""),
            days_of_week=str(data.get("dias_semana") or ""),
            discount_type=str(data.get("tipo_descuento") or ""),
            value=float(data.get("valor") or 0),
            applies_to=str(data.get("aplica_a") or ""),
            applies_value=str(data.get("aplica_valor") or ""),
            message=str(data.get("mensaje_wa") or data.get("message") or ""),
            active=bool(data.get("activo")),
            branch_id="" if data.get("sucursal_id") is None else str(data.get("sucursal_id")),
        )


@dataclass(frozen=True)
class PermissionMatrixDTO:
    """A module and its available permission actions."""

    module: str
    actions: tuple[str, ...]


@dataclass(frozen=True)
class MonthlyClosingSummaryDTO:
    """A monthly closing summary row. ``period`` is the natural identity."""

    period: str
    closed_by: str = ""
    closing_date: str = ""
    total_sales: float = 0.0
    total_purchases: float = 0.0
    total_waste: float = 0.0

    @classmethod
    def from_row(cls, row) -> "MonthlyClosingSummaryDTO":
        # get_monthly_closures: periodo, cerrado_por, fecha_cierre, ventas, compras, merma
        return cls(
            period=str(row[0] or ""),
            closed_by=str(row[1] or ""),
            closing_date=str(row[2] or ""),
            total_sales=float(row[3] or 0),
            total_purchases=float(row[4] or 0),
            total_waste=float(row[5] or 0),
        )


@dataclass(frozen=True)
class HardwareConfigDTO:
    """Configuration for one hardware device domain (keyed by device type)."""

    device_type: str
    config: dict


@dataclass(frozen=True)
class ModuleToggleDTO:
    """A module enablement toggle."""

    key: str
    enabled: bool
