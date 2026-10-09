"""Directorio de clientes (route ``customers.directory``, §83).

CRM-43: antes mostraba código, nombre, el tipo en crudo (``PUBLIC_CUSTOMER``)
y el estado, sólo de clientes ACTIVOS — un cliente suspendido o bloqueado
desaparecía y no había desde dónde reactivarlo. Ahora usa
``CustomerDirectoryQueryService``: contacto (enmascarado según permiso),
responsable, segmentos, crédito y última actividad, con filtros y acciones.
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal

from backend.application.crm.permissions import CRMPermissions
from backend.application.customers.permissions import CustomerPermissions
from frontend.desktop.components import ColumnSpec
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.customers_crm.formatting import fmt_datetime
from frontend.desktop.modules.customers_crm.labels import label, options
from frontend.desktop.modules.customers_crm.pages._workbench import (
    Action,
    CrmWorkbenchPage,
    FilterSpec,
    Kpi,
    Row,
)

_HIDDEN_BY_DEFAULT = ("CLOSED", "MERGED", "ANONYMIZED")


class CustomersDirectoryPage(CrmWorkbenchPage):
    #: Compatibilidad: el workspace escucha ``entity_selected`` (doble clic).
    entity_selected = pyqtSignal(str)
    create_requested = pyqtSignal()

    route_id = "customers.directory"
    title = "Directorio de clientes"
    subtitle = "Busca por nombre, código, contacto, teléfono o correo."
    icon = Icons.CUSTOMERS
    search_placeholder = "Buscar por nombre, razón social, código, contacto, teléfono o correo…"
    empty_message = "No se encontraron clientes"
    show_detail = True
    detail_title = "Cliente"
    columns = (
        ColumnSpec("Cliente", stretch=True), ColumnSpec("Tipo"), ColumnSpec("Contacto"),
        ColumnSpec("Teléfono"), ColumnSpec("Responsable"), ColumnSpec("Segmento"),
        ColumnSpec("Crédito"), ColumnSpec("Última actividad", "date"),
        ColumnSpec("Estado", "status"),
    )
    filters = (
        FilterSpec("status", "Vigentes", options=(("ALL", "Todos"),) + tuple(
            options("customer_status"))),
        FilterSpec("type", "Todos los tipos", options=tuple(options("customer_type"))),
        FilterSpec("credit", "Con y sin crédito", options=(
            ("WITH", "Con crédito autorizado"), ("WITHOUT", "Sin crédito"))),
    )

    def page_actions(self):
        return [Action("Nuevo cliente", lambda _r: self.create_requested.emit(),
                       permission=CustomerPermissions.CREATE, primary=True, needs_row=False)]

    def row_actions(self):
        from frontend.desktop.modules.customers_crm.pages.opportunity_pages import (
            create_opportunity_dialog,
        )
        from frontend.desktop.modules.customers_crm.pages.service_pages import create_case_dialog
        p = self._presenter
        return [
            Action("Abrir expediente", lambda r: self.entity_selected.emit(r.id), primary=True),
            Action("Nueva oportunidad", lambda r: self.report(create_opportunity_dialog(
                self, p, customer_id=r.id, customer_label=r.data.customer.display_name)),
                permission=CRMPermissions.OPPORTUNITIES_CREATE),
            Action("Nuevo caso", lambda r: self.report(create_case_dialog(
                self, p, customer_id=r.id, customer_label=r.data.customer.display_name)),
                permission=CRMPermissions.CASES_CREATE),
        ]

    def fetch(self, filters):
        rows = self._presenter.read("customer_rows")
        status = filters.get("status")
        if status and status != "ALL":
            rows = [r for r in rows if r.customer.status.value == status]
        elif not status:
            rows = [r for r in rows if r.customer.status.value not in _HIDDEN_BY_DEFAULT]
        if filters.get("type"):
            rows = [r for r in rows if r.customer.customer_type.value == filters["type"]]
        if filters.get("credit") == "WITH":
            rows = [r for r in rows if r.credit_status == "AUTHORIZED"]
        elif filters.get("credit") == "WITHOUT":
            rows = [r for r in rows if r.credit_status != "AUTHORIZED"]
        result = []
        for r in rows:
            c = r.customer
            owner = self._presenter.user_name(r.owner_user_id) if r.owner_user_id else "—"
            segments = ", ".join(r.segments) or "—"
            result.append(Row(c.id, [
                c.display_name, label("customer_type", c.customer_type), r.contact_name or "—",
                r.phone or "—", owner, segments, label("credit_status", r.credit_status),
                fmt_datetime(r.last_activity_at), label("customer_status", c.status)], r,
                [("Código", str(c.code)), ("Cliente", c.display_name),
                 ("Razón social", c.legal_name or "—"),
                 ("Tipo", label("customer_type", c.customer_type)),
                 ("Etapa", label("lifecycle", c.lifecycle_stage)),
                 ("Contacto", r.contact_name or "—"), ("Teléfono", r.phone or "—"),
                 ("Correo", r.email or "—"), ("Responsable", owner), ("Segmentos", segments),
                 ("Crédito", label("credit_status", r.credit_status)),
                 ("Compras", str(c.purchase_count)),
                 ("Última compra", fmt_datetime(c.last_purchase_at)),
                 ("Estado", label("customer_status", c.status))],
                search_text=f"{c.code} {c.legal_name} {r.email}"))
        return result

    def kpis(self, rows):
        data = [r.data for r in rows]
        return [
            Kpi("En la lista", str(len(data))),
            Kpi("Activos", str(sum(1 for d in data if d.customer.status.value == "ACTIVE")),
                "success"),
            Kpi("Con crédito", str(sum(1 for d in data if d.credit_status == "AUTHORIZED")),
                "info"),
            Kpi("Sin responsable", str(sum(1 for d in data if not d.owner_user_id)), "warning"),
        ]

    def open_row(self, row) -> None:
        self.entity_selected.emit(row.id)
