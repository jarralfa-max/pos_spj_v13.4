"""Quién ve los importes de un turno de Caja — UNA regla para todas las consultas
(auditoría de Caja 968e0bc, CJA-01, 2026-10-16).

MEDIDO: con un fondo de 500 y un arqueo ciego abierto, la lista de turnos
ocultaba el esperado pero el libro de movimientos devolvía `balance=500` — el
mismo número que el arqueo ciego debe ocultar —, sin pedir usuario ni permiso; y
el resumen mostraba fondo inicial, diferencias y montos de entrega a cualquiera
con acceso a Caja. El criterio existía (Corte Z ya pedía
`CAJA.ver.importes_sensibles`) pero fragmentado.

Regla:

* Con un ARQUEO CIEGO ABIERTO en el turno, nadie ve importes del turno (saldo,
  totales ni el monto de cada movimiento: sumarlos revela el esperado), salvo
  un supervisor con `CAJA.conteo.ver_esperado` que NO sea el cajero del turno.
* Sin arqueo abierto: el cajero ve los de SU turno; los de un turno ajeno exigen
  `CAJA.ver.importes_sensibles`.
"""

from __future__ import annotations

from backend.application.cash_register.blind_count_visibility import shift_has_open_blind_count
from backend.application.cash_register.permissions import CashPermissions


class CashAmountVisibility:
    def __init__(self, connection, authorization) -> None:
        self._conn = connection
        self._auth = authorization

    def _has(self, requester_user_id: str, permission: str, branch_id: str) -> bool:
        return bool(self._auth.has_permission(user_id=requester_user_id,
                                              permission_code=permission, branch_id=branch_id))

    def shift_amounts_visible(self, *, shift_id: str, cashier_user_id: str,
                              requester_user_id: str, branch_id: str) -> bool:
        owner = str(cashier_user_id or "") == str(requester_user_id or "")
        if shift_has_open_blind_count(self._conn, shift_id):
            return (not owner) and self._has(
                requester_user_id, CashPermissions.BLIND_COUNT_REVEAL_EXPECTED, branch_id)
        return owner or self._has(requester_user_id, CashPermissions.VIEW_SENSITIVE_AMOUNTS,
                                  branch_id)

    def branch_amounts_visible(self, *, requester_user_id: str, branch_id: str) -> bool:
        """Importes agregados de la sucursal (resumen): sólo con importes
        sensibles, y nunca mientras haya un arqueo ciego abierto."""
        from backend.application.cash_register.blind_count_visibility import (
            branch_has_open_blind_count,
        )
        if branch_has_open_blind_count(self._conn, branch_id):
            return False
        return self._has(requester_user_id, CashPermissions.VIEW_SENSITIVE_AMOUNTS, branch_id)
