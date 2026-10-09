"""Segmentación (§33-36, CRM-43): segmentos, etiquetas, territorios, carteras
y propietarios.

Antes: cinco rutas «en construcción»; los casos de uso de segmentos,
etiquetas, territorios, carteras y responsables existían sin pantalla.

Patrón común: el catálogo a la izquierda y, al elegir un renglón, sus
clientes en el panel de detalle; agregar o quitar un cliente se hace desde
ahí. Las etiquetas no sustituyen estatus, segmento, riesgo ni territorio
(§36): cada cosa tiene su lugar.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout

from backend.application.crm.permissions import CRMPermissions
from frontend.desktop.components import ColumnSpec, StandardTable, create_secondary_button
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.customers_crm.formatting import fmt_datetime
from frontend.desktop.modules.customers_crm.forms import FieldSpec, ask
from frontend.desktop.modules.customers_crm.labels import label, options
from frontend.desktop.modules.customers_crm.pages._workbench import (
    Action,
    CrmWorkbenchPage,
    Kpi,
    Row,
)
from frontend.desktop.themes.tokens import Spacing


class _CatalogPage(CrmWorkbenchPage):
    """Catálogo + miembros (clientes) del renglón elegido."""

    show_detail = True
    searchable = True
    reader = ""
    members_reader = ""
    member_key = ""
    view_permission = ""
    manage_permission = ""
    assign_permission = ""
    remove_permission = ""
    deactivate_command = ""
    deactivate_key = ""
    columns = (ColumnSpec("Código"), ColumnSpec("Nombre", stretch=True),
               ColumnSpec("Descripción"), ColumnSpec("Clientes", "numeric"))

    def _build_detail_extra(self, card) -> None:
        self._members = StandardTable([ColumnSpec("Cliente", stretch=True),
                                       ColumnSpec("Desde", "date"), ColumnSpec("Detalle")], card)
        self._members.setAccessibleName("Clientes del renglón elegido")
        self._members.setMinimumHeight(180)
        card.add(self._members)
        row = QHBoxLayout()
        row.setSpacing(Spacing.SM)
        self._add_member_btn = create_secondary_button(card, "Agregar cliente")
        self._add_member_btn.clicked.connect(self._add_member)
        self._remove_member_btn = create_secondary_button(card, "Quitar cliente")
        self._remove_member_btn.clicked.connect(self._remove_member)
        for button, perm in ((self._add_member_btn, self.assign_permission),
                             (self._remove_member_btn, self.remove_permission)):
            button.setVisible(bool(perm) and self._presenter.can(perm))
            row.addWidget(button)
        row.addStretch(1)
        card.body().addLayout(row)
        self._member_rows: dict = {}

    def page_actions(self):
        return [Action(self.new_label, lambda _r: self.report(self._create()),
                       permission=self.manage_permission, primary=True, needs_row=False)]

    def row_actions(self):
        return [Action("Retirar", lambda r: self.report(self._presenter.run(
            self.deactivate_command, **{self.deactivate_key: r.id})),
            permission=self.manage_permission,
            tooltip="Deja de ofrecerse; el historial se conserva.")]

    def fetch(self, filters):
        return [self._catalog_row(item) for item in self._presenter.read(self.reader)]

    def _catalog_row(self, item) -> Row:
        e = item.entity
        name = getattr(e, "name", None) or getattr(e, "label", "")
        return Row(e.id, [e.code, name, getattr(e, "description", "") or "—",
                          str(item.member_count)], item,
                   [("Código", e.code), ("Nombre", name),
                    ("Descripción", getattr(e, "description", "") or "—"),
                    ("Clientes", str(item.member_count))])

    def kpis(self, rows):
        return [Kpi("Activos", str(len(rows))),
                Kpi("Clientes asignados", str(sum(r.data.member_count for r in rows)), "info")]

    def on_selection(self, row) -> None:
        self._member_rows = {}
        if not hasattr(self, "_members"):
            return
        if row is None:
            self._members.load_rows([], row_ids=[])
        else:
            members = self._presenter.read(self.members_reader, **{self.member_key: row.id})
            names = self._presenter.customer_names({m.customer_id for m in members})
            self._member_rows = {m.link_id: m for m in members}
            self._members.load_rows([[names.get(m.customer_id, "—"), fmt_datetime(m.since),
                                      self._member_detail(m)] for m in members],
                                    row_ids=[m.link_id for m in members])
        self._add_member_btn.setEnabled(row is not None)
        self._remove_member_btn.setEnabled(row is not None)

    def _member_detail(self, member) -> str:
        return member.detail or (self._presenter.user_name(member.by_user_id)
                                 if member.by_user_id else "—")

    def _pick_customer(self, title: str, extra=()):
        return ask(self, title=title, submit_text="Agregar", fields=(
            FieldSpec("customer_id", "Cliente", "customer", required=True),) + tuple(extra),
            customer_provider=self._presenter.customer_search_options)

    def _selected_member(self):
        link = self._members.selected_row_id()
        return self._member_rows.get(link) if link else None


class SegmentsPage(_CatalogPage):
    route_id = "customers.segments"
    title = "Segmentos"
    subtitle = "Grupos de clientes para atenderlos distinto (mayoreo, restaurantes, alto valor…)."
    icon = Icons.CATEGORY
    empty_message = "No hay segmentos. Crea el primero."
    new_label = "Nuevo segmento"
    reader, members_reader, member_key = "segments", "segment_members", "segment_id"
    manage_permission = CRMPermissions.SEGMENTS_CREATE
    assign_permission = CRMPermissions.SEGMENTS_ASSIGN
    remove_permission = CRMPermissions.SEGMENTS_REMOVE
    deactivate_command, deactivate_key = "deactivate_segment", "segment_id"

    def _create(self):
        return ask(self, title="Nuevo segmento", submit_text="Crear", fields=(
            FieldSpec("code", "Código", required=True, placeholder="MAYOREO"),
            FieldSpec("name", "Nombre", required=True),
            FieldSpec("description", "Descripción", "textarea"),
            FieldSpec("rule", "Regla (descriptiva, opcional)", "textarea",
                      helper="Cómo se decide quién entra. Los miembros se agregan a mano o "
                             "por análisis de BI."),
        ), on_submit=lambda v: self._presenter.run(
            "create_segment", code=v["code"], name=v["name"], description=v["description"],
            rule_definition=v["rule"]))

    def _member_detail(self, member) -> str:
        return label("segment_source", member.detail)

    def _add_member(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        chosen = self._pick_customer("Agregar cliente al segmento")
        if chosen:
            self.report(self._presenter.run("add_to_segment", customer_id=chosen["customer_id"],
                                            segment_id=row.id))

    def _remove_member(self) -> None:
        member = self._selected_member()
        if member is not None:
            self.report(self._presenter.run("remove_from_segment", membership_id=member.link_id))


class TagsPage(_CatalogPage):
    route_id = "customers.tags"
    title = "Etiquetas"
    subtitle = ("Marcas libres para ubicar clientes. No sustituyen estatus, segmento, riesgo "
                "ni territorio.")
    icon = Icons.PRICE
    empty_message = "No hay etiquetas. Crea la primera."
    new_label = "Nueva etiqueta"
    reader, members_reader, member_key = "tags", "tag_members", "tag_id"
    manage_permission = CRMPermissions.TAGS_CREATE
    assign_permission = CRMPermissions.TAGS_ASSIGN
    remove_permission = CRMPermissions.TAGS_REMOVE
    deactivate_command, deactivate_key = "deactivate_tag", "tag_id"
    columns = (ColumnSpec("Código"), ColumnSpec("Etiqueta", stretch=True),
               ColumnSpec("Descripción"), ColumnSpec("Clientes", "numeric"))

    def _create(self):
        return ask(self, title="Nueva etiqueta", submit_text="Crear", fields=(
            FieldSpec("code", "Código", required=True, placeholder="CUMPLE-PAGOS"),
            FieldSpec("label", "Etiqueta", required=True),
        ), on_submit=lambda v: self._presenter.run("create_tag", code=v["code"],
                                                   label=v["label"]))

    def _add_member(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        chosen = self._pick_customer("Etiquetar cliente")
        if chosen:
            self.report(self._presenter.run("assign_tag", customer_id=chosen["customer_id"],
                                            tag_id=row.id))

    def _remove_member(self) -> None:
        member = self._selected_member()
        if member is not None:
            self.report(self._presenter.run("remove_tag", assignment_id=member.link_id))


class TerritoriesPage(_CatalogPage):
    route_id = "customers.territories"
    title = "Territorios"
    subtitle = "Zonas comerciales (no son sucursales): agrupan clientes para atenderlos."
    icon = Icons.LOCATION
    empty_message = "No hay territorios. Crea el primero."
    new_label = "Nuevo territorio"
    reader, members_reader, member_key = "territories", "territory_members", "territory_id"
    manage_permission = CRMPermissions.TERRITORIES_MANAGE
    assign_permission = CRMPermissions.TERRITORIES_MANAGE
    remove_permission = CRMPermissions.TERRITORIES_MANAGE
    deactivate_command, deactivate_key = "deactivate_territory", "territory_id"

    def _create(self):
        return ask(self, title="Nuevo territorio", submit_text="Crear", fields=(
            FieldSpec("code", "Código", required=True, placeholder="ZONA-NORTE"),
            FieldSpec("name", "Nombre", required=True),
            FieldSpec("description", "Descripción", "textarea"),
        ), on_submit=lambda v: self._presenter.run(
            "create_territory", code=v["code"], name=v["name"], description=v["description"]))

    def _add_member(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        chosen = self._pick_customer("Asignar cliente al territorio")
        if chosen:
            self.report(self._presenter.run("assign_territory",
                                            customer_id=chosen["customer_id"],
                                            territory_id=row.id))

    def _remove_member(self) -> None:
        member = self._selected_member()
        if member is not None:
            self.report(self._presenter.run("assign_territory", customer_id=member.customer_id,
                                            territory_id=None))


class PortfoliosPage(_CatalogPage):
    route_id = "customers.portfolios"
    title = "Carteras"
    subtitle = "Carteras comerciales (mayorista, institucional…) con su responsable."
    icon = Icons.CATALOG
    empty_message = "No hay carteras. Crea la primera."
    new_label = "Nueva cartera"
    reader, members_reader, member_key = "portfolios", "portfolio_members", "portfolio_id"
    manage_permission = CRMPermissions.PORTFOLIOS_MANAGE
    assign_permission = CRMPermissions.PORTFOLIOS_ASSIGN
    remove_permission = ""
    deactivate_command, deactivate_key = "deactivate_portfolio", "portfolio_id"
    columns = (ColumnSpec("Código"), ColumnSpec("Cartera", stretch=True),
               ColumnSpec("Responsable"), ColumnSpec("Clientes", "numeric"))

    def _catalog_row(self, item) -> Row:
        e = item.entity
        manager = self._presenter.user_name(e.manager_user_id) if e.manager_user_id else "—"
        return Row(e.id, [e.code, e.name, manager, str(item.member_count)], item,
                   [("Código", e.code), ("Cartera", e.name), ("Responsable", manager),
                    ("Descripción", e.description or "—"),
                    ("Clientes", str(item.member_count))])

    def _create(self):
        return ask(self, title="Nueva cartera", submit_text="Crear", fields=(
            FieldSpec("code", "Código", required=True, placeholder="MAYORISTAS"),
            FieldSpec("name", "Nombre", required=True),
            FieldSpec("manager", "Responsable", "user"),
            FieldSpec("description", "Descripción", "textarea"),
        ), user_options=self._presenter.users(), on_submit=lambda v: self._presenter.run(
            "create_portfolio", code=v["code"], name=v["name"], description=v["description"],
            manager_user_id=v["manager"] or None))

    def _add_member(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        chosen = self._pick_customer("Asignar cliente a la cartera", extra=(
            FieldSpec("reason", "Motivo (obligatorio al reasignar)", "textarea"),))
        if chosen:
            self.report(self._presenter.run("assign_portfolio",
                                            customer_id=chosen["customer_id"],
                                            portfolio_id=row.id, reason=chosen["reason"]))

    def _remove_member(self) -> None:
        pass


class OwnershipPage(CrmWorkbenchPage):
    """§33: responsable principal y demás roles por cliente, con historial."""

    route_id = "customers.ownership"
    title = "Propietarios"
    subtitle = "Quién atiende a cada cliente (principal, ejecutivo, crédito, atención)."
    icon = Icons.USER
    empty_message = "No hay clientes en tu alcance."
    show_detail = True
    detail_title = "Historial de asignación"
    _TYPES = ("PRIMARY", "ACCOUNT_MANAGER", "CREDIT_MANAGER", "SERVICE_OWNER")
    columns = (ColumnSpec("Cliente", stretch=True), ColumnSpec("Responsable principal"),
               ColumnSpec("Ejecutivo de cuenta"), ColumnSpec("Crédito"),
               ColumnSpec("Atención"))

    def _build_detail_extra(self, card) -> None:
        self._history = StandardTable([ColumnSpec("Fecha", "date"), ColumnSpec("Rol"),
                                       ColumnSpec("Responsable"), ColumnSpec("Asignó"),
                                       ColumnSpec("Motivo")], card)
        self._history.setAccessibleName("Historial de responsables")
        self._history.setMinimumHeight(200)
        card.add(self._history)

    def row_actions(self):
        return [Action("Asignar responsable", lambda r: self.report(ask(
            self, title="Asignar responsable", submit_text="Asignar", fields=(
                FieldSpec("type", "Rol", "choice", required=True,
                          options=tuple(options("ownership_type")), default="PRIMARY"),
                FieldSpec("user", "Responsable", "user", required=True),
                FieldSpec("reason", "Motivo (obligatorio al reasignar)", "textarea")),
            user_options=self._presenter.users(), on_submit=lambda v: self._presenter.run(
                "assign_owner", customer_id=r.id, ownership_type=v["type"],
                owner_user_id=v["user"], reason=v["reason"]))),
            permission=CRMPermissions.CUSTOMER_OWNER_ASSIGN, primary=True)]

    def fetch(self, filters):
        customers = self._presenter.read("customers")
        owners = {o.customer_id: o.owners for o in self._presenter.read(
            "owners", customer_ids=[c.id for c in customers])}
        rows = []
        for customer in customers:
            current = owners.get(customer.id, {})
            names = [self._presenter.user_name(current[t].owner_user_id) if t in current
                     else "—" for t in self._TYPES]
            rows.append(Row(customer.id, [customer.display_name, *names], customer,
                            [("Cliente", customer.display_name),
                             *((label("ownership_type", t), n)
                               for t, n in zip(self._TYPES, names))]))
        return rows

    def kpis(self, rows):
        unassigned = sum(1 for r in rows if r.cells[1] == "—")
        return [Kpi("Clientes", str(len(rows))),
                Kpi("Sin responsable", str(unassigned), "warning" if unassigned else "neutral")]

    def on_selection(self, row) -> None:
        if not hasattr(self, "_history"):
            return
        if row is None:
            self._history.load_rows([], row_ids=[])
            return
        history = self._presenter.read("owner_history", customer_id=row.id)
        self._history.load_rows([[fmt_datetime(h.created_at),
                                  label("ownership_type", h.ownership_type),
                                  self._presenter.user_name(h.owner_user_id),
                                  self._presenter.user_name(h.assigned_by_user_id)
                                  if h.assigned_by_user_id else "—", h.reason or "—"]
                                 for h in history], row_ids=[h.id for h in history])


SEGMENTATION_ROUTE_PAGES = {
    "customers.segments": SegmentsPage,
    "customers.tags": TagsPage,
    "customers.territories": TerritoriesPage,
    "customers.portfolios": PortfoliosPage,
    "customers.ownership": OwnershipPage,
}
