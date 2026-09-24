"""Alcance por sucursal REAL para Transferencias.

POR QUÉ EXISTE — medido el 2026-09-17, no deducido:

`CreateTransferRequestUseCase` YA pide alcance sobre el origen
(`authorization.require(..., branch_id=command.origin_node.branch_id)`), pero
`TransferAuthorizationPolicy.require` sólo lo evalúa `if self._scopes is not
None`, y la raíz de composición construía la política con UN solo argumento:
`TransferAuthorizationPolicy(permission_checker)`. Resultado: `_scopes` era
`None` en producción y esa comprobación **no se ejecutaba nunca**. La única
implementación del puerto en todo el árbol era un doble de test, y la guardia
que parecía cubrirlo sólo comprueba que la cadena `can_access_transfer_scope`
APAREZCA en el código fuente — pasa en verde sobre un protocolo que nadie
implementa.

Es decir: Transferencias no tenía ningún control de alcance por sucursal.

QUÉ NO HACE, dicho explícitamente:

* `warehouse_id` / `location_id` se IGNORAN. Transferencias no tiene hoy una
  fuente de alcance de almacén ni de ubicación; fingir que se validan sería
  peor que no validarlas, porque nadie volvería a mirarlo.
* No hay escape global por permiso. Los códigos de Transferencias son PLANOS
  (`TRANSFERS_VIEW_ALL_BRANCHES`) y el contexto está en `FLAT_CODE_CONTEXTS`,
  así que ese código no existe en `rol_permisos` y jamás concedería. Inventar
  una acción de catálogo aquí está prohibido por el docstring de
  `session_authorization.py`. El administrador sigue pasando porque sus
  permisos llegan como el comodín `{"*"}`, que `BranchScopeQueryService` sí
  reconoce.
* `branch_id=None` PERMITE. `authorize_exception` llama a `require()` sin
  sucursal, y denegar ahí rompería la autorización en caliente por un dato que
  la operación no tiene.
"""

from __future__ import annotations

from backend.application.security.branch_scope_query_service import (
    BranchScopeQueryService,
)


class TransferSessionScopeChecker:
    """`TransferScopeChecker` respaldado por el alcance real del usuario."""

    def __init__(self, connection) -> None:
        self._scope = BranchScopeQueryService(connection)

    def can_access_transfer_scope(
        self, *, user_id: str, branch_id: str | None,
        warehouse_id: str | None = None, location_id: str | None = None,
    ) -> bool:
        objetivo = str(branch_id or "").strip()
        if not objetivo:
            return True
        if not str(user_id or "").strip():
            return False
        permitidas = self._scope.allowed_branch_ids(user_id)
        if permitidas is None:  # alcance global
            return True
        return objetivo in set(permitidas)
