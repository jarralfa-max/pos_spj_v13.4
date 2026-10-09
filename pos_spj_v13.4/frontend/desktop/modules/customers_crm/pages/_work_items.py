"""Seguimiento de un registro: actividades, tareas y notas (CRM-43, §23-25).

Un solo panel para el expediente del cliente, el detalle de un prospecto,
una oportunidad o un caso: lo que cambia es el registro relacionado
(``CUSTOMER``/``LEAD``/``OPPORTUNITY``/``CASE``). Los diálogos de alta viven
aquí también para que «Nueva llamada» abra el mismo formulario desde
cualquier pantalla.

Una actividad vencida se muestra con su ESTADO («Vencida»), no sólo con color
(§24); el estado efectivo lo calcula el dominio (``effective_status``).
"""

from __future__ import annotations

from datetime import timedelta

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget

from backend.application.crm.permissions import CRMPermissions
from frontend.desktop.components import (
    ColumnSpec,
    StandardTable,
    create_secondary_button,
)
from frontend.desktop.modules.customers_crm.formatting import fmt_datetime, local_now
from frontend.desktop.modules.customers_crm.forms import FieldSpec, ask
from frontend.desktop.modules.customers_crm.labels import label, options
from frontend.desktop.modules.customers_crm.pages._pill_tab_bar import PillTabBar
from frontend.desktop.themes.tokens import Spacing


def _default_when():
    return (local_now() + timedelta(days=1)).replace(hour=10, minute=0, second=0,
                                                     microsecond=0).replace(tzinfo=None)


def new_activity(parent, presenter, entity_type: str, entity_id: str, *,
                 activity_type: str | None = None):
    types = options("activity_type", exclude=("TASK", "NOTE"))
    return ask(parent, title="Nueva actividad", submit_text="Programar", fields=(
        FieldSpec("activity_type", "Tipo", "choice", required=True, options=tuple(types),
                  default=activity_type or "CALL"),
        FieldSpec("subject", "Asunto", required=True,
                  placeholder="Ej. Llamar para confirmar pedido semanal"),
        FieldSpec("scheduled_at", "Fecha y hora", "datetime", default=_default_when()),
        FieldSpec("assigned_user_id", "Responsable", "user", default=presenter.current_user_id()),
        FieldSpec("description", "Detalle", "textarea"),
    ), user_options=presenter.users(), on_submit=lambda v: presenter.run(
        "create_activity", related_entity_type=entity_type, related_entity_id=entity_id,
        activity_type=v["activity_type"], subject=v["subject"],
        scheduled_at=v["scheduled_at"], assigned_user_id=v["assigned_user_id"],
        description=v["description"]))


def new_task(parent, presenter, entity_type: str, entity_id: str):
    return ask(parent, title="Nueva tarea", submit_text="Crear tarea", fields=(
        FieldSpec("title", "Tarea", required=True, placeholder="Ej. Enviar lista de precios"),
        FieldSpec("due_at", "Vence", "datetime", default=_default_when()),
        FieldSpec("assigned_user_id", "Responsable", "user", default=presenter.current_user_id()),
        FieldSpec("description", "Detalle", "textarea"),
    ), user_options=presenter.users(), on_submit=lambda v: presenter.run(
        "create_task", related_entity_type=entity_type, related_entity_id=entity_id,
        title=v["title"], due_at=v["due_at"], assigned_user_id=v["assigned_user_id"],
        description=v["description"]))


def new_note(parent, presenter, entity_type: str, entity_id: str):
    fields = [FieldSpec("body", "Nota", "textarea", required=True)]
    if presenter.can(CRMPermissions.NOTES_CREATE_PRIVATE):
        fields.append(FieldSpec("is_private", "Nota privada (sólo quien tenga permiso la ve)",
                                "check"))
    return ask(parent, title="Nueva nota", submit_text="Guardar nota", fields=tuple(fields),
               on_submit=lambda v: presenter.run(
                   "create_note", related_entity_type=entity_type,
                   related_entity_id=entity_id, body=v["body"],
                   is_private=bool(v.get("is_private"))))


def reschedule(parent, presenter, kind: str, item_id: str):
    command = "reschedule_activity" if kind == "ACTIVITY" else "reschedule_task"
    key = "new_scheduled_at" if kind == "ACTIVITY" else "new_due_at"
    id_key = "activity_id" if kind == "ACTIVITY" else "task_id"
    return ask(parent, title="Reprogramar", submit_text="Reprogramar", fields=(
        FieldSpec("when", "Nueva fecha y hora", "datetime", default=_default_when()),
    ), on_submit=lambda v: presenter.run(command, **{id_key: item_id, key: v["when"]}))


def reassign(parent, presenter, kind: str, item_id: str):
    command = "reassign_activity" if kind == "ACTIVITY" else "assign_task"
    id_key = "activity_id" if kind == "ACTIVITY" else "task_id"
    return ask(parent, title="Reasignar", submit_text="Reasignar", fields=(
        FieldSpec("user", "Nuevo responsable", "user", required=True),
    ), user_options=presenter.users(), on_submit=lambda v: presenter.run(
        command, **{id_key: item_id, "assignee_user_id": v["user"]}))


def cancel_item(parent, presenter, kind: str, item_id: str):
    command = "cancel_activity" if kind == "ACTIVITY" else "cancel_task"
    id_key = "activity_id" if kind == "ACTIVITY" else "task_id"
    return ask(parent, title="Cancelar", submit_text="Cancelar registro", fields=(
        FieldSpec("reason", "Motivo", "textarea", required=True),
    ), on_submit=lambda v: presenter.run(command, **{id_key: item_id, "reason": v["reason"]}))


def complete_item(presenter, kind: str, item_id: str):
    if kind == "ACTIVITY":
        return presenter.run("complete_activity", activity_id=item_id)
    return presenter.run("complete_task", task_id=item_id)


class WorkItemsPanel(QWidget):
    """Actividades / Tareas / Notas de UN registro relacionado."""

    _ACTIVITY_COLUMNS = (ColumnSpec("Tipo"), ColumnSpec("Asunto", stretch=True),
                         ColumnSpec("Fecha", "date"), ColumnSpec("Responsable"),
                         ColumnSpec("Estado", "status"))
    _TASK_COLUMNS = (ColumnSpec("Tarea", stretch=True), ColumnSpec("Vence", "date"),
                     ColumnSpec("Responsable"), ColumnSpec("Estado", "status"))
    _NOTE_COLUMNS = (ColumnSpec("Fecha", "date"), ColumnSpec("Nota", stretch=True),
                     ColumnSpec("Autor"), ColumnSpec("Privada"))

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._entity: tuple[str, str] | None = None
        self.setObjectName("crmWorkItemsPanel")
        self.setAccessibleName("Seguimiento del registro")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.SM)

        self._tabs = PillTabBar(self)
        for key, text in (("activities", "Actividades"), ("tasks", "Tareas"), ("notes", "Notas")):
            self._tabs.add_tab(key, text)
        self._tabs.tab_changed.connect(self._show_tab)
        layout.addWidget(self._tabs)

        self._stack = QStackedWidget(self)
        self._tables = {
            "activities": StandardTable(list(self._ACTIVITY_COLUMNS), self),
            "tasks": StandardTable(list(self._TASK_COLUMNS), self),
            "notes": StandardTable(list(self._NOTE_COLUMNS), self),
        }
        for key, table in self._tables.items():
            table.setAccessibleName(f"Listado de {key}")
            table.itemSelectionChanged.connect(self._update_buttons)
            self._stack.addWidget(table)
        layout.addWidget(self._stack, stretch=1)

        self._notice = QLabel("", self)
        self._notice.setWordWrap(True)
        self._notice.hide()
        layout.addWidget(self._notice)

        row = QHBoxLayout()
        row.setSpacing(Spacing.SM)
        can = presenter.can
        self._buttons = {}
        for key, text, perm, slot in (
            ("activity", "Nueva actividad", CRMPermissions.ACTIVITIES_CREATE, self._new_activity),
            ("task", "Nueva tarea", CRMPermissions.TASKS_CREATE, self._new_task),
            ("note", "Nota", CRMPermissions.NOTES_CREATE, self._new_note),
            ("complete", "Completar", None, self._complete),
            ("reschedule", "Reprogramar", None, self._reschedule),
            ("cancel", "Cancelar", None, self._cancel),
        ):
            if perm and not can(perm):
                continue
            button = create_secondary_button(self, text)
            button.setAccessibleName(text)
            button.clicked.connect(slot)
            row.addWidget(button)
            self._buttons[key] = button
        row.addStretch(1)
        layout.addLayout(row)
        self._items: dict[str, dict[str, object]] = {"activities": {}, "tasks": {}, "notes": {}}
        self._current = "activities"
        self._tabs.activate("activities")
        self._update_buttons()

    # -- datos ---------------------------------------------------------------
    def set_entity(self, entity_type: str | None, entity_id: str | None) -> None:
        self._entity = (entity_type, entity_id) if entity_type and entity_id else None
        self.reload()

    def reload(self) -> None:
        for table in self._tables.values():
            table.load_rows([], row_ids=[])
        self._items = {"activities": {}, "tasks": {}, "notes": {}}
        if self._entity is None:
            self._update_buttons()
            return
        entity_type, entity_id = self._entity
        name = self._presenter.user_name
        try:
            activities = self._presenter.read("activities_for", entity_type=entity_type,
                                              entity_id=entity_id)
        except Exception:  # noqa: BLE001 — sin permiso de ver actividades
            activities = []
        self._items["activities"] = {a.id: a for a in activities}
        self._tables["activities"].load_rows(
            [[label("activity_type", a.activity_type), a.subject, fmt_datetime(a.scheduled_at),
              name(a.assigned_user_id), label("work_status", a.effective_status())]
             for a in activities], row_ids=[a.id for a in activities])
        try:
            tasks = self._presenter.read("tasks_for", entity_type=entity_type, entity_id=entity_id)
        except Exception:  # noqa: BLE001
            tasks = []
        self._items["tasks"] = {t.id: t for t in tasks}
        self._tables["tasks"].load_rows(
            [[t.title, fmt_datetime(t.due_at), name(t.assigned_user_id),
              label("work_status", t.effective_status())] for t in tasks],
            row_ids=[t.id for t in tasks])
        try:
            notes = self._presenter.read("notes_for", entity_type=entity_type, entity_id=entity_id)
        except Exception:  # noqa: BLE001
            notes = []
        self._items["notes"] = {n.id: n for n in notes}
        self._tables["notes"].load_rows(
            [[fmt_datetime(n.created_at), n.body, name(n.author_user_id),
              "Sí" if n.is_private else "No"] for n in notes],
            row_ids=[n.id for n in notes])
        self._update_buttons()

    # -- interacción -----------------------------------------------------------
    def _show_tab(self, key: str) -> None:
        self._current = key
        self._stack.setCurrentWidget(self._tables[key])
        self._update_buttons()

    def _selected(self):
        row_id = self._tables[self._current].selected_row_id()
        return self._items[self._current].get(row_id) if row_id else None

    def _update_buttons(self) -> None:
        has_entity = self._entity is not None
        for key in ("activity", "task", "note"):
            if key in self._buttons:
                self._buttons[key].setEnabled(has_entity)
        item = self._selected()
        open_item = (item is not None and self._current in ("activities", "tasks")
                     and getattr(item, "status", None) is not None
                     and item.status.value in ("PLANNED", "IN_PROGRESS"))
        for key in ("complete", "reschedule", "cancel"):
            if key in self._buttons:
                self._buttons[key].setEnabled(open_item)

    def _kind(self) -> str:
        return "ACTIVITY" if self._current == "activities" else "TASK"

    def _after(self, result) -> None:
        if result is None:
            return
        ok = bool(getattr(result, "success", False))
        self._notice.setProperty("state", "SUCCESS" if ok else "ERROR")
        self._notice.setText(getattr(result, "message", "") or ("Listo." if ok else "Rechazado."))
        self._notice.show()
        if ok:
            self.reload()

    def _new_activity(self) -> None:
        if self._entity:
            self._after(new_activity(self, self._presenter, *self._entity))

    def _new_task(self) -> None:
        if self._entity:
            self._after(new_task(self, self._presenter, *self._entity))

    def _new_note(self) -> None:
        if self._entity:
            self._after(new_note(self, self._presenter, *self._entity))

    def _complete(self) -> None:
        item = self._selected()
        if item is not None:
            self._after(complete_item(self._presenter, self._kind(), item.id))

    def _reschedule(self) -> None:
        item = self._selected()
        if item is not None:
            self._after(reschedule(self, self._presenter, self._kind(), item.id))

    def _cancel(self) -> None:
        item = self._selected()
        if item is not None:
            self._after(cancel_item(self, self._presenter, self._kind(), item.id))
