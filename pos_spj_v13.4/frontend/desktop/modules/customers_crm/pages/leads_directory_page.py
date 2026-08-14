"""CRM-16 — Directorio de prospectos/leads (route ``crm.leads``)."""

from __future__ import annotations

from frontend.desktop.components import ColumnSpec
from frontend.desktop.modules.customers_crm.pages._directory_base import (
    CustomerCrmDirectoryPage,
)

_STATUS_LABELS = {
    "NEW": "Nuevo", "ASSIGNED": "Asignado", "CONTACTED": "Contactado",
    "NURTURING": "En seguimiento", "QUALIFIED": "Calificado",
    "UNQUALIFIED": "No calificado", "CONVERTED": "Convertido", "LOST": "Perdido",
    "ARCHIVED": "Archivado",
}


class LeadsDirectoryPage(CustomerCrmDirectoryPage):
    route_id = "crm.leads"
    title = "Prospectos"
    subtitle = "Directorio de leads."
    search_placeholder = "Buscar por nombre o empresa…"
    empty_message = "No hay leads en tu alcance"
    columns = (
        ColumnSpec("Nombre"), ColumnSpec("Empresa"), ColumnSpec("Estado", "status"),
        ColumnSpec("Prioridad"), ColumnSpec("Score", "numeric"),
    )
    status_options = tuple(_STATUS_LABELS.items())

    def _fetch(self, *, search: str, status: str | None) -> list:
        return self._presenter.leads_directory(search=search, status=status)

    def _row(self, lead) -> list[str]:
        return [
            lead.display_name, lead.company_name,
            _STATUS_LABELS.get(lead.status.value, lead.status.value),
            lead.priority.value, str(lead.score),
        ]
