"""NewOrderPage (PASS 6) — "Nuevo pedido": captura completa en una pantalla.

A diferencia del diálogo de "Todos los pedidos" (que pide el UUID del producto a
mano y guarda sin dirección), aquí el producto se busca, el precio lo fija Pricing
y, si la modalidad lleva entrega, la dirección se captura y se guarda con el pedido
en la misma transacción (`CaptureOrderUseCase`).

Es un `FormPage`: el cuerpo desplaza y "Crear pedido" queda siempre alcanzable.
"""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QWidget

from frontend.desktop.components import (
    DecimalInput,
    PhoneInput,
    SearchableComboBox,
    StandardLineEdit,
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.components.pages import FormPage
from frontend.desktop.components.product_search_box import ProductSearchBox
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.orders_delivery.presenters.new_order_presenter import (
    CHANNEL_OPTIONS,
    FULFILLMENT_OPTIONS,
)

LINE_COLUMNS = [
    ColumnSpec("Producto"), ColumnSpec("Cantidad", "numeric"),
    ColumnSpec("Precio", "numeric"), ColumnSpec("Subtotal estimado", "numeric"),
]


class NewOrderPage(FormPage):
    def __init__(self, presenter, *, title: str, subtitle: str, parent=None) -> None:
        super().__init__(parent, title=title, subtitle=subtitle)
        self._presenter = presenter
        self._selected_product_id: str | None = None
        #: (product_id, cantidad) en el orden capturado.
        self._lines: list[tuple[str, Decimal]] = []
        self.title = title
        self.setAccessibleName(title)
        self.setAccessibleDescription(subtitle)

        self.notice = QLabel("", self.content)
        self.notice.setWordWrap(True)
        self.notice.hide()
        self.add_content(self.notice)

        datos = QFormLayout()
        self.channel = SearchableComboBox(placeholder="Selecciona un canal")
        self.channel.set_options(CHANNEL_OPTIONS)
        self.fulfillment = SearchableComboBox(placeholder="Selecciona una modalidad")
        self.fulfillment.set_options(FULFILLMENT_OPTIONS)
        self.fulfillment.selection_changed.connect(lambda *_: self._sync_address())
        self.contact_name = StandardLineEdit(placeholder="Nombre del cliente")
        self.contact_phone = PhoneInput()
        datos.addRow("Canal:", self.channel)
        datos.addRow("Modalidad:", self.fulfillment)
        datos.addRow("Cliente:", self.contact_name)
        datos.addRow("Teléfono:", self.contact_phone)
        self.content_layout.addLayout(datos)

        captura = QHBoxLayout()
        self.product = ProductSearchBox(parent=self.content, provider=presenter.search_products)
        self.product.selected.connect(self._select_product)
        self.quantity = DecimalInput(precision=3, minimum="0.001", nullable=True)
        self.add_button = create_secondary_button(self.content, "Agregar producto")
        self.add_button.clicked.connect(self.add_selected_product)
        captura.addWidget(self.product, stretch=1)
        captura.addWidget(self.quantity)
        captura.addWidget(self.add_button)
        self.content_layout.addLayout(captura)

        self.lines_table = StandardTable(LINE_COLUMNS, self.content)
        self.add_content(self.lines_table, stretch=1)
        self.remove_button = create_secondary_button(self.content, "Quitar producto")
        self.remove_button.clicked.connect(self.remove_selected_line)
        self.add_content(self.remove_button)

        self.address_group = QWidget(self.content)
        direccion = QFormLayout(self.address_group)
        self.recipient_name = StandardLineEdit(placeholder="Quién recibe")
        self.recipient_phone = PhoneInput()
        self.street = StandardLineEdit(placeholder="Calle")
        self.exterior_number = StandardLineEdit(placeholder="Número exterior")
        self.interior_number = StandardLineEdit(placeholder="Número interior")
        self.neighborhood = StandardLineEdit(placeholder="Colonia")
        self.postal_code = StandardLineEdit(placeholder="Código postal")
        self.references = StandardLineEdit(placeholder="Referencias")
        for etiqueta, campo in (("Recibe:", self.recipient_name), ("Teléfono:", self.recipient_phone),
                                ("Calle:", self.street), ("Exterior:", self.exterior_number),
                                ("Interior:", self.interior_number), ("Colonia:", self.neighborhood),
                                ("Código postal:", self.postal_code),
                                ("Referencias:", self.references)):
            direccion.addRow(etiqueta, campo)
        self.add_content(self.address_group)

        self.create_button = create_primary_button(self, "Crear pedido")
        self.create_button.clicked.connect(self.create_order)
        self.create_button.setEnabled(presenter.can_create())
        self.add_action(self.create_button)

        self._sync_address()

    # ciclo de vida ------------------------------------------------------------------
    def ensure_loaded(self) -> None:
        """Nada que cargar: los productos se buscan al teclear."""

    # captura -------------------------------------------------------------------------
    def _select_product(self, option) -> None:
        self._selected_product_id = option.id if option is not None else None

    def _sync_address(self) -> None:
        self.address_group.setVisible(
            self._presenter.requires_address(self.fulfillment.current_id()))

    def add_selected_product(self) -> None:
        producto = self._presenter.product(self._selected_product_id)
        cantidad = self.quantity.decimal_value()
        if producto is None:
            self._show(False, "Busca y elige un producto.")
            return
        if producto.price is None:
            self._show(False, f"«{producto.name}» no tiene precio vigente: no se puede pedir.")
            return
        if not self.quantity.is_valid() or cantidad is None or cantidad <= 0:
            self._show(False, "Captura una cantidad mayor a cero.")
            return
        self._lines.append((producto.product_id, cantidad))
        self._refresh_lines()
        self.quantity.set_decimal(None)
        self.notice.hide()

    def remove_selected_line(self) -> None:
        fila = self.lines_table.currentRow()
        if 0 <= fila < len(self._lines):
            del self._lines[fila]
            self._refresh_lines()

    def _refresh_lines(self) -> None:
        filas = [self._presenter.line_row(self._presenter.product(pid), cantidad)
                 for pid, cantidad in self._lines]
        self.lines_table.load_rows(filas, row_ids=[str(i) for i in range(len(filas))])

    def data(self) -> dict:
        datos = {
            "channel": self.channel.current_id(),
            "fulfillment_type": self.fulfillment.current_id(),
            "contact_name": self.contact_name.text().strip() or None,
            "contact_phone": self.contact_phone.value().strip() or None,
            "lines": [{"product_id": pid, "quantity": str(cantidad)}
                      for pid, cantidad in self._lines],
            "address": None,
        }
        if self._presenter.requires_address(datos["fulfillment_type"]):
            datos["address"] = {
                "recipient_name": self.recipient_name.text().strip(),
                "recipient_phone": self.recipient_phone.value().strip(),
                "street": self.street.text().strip(),
                "exterior_number": self.exterior_number.text().strip(),
                "interior_number": self.interior_number.text().strip() or None,
                "neighborhood": self.neighborhood.text().strip() or None,
                "postal_code": self.postal_code.text().strip(),
                "references": self.references.text().strip() or None,
            }
        return datos

    def create_order(self) -> None:
        datos = self.data()
        if not datos["channel"] or not datos["fulfillment_type"]:
            self._show(False, "Elige canal y modalidad.")
            return
        ok, mensaje = self._presenter.create(datos)
        self._show(ok, mensaje)
        if ok:
            self._reset()

    def _reset(self) -> None:
        self._lines.clear()
        self._refresh_lines()
        self._selected_product_id = None
        self.product.clear()
        for campo in (self.contact_name, self.recipient_name, self.street, self.exterior_number,
                      self.interior_number, self.neighborhood, self.postal_code, self.references):
            campo.clear()

    def _show(self, ok: bool, mensaje: str) -> None:
        self.notice.setProperty("state", "SUCCESS" if ok else "ERROR")
        self.notice.setText(mensaje)
        self.notice.show()
