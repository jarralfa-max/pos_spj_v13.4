"""Única fuente del turno activo (SDLC-ARQ-SHIFT-001).

Antes el "turno activo" se resolvía por una docena de caminos con filtros y
conjuntos de estado distintos: el POS sólo veía `OPEN`, Caja veía cualquier
estado activo y además guardaba una caché en memoria, y Finanzas,
Organización y Actualizaciones copiaban sus propias tuplas de estados. Con un
turno suspendido Caja lo mostraba y el POS decía "no tienes turno".

Ahora todos preguntan aquí, y aquí sólo se lee la base:

- El turno activo de un cajero es el que está en un estado de
  `CashShiftLifecyclePolicy.ACTIVE_STATUSES` (la base garantiza a lo sumo uno
  por cajero, caja, cajón y terminal: índices `ux_cash_shift_active_*` de la
  migración 175).
- Para cobrar o reembolsar debe ser operable (decisión 2026-11-02): `OPEN`
  cobra; `SUSPENDED` sigue siendo su turno pero debe reanudarse; en cierre no
  sirve: se termina el cierre y se abre un turno nuevo.

Corre sobre la conexión del llamador, dentro de su transacción si la hay; no
hace commit ni rollback.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Literal, Mapping

from backend.domain.cash_register.enums import CashShiftOperability
from backend.domain.cash_register.exceptions import (
    CashRegisterError, CashShiftClosingError, CashShiftNotOpenError,
    CashShiftSuspendedError,
)
from backend.domain.cash_register.policies.workflow_policies import CashShiftLifecyclePolicy
from backend.infrastructure.db.repositories.cash_register.repositories import CashShiftRepository

Purpose = Literal["sale", "refund"]

#: Lo que se le dice al cajero, por propósito y situación.
_MESSAGES: dict[Purpose, dict[str, str]] = {
    "sale": {
        "none": ("No tienes un turno de caja abierto. Abre tu turno en Caja antes de "
                 "cobrar: sin turno, el dinero de la venta no entra a ningún corte."),
        CashShiftOperability.MUST_RESUME.value: (
            "Tu turno de caja está suspendido. Reanúdalo en Caja antes de cobrar."),
        CashShiftOperability.MUST_OPEN_NEW.value: (
            "Tu turno de caja está en cierre. Termina el cierre en Caja y abre un turno "
            "nuevo para cobrar."),
    },
    "refund": {
        "none": ("Para devolver efectivo necesitas tu turno de caja abierto: el reembolso "
                 "sale de tu cajón."),
        CashShiftOperability.MUST_RESUME.value: (
            "Tu turno de caja está suspendido. Reanúdalo en Caja para devolver efectivo."),
        CashShiftOperability.MUST_OPEN_NEW.value: (
            "Tu turno de caja está en cierre. Termina el cierre en Caja y abre un turno "
            "nuevo para devolver efectivo."),
    },
}


@dataclass(frozen=True, slots=True)
class ActiveShift:
    id: str
    branch_id: str
    register_id: str
    drawer_id: str
    terminal_id: str
    cashier_user_id: str
    status: str
    opened_at: str

    @property
    def operability(self) -> CashShiftOperability:
        return CashShiftLifecyclePolicy.operability(self.status)

    @classmethod
    def from_row(cls, row: Mapping[str, object]) -> "ActiveShift":
        return cls(**{name: str(row[name]) for name in cls.__slots__})


class ActiveShiftResolver:
    def __init__(self, connection) -> None:
        self._shifts = CashShiftRepository(connection)

    # ── consulta ──────────────────────────────────────────────────────
    def for_cashier(self, *, cashier_user_id: str,
                    branch_id: str | None = None) -> ActiveShift | None:
        """El turno activo del cajero; en la sucursal dada si se pide. Sin
        sucursal es la regla de incompatibilidad "por cajero" (SHIFT-004)."""
        if not cashier_user_id:
            return None
        row = self._shifts.find_active(cashier_user_id=cashier_user_id, branch_id=branch_id)
        return ActiveShift.from_row(row) if row else None

    def for_resource(self, *, column: str, value: str) -> ActiveShift | None:
        """El turno activo que ocupa una caja, cajón o terminal."""
        row = self._shifts.find_active(column=column, value=value)
        return ActiveShift.from_row(row) if row else None

    def busy_register_ids(self, *, branch_id: str) -> set[str]:
        return self._shifts.active_register_ids(branch_id=branch_id)

    def count_active(self, *, branch_id: str | None = None,
                     business_date_until: str | None = None) -> int:
        return self._shifts.count_active(branch_id=branch_id,
                                         business_date_until=business_date_until)

    # ── operar ────────────────────────────────────────────────────────
    def require_operable(self, *, branch_id: str, cashier_user_id: str,
                         purpose: Purpose = "sale") -> ActiveShift:
        """El turno con el que el cajero cobra o reembolsa en la sucursal, o
        `CashShiftNotOpenError` (o su subclase) con el turno identificado."""
        messages = _MESSAGES[purpose]
        shift = self.for_cashier(cashier_user_id=cashier_user_id, branch_id=branch_id)
        if shift is None:
            raise CashShiftNotOpenError(messages["none"])
        operability = shift.operability
        if operability is CashShiftOperability.OPERABLE:
            return shift
        error = (CashShiftSuspendedError if operability is CashShiftOperability.MUST_RESUME
                 else CashShiftClosingError)
        raise error(messages[operability.value], shift_id=shift.id, status=shift.status)

    def operability_problem(self, *, branch_id: str, cashier_user_id: str,
                            purpose: Purpose = "sale") -> str | None:
        """Por qué el cajero no puede cobrar/reembolsar, o None. Falla cerrado:
        sin esquema de Caja no puede haber turno (distinguir esa falla es
        SDLC-SALES-007)."""
        try:
            self.require_operable(branch_id=branch_id, cashier_user_id=cashier_user_id,
                                  purpose=purpose)
        except CashShiftNotOpenError as exc:
            return str(exc)
        except (CashRegisterError, sqlite3.OperationalError):
            return _MESSAGES[purpose]["none"]
        return None
