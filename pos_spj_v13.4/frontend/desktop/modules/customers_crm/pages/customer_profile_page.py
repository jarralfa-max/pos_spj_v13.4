"""Expediente del cliente (route ``customers.profile``), §26-29.

``Customer360QueryService`` arma la vista consolidada; esta página sólo la
presenta y ofrece las acciones de cada pestaña — nunca recalcula un total,
un estado ni un importe enmascarado (§90 «la UI no calcula»).

CRM-43 (re-auditoría sobre la base real): las pestañas eran tablas de sólo
lectura con estados crudos (``NOT_CONFIGURED``, ``PUBLIC_CUSTOMER``). Ahora:

* Identidad / Contactos / Direcciones usan las secciones editables
  (``customer_sections.py``) con datos sensibles enmascarados por permiso;
* Actividad es el panel de seguimiento (actividades, tareas, notas);
* Oportunidades, Crédito y Atención permiten dar de alta en contexto;
* el encabezado ofrece «Estado…» (activar, suspender, bloquear, dar de baja,
  cerrar) con motivo obligatorio — el ciclo de vida existía sin pantalla.

Tabs (§27): Resumen, Identidad, Contactos, Direcciones, Actividad,
Oportunidades, Comercial, Crédito, Atención, Consentimientos, Integraciones,
Auditoría — cada una con su clave estable.
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

from backend.application.crm.permissions import CRMPermissions
from backend.application.customers.permissions import CustomerPermissions
from frontend.desktop.components import (
    ColumnSpec,
    PageHeader,
    SectionCard,
    StandardTable,
    StatusBadge,
    ViewState,
    create_primary_button,
    create_secondary_button,
    create_state_widget,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.customers_crm.formatting import fmt_date, fmt_datetime, fmt_money
from frontend.desktop.modules.customers_crm.forms import FieldSpec, ask
from frontend.desktop.modules.customers_crm.labels import (
    event_label,
    label,
    module_label,
    variant,
    yes_no,
)
from frontend.desktop.modules.customers_crm.pages._pill_tab_bar import PillTabBar
from frontend.desktop.modules.customers_crm.pages._work_items import WorkItemsPanel
from frontend.desktop.modules.customers_crm.pages.customer_sections import (
    AccountsSection,
    AddressesSection,
    ContactsSection,
    TaxProfileSection,
)
from frontend.desktop.navigation.navigation_intent import NavigationIntent
from frontend.desktop.themes.tokens import Spacing

_TABS = (
    ("resumen", "Resumen"), ("identidad", "Identidad"), ("contactos", "Contactos"),
    ("direcciones", "Direcciones"), ("actividad", "Actividad"),
    ("oportunidades", "Oportunidades"), ("comercial", "Comercial"),
    ("credito", "Crédito"), ("atencion", "Atención"),
    ("consentimientos", "Consentimientos"), ("integraciones", "Integraciones"),
    ("auditoria", "Auditoría"),
)

#: comando → (etiqueta, permiso, estados desde los que aplica, ¿motivo obligatorio?)
_LIFECYCLE = (
    ("activate_customer", "Activar", CustomerPermissions.ACTIVATE,
     ("DRAFT", "PROSPECT", "INACTIVE", "SUSPENDED", "BLOCKED"), False),
    ("suspend_customer", "Suspender", CustomerPermissions.SUSPEND, ("ACTIVE",), True),
    ("block_customer", "Bloquear", CustomerPermissions.BLOCK, ("ACTIVE", "SUSPENDED"), True),
    ("deactivate_customer", "Dar de baja (reversible)", CustomerPermissions.DEACTIVATE,
     ("ACTIVE", "SUSPENDED", "PROSPECT"), True),
    ("close_customer", "Cerrar", CustomerPermissions.CLOSE,
     ("ACTIVE", "INACTIVE", "SUSPENDED", "BLOCKED"), True),
)


class CustomerProfilePage(QWidget):
    edit_requested = pyqtSignal(str)
    #: CRM-32: salto a otro módulo (p. ej. Ventas con el cliente preseleccionado).
    navigation_requested = pyqtSignal(object)
    opportunity_opened = pyqtSignal(str)
    case_opened = pyqtSignal(str)

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("customerProfilePage")
        self._presenter = presenter
        self._customer_id: str | None = None
        self._status_value: str | None = None
        self._view = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(Spacing.MD)

        refresh = create_secondary_button(self, "Actualizar")
        refresh.clicked.connect(self._reload_current)
        edit_btn = create_secondary_button(self, "Editar")
        edit_btn.clicked.connect(self._request_edit)
        new_sale_btn = create_primary_button(self, "Nueva venta")
        new_sale_btn.clicked.connect(self._request_new_sale)
        cxc_btn = create_secondary_button(self, "Ver CxC")
        cxc_btn.clicked.connect(self._request_receivables)
        actions = [new_sale_btn, cxc_btn, edit_btn]
        if any(presenter.can(perm) for _c, _l, perm, _s, _r in _LIFECYCLE):
            self._lifecycle_btn = create_secondary_button(self, "Estado…")
            self._lifecycle_btn.setToolTip("Activar, suspender, bloquear, dar de baja o cerrar.")
            self._lifecycle_btn.clicked.connect(self._change_status)
            actions.append(self._lifecycle_btn)
        actions.append(refresh)
        self._header = PageHeader(
            self, title="Expediente del cliente", icon=Icons.CUSTOMERS,
            compact=True, actions=actions)
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
        for key, text in _TABS:
            self._tab_bar.add_tab(key, text)
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

    # -- navegación ------------------------------------------------------------
    def _on_tab_changed(self, key: str) -> None:
        if self._customer_id is not None and key in self._tab_index:
            self._stack.setCurrentIndex(self._tab_index[key])

    def ensure_loaded(self) -> None:
        pass  # nada que mostrar hasta elegir cliente — ver show_customer()

    def show_customer(self, customer_id: str, tab: str = "resumen") -> None:
        self._customer_id = customer_id
        self._tab_bar.activate(tab)
        self._stack.setCurrentIndex(self._tab_index.get(tab, self._tab_index["resumen"]))
        for section in self._sections():
            section.set_customer(customer_id)
        self._work.set_entity("CUSTOMER", customer_id)
        self._reload_current()

    def _sections(self):
        return (self._tax_section, self._accounts_section, self._contacts_section,
                self._addresses_section, self._consents_section, self._preferences_section,
                *(section for _key, section in self._commercial_sections))

    def _request_edit(self) -> None:
        if self._customer_id is not None:
            self.edit_requested.emit(self._customer_id)

    def _request_new_sale(self) -> None:
        """CRM-32: salta a Ventas con este cliente preseleccionado."""
        if self._customer_id is not None:
            self.navigation_requested.emit(
                NavigationIntent(route="sales.new", context={"customer_id": self._customer_id}))

    def _request_receivables(self) -> None:
        """CRM-37: salta a la CxC de Finanzas con este cliente."""
        if self._customer_id is not None:
            self.navigation_requested.emit(
                NavigationIntent(
                    route="finance.receivables", context={"customer_id": self._customer_id}))

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
            self._view = view
            self._populate(view)
            self._status.hide()
        except Exception as exc:  # una página siempre muestra algo
            self._status.setText(f"No fue posible cargar el expediente: {exc}")
            self._status.show()

    # -- acciones ----------------------------------------------------------------
    def _say(self, ok: bool, message: str) -> None:
        self._status.setProperty("state", "SUCCESS" if ok else "ERROR")
        self._status.setText(message)
        self._status.show()

    def _after(self, result) -> None:
        if result is None:
            return
        ok = bool(getattr(result, "success", False))
        self._say(ok, getattr(result, "message", "") or ("Listo." if ok else "Rechazado."))
        if ok:
            self.reload()

    def _change_status(self) -> None:
        if self._customer_id is None:
            return
        current = self._status_value or ""
        choices = [(cmd, text) for cmd, text, perm, states, _r in _LIFECYCLE
                   if current in states and self._presenter.can(perm)]
        if not choices:
            self._say(False, f"No hay cambios de estado disponibles desde "
                             f"«{label('customer_status', current)}».")
            return
        reason_required = {cmd: needs for cmd, _t, _p, _s, needs in _LIFECYCLE}

        def submit(v):
            command = v["command"]
            if reason_required.get(command) and not (v["reason"] or "").strip():
                from frontend.desktop.modules.customers_crm.pages._outcomes import Fail
                return Fail("Indica el motivo del cambio de estado.")
            return self._presenter.run(command, customer_id=self._customer_id,
                                       reason=v["reason"] or "")

        self._after(ask(self, title="Cambiar estado del cliente", submit_text="Aplicar",
                        intro="Suspender o bloquear detiene la venta a crédito; dar de baja es "
                              "reversible y conserva el historial.", fields=(
                            FieldSpec("command", "Acción", "choice", required=True,
                                      options=tuple(choices), default=choices[0][0]),
                            FieldSpec("reason", "Motivo", "textarea"),
                        ), on_submit=submit))

    def _new_opportunity(self) -> None:
        from frontend.desktop.modules.customers_crm.pages.opportunity_pages import (
            create_opportunity_dialog,
        )
        if self._customer_id:
            self._after(create_opportunity_dialog(
                self, self._presenter, customer_id=self._customer_id,
                customer_label=self._header_title()))

    def _new_case(self) -> None:
        from frontend.desktop.modules.customers_crm.pages.service_pages import (
            create_case_dialog,
        )
        if self._customer_id:
            self._after(create_case_dialog(self, self._presenter, customer_id=self._customer_id,
                                           customer_label=self._header_title()))

    def _request_credit(self) -> None:
        from frontend.desktop.modules.customers_crm.pages.credit_pages import (
            request_credit_dialog,
        )
        if self._customer_id:
            self._after(request_credit_dialog(self, self._presenter,
                                              customer_id=self._customer_id,
                                              customer_label=self._header_title()))

    def _header_title(self) -> str:
        view = self._view
        return view.profile.customer.display_name if view is not None else ""

    # -- construcción de pestañas (una vez) -----------------------------------------
    _TABLE_TAB_COLUMNS = {
        "oportunidades": (ColumnSpec("Oportunidad", stretch=True),
                          ColumnSpec("Estado", "status"), ColumnSpec("Valor", "numeric"),
                          ColumnSpec("Cierre esperado", "date")),
        "atencion": (ColumnSpec("Caso"), ColumnSpec("Asunto", stretch=True),
                     ColumnSpec("Tipo"), ColumnSpec("Estado", "status")),
        "auditoria": (ColumnSpec("Fecha", "date"), ColumnSpec("Módulo"),
                      ColumnSpec("Acción", stretch=True), ColumnSpec("Motivo")),
    }

    def _build_tab(self, key: str) -> QWidget:
        builders = {
            "resumen": self._build_resumen_tab,
            "identidad": self._build_identidad_tab,
            "contactos": self._build_contactos_tab,
            "direcciones": self._build_direcciones_tab,
            "actividad": self._build_actividad_tab,
            "consentimientos": self._build_consentimientos_tab,
            "comercial": self._build_comercial_tab,
            "credito": self._build_credito_tab,
            "integraciones": self._build_integraciones_tab,
        }
        if key in builders:
            return builders[key]()
        return self._build_table_tab(key)

    def _build_table_tab(self, key: str) -> QWidget:
        card = SectionCard(self)
        table = StandardTable(list(self._TABLE_TAB_COLUMNS[key]), card)
        table.setObjectName(f"{key}Table")
        card.add(table)
        self._tables[key] = table
        extra = {
            "oportunidades": ("Nueva oportunidad", CRMPermissions.OPPORTUNITIES_CREATE,
                              self._new_opportunity),
            "atencion": ("Nuevo caso", CRMPermissions.CASES_CREATE, self._new_case),
        }.get(key)
        if extra and self._presenter.can(extra[1]):
            button = create_secondary_button(card, extra[0])
            button.clicked.connect(extra[2])
            card.add(button)
        if key == "oportunidades":
            table.doubleClicked.connect(
                lambda *_: table.selected_row_id() and self.opportunity_opened.emit(
                    table.selected_row_id()))
        if key == "atencion":
            table.doubleClicked.connect(
                lambda *_: table.selected_row_id() and self.case_opened.emit(
                    table.selected_row_id()))
        return card

    def _table_of(self, key: str) -> StandardTable:
        return self._tables[key]

    def _build_form_tab(
        self, title: str, fields: tuple[tuple[str, str], ...],
    ) -> tuple[QWidget, dict[str, QLabel]]:
        card = SectionCard(self, title=title)
        labels: dict[str, QLabel] = {}
        host = QWidget(card)
        form = QFormLayout(host)
        form.setContentsMargins(0, 0, 0, 0)
        for field_key, caption in fields:
            value = QLabel("—", host)
            value.setWordWrap(True)
            labels[field_key] = value
            form.addRow(f"{caption}:", value)
        card.add(host)
        return card, labels

    def _build_resumen_tab(self) -> QWidget:
        card, self._resumen_labels = self._build_form_tab("Resumen", (
            ("owner", "Responsable principal"), ("segments", "Segmentos activos"),
            ("tags", "Etiquetas"), ("opportunities", "Oportunidades abiertas"),
            ("cases", "Casos abiertos"), ("tasks", "Tareas pendientes"),
            ("credit_status", "Crédito"), ("quality", "Pendientes de calidad de datos"),
            ("duplicates", "Posibles duplicados"),
        ))
        card.body().addStretch(1)
        return card

    def _build_identidad_tab(self) -> QWidget:
        host = QWidget(self)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        card, self._identidad_labels = self._build_form_tab("Identidad", (
            ("code", "Código"), ("display_name", "Nombre"), ("legal_name", "Razón social"),
            ("commercial_name", "Nombre comercial"), ("customer_type", "Tipo"),
            ("tax_id", "RFC"), ("source", "Origen"), ("created", "Alta"),
        ))
        layout.addWidget(card)
        tax_card = SectionCard(host, title="Datos fiscales")
        self._tax_section = TaxProfileSection(self._presenter, tax_card)
        self._tax_section.changed.connect(self.reload)
        tax_card.add(self._tax_section)
        layout.addWidget(tax_card)
        accounts_card = SectionCard(host, title="Cuentas comerciales")
        self._accounts_section = AccountsSection(self._presenter, accounts_card)
        accounts_card.add(self._accounts_section)
        layout.addWidget(accounts_card, stretch=1)
        return host

    def _build_contactos_tab(self) -> QWidget:
        card = SectionCard(self, title="Contactos")
        self._contacts_section = ContactsSection(self._presenter, card)
        card.add(self._contacts_section)
        return card

    def _build_direcciones_tab(self) -> QWidget:
        card = SectionCard(self, title="Direcciones")
        self._addresses_section = AddressesSection(self._presenter, card)
        card.add(self._addresses_section)
        return card

    def _build_consentimientos_tab(self) -> QWidget:
        from frontend.desktop.modules.customers_crm.pages.privacy_pages import (
            ConsentsSection,
            PreferencesSection,
        )
        host = QWidget(self)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        consents_card = SectionCard(host, title="Consentimientos")
        self._consents_section = ConsentsSection(self._presenter, consents_card)
        consents_card.add(self._consents_section)
        layout.addWidget(consents_card, stretch=1)
        prefs_card = SectionCard(host, title="Preferencias de comunicación")
        self._preferences_section = PreferencesSection(self._presenter, prefs_card)
        prefs_card.add(self._preferences_section)
        layout.addWidget(prefs_card)
        return host

    def _build_actividad_tab(self) -> QWidget:
        card = SectionCard(self, title="Seguimiento")
        self._work = WorkItemsPanel(self._presenter, card)
        card.add(self._work)
        return card

    def _build_comercial_tab(self) -> QWidget:
        from frontend.desktop.modules.customers_crm.pages.commercial_pages import (
            AffinitySection,
            OrdersSection,
            PaymentsSection,
            PurchasesSection,
            QuotesSection,
            ReturnsSection,
        )
        host = QWidget(self)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        card, self._comercial_labels = self._build_form_tab("Relación comercial", (
            ("purchases", "Compras registradas"), ("last_purchase", "Última compra"),
            ("orders", "Pedidos totales"), ("orders_open", "Pedidos abiertos"),
            ("last_order", "Último pedido"), ("deliveries", "Entregas totales"),
            ("deliveries_open", "Entregas abiertas"), ("last_delivery", "Última entrega"),
        ))
        layout.addWidget(card)
        history_card = SectionCard(host, title="Historial")
        tabs = PillTabBar(history_card)
        stack = QStackedWidget(history_card)
        self._commercial_sections = []
        for key, text, section_class in (
            ("compras", "Compras", PurchasesSection), ("pagos", "Pagos", PaymentsSection),
            ("pedidos", "Pedidos", OrdersSection), ("cotizaciones", "Cotizaciones", QuotesSection),
            ("devoluciones", "Devoluciones", ReturnsSection),
            ("frecuentes", "Productos frecuentes", AffinitySection),
        ):
            tabs.add_tab(key, text)
            section = section_class(self._presenter, history_card)
            stack.addWidget(section)
            self._commercial_sections.append((key, section))
        keys = [key for key, _s in self._commercial_sections]
        tabs.tab_changed.connect(lambda key: stack.setCurrentIndex(keys.index(key)))
        history_card.add(tabs)
        history_card.add(stack)
        layout.addWidget(history_card, stretch=1)
        return host

    def _build_credito_tab(self) -> QWidget:
        card, self._credito_labels = self._build_form_tab("Crédito", (
            ("status", "Estatus"), ("risk", "Riesgo"), ("terms", "Plazo"),
            ("limit", "Límite de crédito"), ("available", "Crédito disponible"),
            ("exposure", "Exposición actual"), ("overdue", "Monto vencido"),
            ("next_due", "Próximo vencimiento"), ("receivable_status", "Estatus de cobranza"),
        ))
        if self._presenter.can(CustomerPermissions.CREDIT_REQUEST):
            button = create_secondary_button(card, "Solicitar crédito")
            button.clicked.connect(self._request_credit)
            card.add(button)
        card.body().addStretch(1)
        return card

    def _build_integraciones_tab(self) -> QWidget:
        card, self._integraciones_labels = self._build_form_tab("Integraciones", (
            ("whatsapp_consent", "Consentimiento WhatsApp"),
            ("whatsapp_last", "Última conversación"),
            ("whatsapp_open", "Conversaciones abiertas"),
            ("loyalty_enrolled", "Programa de fidelidad"),
            ("loyalty_points", "Puntos"), ("loyalty_tier", "Nivel"),
        ))
        hint = QLabel("Puntos, tarjetas y recompensas se administran en Fidelidad; "
                      "las conversaciones, en WhatsApp.", card)
        hint.setProperty("role", "muted")
        hint.setWordWrap(True)
        card.add(hint)
        card.body().addStretch(1)
        return card

    # -- datos (en cada recarga) --------------------------------------------------
    def _populate(self, view) -> None:
        customer = view.profile.customer
        self._status_value = customer.status.value
        self._header.set_title(customer.display_name)
        self._header.set_subtitle(str(customer.code))
        self._status_badge.setText(label("customer_status", customer.status))
        self._status_badge.set_status(variant("customer_status", customer.status))
        self._lifecycle_label.setText(label("lifecycle", customer.lifecycle_stage))

        owners = view.ownership_by_type or {}
        primary = owners.get("PRIMARY") if isinstance(owners, dict) else None
        owner_id = (getattr(primary, "owner_user_id", None)
                    or customer.account_owner_user_id)
        credit = view.credit_summary
        self._resumen_labels["owner"].setText(
            self._presenter.user_name(owner_id) if owner_id else "Sin asignar")
        self._resumen_labels["segments"].setText(str(len(view.active_segments)))
        self._resumen_labels["tags"].setText(str(len(view.active_tags)))
        self._resumen_labels["opportunities"].setText(str(len(view.open_opportunities)))
        self._resumen_labels["cases"].setText(str(len(view.open_cases)))
        self._resumen_labels["tasks"].setText(str(len(view.pending_tasks)))
        self._resumen_labels["credit_status"].setText(
            label("credit_status", credit.status) if credit else "Sin datos")
        self._resumen_labels["quality"].setText(str(len(view.open_quality_issues)))
        self._resumen_labels["duplicates"].setText(str(len(view.open_duplicate_candidates)))

        tax_profile = view.profile.tax_profile
        self._identidad_labels["code"].setText(str(customer.code))
        self._identidad_labels["display_name"].setText(customer.display_name)
        self._identidad_labels["legal_name"].setText(customer.legal_name or "—")
        self._identidad_labels["commercial_name"].setText(customer.commercial_name or "—")
        self._identidad_labels["customer_type"].setText(
            label("customer_type", customer.customer_type))
        self._identidad_labels["tax_id"].setText(
            (tax_profile.tax_identifier or "—") if tax_profile else "—")
        self._identidad_labels["source"].setText(customer.source or "—")
        self._identidad_labels["created"].setText(fmt_datetime(customer.created_at))

        self._table_of("oportunidades").load_rows(
            [[o.name, label("opportunity_status", o.status), fmt_money(o.amount),
              fmt_date(o.expected_close_date)] for o in view.open_opportunities],
            row_ids=[o.id for o in view.open_opportunities])

        orders = view.orders_summary
        deliveries = view.delivery_summary
        self._comercial_labels["purchases"].setText(str(getattr(customer, "purchase_count",
                                                                "—")))
        self._comercial_labels["last_purchase"].setText(
            fmt_datetime(getattr(customer, "last_purchase_at", None)))
        self._comercial_labels["orders"].setText(str(orders.total_orders) if orders else "—")
        self._comercial_labels["orders_open"].setText(str(orders.open_orders) if orders else "—")
        self._comercial_labels["last_order"].setText(
            fmt_datetime(orders.last_order_at) if orders else "—")
        self._comercial_labels["deliveries"].setText(
            str(deliveries.total_deliveries) if deliveries else "—")
        self._comercial_labels["deliveries_open"].setText(
            str(deliveries.open_deliveries) if deliveries else "—")
        self._comercial_labels["last_delivery"].setText(
            (deliveries.last_delivery_status or "—") if deliveries else "—")

        self._credito_labels["status"].setText(
            label("credit_status", credit.status) if credit else "—")
        self._credito_labels["risk"].setText(
            label("risk_level", credit.risk_level) if credit and credit.risk_level else "—")
        self._credito_labels["terms"].setText(
            f"{credit.payment_terms_days} días" if credit and credit.payment_terms_days
            else "—")
        for key, attr in (("limit", "credit_limit"), ("available", "available_credit"),
                          ("exposure", "current_exposure"), ("overdue", "overdue_amount")):
            raw = str(getattr(credit, attr, "") or "") if credit else ""
            self._credito_labels[key].setText(
                fmt_money(raw) if raw.replace(".", "", 1).replace("-", "", 1).isdigit()
                else (raw or "—"))
        self._credito_labels["next_due"].setText(
            fmt_date(credit.next_due_date) if credit else "—")
        self._credito_labels["receivable_status"].setText(
            label("receivable_status", credit.receivable_status) if credit else "—")

        self._table_of("atencion").load_rows(
            [[str(case.code), case.subject, label("case_type", case.case_type),
              label("case_status", case.status)] for case in view.open_cases],
            row_ids=[case.id for case in view.open_cases])

        whatsapp = view.whatsapp_summary
        loyalty = view.loyalty_summary
        self._integraciones_labels["whatsapp_consent"].setText(
            yes_no(whatsapp.has_active_whatsapp_consent) if whatsapp else "—")
        self._integraciones_labels["whatsapp_last"].setText(
            fmt_datetime(whatsapp.last_conversation_at) if whatsapp else "—")
        self._integraciones_labels["whatsapp_open"].setText(
            str(whatsapp.open_conversations_count) if whatsapp else "—")
        self._integraciones_labels["loyalty_enrolled"].setText(
            (loyalty.program or yes_no(loyalty.enrolled)) if loyalty else "—")
        self._integraciones_labels["loyalty_points"].setText(
            str(loyalty.current_points) if loyalty else "—")
        self._integraciones_labels["loyalty_tier"].setText(
            (loyalty.tier or "—") if loyalty else "—")

        self._table_of("auditoria").load_rows(
            [[fmt_datetime(entry.occurred_at), module_label(entry.source_module),
              event_label(entry.action), entry.reason or "—"] for entry in view.recent_history])
