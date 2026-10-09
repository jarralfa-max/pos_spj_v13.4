"""Control (§45-47, §56, §76, CRM-43): calidad de datos, duplicados y fusión,
importaciones, auditoría y configuración del módulo.

Antes: cinco rutas «en construcción». Reglas que viven en los casos de uso:
fusionar exige que la ejecute alguien distinto de quien la propuso (§73);
una importación sensible la aprueba otra persona; la bitácora nunca se borra.
"""

from __future__ import annotations

import csv
from pathlib import Path

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QFileDialog, QHBoxLayout

from backend.application.crm.permissions import CRMPermissions
from backend.application.customers.permissions import CustomerPermissions
from frontend.desktop.components import (
    ColumnSpec,
    SectionCard,
    StandardTable,
    create_secondary_button,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.customers_crm.formatting import fmt_datetime
from frontend.desktop.modules.customers_crm.forms import FieldSpec, ask
from frontend.desktop.modules.customers_crm.labels import (
    event_label,
    label,
    module_label,
    options,
)
from frontend.desktop.modules.customers_crm.pages._outcomes import Fail
from frontend.desktop.modules.customers_crm.pages._workbench import (
    Action,
    CrmWorkbenchPage,
    FilterSpec,
    Kpi,
    Row,
)
from frontend.desktop.themes.tokens import Spacing


def _reason_dialog(page, title: str, run):
    return ask(page, title=title, submit_text=title, fields=(
        FieldSpec("reason", "Motivo", "textarea", required=True),),
        on_submit=lambda v: run(v["reason"]))


class DataQualityPage(CrmWorkbenchPage):
    route_id = "customers.data_quality"
    title = "Calidad de datos"
    subtitle = "Nombres incompletos, teléfonos y correos inválidos, RFC mal formado, direcciones."
    icon = Icons.QUALITY
    empty_message = "Sin pendientes de calidad. Usa «Analizar» para revisar todos los clientes."
    customer_opened = pyqtSignal(str)
    columns = (ColumnSpec("Cliente", stretch=True), ColumnSpec("Problema"),
               ColumnSpec("Detalle"), ColumnSpec("Estado", "status"),
               ColumnSpec("Detectado", "date"))
    filters = (FilterSpec("status", "Abiertas y reconocidas", options=(
        ("OPEN", "Abiertas"), ("ACKNOWLEDGED", "Reconocidas"), ("CORRECTED", "Corregidas"),
        ("DISMISSED", "Descartadas"))),)

    def page_actions(self):
        return [Action("Analizar", lambda _r: self.report(self._presenter.run(
            "scan_data_quality")), permission=CustomerPermissions.DATA_QUALITY_RESOLVE,
            primary=True, needs_row=False,
            tooltip="Revisa todos los clientes y registra lo que falte o esté mal.")]

    def row_actions(self):
        p = self._presenter
        st = lambda r: r.data.status.value  # noqa: E731
        return [
            Action("Abrir cliente", lambda r: self.customer_opened.emit(r.data.customer_id)),
            Action("Reconocer", lambda r: self.report(p.run("acknowledge_quality_issue",
                                                            issue_id=r.id)),
                   enabled=lambda r: st(r) == "OPEN",
                   permission=CustomerPermissions.DATA_QUALITY_RESOLVE),
            Action("Corregido", lambda r: self.report(p.run("correct_quality_issue",
                                                            issue_id=r.id)),
                   enabled=lambda r: st(r) in ("OPEN", "ACKNOWLEDGED"),
                   permission=CustomerPermissions.DATA_QUALITY_RESOLVE, primary=True),
            Action("Descartar", lambda r: self.report(_reason_dialog(
                self, "Descartar", lambda reason: p.run("dismiss_quality_issue", issue_id=r.id,
                                                        reason=reason))),
                enabled=lambda r: st(r) in ("OPEN", "ACKNOWLEDGED"),
                permission=CustomerPermissions.DATA_QUALITY_RESOLVE),
        ]

    def fetch(self, filters):
        wanted = filters.get("status")
        statuses = (wanted,) if wanted else ("OPEN", "ACKNOWLEDGED")
        issues = self._presenter.read("quality_issues", statuses=statuses)
        names = self._presenter.customer_names({i.customer_id for i in issues})
        return [Row(i.id, [names.get(i.customer_id, "—"), label("quality_rule", i.rule_code),
                           i.description or "—", label("quality_status", i.status),
                           fmt_datetime(i.created_at)], i) for i in issues]

    def kpis(self, rows):
        return [Kpi("Pendientes", str(len(rows)), "warning" if rows else "neutral")]

    def open_row(self, row) -> None:
        self.customer_opened.emit(row.data.customer_id)


class DuplicatesPage(CrmWorkbenchPage):
    """§45: candidatos a duplicado y fusiones (propuesta + ejecución por otra persona)."""

    route_id = "customers.duplicates"
    title = "Duplicados"
    subtitle = "Clientes que parecen la misma persona o empresa, y sus fusiones."
    icon = Icons.BUNDLE
    empty_message = "No hay posibles duplicados. Usa «Detectar» para buscarlos."
    show_detail = True
    detail_title = "Par de clientes"
    columns = (ColumnSpec("Cliente A", stretch=True), ColumnSpec("Cliente B", stretch=True),
               ColumnSpec("Coincide en"), ColumnSpec("Estado", "status"),
               ColumnSpec("Detectado", "date"))
    _REASONS = {"phone": "teléfono", "email": "correo", "tax_identifier": "RFC",
                "name": "nombre", "display_name": "nombre", "address": "dirección"}

    def _build_detail_extra(self, card) -> None:
        merges_card = SectionCard(card, title="Fusiones")
        self._merges = StandardTable([ColumnSpec("Maestro"), ColumnSpec("Se fusiona"),
                                      ColumnSpec("Estado"), ColumnSpec("Propuso"),
                                      ColumnSpec("Motivo", stretch=True)], merges_card)
        self._merges.setAccessibleName("Propuestas de fusión")
        self._merges.setMinimumHeight(160)
        merges_card.add(self._merges)
        row = QHBoxLayout()
        row.setSpacing(Spacing.SM)
        self._execute_btn = create_secondary_button(merges_card, "Ejecutar fusión")
        self._execute_btn.setToolTip("La ejecuta alguien distinto de quien la propuso.")
        self._execute_btn.clicked.connect(self._execute_merge)
        self._reject_btn = create_secondary_button(merges_card, "Rechazar fusión")
        self._reject_btn.clicked.connect(self._reject_merge)
        for button in (self._execute_btn, self._reject_btn):
            button.setVisible(self._presenter.can(CustomerPermissions.DUPLICATES_MERGE))
            row.addWidget(button)
        row.addStretch(1)
        merges_card.body().addLayout(row)
        card.add(merges_card)
        self._merge_rows: dict = {}

    def page_actions(self):
        return [Action("Detectar", lambda _r: self.report(self._presenter.run(
            "detect_duplicates")), permission=CustomerPermissions.DUPLICATES_REVIEW,
            primary=True, needs_row=False)]

    def row_actions(self):
        p = self._presenter
        st = lambda r: r.data.status.value  # noqa: E731
        return [
            Action("En revisión", lambda r: self.report(p.run("review_duplicate",
                                                              candidate_id=r.id)),
                   enabled=lambda r: st(r) == "DETECTED",
                   permission=CustomerPermissions.DUPLICATES_REVIEW),
            Action("Es duplicado", lambda r: self.report(p.run("confirm_duplicate",
                                                               candidate_id=r.id)),
                   enabled=lambda r: st(r) in ("DETECTED", "UNDER_REVIEW"),
                   permission=CustomerPermissions.DUPLICATES_REVIEW),
            Action("No es duplicado", lambda r: self.report(_reason_dialog(
                self, "Descartar", lambda reason: p.run("dismiss_duplicate", candidate_id=r.id,
                                                        reason=reason))),
                enabled=lambda r: st(r) in ("DETECTED", "UNDER_REVIEW", "CONFIRMED_DUPLICATE"),
                permission=CustomerPermissions.DUPLICATES_DISMISS),
            Action("Proponer fusión", lambda r: self.report(self._propose(r)),
                   enabled=lambda r: st(r) == "CONFIRMED_DUPLICATE",
                   permission=CustomerPermissions.DUPLICATES_MERGE, primary=True),
        ]

    def _propose(self, row):
        c = row.data
        names = self._names
        return ask(self, title="Proponer fusión", submit_text="Proponer", intro=(
            "El cliente maestro conserva su identidad; el otro queda «Fusionado» y sus "
            "referencias pasan al maestro. Otra persona debe ejecutar la fusión."), fields=(
            FieldSpec("master", "Conservar como maestro", "choice", required=True, options=(
                (c.customer_id_a, names.get(c.customer_id_a, "Cliente A")),
                (c.customer_id_b, names.get(c.customer_id_b, "Cliente B"))),
                default=c.customer_id_a),
            FieldSpec("reason", "Motivo", "textarea", required=True),
        ), on_submit=lambda v: self._presenter.run(
            "propose_merge", master_customer_id=v["master"],
            merged_customer_id=c.customer_id_b if v["master"] == c.customer_id_a
            else c.customer_id_a, duplicate_candidate_id=c.id, reason=v["reason"]))

    def fetch(self, filters):
        candidates = self._presenter.read("duplicates")
        merges = self._presenter.read("merges")
        ids = {x for c in candidates for x in (c.customer_id_a, c.customer_id_b)}
        ids |= {x for m in merges for x in (m.master_customer_id, m.merged_customer_id)}
        self._names = self._presenter.customer_names(ids)
        self._merge_rows = {m.id: m for m in merges}
        self._merges.load_rows([[self._names.get(m.master_customer_id, "—"),
                                 self._names.get(m.merged_customer_id, "—"),
                                 label("merge_status", m.status),
                                 self._presenter.user_name(m.proposed_by_user_id),
                                 m.reason or "—"] for m in merges],
                               row_ids=[m.id for m in merges])
        rows = []
        for c in candidates:
            reasons = ", ".join(self._REASONS.get(r, r) for r in c.match_reasons) or "—"
            rows.append(Row(c.id, [self._names.get(c.customer_id_a, "—"),
                                   self._names.get(c.customer_id_b, "—"), reasons,
                                   label("duplicate_status", c.status),
                                   fmt_datetime(c.created_at)], c,
                            [("Cliente A", self._names.get(c.customer_id_a, "—")),
                             ("Cliente B", self._names.get(c.customer_id_b, "—")),
                             ("Coincide en", reasons),
                             ("Estado", label("duplicate_status", c.status))]))
        return rows

    def _selected_merge(self):
        merge_id = self._merges.selected_row_id()
        return self._merge_rows.get(merge_id) if merge_id else None

    def _execute_merge(self) -> None:
        merge = self._selected_merge()
        if merge is None or merge.status.value != "PROPOSED":
            self.notify(False, "Elige una fusión propuesta.")
            return
        self.report(_reason_dialog(self, "Ejecutar fusión", lambda reason: self._presenter.run(
            "execute_merge", merge_record_id=merge.id, reason=reason)))

    def _reject_merge(self) -> None:
        merge = self._selected_merge()
        if merge is None or merge.status.value != "PROPOSED":
            self.notify(False, "Elige una fusión propuesta.")
            return
        self.report(_reason_dialog(self, "Rechazar fusión", lambda reason: self._presenter.run(
            "reject_merge", merge_record_id=merge.id, reason=reason)))


class ImportsPage(CrmWorkbenchPage):
    """§47: archivo → mapeo → vista previa → confirmación → resultado."""

    route_id = "customers.imports"
    title = "Importaciones"
    subtitle = "Alta o actualización masiva de clientes desde CSV, con vista previa y duplicados."
    icon = Icons.IMPORT
    empty_message = "Todavía no hay importaciones."
    columns = (ColumnSpec("Fecha", "date"), ColumnSpec("Importó"), ColumnSpec("Filas", "numeric"),
               ColumnSpec("Creados", "numeric"), ColumnSpec("Actualizados", "numeric"),
               ColumnSpec("Duplicados", "numeric"), ColumnSpec("Errores", "numeric"),
               ColumnSpec("Sensible"), ColumnSpec("Estado", "status"))
    searchable = False
    _TARGETS = (("display_name", "Nombre", ("nombre", "cliente", "name", "display_name")),
                ("legal_name", "Razón social", ("razon social", "razón social", "legal_name")),
                ("customer_type", "Tipo", ("tipo", "customer_type")),
                ("tax_identifier", "RFC", ("rfc", "tax_identifier")),
                ("phone_e164", "Teléfono", ("telefono", "teléfono", "celular", "phone")),
                ("email", "Correo", ("correo", "email", "e-mail")))

    def page_actions(self):
        return [Action("Importar CSV", lambda _r: self._import(),
                       permission=CustomerPermissions.IMPORT, primary=True, needs_row=False)]

    def row_actions(self):
        p = self._presenter
        pending = lambda r: r.data.status.value == "PENDING_APPROVAL"  # noqa: E731
        return [Action("Aprobar", lambda r: self.report(p.run("approve_import", batch_id=r.id)),
                       enabled=pending, permission=CustomerPermissions.IMPORT_APPROVE,
                       primary=True, tooltip="Debe aprobarla alguien distinto de quien importó."),
                Action("Rechazar", lambda r: self.report(p.run("reject_import", batch_id=r.id)),
                       enabled=pending, permission=CustomerPermissions.IMPORT_APPROVE)]

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Archivo de clientes", "", "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, newline="", encoding="utf-8-sig") as handle:
                sample = handle.read(4096)
                handle.seek(0)
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
                records = list(csv.DictReader(handle, dialect=dialect))
        except (OSError, csv.Error, UnicodeDecodeError) as exc:
            self.notify(False, f"No se pudo leer el archivo: {exc}")
            return
        if not records:
            self.notify(False, "El archivo no tiene renglones.")
            return
        headers = list(records[0].keys())
        lowered = {h.strip().lower(): h for h in headers}
        mapping_fields = []
        for key, caption, aliases in self._TARGETS:
            guess = next((lowered[a] for a in aliases if a in lowered), None)
            mapping_fields.append(FieldSpec(key, f"{caption} ←", "choice",
                                            required=key == "display_name",
                                            options=tuple((h, h) for h in headers), default=guess))
        mapping = ask(self, title=f"Columnas de {Path(path).name}", submit_text="Vista previa",
                      intro="Indica qué columna del archivo corresponde a cada dato.",
                      fields=tuple(mapping_fields))
        if not mapping:
            return
        rows = [{key: (record.get(column) or "").strip()
                 for key, column in mapping.items() if column} for record in records]
        preview = self._presenter.read("import_preview", rows=rows)
        tally: dict[str, int] = {}
        for item in preview:
            tally[item.outcome] = tally.get(item.outcome, 0) + 1
        words = {"WOULD_CREATE": "se crearán", "WOULD_UPDATE": "se actualizarán",
                 "DUPLICATE": "parecen duplicados", "ERROR": "tienen errores"}
        summary = "; ".join(f"{n} {words.get(k, k)}" for k, n in tally.items())

        def submit(v):
            return self._presenter.run("import_customers", rows=rows,
                                       is_sensitive=bool(v["sensitive"]),
                                       allow_duplicates=bool(v["allow_duplicates"]))

        self.report(ask(self, title="Confirmar importación", submit_text="Importar",
                        intro=f"{len(rows)} renglones: {summary}.", fields=(
                            FieldSpec("allow_duplicates", "Importar también los que parecen "
                                                          "duplicados", "check"),
                            FieldSpec("sensitive", "Importación sensible (la aprueba otra "
                                                   "persona antes de escribir)", "check"),
                        ), on_submit=submit))

    def fetch(self, filters):
        return [Row(b.id, [fmt_datetime(b.created_at), self._presenter.user_name(
            b.submitted_by_user_id), str(b.total_rows), str(b.created_count),
            str(b.updated_count), str(b.duplicate_count), str(b.error_count + b.rejected_count),
            "Sí" if b.is_sensitive else "No", label("import_status", b.status)], b)
            for b in self._presenter.read("import_batches")]


class AuditPage(CrmWorkbenchPage):
    route_id = "customers.audit"
    title = "Auditoría"
    subtitle = "Quién creó, consultó, asignó, modificó, aprobó, exportó, fusionó o cerró cada registro."
    icon = Icons.AUDIT
    empty_message = "Sin movimientos."
    show_detail = True
    columns = (ColumnSpec("Fecha", "date"), ColumnSpec("Módulo"), ColumnSpec("Acción"),
               ColumnSpec("Usuario"), ColumnSpec("Autorizó"), ColumnSpec("Motivo", stretch=True))
    filters = (FilterSpec("module", "Todos los módulos", options=(
        ("customers", "Clientes"), ("crm", "CRM"), ("customer_service", "Atención"),
        ("customer_credit", "Crédito"), ("customer_privacy", "Privacidad"))),)

    def fetch(self, filters):
        entries = self._presenter.read("audit_trail", module=filters.get("module"))
        rows = []
        for index, e in enumerate(entries):
            who = self._presenter.user_name(e.get("actor_user_id")) if e.get(
                "actor_user_id") else "Sistema"
            authorized = (self._presenter.user_name(e.get("authorized_by"))
                          if e.get("authorized_by") else "—")
            rows.append(Row(str(index), [fmt_datetime(e.get("created_at")),
                                         module_label(e.get("module")),
                                         event_label(e.get("action")), who, authorized,
                                         e.get("reason") or "—"], e,
                            [("Fecha", fmt_datetime(e.get("created_at"))),
                             ("Acción", event_label(e.get("action"))), ("Usuario", who),
                             ("Autorizó", authorized), ("Motivo", e.get("reason") or "—"),
                             ("Detalle", e.get("after_json") or "—")]))
        return rows


class SettingsPage(CrmWorkbenchPage):
    """Configuración del módulo: etapas del pipeline (§20) y automatizaciones (§56)."""

    route_id = "customers.settings"
    title = "Configuración"
    subtitle = "Etapas del pipeline y automatizaciones. SLA y retención tienen su propia sección."
    icon = Icons.SETTINGS
    empty_message = "Sin etapas."
    show_detail = True
    detail_title = "Etapa"
    searchable = False
    columns = (ColumnSpec("Orden", "numeric", min_width=60, preferred_width=70),
               ColumnSpec("Código"), ColumnSpec("Etapa", stretch=True),
               ColumnSpec("Probabilidad"), ColumnSpec("Tipo"),
               ColumnSpec("Actividades mínimas", "numeric"), ColumnSpec("Estado"))

    def _build_detail_extra(self, card) -> None:
        rules_card = SectionCard(card, title="Automatizaciones")
        self._rules = StandardTable([ColumnSpec("Regla", stretch=True), ColumnSpec("Cuando"),
                                     ColumnSpec("Hace"), ColumnSpec("Estado")], rules_card)
        self._rules.setAccessibleName("Reglas de automatización")
        self._rules.setMinimumHeight(160)
        rules_card.add(self._rules)
        row = QHBoxLayout()
        row.setSpacing(Spacing.SM)
        self._rule_buttons = []
        for text, perm, slot in (
            ("Nueva regla", CRMPermissions.AUTOMATION_RULES_CREATE, self._new_rule),
            ("Activar", CRMPermissions.AUTOMATION_RULES_ACTIVATE, self._activate_rule),
            ("Desactivar", CRMPermissions.AUTOMATION_RULES_DEACTIVATE, self._deactivate_rule),
        ):
            button = create_secondary_button(rules_card, text)
            button.clicked.connect(slot)
            button.setVisible(self._presenter.can(perm))
            row.addWidget(button)
        row.addStretch(1)
        rules_card.body().addLayout(row)
        card.add(rules_card)
        self._rule_rows: dict = {}

    def page_actions(self):
        return [Action("Nueva etapa", lambda _r: self.report(ask(
            self, title="Nueva etapa del pipeline", submit_text="Crear", fields=(
                FieldSpec("code", "Código", required=True, placeholder="DEMO"),
                FieldSpec("name", "Nombre", required=True),
                FieldSpec("probability", "Probabilidad (%)", "percent", default=30),
                FieldSpec("min_activities", "Actividades mínimas para entrar", "integer",
                          default=0, maximum=20)),
            on_submit=lambda v: self._presenter.run(
                "create_stage", code=v["code"], name=v["name"],
                probability_default=v["probability"], min_activities=v["min_activities"]))),
            permission=CRMPermissions.PIPELINE_CONFIGURE, primary=True, needs_row=False)]

    def row_actions(self):
        p = self._presenter
        active = lambda r: r.data.active  # noqa: E731
        return [
            Action("Editar", lambda r: self.report(ask(
                self, title="Editar etapa", submit_text="Guardar", fields=(
                    FieldSpec("name", "Nombre", required=True, default=r.data.name),
                    FieldSpec("probability", "Probabilidad (%)", "percent",
                              default=r.data.probability_default),
                    FieldSpec("min_activities", "Actividades mínimas para entrar", "integer",
                              default=r.data.min_activities, maximum=20)),
                on_submit=lambda v: p.run("update_stage", stage_id=r.id, name=v["name"],
                                          probability_default=v["probability"],
                                          min_activities=v["min_activities"]))),
                enabled=active, permission=CRMPermissions.PIPELINE_CONFIGURE),
            Action("Subir", lambda r: self.report(p.run("move_stage", stage_id=r.id,
                                                        direction=-1)),
                   enabled=active, permission=CRMPermissions.PIPELINE_CONFIGURE),
            Action("Bajar", lambda r: self.report(p.run("move_stage", stage_id=r.id,
                                                        direction=1)),
                   enabled=active, permission=CRMPermissions.PIPELINE_CONFIGURE),
            Action("Retirar", lambda r: self.report(p.run("deactivate_stage", stage_id=r.id)),
                   enabled=active, permission=CRMPermissions.PIPELINE_CONFIGURE),
        ]

    def fetch(self, filters):
        stages = self._presenter.read("stages", include_inactive=True)
        self._load_rules()
        rows = []
        for s in stages:
            kind = "Ganada" if s.is_won_stage else ("Perdida" if s.is_lost_stage else "Abierta")
            rows.append(Row(s.id, [str(s.sequence_order), s.code, s.name,
                                   f"{s.probability_default}%", kind, str(s.min_activities),
                                   "Activa" if s.active else "Retirada"], s,
                            [("Etapa", s.name), ("Código", s.code), ("Tipo", kind),
                             ("Probabilidad", f"{s.probability_default}%"),
                             ("Actividades mínimas", str(s.min_activities))]))
        return rows

    def _load_rules(self) -> None:
        try:
            rules = self._presenter.read("automation_rules")
        except Exception:  # noqa: BLE001 — sin permiso de ver automatizaciones
            rules = []
        self._rule_rows = {r.id: r for r in rules}
        self._rules.load_rows([[r.name, label("automation_trigger", r.trigger_type),
                                label("automation_action", r.action_type),
                                "Activa" if r.active else "Inactiva"] for r in rules],
                              row_ids=[r.id for r in rules])

    def _selected_rule(self):
        rule_id = self._rules.selected_row_id()
        return self._rule_rows.get(rule_id) if rule_id else None

    def _new_rule(self) -> None:
        tags = []
        segments = []
        try:
            tags = [(t.entity.id, t.entity.label) for t in self._presenter.read("tags")]
            segments = [(s.entity.id, s.entity.name) for s in self._presenter.read("segments")]
        except Exception:  # noqa: BLE001
            pass
        actions = options("automation_action", exclude=("CHANGE_PRIORITY", "SEND_NOTIFICATION"))

        def submit(v):
            action = v["action"]
            config = {}
            if action == "CREATE_TASK":
                config = {"title": v["title"] or None, "due_in_hours": v["hours"],
                          "assigned_user_id": v["user"] or None}
            elif action == "ASSIGN_OWNER":
                config = {"assignee_user_id": v["user"]}
            elif action == "ESCALATE_CASE":
                config = {"escalated_to_user_id": v["user"]}
            elif action == "ADD_TAG":
                config = {"tag_id": v["tag"]}
            elif action == "ADD_TO_SEGMENT":
                config = {"segment_id": v["segment"]}
            config = {k: val for k, val in config.items() if val not in (None, "")}
            if action in ("ASSIGN_OWNER", "ESCALATE_CASE") and "assignee_user_id" not in config \
                    and "escalated_to_user_id" not in config:
                return Fail("Elige el usuario.")
            trigger_config = {"idle_days": v["idle_days"]} if v["trigger"].endswith("IDLE") else {}
            return self._presenter.run("create_automation", name=v["name"],
                                       trigger_type=v["trigger"], action_type=action,
                                       trigger_config=trigger_config, action_config=config,
                                       description=v["description"])

        self.notify_result(ask(self, title="Nueva automatización", submit_text="Crear", intro=(
            "Reglas declarativas: cuando ocurre algo, el sistema hace una acción con los "
            "permisos de esa acción. No se ejecutan scripts."), fields=(
            FieldSpec("name", "Nombre", required=True),
            FieldSpec("trigger", "Cuando", "choice", required=True,
                      options=tuple(options("automation_trigger")), default="LEAD_CREATED"),
            FieldSpec("idle_days", "Días sin movimiento (si aplica)", "integer", default=3,
                      minimum=1, maximum=365),
            FieldSpec("action", "Hacer", "choice", required=True, options=tuple(actions),
                      default="CREATE_TASK"),
            FieldSpec("title", "Título de la tarea (crear tarea)"),
            FieldSpec("hours", "Vence en horas (crear tarea)", "integer", default=24,
                      minimum=1, maximum=720),
            FieldSpec("user", "Usuario (asignar / escalar / tarea)", "user"),
            FieldSpec("tag", "Etiqueta (agregar etiqueta)", "choice", options=tuple(tags)),
            FieldSpec("segment", "Segmento (agregar a segmento)", "choice",
                      options=tuple(segments)),
            FieldSpec("description", "Descripción", "textarea"),
        ), user_options=self._presenter.users(), on_submit=submit))

    def notify_result(self, result) -> None:
        if self.report(result):
            self._load_rules()

    def _activate_rule(self) -> None:
        rule = self._selected_rule()
        if rule is not None:
            self.notify_result(self._presenter.run("activate_automation", rule_id=rule.id))

    def _deactivate_rule(self) -> None:
        rule = self._selected_rule()
        if rule is not None:
            self.notify_result(self._presenter.run("deactivate_automation", rule_id=rule.id))


CONTROL_ROUTE_PAGES = {
    "customers.data_quality": DataQualityPage,
    "customers.duplicates": DuplicatesPage,
    "customers.imports": ImportsPage,
    "customers.audit": AuditPage,
    "customers.settings": SettingsPage,
}
