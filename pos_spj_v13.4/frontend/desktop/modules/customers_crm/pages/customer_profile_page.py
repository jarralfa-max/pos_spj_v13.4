"""CRM-17 — Expediente del cliente (route ``customers.profile``), §27-29.

``Customer360QueryService`` (CRM-12, extended by CRM-13) already aggregates
everything every tab below needs — this page is pure composition/rendering,
never a second source of truth: no tab recomputes a total, a status, or a
masked amount the backend didn't already hand it (§90 "la UI no calcula").

§27-29 names `PageHeader`, `CustomerSummaryHeader`, `ContextBar`, internal
tabs (each with a `route_id`), `ActionBar`, `PageState`. Like every other
CRM-14/15/16 UI phase, most of those names don't exist as real classes —
`PageHeader` does; the rest are composed from `StatusBadge` (the "summary
header"/"context bar" facts) and `PillTabBar` (see ``_pill_tab_bar.py`` for
why not the forbidden raw tab widget).

Tabs (§27-29's own list, in order): Resumen, Identidad, Contactos,
Direcciones, Actividad, Oportunidades, Comercial, Crédito, Atención,
Consentimientos, Integraciones, Auditoría. "Comercial" renders
`orders_summary`/`delivery_summary` (Pedidos/Delivery); "Integraciones"
renders `whatsapp_summary`/`loyalty_summary` (WhatsApp/Fidelidad) — a
deliberate split along §49-55's own module boundaries, not an arbitrary one.
"Auditoría" is `recent_history` — the cross-context timeline
`CustomerHistoryQueryService` (CRM-12) builds, i.e. this phase's "timeline"
sub-topic.

This page stayed fully read-only until the module gained a real edit path
(``pages/edit_customer_page.py``, route ``customers.edit``) — an "Editar"
header action now emits ``edit_requested(customer_id)``, handled by the
workspace the same way ``customers.create``'s success already hands off to
this same page (``customers_crm_workspace.py::_open_customer_profile``).
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

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
from frontend.desktop.formatters.money_formatter import format_money
from frontend.desktop.modules.customers_crm.pages._pill_tab_bar import PillTabBar
from frontend.desktop.themes.tokens import Spacing

_STATUS_LABELS = {
    "DRAFT": "Borrador", "PROSPECT": "Prospecto", "ACTIVE": "Activo",
    "INACTIVE": "Inactivo", "SUSPENDED": "Suspendido", "BLOCKED": "Bloqueado",
    "CLOSED": "Cerrado", "MERGED": "Fusionado", "ANONYMIZED": "Anonimizado",
}
_STATUS_VARIANTS = {
    "ACTIVE": "success", "PROSPECT": "info", "INACTIVE": "neutral",
    "SUSPENDED": "warning", "BLOCKED": "danger", "CLOSED": "neutral",
    "MERGED": "neutral", "ANONYMIZED": "neutral",
}
_LIFECYCLE_LABELS = {
    "PROSPECT": "Prospecto", "LEAD": "Lead", "QUALIFIED": "Calificado",
    "CUSTOMER": "Cliente", "REPEAT_CUSTOMER": "Cliente recurrente",
    "AT_RISK": "En riesgo", "INACTIVE": "Inactivo", "LOST": "Perdido",
}
_TABS = (
    ("resumen", "Resumen"), ("identidad", "Identidad"), ("contactos", "Contactos"),
    ("direcciones", "Direcciones"), ("actividad", "Actividad"),
    ("oportunidades", "Oportunidades"), ("comercial", "Comercial"),
    ("credito", "Crédito"), ("atencion", "Atención"),
    ("consentimientos", "Consentimientos"), ("integraciones", "Integraciones"),
    ("auditoria", "Auditoría"),
)


class CustomerProfilePage(QWidget):
    edit_requested = pyqtSignal(str)

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("customerProfilePage")
        self._presenter = presenter
        self._customer_id: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(Spacing.MD)

        refresh = create_secondary_button(self, "Actualizar")
        refresh.clicked.connect(self._reload_current)
        edit_btn = create_secondary_button(self, "Editar")
        edit_btn.clicked.connect(self._request_edit)
        self._header = PageHeader(
            self, title="Expediente del cliente", icon=Icons.CUSTOMERS,
            compact=True, actions=[edit_btn, refresh])
        root.addWidget(self._header)

        self._summary_row = QHBoxLayout()
        self._summary_row.setSpacing(Spacing.SM)
        self._status_badge = StatusBadge("—", self)
        self._lifecycle_label = QLabel("", self)
        self._lifecycle_label.setProperty("role", "muted")
        self._summary_row.addWidget(self._status_badge)
        self._summary_row.addWidget(self._lifecycle_label)
        self._summary_row.addStretch(1)
        root.addLayout(self._summary_row)

        self._status = QLabel("", self)
        self._status.setObjectName("customerProfileStatus")
        self._status.setProperty("state", "ERROR")
        self._status.setWordWrap(True)
        self._status.hide()
        root.addWidget(self._status)

        self._tab_bar = PillTabBar(self)
        self._tab_bar.tab_changed.connect(self._on_tab_changed)
        root.addWidget(self._tab_bar)

        self._stack = QStackedWidget(self)
        self._tab_index: dict[str, int] = {}
        self._tab_widgets: dict[str, QWidget] = {}
        self._tables: dict[str, StandardTable] = {}
        for key, label in _TABS:
            self._tab_bar.add_tab(key, label)
            widget = self._build_tab(key)
            self._tab_widgets[key] = widget
            self._tab_index[key] = self._stack.count()
            self._stack.addWidget(widget)
        root.addWidget(self._stack, stretch=1)

        self._placeholder = create_state_widget(
            ViewState.EMPTY, self,
            message="Selecciona un cliente desde el Directorio para ver su expediente.")
        self._stack.insertWidget(0, self._placeholder)
        for key in self._tab_index:
            self._tab_index[key] += 1
        self._stack.setCurrentWidget(self._placeholder)

    # -- navigation -------------------------------------------------------
    def _on_tab_changed(self, key: str) -> None:
        if self._customer_id is not None and key in self._tab_index:
            self._stack.setCurrentIndex(self._tab_index[key])

    def ensure_loaded(self) -> None:
        pass  # nothing to show until a customer is selected — see show_customer()

    def show_customer(self, customer_id: str) -> None:
        self._customer_id = customer_id
        self._tab_bar.activate("resumen")
        self._stack.setCurrentIndex(self._tab_index["resumen"])
        self._reload_current()

    def _request_edit(self) -> None:
        if self._customer_id is not None:
            self.edit_requested.emit(self._customer_id)

    def _reload_current(self) -> None:
        if self._customer_id is None:
            self._stack.setCurrentWidget(self._placeholder)
            return
        self.reload()

    def reload(self) -> None:
        if self._customer_id is None:
            return
        try:
            view = self._presenter.customer_360(self._customer_id)
            self._populate(view)
            self._status.hide()
        except Exception as exc:  # a page must always show *something*
            self._status.setText(f"No fue posible cargar el expediente: {exc}")
            self._status.show()

    #: tab key -> column specs, for the tabs that are plain tables.
    _TABLE_TAB_COLUMNS = {
        "contactos": (ColumnSpec("Nombre"), ColumnSpec("Puesto"),
                     ColumnSpec("Teléfono"), ColumnSpec("Correo")),
        "direcciones": (ColumnSpec("Tipo"), ColumnSpec("Calle"),
                        ColumnSpec("Municipio"), ColumnSpec("Estado")),
        "actividad": (ColumnSpec("Tipo"), ColumnSpec("Asunto"), ColumnSpec("Fecha", "date")),
        "oportunidades": (ColumnSpec("Nombre"), ColumnSpec("Estado", "status"),
                          ColumnSpec("Monto", "numeric")),
        "atencion": (ColumnSpec("Código"), ColumnSpec("Asunto"), ColumnSpec("Estado", "status")),
        "consentimientos": (ColumnSpec("Tipo"), ColumnSpec("Estado", "status"),
                            ColumnSpec("Canal")),
        "auditoria": (ColumnSpec("Fecha", "date"), ColumnSpec("Módulo"), ColumnSpec("Acción")),
    }

    # -- tab construction (structure only, built once) ---------------------
    def _build_tab(self, key: str) -> QWidget:
        if key in self._TABLE_TAB_COLUMNS:
            return self._build_table_tab(key)
        builders = {
            "resumen": self._build_resumen_tab,
            "identidad": self._build_identidad_tab,
            "comercial": self._build_comercial_tab,
            "credito": self._build_credito_tab,
            "integraciones": self._build_integraciones_tab,
        }
        return builders[key]()

    def _build_table_tab(self, key: str) -> QWidget:
        card = SectionCard(self)
        table = StandardTable(list(self._TABLE_TAB_COLUMNS[key]), card)
        table.setObjectName(f"{key}Table")
        card.add(table)
        self._tables[key] = table
        return card

    def _table_of(self, key: str) -> StandardTable:
        return self._tables[key]

    def _build_form_tab(
        self, title: str, fields: tuple[tuple[str, str], ...],
    ) -> tuple[QWidget, dict[str, QLabel]]:
        """A tab that's a vertical stack of "Etiqueta: valor" rows —
        shared by Resumen/Identidad/Comercial/Crédito/Integraciones.
        Returns the card plus a dict of the value labels, keyed by field,
        so ``_populate()`` can update them on every reload without
        rebuilding the widgets."""
        card = SectionCard(self, title=title)
        labels: dict[str, QLabel] = {}
        for field_key, label in fields:
            value = QLabel("—", self)
            labels[field_key] = value
            row = QWidget()
            form = QFormLayout(row)
            form.setContentsMargins(0, 0, 0, 0)
            form.addRow(f"{label}:", value)
            card.add(row)
        return card, labels

    def _build_resumen_tab(self) -> QWidget:
        card, self._resumen_labels = self._build_form_tab("Resumen", (
            ("owner", "Propietario asignado"), ("segments", "Segmentos activos"),
            ("tags", "Etiquetas"), ("opportunities", "Oportunidades abiertas"),
            ("cases", "Casos abiertos"), ("credit_status", "Estatus de cuenta"),
        ))
        return card

    def _build_identidad_tab(self) -> QWidget:
        card, self._identidad_labels = self._build_form_tab("Identidad", (
            ("code", "Código"), ("legal_name", "Razón social"),
            ("commercial_name", "Nombre comercial"), ("customer_type", "Tipo"),
            ("tax_id", "RFC"),
        ))
        return card

    def _build_comercial_tab(self) -> QWidget:
        card, self._comercial_labels = self._build_form_tab("Comercial", (
            ("orders", "Pedidos totales"), ("orders_open", "Pedidos abiertos"),
            ("deliveries", "Entregas totales"), ("deliveries_open", "Entregas abiertas"),
        ))
        return card

    def _build_credito_tab(self) -> QWidget:
        card, self._credito_labels = self._build_form_tab("Crédito", (
            ("status", "Estatus"), ("limit", "Límite de crédito"),
            ("available", "Crédito disponible"), ("exposure", "Exposición actual"),
            ("overdue", "Monto vencido"), ("receivable_status", "Estatus de cobranza"),
        ))
        return card

    def _build_integraciones_tab(self) -> QWidget:
        card, self._integraciones_labels = self._build_form_tab("Integraciones", (
            ("whatsapp_consent", "Consentimiento WhatsApp"),
            ("loyalty_enrolled", "Programa de fidelidad"),
            ("loyalty_points", "Puntos"), ("loyalty_tier", "Nivel"),
        ))
        return card

    # -- population (data only, called on every reload) --------------------
    def _populate(self, view) -> None:
        customer = view.profile.customer
        self._header.set_title(customer.display_name)
        self._header.set_subtitle(str(customer.code))
        self._status_badge.setText(_STATUS_LABELS.get(customer.status.value, customer.status.value))
        self._status_badge.set_status(_STATUS_VARIANTS.get(customer.status.value, "neutral"))
        self._lifecycle_label.setText(
            _LIFECYCLE_LABELS.get(customer.lifecycle_stage.value, customer.lifecycle_stage.value))

        self._resumen_labels["owner"].setText("Sí" if customer.account_owner_user_id else "No")
        self._resumen_labels["segments"].setText(str(len(view.active_segments)))
        self._resumen_labels["tags"].setText(str(len(view.active_tags)))
        self._resumen_labels["opportunities"].setText(str(len(view.open_opportunities)))
        self._resumen_labels["cases"].setText(str(len(view.open_cases)))
        self._resumen_labels["credit_status"].setText(
            view.credit_summary.status if view.credit_summary else "Sin datos")

        tax_profile = view.profile.tax_profile
        self._identidad_labels["code"].setText(str(customer.code))
        self._identidad_labels["legal_name"].setText(customer.legal_name or "—")
        self._identidad_labels["commercial_name"].setText(customer.commercial_name or "—")
        self._identidad_labels["customer_type"].setText(customer.customer_type.value)
        self._identidad_labels["tax_id"].setText(
            tax_profile.tax_identifier if tax_profile else "—")

        self._table_of("contactos").load_rows(
            [[f"{c.first_name} {c.last_name}".strip(), c.job_title,
              c.phone_e164 or "—", c.email or "—"] for c in view.profile.contacts],
            row_ids=[c.id for c in view.profile.contacts])

        self._table_of("direcciones").load_rows(
            [[a.address_type.value, a.street, a.municipality, a.state]
             for a in view.profile.addresses],
            row_ids=[a.id for a in view.profile.addresses])

        activity_rows = [["Actividad", a.subject, (a.scheduled_at or "")[:10]]
                         for a in view.recent_activities]
        activity_rows += [["Tarea", t.title, (t.due_at or "")[:10]] for t in view.pending_tasks]
        activity_ids = [a.id for a in view.recent_activities] + [t.id for t in view.pending_tasks]
        self._table_of("actividad").load_rows(activity_rows, row_ids=activity_ids)

        self._table_of("oportunidades").load_rows(
            [[o.name, o.status.value, format_money(o.amount) if o.amount is not None else "—"]
             for o in view.open_opportunities],
            row_ids=[o.id for o in view.open_opportunities])

        orders = view.orders_summary
        deliveries = view.delivery_summary
        self._comercial_labels["orders"].setText(str(orders.total_orders) if orders else "—")
        self._comercial_labels["orders_open"].setText(str(orders.open_orders) if orders else "—")
        self._comercial_labels["deliveries"].setText(
            str(deliveries.total_deliveries) if deliveries else "—")
        self._comercial_labels["deliveries_open"].setText(
            str(deliveries.open_deliveries) if deliveries else "—")

        credit = view.credit_summary
        self._credito_labels["status"].setText(credit.status if credit else "—")
        self._credito_labels["limit"].setText(credit.credit_limit if credit else "—")
        self._credito_labels["available"].setText(credit.available_credit if credit else "—")
        self._credito_labels["exposure"].setText(credit.current_exposure if credit else "—")
        self._credito_labels["overdue"].setText(credit.overdue_amount if credit else "—")
        self._credito_labels["receivable_status"].setText(
            credit.receivable_status if credit else "—")

        self._table_of("atencion").load_rows(
            [[str(case.code), case.subject, case.status.value] for case in view.open_cases],
            row_ids=[case.id for case in view.open_cases])

        self._table_of("consentimientos").load_rows(
            [[consent.consent_type.value, consent.status.value, consent.channel.value]
             for consent in view.active_consents],
            row_ids=[consent.id for consent in view.active_consents])

        whatsapp = view.whatsapp_summary
        loyalty = view.loyalty_summary
        self._integraciones_labels["whatsapp_consent"].setText(
            ("Sí" if whatsapp.has_active_whatsapp_consent else "No") if whatsapp else "—")
        self._integraciones_labels["loyalty_enrolled"].setText(
            ("Sí" if loyalty.enrolled else "No") if loyalty else "—")
        self._integraciones_labels["loyalty_points"].setText(
            str(loyalty.current_points) if loyalty else "—")
        self._integraciones_labels["loyalty_tier"].setText(
            (loyalty.tier or "—") if loyalty else "—")

        self._table_of("auditoria").load_rows(
            [[entry.occurred_at[:10], entry.source_module, entry.action]
             for entry in view.recent_history])
