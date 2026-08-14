"""CRM-16 — Bandeja de casos de atención (route ``crm.service_cases``)."""

from __future__ import annotations

from frontend.desktop.components import ColumnSpec
from frontend.desktop.modules.customers_crm.pages._directory_base import (
    CustomerCrmDirectoryPage,
)

_STATUS_LABELS = {
    "NEW": "Nuevo", "ASSIGNED": "Asignado", "IN_PROGRESS": "En progreso",
    "WAITING_CUSTOMER": "Esperando cliente", "WAITING_INTERNAL": "Esperando interno",
    "ESCALATED": "Escalado", "RESOLVED": "Resuelto", "CLOSED": "Cerrado",
    "CANCELLED": "Cancelado",
}


class ServiceCasesDirectoryPage(CustomerCrmDirectoryPage):
    route_id = "crm.service_cases"
    title = "Casos"
    subtitle = "Bandeja de casos de atención."
    search_placeholder = "Buscar por asunto…"
    empty_message = "No hay casos en tu alcance"
    columns = (
        ColumnSpec("Código"), ColumnSpec("Asunto"), ColumnSpec("Tipo"),
        ColumnSpec("Estado", "status"), ColumnSpec("Prioridad"),
    )
    status_options = tuple(_STATUS_LABELS.items())

    def _fetch(self, *, search: str, status: str | None) -> list:
        return self._presenter.cases_directory(search=search, status=status)

    def _row(self, case) -> list[str]:
        return [
            str(case.code), case.subject, case.case_type.value,
            _STATUS_LABELS.get(case.status.value, case.status.value), case.priority.value,
        ]
