"""Secciones del expediente que se editan (CRM-43): contactos, direcciones,
datos fiscales y cuentas comerciales.

Cada sección es un widget con ``set_customer(customer_id)``: se usa dentro de
la pestaña correspondiente del Expediente y, sola, en las rutas del menú
(``customers.contacts`` / ``addresses`` / ``tax_profiles`` / ``accounts``)
detrás de un buscador de cliente (``CustomerScopedPage``).

Antes esas cuatro rutas decían «en construcción» y en el Expediente las
pestañas eran tablas de sólo lectura: no había forma de agregar un contacto,
cambiar la dirección predeterminada ni capturar el RFC.

Los datos sensibles llegan enmascarados según el permiso (§75). Un formulario
de edición NO precarga un valor enmascarado: guardarlo lo destruiría; el campo
se deja vacío y «vacío» significa «sin cambios».
"""

from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from backend.application.customers.permissions import CustomerPermissions
from frontend.desktop.components import (
    ColumnSpec,
    CustomerSearchBox,
    PageHeader,
    SearchOption,
    SectionCard,
    StandardTable,
    ViewState,
    create_secondary_button,
    create_state_widget,
)
from frontend.desktop.modules.customers_crm.forms import FieldSpec, ask
from frontend.desktop.modules.customers_crm.labels import label, options
from frontend.desktop.themes.tokens import Spacing

_ACCOUNT_TYPES = (("BUSINESS", "Empresa"), ("WHOLESALE", "Mayorista"),
                  ("INSTITUTIONAL", "Institucional"), ("RESTAURANT", "Restaurante"),
                  ("RETAIL", "Minorista"), ("OTHER", "Otro"))
_COMPANY_SIZES = (("MICRO", "Micro"), ("SMALL", "Pequeña"), ("MEDIUM", "Mediana"),
                  ("LARGE", "Grande"))


class _Section(QWidget):
    """Base: tabla + barra de acciones + aviso; el expediente se relee al
    cambiar de cliente o tras una operación exitosa."""

    changed = pyqtSignal()
    columns: tuple[ColumnSpec, ...] = ()
    empty_message = "Sin registros"

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._customer_id: str | None = None
        self._display = None
        self._items: dict[str, object] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.SM)
        self._layout = layout
        self._build_top()
        if self.columns:
            self._table = StandardTable(list(self.columns), self)
            self._table.setAccessibleName(self.accessibleName() or "Listado")
            self._table.itemSelectionChanged.connect(self._sync)
            layout.addWidget(self._table, stretch=1)
        self._notice = QLabel("", self)
        self._notice.setWordWrap(True)
        self._notice.hide()
        layout.addWidget(self._notice)
        self._buttons: list[tuple[QWidget, bool]] = []
        row = QHBoxLayout()
        row.setSpacing(Spacing.SM)
        for text, permission, needs_row, slot in self.actions():
            if permission and not presenter.can(permission):
                continue
            button = create_secondary_button(self, text)
            button.setAccessibleName(text)
            button.clicked.connect(slot)
            row.addWidget(button)
            self._buttons.append((button, needs_row))
        row.addStretch(1)
        layout.addLayout(row)
        self._sync()

    def _build_top(self) -> None:
        pass

    def actions(self):
        return []

    def set_customer(self, customer_id: str | None) -> None:
        self._customer_id = customer_id
        self.reload()

    def reload(self) -> None:
        self._display = None
        if self._customer_id:
            try:
                self._display = self._presenter.read("customer_profile",
                                                     customer_id=self._customer_id)
            except Exception as exc:  # noqa: BLE001
                self._say(False, f"No fue posible leer el expediente: {exc}")
        self._render()
        self._sync()

    def _render(self) -> None:
        raise NotImplementedError

    @property
    def _visible(self) -> bool:
        return self._display is not None and self._display.visibility.value == "VISIBLE"

    def _selected(self):
        if not self.columns:
            return None
        row_id = self._table.selected_row_id()
        return self._items.get(row_id) if row_id else None

    def _sync(self) -> None:
        has_customer = self._customer_id is not None and self._display is not None
        selected = self._selected() is not None
        for button, needs_row in getattr(self, "_buttons", []):
            button.setEnabled(has_customer and (selected or not needs_row))

    def _say(self, ok: bool, message: str) -> None:
        self._notice.setProperty("state", "SUCCESS" if ok else "ERROR")
        self._notice.setText(message)
        self._notice.show()

    def _after(self, result) -> None:
        if result is None:
            return
        ok = bool(getattr(result, "success", False))
        self._say(ok, getattr(result, "message", "") or ("Listo." if ok else "Rechazado."))
        if ok:
            self.reload()
            self.changed.emit()


class ContactsSection(_Section):
    columns = (ColumnSpec("Nombre", stretch=True), ColumnSpec("Puesto"),
               ColumnSpec("Rol en la compra"), ColumnSpec("Teléfono"), ColumnSpec("Correo"),
               ColumnSpec("Principal"))

    def actions(self):
        return [("Agregar contacto", CustomerPermissions.CONTACT_CREATE, False, self._add),
                ("Editar", CustomerPermissions.CONTACT_EDIT, True, self._edit),
                ("Hacer principal", CustomerPermissions.CONTACT_SET_PRIMARY, True,
                 self._primary),
                ("Quitar", CustomerPermissions.CONTACT_DELETE, True, self._remove)]

    def _render(self) -> None:
        contacts = list(self._display.profile.contacts) if self._display else []
        self._items = {c.id: c for c in contacts}
        self._table.load_rows([[f"{c.first_name} {c.last_name}".strip(), c.job_title or "—",
                                label("decision_role", c.decision_role), c.phone_e164 or "—",
                                c.email or "—", "Sí" if c.is_primary else "No"]
                               for c in contacts], row_ids=[c.id for c in contacts])

    def _fields(self, contact=None):
        visible = contact is None or self._visible
        return (
            FieldSpec("first_name", "Nombre", required=True,
                      default=contact.first_name if contact else None),
            FieldSpec("last_name", "Apellidos", default=contact.last_name if contact else None),
            FieldSpec("job_title", "Puesto", default=contact.job_title if contact else None),
            FieldSpec("department", "Área", default=contact.department if contact else None),
            FieldSpec("decision_role", "Rol en la compra", "choice",
                      options=tuple(options("decision_role")),
                      default=contact.decision_role.value if contact else "OTHER"),
            FieldSpec("phone", "Teléfono", "phone",
                      default=(contact.phone_e164 if contact and visible else None),
                      helper=None if visible else "Oculto: deja vacío para no cambiarlo."),
            FieldSpec("email", "Correo", "email",
                      default=(contact.email if contact and visible else None),
                      helper=None if visible else "Oculto: deja vacío para no cambiarlo."),
        )

    def _add(self) -> None:
        fields = self._fields() + (FieldSpec("is_primary", "Contacto principal", "check"),)
        self._after(ask(self, title="Nuevo contacto", submit_text="Agregar", fields=fields,
                        on_submit=lambda v: self._presenter.run(
                            "add_contact", customer_id=self._customer_id,
                            first_name=v["first_name"], last_name=v["last_name"],
                            job_title=v["job_title"], department=v["department"],
                            phone_e164=v["phone"], email=v["email"],
                            decision_role=v["decision_role"] or "OTHER",
                            is_primary=bool(v["is_primary"]))))

    def _edit(self) -> None:
        contact = self._selected()
        if contact is None:
            return
        self._after(ask(self, title="Editar contacto", submit_text="Guardar",
                        fields=self._fields(contact), on_submit=lambda v: self._presenter.run(
                            "update_contact", contact_id=contact.id, first_name=v["first_name"],
                            last_name=v["last_name"], job_title=v["job_title"],
                            department=v["department"], decision_role=v["decision_role"],
                            phone_e164=v["phone"] or None, email=v["email"] or None)))

    def _primary(self) -> None:
        contact = self._selected()
        if contact is not None:
            self._after(self._presenter.run("set_primary_contact", contact_id=contact.id))

    def _remove(self) -> None:
        contact = self._selected()
        if contact is not None:
            self._after(self._presenter.run("remove_contact", contact_id=contact.id))


class AddressesSection(_Section):
    columns = (ColumnSpec("Tipo"), ColumnSpec("Calle y número", stretch=True),
               ColumnSpec("Colonia"), ColumnSpec("C.P."), ColumnSpec("Municipio"),
               ColumnSpec("Estado"), ColumnSpec("Predeterminada"))

    def actions(self):
        return [("Agregar dirección", CustomerPermissions.ADDRESS_CREATE, False, self._add),
                ("Editar", CustomerPermissions.ADDRESS_EDIT, True, self._edit),
                ("Predeterminada", CustomerPermissions.ADDRESS_SET_DEFAULT, True,
                 self._default),
                ("Quitar", CustomerPermissions.ADDRESS_DELETE, True, self._remove)]

    def _render(self) -> None:
        addresses = list(self._display.profile.addresses) if self._display else []
        self._items = {a.id: a for a in addresses}
        self._table.load_rows([[label("address_type", a.address_type),
                                " ".join(p for p in (a.street, a.external_number,
                                                     a.internal_number) if p),
                                a.neighborhood or "—", a.postal_code or "—",
                                a.municipality or "—", a.state or "—",
                                "Sí" if a.is_default else "No"] for a in addresses],
                              row_ids=[a.id for a in addresses])

    def _add(self) -> None:
        from frontend.desktop.modules.customers_crm.dialogs import CustomerAddressDialog

        search = self._presenter.address_search_service()
        dialog = CustomerAddressDialog(self, search_service=search)
        if dialog.exec_():
            self._after(self._presenter.add_customer_address(self._customer_id,
                                                             **dialog.values()))

    def _edit(self) -> None:
        address = self._selected()
        if address is None:
            return
        visible = self._visible
        hidden = None if visible else "Oculto: deja vacío para no cambiarlo."
        self._after(ask(self, title="Editar dirección", submit_text="Guardar", fields=(
            FieldSpec("street", "Calle", default=address.street if visible else None,
                      helper=hidden),
            FieldSpec("external_number", "Número exterior",
                      default=address.external_number if visible else None, helper=hidden),
            FieldSpec("internal_number", "Número interior",
                      default=address.internal_number if visible else None, helper=hidden),
            FieldSpec("neighborhood", "Colonia", default=address.neighborhood),
            FieldSpec("postal_code", "Código postal", default=address.postal_code),
            FieldSpec("municipality", "Municipio", default=address.municipality),
            FieldSpec("state", "Estado", default=address.state),
            FieldSpec("references", "Referencias", "textarea",
                      default=address.references if visible else None, helper=hidden),
        ), on_submit=lambda v: self._presenter.run(
            "update_address", address_id=address.id,
            **{k: (val or None) for k, val in v.items()})))

    def _default(self) -> None:
        address = self._selected()
        if address is not None:
            self._after(self._presenter.run("set_default_address", address_id=address.id))

    def _remove(self) -> None:
        address = self._selected()
        if address is not None:
            self._after(self._presenter.run("remove_address", address_id=address.id))


class TaxProfileSection(_Section):
    """§15: datos fiscales maestros (Fiscal administra los CFDI)."""

    _FIELDS = (("tax_identifier", "RFC"), ("legal_name", "Razón social"),
               ("tax_regime", "Régimen fiscal"), ("fiscal_postal_code", "C.P. fiscal"),
               ("default_cfdi_use", "Uso de CFDI"), ("billing_email", "Correo de facturación"),
               ("validation_status", "Validación"))

    def _build_top(self) -> None:
        self._form_host = QWidget(self)
        self._form = QFormLayout(self._form_host)
        self._values: dict[str, QLabel] = {}
        for key, caption in self._FIELDS:
            value = QLabel("—", self._form_host)
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._values[key] = value
            self._form.addRow(f"{caption}:", value)
        self._layout.addWidget(self._form_host)

    def actions(self):
        return [("Editar datos fiscales", CustomerPermissions.TAX_PROFILE_EDIT, False,
                 self._edit)]

    def _render(self) -> None:
        tax = self._display.profile.tax_profile if self._display else None
        for key, _caption in self._FIELDS:
            raw = getattr(tax, key, None) if tax else None
            text = label("validation", raw) if key == "validation_status" else raw
            self._values[key].setText(str(text) if text else "—")

    def _edit(self) -> None:
        tax = self._display.profile.tax_profile if self._display else None
        visible = self._visible
        hidden = None if visible else "Oculto: deja vacío para no cambiarlo."
        self._after(ask(self, title="Datos fiscales", submit_text="Guardar", intro=(
            "Datos maestros para facturar. Cada venta conserva la copia con la que se "
            "facturó."), fields=(
            FieldSpec("tax_identifier", "RFC", "rfc",
                      default=(tax.tax_identifier if tax and visible else None), helper=hidden),
            FieldSpec("legal_name", "Razón social", default=tax.legal_name if tax else None),
            FieldSpec("tax_regime", "Régimen fiscal (clave SAT)",
                      default=tax.tax_regime if tax else None, placeholder="601"),
            FieldSpec("fiscal_postal_code", "Código postal fiscal",
                      default=tax.fiscal_postal_code if tax else None),
            FieldSpec("default_cfdi_use", "Uso de CFDI (clave SAT)",
                      default=tax.default_cfdi_use if tax else None, placeholder="G03"),
            FieldSpec("billing_email", "Correo de facturación", "email",
                      default=(tax.billing_email if tax and visible else None), helper=hidden),
        ), on_submit=lambda v: self._presenter.run(
            "update_tax_profile", customer_id=self._customer_id,
            **{k: (val or None) for k, val in v.items()})))


class AccountsSection(_Section):
    """§13: cuentas comerciales de un cliente empresarial."""

    columns = (ColumnSpec("Tipo"), ColumnSpec("Giro", stretch=True), ColumnSpec("Tamaño"),
               ColumnSpec("Sitio web"), ColumnSpec("Estado"))

    def actions(self):
        return [("Nueva cuenta", CustomerPermissions.EDIT, False, self._add),
                ("Editar", CustomerPermissions.EDIT, True, self._edit)]

    def _render(self) -> None:
        accounts = list(self._display.profile.accounts) if self._display else []
        self._items = {a.id: a for a in accounts}
        types, sizes = dict(_ACCOUNT_TYPES), dict(_COMPANY_SIZES)
        self._table.load_rows([[types.get(a.account_type, a.account_type), a.industry or "—",
                                sizes.get(a.company_size, a.company_size or "—"),
                                a.website or "—",
                                "Activa" if a.status == "ACTIVE" else "Inactiva"]
                               for a in accounts], row_ids=[a.id for a in accounts])

    def _fields(self, account=None):
        return (FieldSpec("account_type", "Tipo de cuenta", "choice", options=_ACCOUNT_TYPES,
                          default=account.account_type if account else "BUSINESS"),
                FieldSpec("industry", "Giro", default=account.industry if account else None),
                FieldSpec("company_size", "Tamaño", "choice", options=_COMPANY_SIZES,
                          default=account.company_size if account else None),
                FieldSpec("website", "Sitio web", default=account.website if account else None))

    def _add(self) -> None:
        self._after(ask(self, title="Nueva cuenta comercial", submit_text="Registrar",
                        fields=self._fields(), on_submit=lambda v: self._presenter.run(
                            "create_account", customer_id=self._customer_id,
                            account_type=v["account_type"] or "BUSINESS",
                            industry=v["industry"], company_size=v["company_size"] or "",
                            website=v["website"])))

    def _edit(self) -> None:
        account = self._selected()
        if account is None:
            return
        fields = self._fields(account) + (FieldSpec(
            "status", "Estado", "choice", options=(("ACTIVE", "Activa"), ("INACTIVE", "Inactiva")),
            default=account.status),)
        self._after(ask(self, title="Editar cuenta comercial", submit_text="Guardar",
                        fields=fields, on_submit=lambda v: self._presenter.run(
                            "update_account", account_id=account.id,
                            account_type=v["account_type"], industry=v["industry"],
                            company_size=v["company_size"], website=v["website"],
                            status=v["status"])))


class CustomerScopedPage(QWidget):
    """Ruta del menú que trabaja sobre UN cliente: buscador + sección."""

    section_class = ContactsSection
    title = ""
    subtitle = ""
    icon = None

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self.setObjectName("crmCustomerScopedPage")
        self.setAccessibleName(self.title)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(Spacing.MD)
        self._header = PageHeader(self, title=self.title, subtitle=self.subtitle, icon=self.icon,
                                  compact=True)
        root.addWidget(self._header)
        picker_card = SectionCard(self, title="Cliente")
        self._picker = CustomerSearchBox(self, provider=presenter.customer_search_options,
                                         collapse_when_empty=True)
        self._picker.setAccessibleName("Buscar cliente")
        self._picker.selected.connect(self._on_pick)
        picker_card.add(self._picker)
        self._current = QLabel("Busca un cliente por nombre, código, teléfono o correo.", self)
        self._current.setProperty("role", "muted")
        picker_card.add(self._current)
        root.addWidget(picker_card)
        self._empty = create_state_widget(ViewState.EMPTY, self,
                                          message="Elige un cliente para continuar.")
        root.addWidget(self._empty)
        self.section = self.section_class(presenter, self)
        self.section.hide()
        root.addWidget(self.section, stretch=1)

    def ensure_loaded(self) -> None:
        pass

    def _on_pick(self, option) -> None:
        if isinstance(option, SearchOption):
            self.show_customer(option.id, option.label)

    def show_customer(self, customer_id: str, name: str = "") -> None:
        if not name:
            name = self._presenter.customer_names([customer_id]).get(customer_id, "")
        self._picker.set_selected_label(name)
        self._current.setText(f"Cliente: {name}")
        self._empty.hide()
        self.section.show()
        self.section.set_customer(customer_id)


def scoped_page(route_id: str, section, title: str, subtitle: str, icon=None):
    return type(f"Scoped_{route_id.replace('.', '_')}", (CustomerScopedPage,), {
        "section_class": section, "title": title, "subtitle": subtitle, "icon": icon,
        "route_id": route_id})


__all__ = ["AccountsSection", "AddressesSection", "ContactsSection", "CustomerScopedPage",
           "TaxProfileSection", "scoped_page"]
