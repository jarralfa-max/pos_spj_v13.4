"""Use cases for the "Rutas de impresión" action on the Dispositivos
section — SET-8's Routing/Failover pillar had zero UI before this round
(Perfiles was extended in `device_management_use_cases.py`; Test remains
out of scope, same reasoning as SET-9/SET-10's connection tests — it
needs a real hardware gateway this repo only has as a Protocol stub).

`CreatePrintRouteUseCase` checks for an exact-scope conflict BEFORE
inserting — `PrintRouteConflictError` mirrors the same "never let the
schema's unique-index IntegrityError reach the UI" discipline already
established for `AssignDeviceUseCase` (§62's uniqueness constraints are
real, but the clean domain error is what the presenter should catch).
"""

from __future__ import annotations

from enum import Enum

from backend.domain.device_management.entities.print_route import PrintRoute
from backend.domain.device_management.exceptions import PrintRouteConflictError, PrintRouteNotFoundError
from backend.infrastructure.db.repositories.device_management.print_route_repository import (
    SqlitePrintRouteRepository,
)


class PrintRouteStatusAction(str, Enum):
    ACTIVATE = "ACTIVATE"
    DEACTIVATE = "DEACTIVATE"


def _same_scope(route: PrintRoute, *, branch_id, workstation_id, module, channel) -> bool:
    return (
        route.branch_id == branch_id and route.workstation_id == workstation_id
        and route.module == module and route.channel == channel
    )


class CreatePrintRouteUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._routes = SqlitePrintRouteRepository(connection)

    def execute(
        self, *, document_type: str, primary_device_id: str, fallback_device_ids: tuple[str, ...] = (),
        branch_id: str | None = None, workstation_id: str | None = None, module: str | None = None,
        channel: str | None = None,
    ) -> PrintRoute:
        normalized_type = document_type.strip().upper()
        branch_id = branch_id or None
        workstation_id = workstation_id or None
        module = module or None
        channel = channel or None
        # The schema's unique index covers every row regardless of `active`
        # (§62) — an inactive route still occupies its exact scope, so the
        # conflict check must too, not just list_candidates()' active-only view.
        for candidate in self._routes.list_all():
            if candidate.document_type != normalized_type:
                continue
            if _same_scope(
                candidate, branch_id=branch_id, workstation_id=workstation_id, module=module,
                channel=channel,
            ):
                raise PrintRouteConflictError(
                    f"Ya existe una ruta para {normalized_type} en este mismo ámbito "
                    f"({'activa' if candidate.active else 'inactiva'}); edita su dispositivo principal "
                    "en vez de crear una nueva — el ámbito no puede repetirse (§62)."
                )
        route = PrintRoute.create(
            document_type=document_type, primary_device_id=primary_device_id,
            fallback_device_ids=fallback_device_ids, branch_id=branch_id, workstation_id=workstation_id,
            module=module, channel=channel,
        )
        self._routes.save(route)
        self._conn.commit()
        return route


class UpdatePrintRouteUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._routes = SqlitePrintRouteRepository(connection)

    def execute(
        self, *, route_id: str, primary_device_id: str, fallback_device_ids: tuple[str, ...] = (),
    ) -> PrintRoute:
        route = self._routes.get(route_id)
        if route is None:
            raise PrintRouteNotFoundError(f"Ruta {route_id} no encontrada")
        # Clear the fallback chain first so set_primary_device() never trips
        # on stale state (e.g. promoting a device straight from fallback
        # into primary) — same "unmark old before marking new" discipline
        # as SetDefaultThemeUseCase/ChangeTemplateVersionStatusUseCase.
        # The final set_fallback_chain() call is what validates against the
        # route's actual new primary_device_id.
        route.set_fallback_chain(())
        route.set_primary_device(primary_device_id)
        route.set_fallback_chain(fallback_device_ids)
        self._routes.save(route)
        self._conn.commit()
        return route


class ChangePrintRouteStatusUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._routes = SqlitePrintRouteRepository(connection)

    def execute(self, *, route_id: str, action: PrintRouteStatusAction) -> PrintRoute:
        route = self._routes.get(route_id)
        if route is None:
            raise PrintRouteNotFoundError(f"Ruta {route_id} no encontrada")

        if action is PrintRouteStatusAction.ACTIVATE:
            route.activate()
        elif action is PrintRouteStatusAction.DEACTIVATE:
            route.deactivate()

        self._routes.save(route)
        self._conn.commit()
        return route
