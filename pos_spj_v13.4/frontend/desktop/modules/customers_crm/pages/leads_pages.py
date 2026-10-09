"""Prospectos (§16-18, §84): directorio, calificación, conversión, descartados
y detalle (CRM-43).

Antes había sólo un directorio de lectura: no se podía dar de alta un
prospecto, asignarlo, calificarlo ni convertirlo — los casos de uso existían
sin pantalla, y un prospecto sin asignar no aparecía en ningún directorio.

Las cinco rutas comparten ``LeadsPage``; cada una fija qué estados muestra y
qué acciones pone primero.
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
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
from frontend.desktop.modules.customers_crm.formatting import fmt_date, fmt_datetime, fmt_money
from frontend.desktop.modules.customers_crm.forms import FieldSpec, ask
from frontend.desktop.modules.customers_crm.labels import label, options, variant
from frontend.desktop.modules.customers_crm.pages._outcomes import DoneWithWarning, Fail
from frontend.desktop.modules.customers_crm.pages._work_items import (
    WorkItemsPanel,
    new_activity,
    new_note,
    new_task,
)
from frontend.desktop.modules.customers_crm.pages._workbench import (
    Action,
    CrmWorkbenchPage,
    FilterSpec,
    Kpi,
    Row,
)
from frontend.desktop.themes.tokens import Spacing

_OPEN = ("NEW", "ASSIGNED", "CONTACTED", "NURTURING", "QUALIFIED")


def _status(row: Row) -> str:
    return row.data.status.value


def lead_row(presenter, lead) -> Row:
    is_open = lead.status.value in _OPEN
    follow = (fmt_datetime(lead.next_action_at) if lead.next_action_at
              else ("Sin seguimiento" if is_open else "—"))
    cells = [
        lead.display_name, lead.company_name or "—", label("lead_source", lead.source),
        presenter.user_name(lead.assigned_user_id), str(lead.score),
        label("priority", lead.priority), fmt_datetime(lead.last_contact_at), follow,
        label("lead_status", lead.status),
    ]
    detail = [
        ("Folio", str(lead.code)), ("Prospecto", lead.display_name),
        ("Empresa", lead.company_name), ("Contacto", lead.contact_name),
        ("Teléfono", lead.phone_e164 or ""), ("Correo", lead.email or ""),
        ("Fuente", label("lead_source", lead.source)),
        ("Responsable", presenter.user_name(lead.assigned_user_id)),
        ("Valor estimado", fmt_money(lead.estimated_value)),
        ("Próxima acción", follow), ("Estado", label("lead_status", lead.status)),
        ("Alta", fmt_datetime(lead.created_at)),
    ]
    return Row(lead.id, cells, lead, detail, search_text=f"{lead.code} {lead.contact_name} "
               f"{lead.phone_e164 or ''} {lead.email or ''}")


# -- diálogos compartidos ------------------------------------------------------
def create_lead_dialog(parent, presenter):
    def submit(v):
        result = presenter.run(
            "create_lead", display_name=v["display_name"], company_name=v["company_name"],
            contact_name=v["contact_name"], phone_e164=v["phone"], email=v["email"],
            source=v["source"] or "OTHER", priority=v["priority"] or "NORMAL",
            estimated_value=v["estimated_value"] or None, origin_branch_id=presenter.branch_id(),
            allow_duplicate=bool(v["allow_duplicate"]))
        if not result.success:
            if getattr(result, "error_code", "") == "DUPLICATE":
                return Fail("Ya existe un prospecto con ese nombre, teléfono o correo. "
                             "Revísalo en el directorio o marca «Registrar aunque parezca "
                             "duplicado».")
            return result
        if v["assigned_user_id"] and presenter.can(CRMPermissions.LEADS_ASSIGN):
            try:
                assigned = presenter.run("assign_lead", lead_id=result.entity_id,
                                         assignee_user_id=v["assigned_user_id"], reason="alta")
            except Exception as exc:  # noqa: BLE001 — el alta YA ocurrió
                assigned = Fail(str(exc))
            if not assigned.success:
                return DoneWithWarning(
                    f"Prospecto creado, pero no se asignó: {assigned.message}")
        return result

    return ask(parent, title="Nuevo prospecto", submit_text="Registrar prospecto", fields=(
        FieldSpec("display_name", "Prospecto", required=True,
                  placeholder="Nombre de la persona o del negocio"),
        FieldSpec("company_name", "Empresa"),
        FieldSpec("contact_name", "Persona de contacto"),
        FieldSpec("phone", "Teléfono", "phone"),
        FieldSpec("email", "Correo", "email"),
        FieldSpec("source", "Fuente", "choice", options=tuple(options("lead_source")),
                  default="WALK_IN"),
        FieldSpec("priority", "Prioridad", "choice",
                  options=tuple(options("priority", exclude=("CRITICAL",))), default="NORMAL"),
        FieldSpec("estimated_value", "Valor estimado", "money"),
        FieldSpec("assigned_user_id", "Responsable", "user",
                  default=presenter.current_user_id()),
        FieldSpec("allow_duplicate", "Registrar aunque parezca duplicado", "check"),
    ), user_options=presenter.users(), on_submit=submit)


def qualify_dialog(parent, presenter, lead_id: str):
    def submit(v):
        model = v["model"] or "MANUAL"
        criteria = {key: bool(v[key]) for key in
                    ("need", "budget", "authority", "timeline", "zone", "credit")}
        kwargs = {"lead_id": lead_id, "model": model, "notes": v["notes"]}
        if model == "MANUAL":
            kwargs["manual_decision"] = v["decision"] or None
            kwargs["criteria"] = {k: c for k, c in criteria.items() if c} or None
        elif model == "SCORE_BASED":
            kwargs.update(score=v["score"], score_threshold=v["threshold"])
        elif model == "BANT_LIKE":
            kwargs.update(criteria=criteria, min_criteria_passed=v["min_criteria"])
        else:
            kwargs.update(criteria=criteria, custom_decision=v["decision"] or None)
        return presenter.run("qualify_lead", **kwargs)

    return ask(parent, title="Calificar prospecto", submit_text="Registrar calificación",
               intro="Elige cómo se decide. La calificación queda como evidencia: modelo, "
                     "criterios, puntaje, quién decidió y cuándo.", fields=(
        FieldSpec("model", "Modelo", "choice", options=tuple(options("qualification_model")),
                  default="BANT_LIKE"),
        FieldSpec("need", "Tiene una necesidad que cubrimos", "check"),
        FieldSpec("budget", "Tiene presupuesto", "check"),
        FieldSpec("authority", "Habla con quien decide la compra", "check"),
        FieldSpec("timeline", "Compraría en un plazo concreto", "check"),
        FieldSpec("zone", "Está en zona de atención / reparto", "check"),
        FieldSpec("credit", "Capacidad de pago o de crédito", "check"),
        FieldSpec("min_criteria", "Criterios mínimos para calificar (criterios)", "integer",
                  default=4, maximum=6),
        FieldSpec("score", "Puntaje (por puntaje)", "integer", default=0, maximum=100),
        FieldSpec("threshold", "Puntaje mínimo (por puntaje)", "integer", default=60,
                  maximum=100),
        FieldSpec("decision", "Decisión (manual o regla propia)", "choice",
                  options=tuple(options("qualification_decision"))),
        FieldSpec("notes", "Notas / evidencia", "textarea"),
    ), on_submit=submit)


def convert_dialog(parent, presenter, lead):
    stages = [(s.id, s.name) for s in presenter.read("stages") if not s.is_terminal()]

    def submit(v):
        result = presenter.run("convert_lead", lead_id=lead.id,
                               link_to_customer_id=v["link_customer"] or None,
                               allow_duplicate=bool(v["allow_duplicate"]))
        if not result.success:
            if getattr(result, "error_code", "") == "DUPLICATE":
                dupes = result.data.get("duplicates", [])
                names = presenter.customer_names([d["customer_id"] for d in dupes])
                listed = ", ".join(names.get(d["customer_id"], "cliente") for d in dupes)
                return Fail(f"Ya hay clientes parecidos: {listed}. Vincúlalo a uno existente "
                             "o marca «Crear cliente nuevo aunque se parezca».")
            return result
        if v["create_opportunity"]:
            try:
                opportunity = presenter.run(
                    "create_opportunity_from_lead", lead_id=lead.id,
                    customer_id=result.data["customer_id"], stage_id=v["stage_id"] or None,
                    amount=v["amount"] or lead.estimated_value,
                    expected_close_date=v["expected_close"])
            except Exception as exc:  # noqa: BLE001 — la conversión YA ocurrió
                opportunity = Fail(str(exc))
            if not opportunity.success:
                return DoneWithWarning(
                    f"Prospecto convertido, pero la oportunidad no se creó: "
                    f"{opportunity.message}")
        return result

    return ask(parent, title=f"Convertir a cliente: {lead.display_name}",
               submit_text="Convertir", intro="El prospecto no se borra: queda como "
               "«Convertido» y enlazado al cliente. Si el cliente ya existe, vincúlalo para "
               "no duplicarlo.", fields=(
        FieldSpec("link_customer", "Vincular a un cliente existente (opcional)", "customer"),
        FieldSpec("allow_duplicate", "Crear cliente nuevo aunque se parezca a otro", "check"),
        FieldSpec("create_opportunity", "Crear también una oportunidad", "check", default=True),
        FieldSpec("stage_id", "Etapa inicial", "choice", options=tuple(stages),
                  default=stages[0][0] if stages else None),
        FieldSpec("amount", "Monto estimado", "money", default=lead.estimated_value),
        FieldSpec("expected_close", "Cierre esperado", "date"),
    ), customer_provider=presenter.customer_search_options, on_submit=submit)


def reason_dialog(parent, title: str, submit_text: str, run):
    return ask(parent, title=title, submit_text=submit_text, fields=(
        FieldSpec("reason", "Motivo", "textarea", required=True),
    ), on_submit=lambda v: run(v["reason"]))


def assign_dialog(parent, presenter, command: str, id_key: str, record_id: str,
                  *, with_reason: bool = True):
    fields = [FieldSpec("user", "Responsable", "user", required=True)]
    if with_reason:
        fields.append(FieldSpec("reason", "Motivo de la asignación", "textarea"))

    def submit(v):
        kwargs = {id_key: record_id, "assignee_user_id": v["user"]}
        if with_reason:
            kwargs["reason"] = v.get("reason") or ""
        return presenter.run(command, **kwargs)

    return ask(parent, title="Asignar responsable", submit_text="Asignar",
               fields=tuple(fields), user_options=presenter.users(), on_submit=submit)


def edit_lead_dialog(parent, presenter, lead):
    return ask(parent, title="Editar prospecto", submit_text="Guardar", fields=(
        FieldSpec("display_name", "Prospecto", required=True, default=lead.display_name),
        FieldSpec("company_name", "Empresa", default=lead.company_name),
        FieldSpec("contact_name", "Persona de contacto", default=lead.contact_name),
        FieldSpec("next_action_at", "Próxima acción", "datetime"),
    ), on_submit=lambda v: presenter.run(
        "update_lead", lead_id=lead.id, display_name=v["display_name"],
        company_name=v["company_name"], contact_name=v["contact_name"],
        next_action_at=v["next_action_at"]))


# -- páginas ---------------------------------------------------------------------
class LeadsPage(CrmWorkbenchPage):
    route_id = "crm.leads"
    title = "Prospectos"
    subtitle = "Prospectos y leads en tu alcance."
    icon = Icons.SEARCH
    search_placeholder = "Buscar por nombre, empresa, folio, teléfono o correo…"
    empty_message = "No hay prospectos en tu alcance. Registra el primero con «Nuevo prospecto»."
    show_detail = True
    detail_title = "Prospecto"
    columns = (
        ColumnSpec("Prospecto", stretch=True), ColumnSpec("Empresa"), ColumnSpec("Fuente"),
        ColumnSpec("Responsable"), ColumnSpec("Score", "numeric", min_width=60,
                                              preferred_width=70),
        ColumnSpec("Prioridad"), ColumnSpec("Último contacto", "date"),
        ColumnSpec("Próxima acción", "date"), ColumnSpec("Estado", "status"),
    )
    #: estados que muestra esta ruta (vacío = todos).
    statuses: tuple[str, ...] = ()
    filters = (FilterSpec("status", "Todos los estados",
                          options=tuple(options("lead_status"))),)

    def page_actions(self):
        return [Action("Nuevo prospecto", lambda _r: self.report(
            create_lead_dialog(self, self._presenter)), permission=CRMPermissions.LEADS_CREATE,
            primary=True, needs_row=False)]

    def row_actions(self):
        p = self._presenter
        return [
            Action("Asignar", lambda r: self.report(assign_dialog(
                self, p, "assign_lead", "lead_id", r.id)),
                enabled=lambda r: _status(r) in ("NEW", "ASSIGNED", "CONTACTED", "NURTURING",
                                                 "UNQUALIFIED"),
                permission=CRMPermissions.LEADS_ASSIGN),
            Action("Contactado", lambda r: self.report(p.run("mark_lead_contacted",
                                                             lead_id=r.id)),
                   enabled=lambda r: _status(r) in ("ASSIGNED", "NURTURING"),
                   permission=CRMPermissions.LEADS_EDIT,
                   tooltip="Registra que ya se contactó (fecha de último contacto)."),
            Action("En seguimiento", lambda r: self.report(p.run("start_lead_nurturing",
                                                                 lead_id=r.id)),
                   enabled=lambda r: _status(r) in ("ASSIGNED", "CONTACTED"),
                   permission=CRMPermissions.LEADS_EDIT),
            Action("Calificar", lambda r: self.report(qualify_dialog(self, p, r.id)),
                   enabled=lambda r: _status(r) in ("ASSIGNED", "CONTACTED", "NURTURING"),
                   permission=CRMPermissions.LEADS_QUALIFY, primary=self.route_id ==
                   "crm.lead_qualification"),
            Action("Descalificar", lambda r: self.report(reason_dialog(
                self, "Descalificar prospecto", "Descalificar",
                lambda reason: p.run("disqualify_lead", lead_id=r.id, reason=reason))),
                enabled=lambda r: _status(r) in ("NEW", "ASSIGNED", "CONTACTED", "NURTURING"),
                permission=CRMPermissions.LEADS_DISQUALIFY),
            Action("Convertir", lambda r: self.report(convert_dialog(self, p, r.data)),
                   enabled=lambda r: _status(r) == "QUALIFIED",
                   permission=CRMPermissions.LEADS_CONVERT,
                   primary=self.route_id == "crm.lead_conversion"),
            Action("Perdido", lambda r: self.report(reason_dialog(
                self, "Marcar prospecto como perdido", "Marcar perdido",
                lambda reason: p.run("lose_lead", lead_id=r.id, reason=reason))),
                enabled=lambda r: _status(r) in _OPEN, permission=CRMPermissions.LEADS_EDIT),
            Action("Archivar", lambda r: self.report(p.run("archive_lead", lead_id=r.id)),
                   enabled=lambda r: _status(r) in ("UNQUALIFIED", "LOST"),
                   permission=CRMPermissions.LEADS_ARCHIVE),
            Action("Editar", lambda r: self.report(edit_lead_dialog(self, p, r.data)),
                   enabled=lambda r: _status(r) in _OPEN, permission=CRMPermissions.LEADS_EDIT),
            Action("Actividad", lambda r: self.report(new_activity(self, p, "LEAD", r.id)),
                   permission=CRMPermissions.ACTIVITIES_CREATE),
            Action("Nota", lambda r: self.report(new_note(self, p, "LEAD", r.id)),
                   permission=CRMPermissions.NOTES_CREATE),
        ]

    def fetch(self, filters):
        leads = self._presenter.read("leads")
        if self.statuses:
            leads = [lead for lead in leads if lead.status.value in self.statuses]
        if filters.get("status"):
            leads = [lead for lead in leads if lead.status.value == filters["status"]]
        return [lead_row(self._presenter, lead) for lead in leads]

    def kpis(self, rows):
        leads = [r.data for r in rows]
        open_leads = [lead for lead in leads if lead.status.value in _OPEN]
        return [
            Kpi("Nuevos", str(sum(1 for lead in leads if lead.status.value == "NEW")), "info"),
            Kpi("Abiertos", str(len(open_leads))),
            Kpi("Sin seguimiento", str(sum(1 for lead in open_leads if not lead.next_action_at)),
                "warning"),
            Kpi("Calificados", str(sum(1 for lead in leads if lead.status.value == "QUALIFIED")),
                "success"),
        ]


class LeadQualificationPage(LeadsPage):
    route_id = "crm.lead_qualification"
    title = "Calificación"
    subtitle = "Prospectos asignados o contactados que falta calificar."
    statuses = ("ASSIGNED", "CONTACTED", "NURTURING")
    empty_message = "No hay prospectos pendientes de calificar."
    filters = ()


class LeadConversionPage(LeadsPage):
    route_id = "crm.lead_conversion"
    title = "Conversión"
    subtitle = "Prospectos calificados listos para convertirse en clientes."
    statuses = ("QUALIFIED",)
    empty_message = "No hay prospectos calificados por convertir."
    filters = ()


class DiscardedLeadsPage(LeadsPage):
    route_id = "crm.leads_discarded"
    title = "Leads descartados"
    subtitle = "No calificados, perdidos y archivados."
    statuses = ("UNQUALIFIED", "LOST", "ARCHIVED")
    empty_message = "No hay prospectos descartados."
    filters = ()

    def page_actions(self):
        return []

    def kpis(self, rows):
        return None


class LeadDetailPage(QWidget):
    """Detalle de un prospecto: datos, evidencia de calificación y seguimiento."""

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._lead_id: str | None = None
        self.setObjectName("crmLeadDetailPage")
        self.setAccessibleName("Detalle de prospecto")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(Spacing.MD)
        refresh = create_secondary_button(self, "Actualizar")
        refresh.clicked.connect(self.reload)
        self._header = PageHeader(self, title="Detalle de prospecto", icon=Icons.USER,
                                  compact=True, actions=[refresh])
        root.addWidget(self._header)
        badge_row = QHBoxLayout()
        self._badge = StatusBadge("—", self)
        badge_row.addWidget(self._badge)
        badge_row.addStretch(1)
        root.addLayout(badge_row)
        self._placeholder = create_state_widget(
            ViewState.EMPTY, self, message="Abre un prospecto desde «Prospectos» (doble clic).")
        root.addWidget(self._placeholder)
        self._body = QWidget(self)
        body = QVBoxLayout(self._body)
        body.setContentsMargins(0, 0, 0, 0)
        self._facts_card = SectionCard(self._body, title="Datos")
        self._facts = QWidget(self._facts_card)
        self._facts_form = QFormLayout(self._facts)
        self._facts_card.add(self._facts)
        self._facts_card.body().addStretch(1)
        body.addWidget(self._facts_card)
        qual_card = SectionCard(self._body, title="Calificaciones")
        self._qualifications = StandardTable(
            [ColumnSpec("Fecha", "date"), ColumnSpec("Modelo"), ColumnSpec("Decisión"),
             ColumnSpec("Puntaje", "numeric"), ColumnSpec("Notas", stretch=True)], qual_card)
        self._qualifications.setAccessibleName("Historial de calificaciones")
        qual_card.add(self._qualifications)
        body.addWidget(qual_card)
        follow_card = SectionCard(self._body, title="Seguimiento")
        self._work = WorkItemsPanel(presenter, follow_card)
        follow_card.add(self._work)
        body.addWidget(follow_card, stretch=1)
        root.addWidget(self._body, stretch=1)
        self._body.hide()
        self._error = QLabel("", self)
        self._error.setProperty("state", "ERROR")
        self._error.setWordWrap(True)
        self._error.hide()
        root.addWidget(self._error)

    def ensure_loaded(self) -> None:
        pass

    def show_lead(self, lead_id: str) -> None:
        self._lead_id = lead_id
        self.reload()

    def reload(self) -> None:
        if not self._lead_id:
            return
        try:
            profile = self._presenter.read("lead_profile", lead_id=self._lead_id)
        except Exception as exc:  # noqa: BLE001
            self._error.setText(f"No fue posible abrir el prospecto: {exc}")
            self._error.show()
            return
        self._error.hide()
        lead = profile.lead
        self._header.set_title(lead.display_name)
        self._header.set_subtitle(f"{lead.code} · {label('lead_source', lead.source)}")
        self._badge.setText(label("lead_status", lead.status))
        self._badge.set_status(variant("lead_status", lead.status))
        while self._facts_form.rowCount():
            self._facts_form.removeRow(0)
        for caption, value in lead_row(self._presenter, lead).detail:
            text = QLabel(value or "—", self._facts)
            text.setWordWrap(True)
            self._facts_form.addRow(f"{caption}:", text)
        quals = profile.qualifications
        self._qualifications.load_rows(
            [[fmt_date(q.created_at), label("qualification_model", q.model),
              label("qualification_decision", q.decision),
              "—" if q.score is None else str(q.score), q.notes or "—"] for q in quals],
            row_ids=[q.id for q in quals])
        self._work.set_entity("LEAD", lead.id)
        self._placeholder.hide()
        self._body.show()


LEAD_ROUTE_PAGES = {
    "crm.leads": LeadsPage,
    "crm.lead_qualification": LeadQualificationPage,
    "crm.lead_conversion": LeadConversionPage,
    "crm.leads_discarded": DiscardedLeadsPage,
}

__all__ = ["LEAD_ROUTE_PAGES", "LeadDetailPage", "LeadsPage", "create_lead_dialog",
           "assign_dialog", "reason_dialog"]
