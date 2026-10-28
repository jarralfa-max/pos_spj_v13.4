"""Asignación de un rol con ámbito (auditoría enterprise, Fase 2; decisión D4).

Una persona puede tener varios roles, cada uno válido en un ámbito: el comprador
corporativo compra para toda la empresa, el gerente regional gerencia las
sucursales de su región y además es cajero en una. El rol principal sigue en
`usuarios.rol`; éstos son los adicionales.

* El ámbito es explícito: `COMPANY` con el id de la empresa u `ORG_UNIT` con el
  id de una unidad (cubre la unidad y todo lo que cuelga de ella). Nunca vacío.
* Vigencia opcional (desde/hasta, fechas de calendario inclusivas).
* Se revoca, no se borra: la historia de quién tuvo qué y cuándo se conserva.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum

from backend.shared.ids import new_uuid


class RoleAssignmentError(ValueError):
    """La asignación viola una regla."""


class ScopeType(str, Enum):
    COMPANY = "COMPANY"
    ORG_UNIT = "ORG_UNIT"


class AssignmentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class RoleAssignment:
    id: str
    user_id: str
    role_id: str
    scope_type: ScopeType
    scope_id: str
    reason: str
    valid_from: date | None = None
    valid_until: date | None = None
    status: AssignmentStatus = AssignmentStatus.ACTIVE
    granted_by: str | None = None
    created_at: str = field(default_factory=_utcnow)
    revoked_at: str | None = None
    revoked_by: str | None = None
    revoke_reason: str | None = None

    @classmethod
    def create(cls, *, user_id: str, role_id: str, scope_type: ScopeType | str,
               scope_id: str, reason: str, valid_from: date | None = None,
               valid_until: date | None = None, granted_by: str | None = None
               ) -> "RoleAssignment":
        if not str(user_id or "").strip() or not str(role_id or "").strip():
            raise RoleAssignmentError("La asignación necesita usuario y rol")
        if not str(scope_id or "").strip():
            raise RoleAssignmentError("La asignación necesita un ámbito (empresa o unidad)")
        motivo = str(reason or "").strip()
        if not motivo:
            raise RoleAssignmentError("Indique el motivo de la asignación")
        if valid_from and valid_until and valid_until < valid_from:
            raise RoleAssignmentError("La vigencia termina antes de empezar")
        return cls(id=new_uuid(), user_id=str(user_id), role_id=str(role_id),
                   scope_type=ScopeType(scope_type), scope_id=str(scope_id), reason=motivo,
                   valid_from=valid_from, valid_until=valid_until, granted_by=granted_by)

    def is_effective(self, on: date) -> bool:
        if self.status is not AssignmentStatus.ACTIVE:
            return False
        if self.valid_from and on < self.valid_from:
            return False
        return not (self.valid_until and on > self.valid_until)

    def revoke(self, *, by: str | None, reason: str) -> None:
        if self.status is AssignmentStatus.REVOKED:
            raise RoleAssignmentError("La asignación ya estaba revocada")
        motivo = str(reason or "").strip()
        if not motivo:
            raise RoleAssignmentError("Indique el motivo de la revocación")
        self.status = AssignmentStatus.REVOKED
        self.revoked_at = _utcnow()
        self.revoked_by = by
        self.revoke_reason = motivo


def effective_on(valid_from: str | date | None, valid_until: str | date | None,
                 on: date) -> bool:
    """La misma regla de vigencia, para filas leídas directamente de la base."""
    def _d(valor):
        if valor in (None, ""):
            return None
        return valor if isinstance(valor, date) else date.fromisoformat(str(valor)[:10])
    desde, hasta = _d(valid_from), _d(valid_until)
    return not ((desde and on < desde) or (hasta and on > hasta))


__all__ = ["AssignmentStatus", "RoleAssignment", "RoleAssignmentError", "ScopeType",
           "effective_on"]
