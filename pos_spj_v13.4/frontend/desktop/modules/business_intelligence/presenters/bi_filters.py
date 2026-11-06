"""Filtros de sucursal y fecha de una página de BI (SDLC-BI-001).

La sucursal se valida aquí y otra vez en `BiDashboardService`: quien pide fuera de
su alcance recibe un rechazo, no un resultado vacío.
"""
from __future__ import annotations

from dataclasses import replace

from backend.application.analytics.access import BiAccess
from backend.application.analytics.dto.bi_dashboard_dto import DashboardFilters

ALL_BRANCHES_LABEL = "Todas las sucursales"
PERIOD_PRESETS = (
    ("today", "Hoy"), ("yesterday", "Ayer"), ("week", "Esta semana"), ("month", "Este mes"),
    ("last_month", "Mes anterior"), ("custom", "Personalizado"),
)


class BiFilterState:
    def __init__(self, access: BiAccess, query_service) -> None:
        self._access = access
        self._query = query_service
        self._requested = DashboardFilters()

    @property
    def allows_all_branches(self) -> bool:
        return self._access.company_wide

    @property
    def current(self) -> DashboardFilters:
        return self._access.scope(self._requested)

    @property
    def selected_branch_id(self) -> str:
        """La sucursal elegida; `""` si no hay ninguna que elegir."""
        if self._requested.branch_id or self.allows_all_branches:
            return self._requested.branch_id
        opciones = self.branch_options()
        ids = [branch_id for branch_id, _name in opciones]
        if self._access.default_branch_id in ids:
            return self._access.default_branch_id
        return ids[0] if ids else ""

    def branch_options(self) -> list[tuple[str, str]]:
        return [(b["id"], b["nombre"]) for b in self._access.scoped_branches(self._query)]

    def branch_label(self) -> str:
        branch_id = self.current.branch_id
        if not branch_id:
            return ALL_BRANCHES_LABEL
        return next((name for bid, name in self.branch_options() if bid == branch_id), branch_id)

    def set(self, *, branch_id: str | None = None, preset: str | None = None,
            date_from: str = "", date_to: str = "") -> None:
        cambios = {}
        if branch_id is not None:
            if branch_id:
                self._access.require_branch(branch_id)
            cambios["branch_id"] = branch_id
        if preset is not None:
            if preset == "custom" and (not date_from or not date_to or date_from > date_to):
                raise ValueError("Indica un rango de fechas válido.")
            cambios.update(preset=preset, date_from=date_from, date_to=date_to)
        self._requested = replace(self._requested, **cambios)
