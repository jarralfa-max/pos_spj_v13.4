"""Actividades (§23-25, CRM-43): agenda, tareas, llamadas, reuniones,
visitas, seguimientos y notas.

Antes las siete rutas decían «en construcción»; los casos de uso de
actividades, tareas, notas y recordatorios no tenían ninguna pantalla.

Las vencidas se muestran con el estado «Vencida» (texto), no sólo con color
(§24); el estado efectivo lo decide el dominio.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.application.crm.permissions import CRMPermissions
from frontend.desktop.components import ColumnSpec
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.customers_crm.formatting import fmt_datetime, local_now, parse_instant
from frontend.desktop.modules.customers_crm.forms import FieldSpec, ask
from frontend.desktop.modules.customers_crm.labels import label, options
from frontend.desktop.modules.customers_crm.pages._work_items import (
    cancel_item,
    complete_item,
    new_activity,
    new_note,
    new_task,
    reassign,
    reschedule,
)
from frontend.desktop.modules.customers_crm.pages._workbench import (
    Action,
    CrmWorkbenchPage,
    FilterSpec,
    Kpi,
    Row,
)

_OPEN = ("PLANNED", "IN_PROGRESS")
_FAR_FUTURE = datetime.max.replace(tzinfo=timezone.utc)


def _user_filter(presenter) -> FilterSpec | None:
    """Sólo quien puede reasignar ve la agenda de otros (gerente)."""
    if not presenter.can(CRMPermissions.ACTIVITIES_REASSIGN):
        return None
    return FilterSpec("user", "Mis registros", options=lambda: presenter.users())


def _related(presenter, items) -> dict:
    pairs = {(i.related_entity_type.value, i.related_entity_id) for i in items}
    if not pairs or not presenter.has_reader("related_names"):
        return {}
    try:
        return presenter.read("related_names", pairs=list(pairs))
    except Exception:  # noqa: BLE001
        return {}


def _related_text(names, item) -> str:
    kind = label("related_entity", item.related_entity_type)
    return f"{kind}: {names.get((item.related_entity_type.value, item.related_entity_id), '—')}"


def _pick_customer_then(parent, presenter, title: str, then):
    """Las altas desde el menú se ligan a un cliente (desde un prospecto,
    oportunidad o caso se hacen en su propio detalle)."""
    chosen = ask(parent, title=title, submit_text="Continuar", fields=(
        FieldSpec("customer_id", "Cliente", "customer", required=True),
    ), customer_provider=presenter.customer_search_options)
    if not chosen:
        return None
    return then(chosen["customer_id"])


class _WorkItemsWorkbench(CrmWorkbenchPage):
    """Base de las bandejas de actividades/tareas."""

    show_detail = True
    detail_title = "Detalle"

    def __init__(self, presenter, parent=None) -> None:
        user_filter = _user_filter(presenter)
        self.filters = tuple(f for f in (*self.base_filters, user_filter) if f is not None)
        super().__init__(presenter, parent)

    base_filters: tuple = ()

    def _user(self, filters) -> str | None:
        return filters.get("user") or None

    def _row_actions_for(self, kind: str) -> list[Action]:
        p = self._presenter
        open_ = lambda r: r.data.status.value in _OPEN  # noqa: E731
        complete_perm = (CRMPermissions.ACTIVITIES_COMPLETE if kind == "ACTIVITY"
                         else CRMPermissions.TASKS_COMPLETE)
        actions = []
        if kind == "ACTIVITY":
            actions.append(Action("Iniciar", lambda r: self.report(
                p.run("start_activity", activity_id=r.id)),
                enabled=lambda r: r.data.status.value == "PLANNED",
                permission=CRMPermissions.ACTIVITIES_EDIT))
        actions += [
            Action("Completar", lambda r: self.report(complete_item(p, kind, r.id)),
                   enabled=open_, permission=complete_perm, primary=True),
            Action("Reprogramar", lambda r: self.report(reschedule(self, p, kind, r.id)),
                   enabled=open_, permission=(CRMPermissions.ACTIVITIES_EDIT if kind == "ACTIVITY"
                                              else CRMPermissions.TASKS_RESCHEDULE)),
            Action("Reasignar", lambda r: self.report(reassign(self, p, kind, r.id)),
                   enabled=open_, permission=(CRMPermissions.ACTIVITIES_REASSIGN
                                              if kind == "ACTIVITY"
                                              else CRMPermissions.TASKS_REASSIGN)),
            Action("Cancelar", lambda r: self.report(cancel_item(self, p, kind, r.id)),
                   enabled=open_, permission=(CRMPermissions.ACTIVITIES_CANCEL
                                              if kind == "ACTIVITY"
                                              else CRMPermissions.TASKS_CANCEL)),
            Action("Recordatorio", lambda r: self.report(reminder_dialog(self, p, kind, r.id)),
                   enabled=open_, permission=CRMPermissions.REMINDERS_CREATE,
                   tooltip="Programa un aviso para el responsable."),
        ]
        return actions


def reminder_dialog(parent, presenter, kind: str, item_id: str):
    channels = options("reminder_channel", exclude=("PUSH_FUTURE",))
    return ask(parent, title="Recordatorio", submit_text="Programar aviso", intro=(
        "El aviso lo entrega el gestor de notificaciones; aquí sólo se define cuándo y a "
        "quién."), fields=(
        FieldSpec("remind_at", "Avisar el", "datetime",
                  default=(local_now() + timedelta(hours=1)).replace(tzinfo=None, second=0,
                                                                     microsecond=0)),
        FieldSpec("recipient", "Destinatario", "user", required=True,
                  default=presenter.current_user_id()),
        FieldSpec("channel", "Canal", "choice", options=tuple(channels), default="IN_APP"),
        FieldSpec("message", "Mensaje", "textarea"),
    ), user_options=presenter.users(), on_submit=lambda v: presenter.run(
        "create_reminder", channel=v["channel"] or "IN_APP", remind_at=v["remind_at"],
        recipient_user_id=v["recipient"], message=v["message"],
        **({"activity_id": item_id} if kind == "ACTIVITY" else {"task_id": item_id})))


def _activity_row(presenter, activity, names) -> Row:
    state = label("work_status", activity.effective_status())
    cells = [fmt_datetime(activity.scheduled_at), label("activity_type", activity.activity_type),
             activity.subject, _related_text(names, activity),
             presenter.user_name(activity.assigned_user_id), state]
    detail = [("Tipo", label("activity_type", activity.activity_type)),
              ("Asunto", activity.subject), ("Relacionado con", _related_text(names, activity)),
              ("Fecha", fmt_datetime(activity.scheduled_at)),
              ("Responsable", presenter.user_name(activity.assigned_user_id)),
              ("Estado", state), ("Completada", fmt_datetime(activity.completed_at)),
              ("Detalle", activity.description)]
    return Row(activity.id, cells, activity, detail)


class ActivitiesByTypePage(_WorkItemsWorkbench):
    """Llamadas / Reuniones / Visitas / Seguimientos."""

    icon = Icons.CALENDAR
    activity_types: tuple[str, ...] = ()
    new_label = "Nueva actividad"
    columns = (ColumnSpec("Fecha", "date"), ColumnSpec("Tipo"),
               ColumnSpec("Asunto", stretch=True), ColumnSpec("Relacionado con"),
               ColumnSpec("Responsable"), ColumnSpec("Estado", "status"))
    base_filters = (FilterSpec("status", "Pendientes", options=(
        ("ALL", "Todas"), ("OVERDUE", "Vencidas"), ("COMPLETED", "Completadas"),
        ("CANCELLED", "Canceladas"))),)

    def page_actions(self):
        p = self._presenter
        return [Action(self.new_label, lambda _r: self.report(_pick_customer_then(
            self, p, self.new_label, lambda customer_id: new_activity(
                self, p, "CUSTOMER", customer_id, activity_type=self.activity_types[0]))),
            permission=CRMPermissions.ACTIVITIES_CREATE, primary=True, needs_row=False)]

    def row_actions(self):
        return self._row_actions_for("ACTIVITY")

    def fetch(self, filters):
        items = self._presenter.read("activities_for_user", user_id=self._user(filters))
        items = [a for a in items if a.activity_type.value in self.activity_types]
        wanted = filters.get("status")
        if wanted == "OVERDUE":
            items = [a for a in items if a.effective_status().value == "OVERDUE"]
        elif wanted in ("COMPLETED", "CANCELLED"):
            items = [a for a in items if a.status.value == wanted]
        elif wanted != "ALL":
            items = [a for a in items if a.status.value in _OPEN]
        items.sort(key=lambda a: a.scheduled_at or "9999")
        names = _related(self._presenter, items)
        return [_activity_row(self._presenter, a, names) for a in items]

    def kpis(self, rows):
        overdue = sum(1 for r in rows if r.data.effective_status().value == "OVERDUE")
        return [Kpi("En la lista", str(len(rows))),
                Kpi("Vencidas", str(overdue), "danger" if overdue else "neutral")]


class CallsPage(ActivitiesByTypePage):
    route_id = "crm.calls"
    title = "Llamadas"
    subtitle = "Llamadas programadas y realizadas."
    activity_types = ("CALL",)
    new_label = "Nueva llamada"
    empty_message = "No hay llamadas pendientes."


class MeetingsPage(ActivitiesByTypePage):
    route_id = "crm.meetings"
    title = "Reuniones"
    subtitle = "Reuniones con clientes y prospectos."
    activity_types = ("MEETING",)
    new_label = "Nueva reunión"
    empty_message = "No hay reuniones pendientes."


class VisitsPage(ActivitiesByTypePage):
    route_id = "crm.visits"
    title = "Visitas"
    subtitle = "Visitas a clientes."
    activity_types = ("VISIT",)
    new_label = "Nueva visita"
    empty_message = "No hay visitas pendientes."


class FollowUpsPage(ActivitiesByTypePage):
    route_id = "crm.followups"
    title = "Seguimientos"
    subtitle = "Seguimientos comerciales, de cotización y de pago."
    activity_types = ("FOLLOW_UP", "QUOTE_REVIEW", "PAYMENT_FOLLOW_UP", "WHATSAPP", "EMAIL",
                      "OTHER")
    new_label = "Nuevo seguimiento"
    empty_message = "No hay seguimientos pendientes."


class TasksPage(_WorkItemsWorkbench):
    route_id = "crm.tasks"
    title = "Tareas"
    subtitle = "Tareas pendientes, vencidas y completadas."
    icon = Icons.TASKS
    empty_message = "No hay tareas pendientes."
    columns = (ColumnSpec("Vence", "date"), ColumnSpec("Tarea", stretch=True),
               ColumnSpec("Relacionado con"), ColumnSpec("Responsable"),
               ColumnSpec("Estado", "status"))
    base_filters = (FilterSpec("status", "Pendientes", options=(
        ("ALL", "Todas"), ("OVERDUE", "Vencidas"), ("COMPLETED", "Completadas"),
        ("CANCELLED", "Canceladas"))),)

    def page_actions(self):
        p = self._presenter
        return [Action("Nueva tarea", lambda _r: self.report(_pick_customer_then(
            self, p, "Nueva tarea", lambda customer_id: new_task(self, p, "CUSTOMER",
                                                                 customer_id))),
            permission=CRMPermissions.TASKS_CREATE, primary=True, needs_row=False)]

    def row_actions(self):
        return self._row_actions_for("TASK")

    def fetch(self, filters):
        items = self._presenter.read("tasks_for_user", user_id=self._user(filters))
        wanted = filters.get("status")
        if wanted == "OVERDUE":
            items = [t for t in items if t.effective_status().value == "OVERDUE"]
        elif wanted in ("COMPLETED", "CANCELLED"):
            items = [t for t in items if t.status.value == wanted]
        elif wanted != "ALL":
            items = [t for t in items if t.status.value in _OPEN]
        items.sort(key=lambda t: t.due_at or "9999")
        names = _related(self._presenter, items)
        rows = []
        for t in items:
            state = label("work_status", t.effective_status())
            rows.append(Row(t.id, [fmt_datetime(t.due_at), t.title, _related_text(names, t),
                                   self._presenter.user_name(t.assigned_user_id), state], t,
                            [("Tarea", t.title), ("Relacionado con", _related_text(names, t)),
                             ("Vence", fmt_datetime(t.due_at)),
                             ("Responsable", self._presenter.user_name(t.assigned_user_id)),
                             ("Estado", state), ("Completada", fmt_datetime(t.completed_at)),
                             ("Detalle", t.description)]))
        return rows

    def kpis(self, rows):
        overdue = sum(1 for r in rows if r.data.effective_status().value == "OVERDUE")
        return [Kpi("En la lista", str(len(rows))),
                Kpi("Vencidas", str(overdue), "danger" if overdue else "neutral")]


class AgendaPage(_WorkItemsWorkbench):
    """Agenda diaria / semanal (§24): actividades y tareas en un periodo."""

    route_id = "crm.calendar"
    title = "Agenda"
    subtitle = "Lo que tienes programado: actividades y tareas."
    icon = Icons.CALENDAR
    empty_message = "No tienes nada programado en este periodo."
    columns = (ColumnSpec("Cuándo", "date"), ColumnSpec("Qué"),
               ColumnSpec("Título", stretch=True), ColumnSpec("Relacionado con"),
               ColumnSpec("Responsable"), ColumnSpec("Estado", "status"))
    base_filters = (FilterSpec("period", "Hoy", options=(
        ("WEEK", "Esta semana"), ("NEXT7", "Próximos 7 días"), ("NEXT30", "Próximos 30 días"),
        ("OVERDUE", "Vencidas"))),)

    def row_actions(self):
        p = self._presenter
        open_ = lambda r: r.data.status.value in _OPEN  # noqa: E731
        kind = lambda r: "ACTIVITY" if hasattr(r.data, "activity_type") else "TASK"  # noqa: E731
        return [
            Action("Completar", lambda r: self.report(complete_item(p, kind(r), r.id)),
                   enabled=open_, primary=True),
            Action("Reprogramar", lambda r: self.report(reschedule(self, p, kind(r), r.id)),
                   enabled=open_),
            Action("Cancelar", lambda r: self.report(cancel_item(self, p, kind(r), r.id)),
                   enabled=open_),
        ]

    def _window(self, period):
        now = local_now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if period == "WEEK":
            start = start - timedelta(days=start.weekday())
            return start, start + timedelta(days=7)
        if period == "NEXT7":
            return start, start + timedelta(days=7)
        if period == "NEXT30":
            return start, start + timedelta(days=30)
        return start, start + timedelta(days=1)

    def fetch(self, filters):
        user = self._user(filters)
        activities = self._presenter.read("activities_for_user", user_id=user)
        tasks = self._presenter.read("tasks_for_user", user_id=user)
        period = filters.get("period")
        entries = []
        for item, when in ([(a, a.scheduled_at) for a in activities]
                           + [(t, t.due_at) for t in tasks]):
            moment = parse_instant(when)
            if period == "OVERDUE":
                if item.effective_status().value != "OVERDUE":
                    continue
            else:
                start, end = self._window(period)
                if moment is None or not start <= moment < end:
                    continue
            entries.append((moment or _FAR_FUTURE, item))
        entries.sort(key=lambda e: e[0])
        items = [item for _m, item in entries]
        names = _related(self._presenter, items)
        rows = []
        for item in items:
            is_activity = hasattr(item, "activity_type")
            what = (label("activity_type", item.activity_type) if is_activity else "Tarea")
            title = item.subject if is_activity else item.title
            when = item.scheduled_at if is_activity else item.due_at
            state = label("work_status", item.effective_status())
            rows.append(Row(item.id, [fmt_datetime(when), what, title,
                                      _related_text(names, item),
                                      self._presenter.user_name(item.assigned_user_id), state],
                            item, [("Qué", what), ("Título", title),
                                   ("Relacionado con", _related_text(names, item)),
                                   ("Cuándo", fmt_datetime(when)), ("Estado", state),
                                   ("Detalle", item.description)]))
        return rows

    def kpis(self, rows):
        overdue = sum(1 for r in rows if r.data.effective_status().value == "OVERDUE")
        return [Kpi("Programado", str(len(rows))),
                Kpi("Vencido", str(overdue), "danger" if overdue else "neutral")]


class NotesPage(CrmWorkbenchPage):
    """«Notas» (route ``crm.activities``): lo que escribiste en tus registros."""

    route_id = "crm.activities"
    title = "Notas"
    subtitle = "Tus notas en clientes, prospectos, oportunidades y casos."
    icon = Icons.EDIT
    empty_message = "No has escrito notas todavía."
    show_detail = True
    columns = (ColumnSpec("Fecha", "date"), ColumnSpec("Relacionado con"),
               ColumnSpec("Nota", stretch=True), ColumnSpec("Privada"))

    def page_actions(self):
        p = self._presenter
        return [Action("Nueva nota", lambda _r: self.report(_pick_customer_then(
            self, p, "Nueva nota", lambda customer_id: new_note(self, p, "CUSTOMER",
                                                                customer_id))),
            permission=CRMPermissions.NOTES_CREATE, primary=True, needs_row=False)]

    def row_actions(self):
        p = self._presenter
        return [
            Action("Editar", lambda r: self.report(ask(
                self, title="Editar nota", submit_text="Guardar", fields=(
                    FieldSpec("body", "Nota", "textarea", required=True, default=r.data.body),),
                on_submit=lambda v: p.run("update_note", note_id=r.id, body=v["body"]))),
                permission=CRMPermissions.NOTES_EDIT_OWN),
            Action("Eliminar", lambda r: self.report(p.run("delete_note", note_id=r.id)),
                   permission=CRMPermissions.NOTES_DELETE_OWN),
        ]

    def fetch(self, filters):
        notes = self._presenter.read("notes_mine")
        names = _related(self._presenter, notes)
        return [Row(n.id, [fmt_datetime(n.created_at), _related_text(names, n), n.body,
                           "Sí" if n.is_private else "No"], n,
                    [("Fecha", fmt_datetime(n.created_at)),
                     ("Relacionado con", _related_text(names, n)), ("Nota", n.body)])
                for n in notes]


ACTIVITY_ROUTE_PAGES = {
    "crm.calendar": AgendaPage,
    "crm.tasks": TasksPage,
    "crm.calls": CallsPage,
    "crm.meetings": MeetingsPage,
    "crm.visits": VisitsPage,
    "crm.activities": NotesPage,
    "crm.followups": FollowUpsPage,
}
