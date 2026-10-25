"""Dimensiones analíticas adicionales (§23): proyectos y departamentos.

Centros de costo y de utilidad viven en sus propios archivos; la sucursal es
la identidad del maestro de sucursales. Toda dimensión es UUIDv7 y su código
visible nunca es su identidad.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.finance.exceptions import FinanceDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _require(code: str, name: str) -> tuple[str, str]:
    code = (code or "").strip().upper()
    name = (name or "").strip()
    if not code or not name:
        raise FinanceDomainError("La dimensión requiere código y nombre")
    return code, name


@dataclass(slots=True)
class Project:
    """Proyecto o inversión. ``is_capex`` separa el CAPEX del gasto operativo."""

    id: str
    code: str
    name: str
    branch_id: str | None = None
    is_capex: bool = False
    active: bool = True
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, code: str, name: str, *, branch_id: str | None = None,
               is_capex: bool = False) -> "Project":
        code, name = _require(code, name)
        return cls(id=new_uuid(), code=code, name=name, branch_id=branch_id,
                   is_capex=bool(is_capex))


@dataclass(slots=True)
class Department:
    id: str
    code: str
    name: str
    active: bool = True
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, code: str, name: str) -> "Department":
        code, name = _require(code, name)
        return cls(id=new_uuid(), code=code, name=name)
