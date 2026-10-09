"""Comunicaciones y Privacidad (§41-44, §48, §52, CRM-43).

Comunicaciones (por cliente): consentimientos, preferencias, resumen de
WhatsApp e historial de avisos. Privacidad: solicitudes de derechos (ARCO),
retención, anonimización y exportaciones.

Antes: ocho rutas «en construcción». Reglas que se cuidan en los casos de uso:
el consentimiento nunca se infiere por tener teléfono o correo (§41), retirar
exige motivo, anonimizar exige una solicitud en proceso y un autorizador
distinto de quien la registró (§73-74), y la bitácora nunca se borra.
"""

from __future__ import annotations

import csv

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFileDialog, QFormLayout, QLabel, QWidget

from backend.application.customers.permissions import CustomerPermissions
from frontend.desktop.components import ColumnSpec
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.customers_crm.formatting import fmt_date, fmt_datetime
from frontend.desktop.modules.customers_crm.forms import FieldSpec, ask
from frontend.desktop.modules.customers_crm.labels import label, options, yes_no
from frontend.desktop.modules.customers_crm.pages._outcomes import Fail
from frontend.desktop.modules.customers_crm.pages._workbench import (
    Action,
    CrmWorkbenchPage,
    FilterSpec,
    Kpi,
    Row,
)
from frontend.desktop.modules.customers_crm.pages.customer_sections import _Section

_EXPORT_DATASETS = (("customers", "Clientes"), ("leads", "Prospectos"),
                    ("opportunities", "Oportunidades"), ("activities", "Mis actividades"))


# -- secciones por cliente ---------------------------------------------------------
class ConsentsSection(_Section):
    columns = (ColumnSpec("Tipo"), ColumnSpec("Estado", "status"), ColumnSpec("Canal"),
               ColumnSpec("Otorgado", "date"), ColumnSpec("Retirado", "date"),
               ColumnSpec("Vence", "date"), ColumnSpec("Evidencia"))

    def actions(self):
        return [("Registrar consentimiento", CustomerPermissions.CONSENT_CAPTURE, False,
                 self._capture),
                ("Pedir consentimiento", CustomerPermissions.CONSENT_CAPTURE, False,
                 self._request),
                ("Confirmar", CustomerPermissions.CONSENT_CAPTURE, True, self._confirm),
                ("Retirar", CustomerPermissions.CONSENT_WITHDRAW, True, self._withdraw),
                ("No requerido", CustomerPermissions.CONSENT_CAPTURE, False, self._not_required)]

    def reload(self) -> None:
        self._display = object() if self._customer_id else None
        self._render()
        self._sync()

    def _render(self) -> None:
        consents = []
        if self._customer_id:
            try:
                consents = self._presenter.read("consents_for", customer_id=self._customer_id)
            except Exception as exc:  # noqa: BLE001
                self._say(False, f"No fue posible leer los consentimientos: {exc}")
        self._items = {c.id: c for c in consents}
        can_evidence = self._presenter.can(CustomerPermissions.CONSENT_EVIDENCE_VIEW)
        self._table.load_rows([[label("consent_type", c.consent_type),
                                label("consent_status", c.status),
                                label("consent_channel", c.channel), fmt_date(c.granted_at),
                                fmt_date(c.withdrawn_at), fmt_date(c.expires_at),
                                (c.evidence_reference or "—") if can_evidence else "Oculta"]
                               for c in consents], row_ids=[c.id for c in consents])

    def _capture(self) -> None:
        self._after(ask(self, title="Registrar consentimiento", submit_text="Registrar",
                        intro="El consentimiento nunca se supone por tener teléfono o correo: "
                              "registra cómo lo otorgó el cliente.", fields=(
                            FieldSpec("consent_type", "Tipo", "choice", required=True,
                                      options=tuple(options("consent_type")),
                                      default="PRIVACY_NOTICE"),
                            FieldSpec("channel", "Canal", "choice",
                                      options=tuple(options("consent_channel")),
                                      default="IN_PERSON"),
                            FieldSpec("evidence", "Evidencia", required=True,
                                      placeholder="Folio del aviso firmado, mensaje, grabación…"),
                            FieldSpec("expires", "Vence (opcional)", "date"),
                            FieldSpec("has_expiry", "El consentimiento vence", "check"),
                        ), on_submit=lambda v: self._presenter.run(
                            "capture_consent", customer_id=self._customer_id,
                            consent_type=v["consent_type"], evidence_reference=v["evidence"],
                            channel=v["channel"] or "OTHER",
                            expires_at=v["expires"].isoformat() if v["has_expiry"] else None)))

    def _request(self) -> None:
        self._after(ask(self, title="Pedir consentimiento", submit_text="Registrar solicitud",
                        fields=(FieldSpec("consent_type", "Tipo", "choice", required=True,
                                          options=tuple(options("consent_type"))),
                                FieldSpec("channel", "Canal", "choice",
                                          options=tuple(options("consent_channel")),
                                          default="WHATSAPP")),
                        on_submit=lambda v: self._presenter.run(
                            "request_consent", customer_id=self._customer_id,
                            consent_type=v["consent_type"], channel=v["channel"] or "OTHER")))

    def _confirm(self) -> None:
        consent = self._selected()
        if consent is None:
            return
        self._after(ask(self, title="Confirmar consentimiento", submit_text="Confirmar",
                        fields=(FieldSpec("evidence", "Evidencia", required=True),),
                        on_submit=lambda v: self._presenter.run(
                            "confirm_consent", consent_id=consent.id,
                            evidence_reference=v["evidence"])))

    def _withdraw(self) -> None:
        consent = self._selected()
        if consent is None:
            return
        self._after(ask(self, title="Retirar consentimiento", submit_text="Retirar", fields=(
            FieldSpec("reason", "Motivo", "textarea", required=True),),
            on_submit=lambda v: self._presenter.run("withdraw_consent", consent_id=consent.id,
                                                    reason=v["reason"])))

    def _not_required(self) -> None:
        self._after(ask(self, title="Consentimiento no requerido", submit_text="Registrar",
                        fields=(FieldSpec("consent_type", "Tipo", "choice", required=True,
                                          options=tuple(options("consent_type"))),
                                FieldSpec("reason", "Motivo", "textarea", required=True)),
                        on_submit=lambda v: self._presenter.run(
                            "consent_not_required", customer_id=self._customer_id,
                            consent_type=v["consent_type"], reason=v["reason"])))


class PreferencesSection(_Section):
    """§42: cómo y cuándo quiere el cliente que se le contacte."""

    _FIELDS = (("preferred_channel", "Canal preferido"), ("preferred_language", "Idioma"),
               ("hours", "Horario"), ("allow_transactional", "Avisos de sus compras"),
               ("allow_operational", "Avisos operativos (entregas, pedidos)"),
               ("allow_reminders", "Recordatorios"), ("allow_promotions", "Promociones"),
               ("allow_marketing", "Marketing"))

    def _build_top(self) -> None:
        self._host = QWidget(self)
        self._form = QFormLayout(self._host)
        self._values = {}
        for key, caption in self._FIELDS:
            value = QLabel("—", self._host)
            self._values[key] = value
            self._form.addRow(f"{caption}:", value)
        self._layout.addWidget(self._host)

    def actions(self):
        return [("Editar preferencias", CustomerPermissions.COMMUNICATION_PREFERENCE_MANAGE,
                 False, self._edit)]

    def reload(self) -> None:
        self._display = object() if self._customer_id else None
        self._pref = None
        if self._customer_id:
            try:
                self._pref = self._presenter.read("preference_for", customer_id=self._customer_id)
            except Exception as exc:  # noqa: BLE001
                self._say(False, f"No fue posible leer las preferencias: {exc}")
        self._render()
        self._sync()

    def _render(self) -> None:
        p = getattr(self, "_pref", None)
        if p is None:
            for value in self._values.values():
                value.setText("Sin definir")
            return
        self._values["preferred_channel"].setText(label("preferred_channel", p.preferred_channel))
        self._values["preferred_language"].setText(p.preferred_language or "—")
        self._values["hours"].setText(
            f"{p.contact_hours_start} a {p.contact_hours_end}"
            if p.contact_hours_start and p.contact_hours_end else "Cualquier hora")
        for key in ("allow_transactional", "allow_operational", "allow_reminders",
                    "allow_promotions", "allow_marketing"):
            self._values[key].setText(yes_no(getattr(p, key)))

    def _edit(self) -> None:
        p = getattr(self, "_pref", None)
        self._after(ask(self, title="Preferencias de comunicación", submit_text="Guardar",
                        intro="Promociones y marketing requieren además el consentimiento "
                              "correspondiente.", fields=(
                            FieldSpec("channel", "Canal preferido", "choice",
                                      options=tuple(options("preferred_channel")),
                                      default=p.preferred_channel.value if p else "WHATSAPP"),
                            FieldSpec("language", "Idioma", "choice",
                                      options=(("es", "Español"), ("en", "Inglés")),
                                      default=p.preferred_language if p else "es"),
                            FieldSpec("start", "Contactar desde (HH:MM)",
                                      default=p.contact_hours_start if p else None),
                            FieldSpec("end", "Contactar hasta (HH:MM)",
                                      default=p.contact_hours_end if p else None),
                            FieldSpec("operational", "Avisos operativos", "check",
                                      default=p.allow_operational if p else True),
                            FieldSpec("reminders", "Recordatorios", "check",
                                      default=p.allow_reminders if p else True),
                            FieldSpec("promotions", "Promociones", "check",
                                      default=p.allow_promotions if p else False),
                            FieldSpec("marketing", "Marketing", "check",
                                      default=p.allow_marketing if p else False),
                        ), on_submit=lambda v: self._presenter.run(
                            "set_communication_preference", customer_id=self._customer_id,
                            preferred_channel=v["channel"], preferred_language=v["language"],
                            contact_hours_start=v["start"] or None,
                            contact_hours_end=v["end"] or None,
                            allow_operational=v["operational"], allow_marketing=v["marketing"],
                            allow_promotions=v["promotions"], allow_reminders=v["reminders"])))


class WhatsAppSection(_Section):
    """§52: lo que CRM ve de WhatsApp (las conversaciones viven en WhatsApp)."""

    _FIELDS = (("consent", "Consentimiento de WhatsApp"), ("last", "Última conversación"),
               ("open", "Conversaciones abiertas"), ("handoff", "Pendiente de atender (handoff)"))
    columns = (ColumnSpec("Fecha", "date"), ColumnSpec("Dirección"), ColumnSpec("Tipo"),
               ColumnSpec("Entrega"))

    def _build_top(self) -> None:
        self._host = QWidget(self)
        self._form = QFormLayout(self._host)
        self._values = {}
        for key, caption in self._FIELDS:
            value = QLabel("—", self._host)
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._values[key] = value
            self._form.addRow(f"{caption}:", value)
        hint = QLabel("El contenido de los mensajes se consulta en WhatsApp; aquí sólo fechas "
                      "y estados.", self._host)
        hint.setProperty("role", "muted")
        hint.setWordWrap(True)
        self._form.addRow(hint)
        self._layout.addWidget(self._host)

    def reload(self) -> None:
        self._display = object() if self._customer_id else None
        self._render()
        self._sync()

    def _render(self) -> None:
        summary, messages = None, []
        if self._customer_id:
            try:
                summary = self._presenter.read("whatsapp_summary", customer_id=self._customer_id)
                messages = self._presenter.read("notification_history",
                                                customer_id=self._customer_id)
            except Exception as exc:  # noqa: BLE001
                self._say(False, f"No fue posible leer WhatsApp: {exc}")
        self._values["consent"].setText(
            yes_no(summary.has_active_whatsapp_consent) if summary else "—")
        self._values["last"].setText(fmt_datetime(summary.last_conversation_at) if summary
                                     else "—")
        self._values["open"].setText(str(summary.open_conversations_count) if summary else "—")
        self._values["handoff"].setText(yes_no(summary.handoff_pending) if summary else "—")
        direction = {"INBOUND": "Recibido", "OUTBOUND": "Enviado"}
        self._table.load_rows([[fmt_datetime(m["created_at"]),
                                direction.get(m["direction"], m["direction"]),
                                m["message_type"] or "—", m["status"] or "—"] for m in messages],
                              row_ids=[m["id"] for m in messages])


# -- privacidad ------------------------------------------------------------------
_OPEN_REQUEST = ("RECEIVED", "VALIDATING", "IN_PROGRESS")


class PrivacyRequestsPage(CrmWorkbenchPage):
    route_id = "customers.privacy_requests"
    title = "Solicitudes de privacidad"
    subtitle = "Derechos del cliente: acceso, rectificación, cancelación, oposición, exportación."
    icon = Icons.REQUEST
    empty_message = "No hay solicitudes de privacidad."
    show_detail = True
    columns = (ColumnSpec("Folio"), ColumnSpec("Cliente", stretch=True), ColumnSpec("Tipo"),
               ColumnSpec("Estado", "status"), ColumnSpec("Recibida", "date"),
               ColumnSpec("Registró"))
    types: tuple[str, ...] = ()
    filters = (FilterSpec("status", "Abiertas", options=(("ALL", "Todas"),) + tuple(
        options("privacy_status"))),)

    def page_actions(self):
        return [Action("Nueva solicitud", lambda _r: self.report(ask(
            self, title="Nueva solicitud de privacidad", submit_text="Registrar", fields=(
                FieldSpec("customer_id", "Cliente", "customer", required=True),
                FieldSpec("type", "Derecho", "choice", required=True,
                          options=tuple(options("privacy_type")), default="ACCESS"),
                FieldSpec("description", "Detalle", "textarea")),
            customer_provider=self._presenter.customer_search_options,
            on_submit=lambda v: self._presenter.run(
                "create_privacy_request", customer_id=v["customer_id"], request_type=v["type"],
                description=v["description"]))),
            permission=CustomerPermissions.PRIVACY_REQUEST_CREATE, primary=True,
            needs_row=False)]

    def row_actions(self):
        p = self._presenter
        st = lambda r: r.data.status.value  # noqa: E731

        def reason(command, title):
            return lambda r: self.report(ask(self, title=title, submit_text=title, fields=(
                FieldSpec("reason", "Motivo", "textarea", required=True),),
                on_submit=lambda v: p.run(command, request_id=r.id, reason=v["reason"])))
        return [
            Action("Validar", lambda r: self.report(p.run("validate_privacy_request",
                                                          request_id=r.id)),
                   enabled=lambda r: st(r) == "RECEIVED",
                   permission=CustomerPermissions.PRIVACY_REQUEST_PROCESS,
                   tooltip="Se verificó la identidad de quien solicita."),
            Action("Procesar", lambda r: self.report(p.run("process_privacy_request",
                                                           request_id=r.id)),
                   enabled=lambda r: st(r) == "VALIDATING",
                   permission=CustomerPermissions.PRIVACY_REQUEST_PROCESS),
            Action("Completar", lambda r: self.report(ask(
                self, title="Completar solicitud", submit_text="Completar", fields=(
                    FieldSpec("notes", "Cómo se atendió", "textarea", required=True),),
                on_submit=lambda v: p.run("complete_privacy_request", request_id=r.id,
                                          resolution_notes=v["notes"]))),
                enabled=lambda r: st(r) == "IN_PROGRESS",
                permission=CustomerPermissions.PRIVACY_REQUEST_PROCESS, primary=True),
            Action("Rechazar", reason("reject_privacy_request", "Rechazar"),
                   enabled=lambda r: st(r) in _OPEN_REQUEST,
                   permission=CustomerPermissions.PRIVACY_REQUEST_PROCESS),
            Action("Cancelar", reason("cancel_privacy_request", "Cancelar"),
                   enabled=lambda r: st(r) in _OPEN_REQUEST,
                   permission=CustomerPermissions.PRIVACY_REQUEST_PROCESS),
        ]

    def fetch(self, filters):
        requests = self._presenter.read("privacy_requests")
        if self.types:
            requests = [r for r in requests if r.request_type.value in self.types]
        wanted = filters.get("status")
        if wanted and wanted != "ALL":
            requests = [r for r in requests if r.status.value == wanted]
        elif not wanted:
            requests = [r for r in requests if r.status.value in _OPEN_REQUEST]
        names = self._presenter.customer_names({r.customer_id for r in requests})
        return [Row(r.id, [str(r.code), names.get(r.customer_id, "—"),
                           label("privacy_type", r.request_type),
                           label("privacy_status", r.status), fmt_datetime(r.received_at),
                           self._presenter.user_name(r.logged_by_user_id)], r,
                    [("Folio", str(r.code)), ("Cliente", names.get(r.customer_id, "—")),
                     ("Derecho", label("privacy_type", r.request_type)),
                     ("Estado", label("privacy_status", r.status)),
                     ("Detalle", r.description), ("Recibida", fmt_datetime(r.received_at)),
                     ("Registró", self._presenter.user_name(r.logged_by_user_id)),
                     ("Validó", self._presenter.user_name(r.validated_by_user_id)
                      if r.validated_by_user_id else "—"),
                     ("Atendió", self._presenter.user_name(r.processed_by_user_id)
                      if r.processed_by_user_id else "—"),
                     ("Resolución", r.resolution_notes)])
                for r in requests]

    def kpis(self, rows):
        return [Kpi("En la lista", str(len(rows))),
                Kpi("Por validar", str(sum(1 for r in rows
                                           if r.data.status.value == "RECEIVED")), "info")]


class AnonymizationPage(PrivacyRequestsPage):
    """§43-44: anonimizar respeta obligaciones fiscales, ventas, CxC y auditoría."""

    route_id = "customers.anonymization"
    title = "Anonimización"
    subtitle = ("Solicitudes de anonimización o cancelación en proceso. Se borra el nombre de "
                "presentación; ventas, CxC, datos fiscales y bitácora se conservan.")
    icon = Icons.LOCK
    types = ("ANONYMIZATION", "CANCELLATION")
    empty_message = "No hay solicitudes de anonimización."

    def page_actions(self):
        return []

    def row_actions(self):
        return [Action("Anonimizar", lambda r: self.report(ask(
            self, title="Anonimizar cliente", submit_text="Anonimizar", intro=(
                "Quien autoriza debe ser distinto de quien registró la solicitud. La acción no "
                "se puede deshacer."), fields=(
                FieldSpec("reason", "Motivo", "textarea", required=True),),
            on_submit=lambda v: self._presenter.run("anonymize_customer", request_id=r.id,
                                                    reason=v["reason"]))),
            enabled=lambda r: r.data.status.value == "IN_PROGRESS",
            permission=CustomerPermissions.ANONYMIZE, primary=True)] + super().row_actions()


class RetentionPage(CrmWorkbenchPage):
    route_id = "customers.retention"
    title = "Retención de datos"
    subtitle = "Cuánto tiempo se conserva cada tipo de dato. Nada se fija en el código."
    icon = Icons.CLOCK
    empty_message = "No hay políticas de retención: nada se elimina automáticamente."
    columns = (ColumnSpec("Código"), ColumnSpec("Política", stretch=True),
               ColumnSpec("Dato"), ColumnSpec("Conservar"), ColumnSpec("Aplica a"),
               ColumnSpec("Fundamento"), ColumnSpec("Estado"))

    def page_actions(self):
        return [Action("Nueva política", lambda _r: self.report(ask(
            self, title="Nueva política de retención", submit_text="Crear", fields=(
                FieldSpec("code", "Código", required=True, placeholder="RET-CONTACTO"),
                FieldSpec("name", "Nombre", required=True),
                FieldSpec("category", "Tipo de dato", "choice", required=True,
                          options=tuple(options("data_category"))),
                FieldSpec("days", "Conservar (días)", "integer", default=1825, minimum=1),
                FieldSpec("customer_type", "Tipo de cliente", "choice",
                          options=tuple(options("customer_type"))),
                FieldSpec("customer_status", "Estatus del cliente", "choice",
                          options=tuple(options("customer_status"))),
                FieldSpec("legal_basis", "Fundamento (ley, obligación fiscal…)", "textarea")),
            on_submit=lambda v: self._presenter.run(
                "create_retention_policy", code=v["code"], name=v["name"],
                data_category=v["category"], retention_days=v["days"],
                legal_basis=v["legal_basis"], customer_type=v["customer_type"],
                customer_status=v["customer_status"]))),
            permission=CustomerPermissions.SETTINGS_MANAGE, primary=True, needs_row=False)]

    def row_actions(self):
        return [Action("Retirar", lambda r: self.report(self._presenter.run(
            "deactivate_retention_policy", policy_id=r.id)), enabled=lambda r: r.data.active,
            permission=CustomerPermissions.SETTINGS_MANAGE)]

    def fetch(self, filters):
        rows = []
        for p in self._presenter.read("retention_policies"):
            scope = ", ".join(x for x in (
                label("customer_type", p.customer_type) if p.customer_type else "",
                label("customer_status", p.customer_status) if p.customer_status else "") if x)
            rows.append(Row(p.id, [p.code, p.name, label("data_category", p.data_category),
                                   f"{p.retention_days} días", scope or "Todos",
                                   p.legal_basis or "—",
                                   "Activa" if p.active else "Retirada"], p))
        return rows


class DataExportsPage(CrmWorkbenchPage):
    """§48: exportaciones con permiso, alcance, sin IDs internos y auditadas."""

    route_id = "customers.data_exports"
    title = "Exportaciones"
    subtitle = ("Descarga en CSV lo que puedes ver. Los datos sensibles salen ocultos salvo "
                "permiso y motivo; toda exportación queda registrada.")
    icon = Icons.EXPORT
    empty_message = "Todavía no hay exportaciones."
    columns = (ColumnSpec("Fecha", "date"), ColumnSpec("Usuario"), ColumnSpec("Conjunto"),
               ColumnSpec("Registros", "numeric"), ColumnSpec("Sensibles"),
               ColumnSpec("Motivo", stretch=True))
    searchable = False

    def page_actions(self):
        return [Action("Exportar", lambda _r: self._export(),
                       permission=CustomerPermissions.EXPORT, primary=True, needs_row=False)]

    def _export(self) -> None:
        fields = [FieldSpec("dataset", "Qué exportar", "choice", required=True,
                            options=_EXPORT_DATASETS, default="customers")]
        if self._presenter.can(CustomerPermissions.SENSITIVE_DATA_EXPORT):
            fields += [FieldSpec("sensitive", "Incluir teléfono, correo y RFC completos", "check"),
                       FieldSpec("reason", "Motivo (obligatorio si incluyes datos sensibles)",
                                 "textarea")]

        def submit(v):
            result = self._presenter.run("export_data", dataset=v["dataset"],
                                         include_sensitive=bool(v.get("sensitive")),
                                         reason=v.get("reason") or "")
            if not result.success:
                return result
            table = result.data["table"]
            path, _ = QFileDialog.getSaveFileName(self, "Guardar exportación",
                                                  f"{table.dataset}.csv", "CSV (*.csv)")
            if not path:
                return Fail("Exportación preparada pero no se eligió dónde guardarla.")
            with open(path, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow(table.headers)
                writer.writerows(table.rows)
            return result

        self.report(ask(self, title="Exportar datos", submit_text="Exportar",
                        fields=tuple(fields), on_submit=submit))

    def fetch(self, filters):
        import json
        rows = []
        for index, e in enumerate(self._presenter.read("exports_history")):
            try:
                detail = json.loads(e.get("after_json") or "{}")
            except ValueError:
                detail = {}
            rows.append(Row(str(index), [
                fmt_datetime(e.get("created_at")), self._presenter.user_name(e.get("actor_user_id")),
                dict(_EXPORT_DATASETS).get(detail.get("dataset"), detail.get("dataset") or "—"),
                str(detail.get("rows", "—")), yes_no(detail.get("include_sensitive")),
                e.get("reason") or "—"], e))
        return rows


PRIVACY_ROUTE_PAGES = {
    "customers.privacy_requests": PrivacyRequestsPage,
    "customers.anonymization": AnonymizationPage,
    "customers.retention": RetentionPage,
    "customers.data_exports": DataExportsPage,
}

__all__ = ["ConsentsSection", "PreferencesSection", "PRIVACY_ROUTE_PAGES", "WhatsAppSection"]
