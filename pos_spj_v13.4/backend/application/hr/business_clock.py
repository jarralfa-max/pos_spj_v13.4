"""Reloj de negocio de RR. HH. (auditoría cebf67a HR-22/HR-24).

"Hoy" y las horas que ve el usuario son los de la SUCURSAL, no los del equipo.
La UI lo pide aquí (capa de aplicación) en vez de leer repositorios.
"""

from __future__ import annotations

from datetime import datetime

from backend.infrastructure.db.repositories.hr.support_repositories import (
    HRCalendarRepository,
)
from backend.shared.business_dates import resolve_timezone


def branch_now(connection, branch_id: str | None) -> datetime:
    zone = resolve_timezone(HRCalendarRepository(connection).timezone_name(branch_id))
    return datetime.now(zone)
