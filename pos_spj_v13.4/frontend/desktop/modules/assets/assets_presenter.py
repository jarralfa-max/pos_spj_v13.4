"""Presenter bridge between the Activos desktop UI and backend services (ASSET-16+).

Mirrors ``frontend/desktop/modules/customers_crm/customers_crm_presenter.py``'s
thin-bridge shape: pages never touch a repository, a QueryService import, or
raw SQL themselves, and this presenter never receives the whole app's
dependency container wholesale (enforced by the ASSET-1 UI guardrails).
Query services are looked up by name from a dict injected at construction —
ASSET-16 only builds the routing/navigation shell, so that dict is normally
empty until a composition root (not built this session, see
``docs/refactor/ASSET-15_integraciones.md``'s "Siguiente fase") wires real
``AssetDirectoryQueryService``/``AssetDashboardQueryService``/etc. instances
in. Every read method degrades to an empty/zeroed result rather than raising
when unwired — a page must always have something safe to render.

ASSET-17 adds ``dashboard()``. ASSET-18 adds ``directory()``/``detail()``.
ASSET-19 adds ``work_orders()`` — still read-only, backing a maintenance
board/agenda preview with no drag/drop or state-changing action, because no
`MaintenanceWorkOrder` use case (start/pause/complete/...) exists to call
yet. No write methods exist anywhere in this presenter — ASSET-16 through
ASSET-19 build the read side only, matching that no
`backend/application/assets/use_cases/` exists yet (see the "Siguiente
fase" note in ``docs/refactor/ASSET-15_integraciones.md``).
"""

from __future__ import annotations

from backend.application.assets.queries.dto import (
    AssetDashboardKPIsDTO,
    AssetDetailDTO,
    AssetSummaryDTO,
    MaintenanceWorkOrderSummaryDTO,
)
from frontend.desktop.modules.assets.capability_resolver import resolve_assets_capabilities
from frontend.desktop.modules.assets.view_models import AssetsCapabilities


class AssetsPresenter:
    def __init__(self, *, session_context, query_services: dict[str, object] | None = None) -> None:
        self._session = session_context
        self._query_services = dict(query_services or {})

    def can(self, permission: str) -> bool:
        checker = getattr(self._session, "tiene_permiso", None)
        return bool(callable(checker) and checker(permission))

    def capabilities(self) -> AssetsCapabilities:
        return resolve_assets_capabilities(self.can)

    def query_service(self, key: str) -> object | None:
        return self._query_services.get(key)

    def current_user_id(self) -> str:
        return str(getattr(self._session, "user_id", "") or "")

    def current_branch_id(self) -> str:
        return str(getattr(self._session, "sucursal_id", "") or "")

    def dashboard(self, *, branch_id: str | None = None) -> AssetDashboardKPIsDTO:
        service = self.query_service("dashboard")
        if service is None:
            return AssetDashboardKPIsDTO(
                total_assets=0, available=0, in_maintenance=0,
                out_of_service=0, disposal_pending=0)
        return service.kpis(branch_id=branch_id or self.current_branch_id() or None)

    def directory(self, *, branch_id: str | None = None, search: str = "",
                  status: str | None = None) -> list[AssetSummaryDTO]:
        service = self.query_service("directory")
        if service is None:
            return []
        results = service.list_by_branch(branch_id or self.current_branch_id())
        return self._filtered(results, search=search, status=status)

    def detail(self, asset_id: str) -> AssetDetailDTO | None:
        service = self.query_service("detail")
        if service is None:
            return None
        return service.get(asset_id)

    def work_orders(self, *, branch_id: str | None = None) -> list[MaintenanceWorkOrderSummaryDTO]:
        service = self.query_service("work_orders")
        if service is None:
            return []
        return service.list_all_open(branch_id=branch_id or self.current_branch_id() or None)

    @staticmethod
    def _filtered(items: list[AssetSummaryDTO], *, search: str,
                  status: str | None) -> list[AssetSummaryDTO]:
        result = items
        if status:
            result = [i for i in result if i.status.value == status]
        needle = search.strip().lower()
        if needle:
            result = [
                i for i in result
                if needle in i.name.lower() or needle in i.asset_number.lower()
            ]
        return result
