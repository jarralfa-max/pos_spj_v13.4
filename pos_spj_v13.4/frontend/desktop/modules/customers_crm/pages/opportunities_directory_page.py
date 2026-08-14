"""CRM-16 — Directorio de oportunidades (route ``crm.opportunities``)."""

from __future__ import annotations

from frontend.desktop.components import ColumnSpec
from frontend.desktop.formatters.money_formatter import format_money
from frontend.desktop.modules.customers_crm.pages._directory_base import (
    CustomerCrmDirectoryPage,
)

_STATUS_LABELS = {
    "OPEN": "Abierta", "WON": "Ganada", "LOST": "Perdida",
    "CANCELLED": "Cancelada", "ON_HOLD": "En espera",
}


class OpportunitiesDirectoryPage(CustomerCrmDirectoryPage):
    route_id = "crm.opportunities"
    title = "Oportunidades"
    subtitle = "Directorio de oportunidades."
    search_placeholder = "Buscar por nombre…"
    empty_message = "No hay oportunidades en tu alcance"
    columns = (
        ColumnSpec("Nombre"), ColumnSpec("Estado", "status"), ColumnSpec("Monto", "numeric"),
        ColumnSpec("Probabilidad", "numeric"), ColumnSpec("Cierre esperado", "date"),
    )
    status_options = tuple(_STATUS_LABELS.items())

    def _fetch(self, *, search: str, status: str | None) -> list:
        return self._presenter.opportunities_directory(search=search, status=status)

    def _row(self, opportunity) -> list[str]:
        return [
            opportunity.name, _STATUS_LABELS.get(opportunity.status.value, opportunity.status.value),
            format_money(opportunity.amount) if opportunity.amount is not None else "—",
            f"{opportunity.probability}%",
            opportunity.expected_close_date.isoformat() if opportunity.expected_close_date else "—",
        ]
