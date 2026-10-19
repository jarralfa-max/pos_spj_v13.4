"""Turno propio o intervención explícita (auditoría de Caja 968e0bc, CJA-02, 2026-10-16).

MEDIDO: abierto un turno del cajero A, el cajero B (con permiso de suspender en
la sucursal) lo suspendió; también podía abrir un turno a nombre de otro y
empezar el arqueo de un turno ajeno. Los permisos se revisaban por ACCIÓN, nunca
por TITULAR del turno.

Regla única:

* el titular del turno opera su turno;
* intervenir el turno de otro cajero exige el permiso de intervención de esa
  acción (supervisor: `CAJA.turno.forzar_cierre` para suspender/reanudar/
  pre-cerrar, `CAJA.conteo.sobrescribir` para arquear un turno ajeno) y, para las
  transiciones, un MOTIVO que queda en el evento;
* abrir un turno a nombre de otro exige `CAJA.turno.reasignar`.
"""

from __future__ import annotations

from backend.application.cash_register.permissions import CashPermissions
from backend.domain.cash_register.exceptions import CashPermissionDeniedError


def ensure_owner_or_intervention(auth, *, shift_cashier_user_id: str, actor_user_id: str,
                                 branch_id: str, intervention_permission: str,
                                 reason: str | None = None, require_reason: bool = True,
                                 action: str = "operar") -> bool:
    """True si es una INTERVENCIÓN (turno ajeno autorizado); False si es propio.
    Lanza `CashPermissionDeniedError` si no procede."""
    if str(shift_cashier_user_id or "") == str(actor_user_id or ""):
        return False
    if not auth.has_permission(user_id=actor_user_id, permission_code=intervention_permission,
                               branch_id=branch_id):
        raise CashPermissionDeniedError(
            f"El turno es de otro cajero: no puedes {action}lo. Sólo un supervisor con "
            "permiso para intervenir turnos ajenos puede hacerlo.")
    if require_reason and not (reason or "").strip():
        raise CashPermissionDeniedError(
            f"Para {action} el turno de otro cajero escribe el motivo de la intervención.")
    return True


def ensure_can_open_for(auth, *, cashier_user_id: str, actor_user_id: str,
                        branch_id: str) -> None:
    if str(cashier_user_id or "") == str(actor_user_id or ""):
        return
    if not auth.has_permission(user_id=actor_user_id,
                               permission_code=CashPermissions.SHIFT_REASSIGN,
                               branch_id=branch_id):
        raise CashPermissionDeniedError(
            "Sólo puedes abrir tu propio turno. Abrirlo a nombre de otro cajero requiere "
            "el permiso de reasignar turnos.")
