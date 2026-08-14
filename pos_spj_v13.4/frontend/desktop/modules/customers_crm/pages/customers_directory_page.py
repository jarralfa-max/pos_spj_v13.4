"""CRM-16 — Directorio de clientes (route ``customers.directory``)."""

from __future__ import annotations

from frontend.desktop.components import ColumnSpec
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.customers_crm.pages._directory_base import (
    CustomerCrmDirectoryPage,
)

_STATUS_LABELS = {
    "DRAFT": "Borrador", "PROSPECT": "Prospecto", "ACTIVE": "Activo",
    "INACTIVE": "Inactivo", "SUSPENDED": "Suspendido", "BLOCKED": "Bloqueado",
    "CLOSED": "Cerrado", "MERGED": "Fusionado", "ANONYMIZED": "Anonimizado",
}


class CustomersDirectoryPage(CustomerCrmDirectoryPage):
    route_id = "customers.directory"
    title = "Directorio de clientes"
    subtitle = "Búsqueda y listado de clientes."
    icon = Icons.CUSTOMERS
    search_placeholder = "Buscar por nombre, razón social o código…"
    empty_message = "No se encontraron clientes"
    columns = (
        ColumnSpec("Código"), ColumnSpec("Nombre"), ColumnSpec("Tipo"),
        ColumnSpec("Estado", "status"),
    )
    status_options = tuple(_STATUS_LABELS.items())

    def _fetch(self, *, search: str, status: str | None) -> list:
        return self._presenter.customers_directory(search=search, status=status)

    def _row(self, customer) -> list[str]:
        return [
            str(customer.code), customer.display_name, customer.customer_type.value,
            _STATUS_LABELS.get(customer.status.value, customer.status.value),
        ]
