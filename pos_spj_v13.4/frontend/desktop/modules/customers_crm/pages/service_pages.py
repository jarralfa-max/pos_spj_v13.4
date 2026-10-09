"""Atención al cliente (§30-32, §86): casos, quejas, solicitudes, incidencias,
escalados, SLA y detalle del caso (CRM-43).

Antes: un directorio de lectura; no se podía abrir un caso, asignarlo,
escalarlo ni resolverlo, y como no había políticas de SLA ningún caso tenía
vencimiento (migración 315).

El SLA nunca se muestra sólo con color: la columna dice «En tiempo / En riesgo
/ Vencido» y la hora de vencimiento.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from backend.application.crm.permissions import CRMPermissions
from frontend.desktop.components import (
    ColumnSpec,
    PageHeader,
    SectionCard,
    StandardTable,
    StatusBadge,
    ViewState,
    create_secondary_button,
    create_state_widget,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.customers_crm.formatting import fmt_datetime
from frontend.desktop.modules.customers_crm.forms import FieldSpec, ask
from frontend.desktop.modules.customers_crm.labels import label, options, variant
from frontend.desktop.modules.customers_crm.pages._work_items import WorkItemsPanel, new_note
from frontend.desktop.modules.customers_crm.pages._workbench import (
    Action,
    CrmWorkbenchPage,
    FilterSpec,
    Kpi,
    Row,
)
from frontend.desktop.themes.tokens import Spacing

_ACTIVE = ("NEW", "ASSIGNED", "IN_PROGRESS", "WAITING_CUSTOMER", "WAITING_INTERNAL", "ESCALATED")


def _status(row: Row) -> str:
    return row.data.case.status.value


def sla_texts(sla) -> tuple[str, str]:
    """(SLA respuesta, SLA resolución) en texto — nunca sólo color."""
    if sla is None:
        return "Sin SLA", "Sin SLA"
    first = sla.first_response_status()
    response = label("sla_status", first)
    if first.value not in ("COMPLETED", "PAUSED"):
        response += f" · {fmt_datetime(sla.first_response_due_at)}"
    overall = sla.effective_breach_status()
    resolution = label("sla_status", overall)
    if overall.value not in ("COMPLETED", "PAUSED"):
        resolution += f" · {fmt_datetime(sla.resolution_due_at)}"
    return response, resolution


def case_row(presenter, item, customer_names) -> Row:
    case = item.case
    response, resolution = sla_texts(item.sla)
    cells = [str(case.code) + (" · sensible" if case.is_sensitive else ""), case.subject,
             customer_names.get(case.customer_id, "—"), label("case_type", case.case_type),
             label("priority", case.priority), label("case_status", case.status),
             presenter.user_name(case.assigned_user_id), response, resolution,
             fmt_datetime(case.updated_at)]
    detail = [("Caso", str(case.code)), ("Asunto", case.subject),
              ("Cliente", customer_names.get(case.customer_id, "—")),
              ("Tipo", label("case_type", case.case_type)),
              ("Prioridad", label("priority", case.priority)),
              ("Canal", label("case_channel", case.channel)),
              ("Estado", label("case_status", case.status)),
              ("Responsable", presenter.user_name(case.assigned_user_id)),
              ("SLA respuesta", response), ("SLA resolución", resolution),
              ("Reaperturas", str(case.reopen_count)), ("Descripción", case.description)]
    return Row(case.id, cells, item, detail)


# -- diálogos -------------------------------------------------------------------
def create_case_dialog(parent, presenter, *, case_type: str | None = None,
                       customer_id: str | None = None, customer_label: str = ""):
    fields = [
        FieldSpec("customer_id", "Cliente", "customer", required=True, default=customer_id,
                  default_label=customer_label),
        FieldSpec("case_type", "Tipo", "choice", required=True,
                  options=tuple(options("case_type")), default=case_type or "COMPLAINT"),
        FieldSpec("subject", "Asunto", required=True,
                  placeholder="Ej. Producto llegó en mal estado"),
        FieldSpec("priority", "Prioridad", "choice", options=tuple(options("priority")),
                  default="NORMAL", helper="Define el tiempo de respuesta y de resolución (SLA)."),
        FieldSpec("channel", "Canal", "choice", options=tuple(options("case_channel")),
                  default="WALK_IN"),
        FieldSpec("description", "Descripción", "textarea"),
    ]
    if presenter.can(CRMPermissions.CASES_VIEW_SENSITIVE):
        fields.append(FieldSpec("is_sensitive", "Caso sensible (sólo lo ve quien tenga permiso)",
                                "check"))
    return ask(parent, title="Nuevo caso", submit_text="Registrar caso", fields=tuple(fields),
               customer_provider=presenter.customer_search_options,
               on_submit=lambda v: presenter.run(
                   "create_case", customer_id=v["customer_id"], case_type=v["case_type"],
                   subject=v["subject"], priority=v["priority"] or "NORMAL",
                   channel=v["channel"] or "OTHER", description=v["description"],
                   origin_branch_id=presenter.branch_id(),
                   is_sensitive=bool(v.get("is_sensitive"))))


def escalate_dialog(parent, presenter, case_id: str):
    return ask(parent, title="Escalar caso", submit_text="Escalar", fields=(
        FieldSpec("reason", "Motivo", "choice", required=True,
                  options=tuple(options("escalation_reason")), default="CRITICAL_CASE"),
        FieldSpec("to", "Escalar a", "user", required=True),
        FieldSpec("detail", "Detalle", "textarea"),
    ), user_options=presenter.users(), on_submit=lambda v: presenter.run(
        "escalate_case", case_id=case_id, reason=v["reason"], escalated_to_user_id=v["to"],
        detail=v["detail"]))


def resolve_dialog(parent, presenter, case_id: str):
    return ask(parent, title="Resolver caso", submit_text="Resolver", fields=(
        FieldSpec("summary", "Solución", "textarea", required=True),
        FieldSpec("root_cause", "Causa raíz", "textarea"),
        FieldSpec("satisfied", "¿El cliente quedó satisfecho?", "choice",
                  options=(("YES", "Sí"), ("NO", "No"), ("UNKNOWN", "No se sabe")),
                  default="UNKNOWN"),
    ), on_submit=lambda v: presenter.run(
        "resolve_case", case_id=case_id, resolution_summary=v["summary"],
        root_cause=v["root_cause"],
        customer_satisfied={"YES": True, "NO": False}.get(v["satisfied"])))


def _reason(parent, presenter, command: str, title: str, submit: str, case_id: str):
    return ask(parent, title=title, submit_text=submit, fields=(
        FieldSpec("reason", "Motivo", "textarea", required=True),
    ), on_submit=lambda v: presenter.run(command, case_id=case_id, reason=v["reason"]))


def edit_case_dialog(parent, presenter, case):
    return ask(parent, title="Editar caso", submit_text="Guardar", fields=(
        FieldSpec("subject", "Asunto", required=True, default=case.subject),
        FieldSpec("priority", "Prioridad", "choice", options=tuple(options("priority")),
                  default=case.priority.value),
        FieldSpec("description", "Descripción", "textarea", default=case.description),
    ), on_submit=lambda v: presenter.run(
        "update_case", case_id=case.id, subject=v["subject"], priority=v["priority"],
        description=v["description"]))


def case_actions(page, presenter) -> list[Action]:
    p = presenter
    st = _status
    return [
        Action("Asignar", lambda r: page.report(ask(
            page, title="Asignar caso", submit_text="Asignar", fields=(
                FieldSpec("user", "Responsable", "user", required=True),),
            user_options=p.users(), on_submit=lambda v: p.run(
                "assign_case", case_id=r.id, assignee_user_id=v["user"]))),
            enabled=lambda r: st(r) in _ACTIVE, permission=CRMPermissions.CASES_ASSIGN),
        Action("Atender", lambda r: page.report(p.run("start_case", case_id=r.id)),
               enabled=lambda r: st(r) == "ASSIGNED", permission=CRMPermissions.CASES_EDIT,
               primary=True),
        Action("1ª respuesta", lambda r: page.report(p.run("first_response_case", case_id=r.id)),
               enabled=lambda r: st(r) in _ACTIVE and r.data.sla is not None
               and r.data.sla.first_response_at is None,
               permission=CRMPermissions.CASES_EDIT,
               tooltip="Registra que ya se le respondió al cliente (cumple el SLA de respuesta)."),
        Action("Espera cliente", lambda r: page.report(p.run("wait_customer_case", case_id=r.id)),
               enabled=lambda r: st(r) in ("IN_PROGRESS", "ESCALATED"),
               permission=CRMPermissions.CASES_EDIT, tooltip="Pausa el SLA."),
        Action("Espera interna", lambda r: page.report(p.run("wait_internal_case", case_id=r.id)),
               enabled=lambda r: st(r) in ("IN_PROGRESS", "ESCALATED"),
               permission=CRMPermissions.CASES_EDIT),
        Action("Reanudar", lambda r: page.report(p.run("resume_case", case_id=r.id)),
               enabled=lambda r: st(r) in ("WAITING_CUSTOMER", "WAITING_INTERNAL"),
               permission=CRMPermissions.CASES_EDIT),
        Action("Escalar", lambda r: page.report(escalate_dialog(page, p, r.id)),
               enabled=lambda r: st(r) in _ACTIVE, permission=CRMPermissions.CASES_ESCALATE),
        Action("Resolver", lambda r: page.report(resolve_dialog(page, p, r.id)),
               enabled=lambda r: st(r) in _ACTIVE and st(r) != "NEW",
               permission=CRMPermissions.CASES_RESOLVE),
        Action("Cerrar", lambda r: page.report(p.run("close_case", case_id=r.id)),
               enabled=lambda r: st(r) == "RESOLVED", permission=CRMPermissions.CASES_CLOSE),
        Action("Reabrir", lambda r: page.report(_reason(
            page, p, "reopen_case", "Reabrir caso", "Reabrir", r.id)),
            enabled=lambda r: st(r) in ("RESOLVED", "CLOSED"),
            permission=CRMPermissions.CASES_REOPEN),
        Action("Cancelar", lambda r: page.report(_reason(
            page, p, "cancel_case", "Cancelar caso", "Cancelar caso", r.id)),
            enabled=lambda r: st(r) in _ACTIVE, permission=CRMPermissions.CASES_EDIT),
        Action("Editar", lambda r: page.report(edit_case_dialog(page, p, r.data.case)),
               enabled=lambda r: st(r) in _ACTIVE, permission=CRMPermissions.CASES_EDIT),
        Action("Nota", lambda r: page.report(new_note(page, p, "CASE", r.id)),
               permission=CRMPermissions.NOTES_CREATE),
    ]


# -- páginas -----------------------------------------------------------------------
class CasesPage(CrmWorkbenchPage):
    route_id = "crm.service_cases"
    title = "Casos"
    subtitle = "Bandeja de casos de atención en tu alcance."
    icon = Icons.PHONE
    search_placeholder = "Buscar por caso, asunto o cliente…"
    empty_message = "No hay casos en tu alcance."
    show_detail = True
    detail_title = "Caso"
    columns = (
        ColumnSpec("Caso"), ColumnSpec("Asunto", stretch=True), ColumnSpec("Cliente"),
        ColumnSpec("Tipo"), ColumnSpec("Prioridad"), ColumnSpec("Estado", "status"),
        ColumnSpec("Responsable"), ColumnSpec("SLA respuesta"), ColumnSpec("SLA resolución"),
        ColumnSpec("Actualizado", "date"),
    )
    #: tipos que muestra la ruta (vacío = todos)
    case_types: tuple[str, ...] = ()
    default_type: str | None = None
    only_escalated = False
    filters = (FilterSpec("status", "Abiertos", options=(("ALL", "Todos"),) + tuple(
        options("case_status"))),)

    def page_actions(self):
        return [Action("Nuevo caso", lambda _r: self.report(create_case_dialog(
            self, self._presenter, case_type=self.default_type)),
            permission=CRMPermissions.CASES_CREATE, primary=True, needs_row=False)]

    def row_actions(self):
        return case_actions(self, self._presenter)

    def fetch(self, filters):
        items = self._presenter.read("case_rows")
        if self.case_types:
            items = [i for i in items if i.case.case_type.value in self.case_types]
        if self.only_escalated:
            items = [i for i in items if i.case.status.value == "ESCALATED"
                     or (i.sla is not None and i.sla.escalation_level > 0
                         and i.case.status.value in _ACTIVE)]
        wanted = filters.get("status")
        if wanted and wanted != "ALL":
            items = [i for i in items if i.case.status.value == wanted]
        elif not wanted and not self.only_escalated:
            items = [i for i in items if i.case.status.value in _ACTIVE + ("RESOLVED",)]
        names = self._presenter.customer_names({i.case.customer_id for i in items})
        return [case_row(self._presenter, i, names) for i in items]

    def kpis(self, rows):
        items = [r.data for r in rows]
        breached = sum(1 for i in items if i.sla is not None
                       and i.sla.effective_breach_status().value == "BREACHED")
        at_risk = sum(1 for i in items if i.sla is not None
                      and i.sla.effective_breach_status().value == "AT_RISK")
        return [
            Kpi("En la bandeja", str(len(items))),
            Kpi("Sin responsable", str(sum(1 for i in items if not i.case.assigned_user_id)),
                "info"),
            Kpi("SLA en riesgo", str(at_risk), "warning" if at_risk else "neutral"),
            Kpi("Fuera de SLA", str(breached), "danger" if breached else "neutral"),
        ]


class ComplaintsPage(CasesPage):
    route_id = "crm.complaints"
    title = "Quejas"
    subtitle = "Quejas y problemas de calidad del producto."
    case_types = ("COMPLAINT", "PRODUCT_QUALITY")
    default_type = "COMPLAINT"
    empty_message = "No hay quejas abiertas."


class RequestsPage(CasesPage):
    route_id = "crm.requests"
    title = "Solicitudes"
    subtitle = "Solicitudes, preguntas y devoluciones solicitadas."
    case_types = ("REQUEST", "QUESTION", "RETURN_REQUEST")
    default_type = "REQUEST"
    empty_message = "No hay solicitudes abiertas."


class IncidentsPage(CasesPage):
    route_id = "crm.incidents"
    title = "Incidencias"
    subtitle = "Incidencias de entrega, pago o crédito."
    case_types = ("INCIDENT", "DELIVERY_ISSUE", "PAYMENT_ISSUE", "CREDIT_ISSUE", "OTHER")
    default_type = "INCIDENT"
    empty_message = "No hay incidencias abiertas."


class EscalationsPage(CasesPage):
    route_id = "crm.escalations"
    title = "Casos escalados"
    subtitle = "Casos escalados (por SLA, prioridad, impacto o riesgo)."
    only_escalated = True
    empty_message = "No hay casos escalados."
    filters = ()

    def page_actions(self):
        return []


class SlaPage(CrmWorkbenchPage):
    """§31: cumplimiento y políticas de SLA (configurables, nunca fijas)."""

    route_id = "crm.sla"
    title = "SLA"
    subtitle = "Políticas de tiempo de respuesta y resolución, y casos en riesgo."
    icon = Icons.CLOCK
    empty_message = "No hay políticas de SLA. Crea una para que los casos tengan vencimiento."
    columns = (ColumnSpec("Código"), ColumnSpec("Política", stretch=True),
               ColumnSpec("Aplica a"), ColumnSpec("1ª respuesta"), ColumnSpec("Resolución"),
               ColumnSpec("Riesgo desde"), ColumnSpec("Estado", "status"))
    searchable = False

    def _build_before_table(self) -> None:
        card = SectionCard(self, title="Casos fuera de SLA o en riesgo")
        self._risk_table = StandardTable(
            [ColumnSpec("Caso"), ColumnSpec("Estado SLA"), ColumnSpec("Vence"),
             ColumnSpec("Escalamiento", "numeric")], card)
        self._risk_table.setAccessibleName("Casos fuera de SLA o en riesgo")
        self._risk_table.setMaximumHeight(220)
        card.add(self._risk_table)
        self._root.addWidget(card)

    def page_actions(self):
        return [Action("Nueva política", lambda _r: self.report(self._new_policy()),
                       permission=CRMPermissions.SLA_MANAGE, primary=True, needs_row=False)]

    def row_actions(self):
        return [Action("Retirar", lambda r: self.report(self._presenter.run(
            "deactivate_sla_policy", policy_id=r.id)), enabled=lambda r: r.data.active,
            permission=CRMPermissions.SLA_MANAGE,
            tooltip="Los casos abiertos conservan su SLA; los nuevos usan otra política.")]

    def _new_policy(self):
        return ask(self, title="Nueva política de SLA", submit_text="Crear", intro=(
            "Deja en blanco lo que no quieras restringir: una política más específica (tipo, "
            "prioridad, canal) gana sobre una general."), fields=(
            FieldSpec("code", "Código", required=True, placeholder="SLA-QUEJAS-ALTA"),
            FieldSpec("name", "Nombre", required=True),
            FieldSpec("case_type", "Tipo de caso", "choice", options=tuple(options("case_type"))),
            FieldSpec("priority", "Prioridad", "choice", options=tuple(options("priority"))),
            FieldSpec("channel", "Canal", "choice", options=tuple(options("case_channel"))),
            FieldSpec("first", "Primera respuesta (minutos)", "integer", default=240, minimum=1),
            FieldSpec("resolution", "Resolución (minutos)", "integer", default=2880, minimum=1),
            FieldSpec("risk", "En riesgo al consumir (%)", "percent", default=80),
        ), on_submit=lambda v: self._presenter.run(
            "create_sla_policy", code=v["code"], name=v["name"],
            first_response_minutes=v["first"], resolution_minutes=v["resolution"],
            case_type=v["case_type"], priority=v["priority"], channel=v["channel"],
            origin_branch_id=None, at_risk_threshold_pct=v["risk"]))

    @staticmethod
    def _minutes(value: int) -> str:
        hours, minutes = divmod(int(value), 60)
        if hours and minutes:
            return f"{hours} h {minutes} min"
        return f"{hours} h" if hours else f"{minutes} min"

    def fetch(self, filters):
        policies = self._presenter.read("sla_policies")
        rows = []
        for policy in policies:
            scope = ", ".join(part for part in (
                label("case_type", policy.case_type) if policy.case_type else "",
                label("priority", policy.priority) if policy.priority else "",
                label("case_channel", policy.channel) if policy.channel else "") if part)
            rows.append(Row(policy.id, [
                policy.code, policy.name, scope or "Todos los casos",
                self._minutes(policy.first_response_minutes),
                self._minutes(policy.resolution_minutes), f"{policy.at_risk_threshold_pct}%",
                "Activa" if policy.active else "Retirada"], policy))
        self._load_risk()
        return rows

    def _load_risk(self) -> None:
        try:
            breached = self._presenter.read("sla_breached")
            at_risk = self._presenter.read("sla_at_risk")
        except Exception:  # noqa: BLE001
            breached, at_risk = [], []
        rows, ids = [], []
        for sla in list(breached) + list(at_risk):
            status = sla.effective_breach_status()
            rows.append([sla.case_id[-8:], label("sla_status", status),
                         fmt_datetime(sla.resolution_due_at), str(sla.escalation_level)])
            ids.append(sla.case_id)
        names = {}
        try:
            names = self._presenter.read("related_names", pairs=[("CASE", i) for i in ids])
        except Exception:  # noqa: BLE001
            pass
        for row, case_id in zip(rows, ids):
            row[0] = names.get(("CASE", case_id), row[0])
        self._risk_table.load_rows(rows, row_ids=ids)

    def kpis(self, rows):
        try:
            breached = len(self._presenter.read("sla_breached"))
            at_risk = len(self._presenter.read("sla_at_risk"))
        except Exception:  # noqa: BLE001
            return None
        return [Kpi("Políticas activas", str(sum(1 for r in rows if r.data.active))),
                Kpi("En riesgo", str(at_risk), "warning" if at_risk else "neutral"),
                Kpi("Vencidos", str(breached), "danger" if breached else "neutral")]


class CaseDetailPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._case_id: str | None = None
        self.setObjectName("crmCaseDetailPage")
        self.setAccessibleName("Detalle de caso")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(Spacing.MD)
        refresh = create_secondary_button(self, "Actualizar")
        refresh.clicked.connect(self.reload)
        self._header = PageHeader(self, title="Detalle de caso", icon=Icons.DOCUMENT,
                                  compact=True, actions=[refresh])
        root.addWidget(self._header)
        badges = QHBoxLayout()
        self._badge = StatusBadge("—", self)
        self._sla_badge = StatusBadge("—", self)
        badges.addWidget(self._badge)
        badges.addWidget(self._sla_badge)
        badges.addStretch(1)
        root.addLayout(badges)
        self._placeholder = create_state_widget(
            ViewState.EMPTY, self, message="Abre un caso desde «Casos» (doble clic).")
        root.addWidget(self._placeholder)
        self._body = QWidget(self)
        body = QVBoxLayout(self._body)
        body.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        facts_card = SectionCard(self._body, title="Datos")
        self._facts = QWidget(facts_card)
        self._facts_form = QFormLayout(self._facts)
        facts_card.add(self._facts)
        facts_card.body().addStretch(1)
        top.addWidget(facts_card)
        right = QVBoxLayout()
        esc_card = SectionCard(self._body, title="Escalamientos")
        self._escalations = StandardTable([ColumnSpec("Fecha", "date"), ColumnSpec("Nivel",
                                           "numeric"), ColumnSpec("Motivo"), ColumnSpec("A"),
                                           ColumnSpec("Detalle", stretch=True)], esc_card)
        self._escalations.setAccessibleName("Escalamientos del caso")
        esc_card.add(self._escalations)
        right.addWidget(esc_card)
        res_card = SectionCard(self._body, title="Resolución")
        self._resolution = QLabel("Sin resolver.", res_card)
        self._resolution.setWordWrap(True)
        res_card.add(self._resolution)
        right.addWidget(res_card)
        top.addLayout(right)
        body.addLayout(top)
        follow = SectionCard(self._body, title="Seguimiento")
        self._work = WorkItemsPanel(presenter, follow)
        follow.add(self._work)
        body.addWidget(follow, stretch=1)
        root.addWidget(self._body, stretch=1)
        self._body.hide()
        self._error = QLabel("", self)
        self._error.setProperty("state", "ERROR")
        self._error.hide()
        root.addWidget(self._error)

    def ensure_loaded(self) -> None:
        pass

    def show_case(self, case_id: str) -> None:
        self._case_id = case_id
        self.reload()

    def reload(self) -> None:
        if not self._case_id:
            return
        try:
            detail = self._presenter.read("case_detail", case_id=self._case_id)
        except Exception as exc:  # noqa: BLE001
            self._error.setText(f"No fue posible abrir el caso: {exc}")
            self._error.show()
            return
        self._error.hide()
        case = detail.case
        names = self._presenter.customer_names([case.customer_id])
        self._header.set_title(f"{case.code} · {case.subject}")
        self._header.set_subtitle(names.get(case.customer_id, ""))
        self._badge.setText(label("case_status", case.status))
        self._badge.set_status(variant("case_status", case.status))
        if detail.sla is not None:
            status = detail.sla.effective_breach_status()
            self._sla_badge.setText(f"SLA: {label('sla_status', status)}")
            self._sla_badge.set_status(variant("sla_status", status))
        else:
            self._sla_badge.setText("Sin SLA")
            self._sla_badge.set_status("neutral")

        class _Item:
            pass

        item = _Item()
        item.case, item.sla = case, detail.sla
        while self._facts_form.rowCount():
            self._facts_form.removeRow(0)
        for caption, value in case_row(self._presenter, item, names).detail:
            text = QLabel(value or "—", self._facts)
            text.setWordWrap(True)
            self._facts_form.addRow(f"{caption}:", text)
        self._escalations.load_rows(
            [[fmt_datetime(e.created_at), str(e.level), label("escalation_reason", e.reason),
              self._presenter.user_name(e.escalated_to_user_id), e.detail or "—"]
             for e in detail.escalations], row_ids=[e.id for e in detail.escalations])
        resolution = detail.resolution
        if resolution is not None:
            satisfied = {True: "Sí", False: "No"}.get(resolution.customer_satisfied, "No se sabe")
            self._resolution.setText(
                f"{resolution.resolution_summary}\nCausa raíz: {resolution.root_cause or '—'}\n"
                f"Cliente satisfecho: {satisfied} · "
                f"{self._presenter.user_name(resolution.resolved_by_user_id)} · "
                f"{fmt_datetime(resolution.created_at)}")
        else:
            self._resolution.setText("Sin resolver.")
        self._work.set_entity("CASE", case.id)
        self._placeholder.hide()
        self._body.show()


CASE_ROUTE_PAGES = {
    "crm.service_cases": CasesPage,
    "crm.complaints": ComplaintsPage,
    "crm.requests": RequestsPage,
    "crm.incidents": IncidentsPage,
    "crm.escalations": EscalationsPage,
}

__all__ = ["CASE_ROUTE_PAGES", "CaseDetailPage", "SlaPage", "create_case_dialog"]
