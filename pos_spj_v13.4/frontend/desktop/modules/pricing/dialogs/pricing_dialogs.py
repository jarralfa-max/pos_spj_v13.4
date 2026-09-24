"""Diálogos de captura de Precios y Costos.

Sólo captura y validación de forma: ni SQL ni reglas de negocio. Entregan un
dict al presentador, que llama al caso de uso — y es el caso de uso quien decide
si la lista es inmutable, si el precio va bajo el mínimo o si falta permiso.

El producto se elige por el buscador canónico compartido (`EntitySearchInput`
sobre `ProductSearchQuery`), nunca escribiendo un UUID a mano.
"""

from __future__ import annotations

from datetime import date

from PyQt5.QtWidgets import QCheckBox, QMessageBox

from backend.domain.pricing.enums import SALE_CHANNELS

from frontend.desktop.components import (
    DateInput,
    EntitySearchInput,
    FormDialog,
    MoneyInput,
    PercentInput,
    SearchableComboBox,
    StandardLineEdit,
)
from frontend.desktop.components.decimal_input import DecimalInput

_KINDS = [("BASE", "Base"), ("CHANNEL", "Canal"), ("CUSTOMER", "Cliente"),
          ("PROMOTIONAL", "Promoción")]

#: Etiquetas de los canales de venta (`SALE_CHANNELS` del dominio de Precios).
#: El canal era texto libre y el motor lo compara contra el código con que
#: Ventas y Pedidos piden precio: "Mostrador" o "whats" nunca coincidían.
_CHANNEL_LABELS = {
    "POS": "Mostrador (POS)", "WHATSAPP": "WhatsApp", "COUNTER": "Ventanilla",
    "PHONE": "Teléfono", "E_COMMERCE": "Tienda en línea", "SALES_REP": "Vendedor",
    "BACKOFFICE": "Backoffice",
}


def _fecha(value):
    """Fecha ISO almacenada → `date`. Un valor ilegible no debe tumbar el
    diálogo: se ignora y el campo queda como estaba."""
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _combo(options) -> SearchableComboBox:
    combo = SearchableComboBox()
    combo.set_options(options)
    return combo


class _PricingDialog(FormDialog):
    """Base con validación previa a aceptar, como el resto de los módulos."""

    def _error(self) -> str | None:
        return None

    def _finish(self, ok_text: str) -> None:
        box = self.add_button_box(ok_text=ok_text)
        box.accepted.disconnect()
        box.accepted.connect(self._accept_if_valid)

    def _accept_if_valid(self) -> None:
        error = self._error()
        if error:
            QMessageBox.warning(self, self.windowTitle(), error)
            return
        self.accept()


class PriceListFormDialog(_PricingDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Nueva lista de precios")
        self._code = StandardLineEdit(placeholder="Código (p. ej. PROMO-OCT)")
        self._name = StandardLineEdit(placeholder="Nombre")
        self._kind = _combo(_KINDS)
        self._channel = _combo([(c, _CHANNEL_LABELS.get(c, c)) for c in SALE_CHANNELS])
        self._discount = PercentInput()
        self.form.addRow("Código *", self._code)
        self.form.addRow("Nombre *", self._name)
        self.form.addRow("Tipo *", self._kind)
        self.form.addRow("Canal de venta", self._channel)
        self.form.addRow("Descuento", self._discount)
        self._finish("Crear")

    def _error(self) -> str | None:
        if not self._code.value().strip():
            return "El código es obligatorio."
        if not self._name.value().strip():
            return "El nombre es obligatorio."
        if self._kind.current_id() is None:
            return "Selecciona el tipo de lista."
        if self._kind.current_id() == "CHANNEL" and self._channel.current_id() is None:
            return "Una lista de canal requiere el canal de venta donde aplica."
        return None

    def values(self) -> dict:
        return {"code": self._code.value().strip(), "name": self._name.value().strip(),
                "kind": self._kind.current_id(),
                # El canal sólo tiene efecto en listas de CANAL.
                "channel": (self._channel.current_id()
                            if self._kind.current_id() == "CHANNEL" else None),
                "discount_pct": str(self._discount.decimal_value())}


class ProductPriceFormDialog(_PricingDialog):
    """Precio de venta de un producto en una lista.

    La vigencia va detrás de una casilla a propósito: `DateInput` es un
    `QDateEdit` y SIEMPRE tiene fecha, así que sin la casilla todo precio
    nacería vigente desde hoy sin que nadie lo pidiera.
    """

    def __init__(self, parent=None, *, list_options, product_provider=None,
                 empty_reason_provider=None, initial=None, branch_options=None) -> None:
        super().__init__(parent, title="Precio por producto")
        self._list = _combo(list_options)
        self._product = EntitySearchInput(
            self, provider=product_provider, placeholder="Buscar producto…",
            empty_reason_provider=empty_reason_provider)
        # La sucursal se ELIGE. Era una caja de texto: había que teclear el
        # UUID a mano. "Todas las sucursales" va como opción explícita porque
        # aquí el vacío SIGNIFICA algo (el precio rige en todas), y no puede
        # depender de que el usuario adivine que dejarlo en blanco es la forma
        # de decirlo.
        self._branch = _combo(list(branch_options or [("", "Todas las sucursales")]))
        self._price = MoneyInput()
        self._min_price = MoneyInput()
        self._scheduled = QCheckBox("Programar vigencia")
        self._from = DateInput()
        self._to = DateInput()
        self.form.addRow("Lista *", self._list)
        self.form.addRow("Producto *", self._product)
        self.form.addRow("Sucursal", self._branch)
        self.form.addRow("Precio de venta *", self._price)
        self.form.addRow("Precio mínimo", self._min_price)
        self.form.addRow("", self._scheduled)
        self.form.addRow("Vigente desde", self._from)
        self.form.addRow("Vigente hasta", self._to)
        self._finish("Guardar")
        if initial:
            self._prefill(dict(initial))

    def _prefill(self, datos: dict) -> None:
        """Precarga para EDITAR un precio existente.

        Lista, producto y sucursal quedan editables a propósito. El caso de uso
        hace upsert por (lista, producto, sucursal), así que cambiar uno de los
        tres crea otro precio en vez de mover éste. Es el comportamiento real
        del dominio y la pantalla no lo disimula bloqueando los campos.
        """
        self.setWindowTitle("Editar precio de producto")
        self._list.set_current_id(datos.get("price_list_id"))
        product_id = datos.get("product_id")
        if product_id:
            etiqueta = " · ".join(str(v) for v in (datos.get("product_code"),
                                                   datos.get("product_name")) if v)
            self._product.set_selected_label(product_id, etiqueta or str(product_id))
        self._preselect_branch(str(datos.get("branch_id") or ""))
        self._price.set_decimal_value(datos.get("sale_price"))
        self._min_price.set_decimal_value(datos.get("min_price"))
        desde, hasta = _fecha(datos.get("effective_from")), _fecha(datos.get("effective_to"))
        if desde or hasta:
            self._scheduled.setChecked(True)
            self._from.set_date_value(desde)
            self._to.set_date_value(hasta)

    def _preselect_branch(self, branch_id: str) -> None:
        """Selecciona la sucursal del precio que se edita, AÑADIÉNDOLA si no
        estaba en la lista.

        Sin esto, editar un precio acotado a una sucursal fuera del alcance del
        usuario lo dejaría en "Todas las sucursales" sin avisar — y como el caso
        de uso hace upsert por (lista, producto, sucursal), guardar crearía un
        precio para TODAS en vez de modificar el de esa sucursal. No es una fuga:
        la sucursal ya viene del renglón que el usuario acaba de abrir.
        """
        if not branch_id:
            self._branch.set_current_id("")
            return
        if not self._branch.set_current_id(branch_id):
            self._branch.addItem(branch_id, branch_id)
            self._branch.set_current_id(branch_id)

    def _error(self) -> str | None:
        if self._list.current_id() is None:
            return "Selecciona una lista de precios editable."
        if not self._product.selected_id():
            return "Selecciona un producto del catálogo."
        if self._price.decimal_value() <= 0:
            return "El precio de venta debe ser mayor a cero."
        if self._scheduled.isChecked() and self._to.date_value() < self._from.date_value():
            return "La vigencia no puede terminar antes de empezar."
        return None

    def values(self) -> dict:
        minimo = self._min_price.decimal_value()
        datos = {
            "price_list_id": self._list.current_id(),
            "product_id": str(self._product.selected_id()),
            "branch_id": str(self._branch.current_id() or "") or None,
            "sale_price": str(self._price.decimal_value()),
            "min_price": str(minimo) if minimo > 0 else None,
        }
        if self._scheduled.isChecked():
            datos["effective_from"] = self._from.date_value().isoformat()
            datos["effective_to"] = self._to.date_value().isoformat()
        return datos


class DuplicatePriceListDialog(_PricingDialog):
    """Código y nombre de la copia.

    Tipo, canal y descuento se heredan del origen y no se piden: cambiarlos aquí
    haría que «duplicar» no duplicara. Para eso ya está «Nueva lista».
    """

    def __init__(self, parent=None, *, source_label: str = "") -> None:
        titulo = f"Duplicar {source_label}".strip() if source_label else "Duplicar lista"
        super().__init__(parent, title=titulo)
        self._code = StandardLineEdit(placeholder="Código de la copia (p. ej. BASE-2026)")
        self._name = StandardLineEdit(placeholder="Nombre de la copia")
        self._copy_prices = QCheckBox("Copiar también los precios de la lista")
        self._copy_prices.setChecked(True)
        self.form.addRow("Código *", self._code)
        self.form.addRow("Nombre *", self._name)
        self.form.addRow("", self._copy_prices)
        self._finish("Duplicar")

    def _error(self) -> str | None:
        if not self._code.value().strip():
            return "El código de la copia es obligatorio."
        if not self._name.value().strip():
            return "El nombre de la copia es obligatorio."
        return None

    def values(self) -> dict:
        return {"code": self._code.value().strip(),
                "name": self._name.value().strip(),
                "copy_prices": self._copy_prices.isChecked()}


class BulkPriceDialog(_PricingDialog):
    """Aplicar un precio a toda una categoría, opcionalmente en una sucursal.

    La categoría sale de un selector real (`ProductCategoryQueryService`), que
    guarda el UUID y muestra el nombre sangrado por nivel. Pedir aquí un
    identificador escrito a mano sería pedirle al usuario un dato que no puede
    conocer.
    """

    def __init__(self, parent=None, *, list_options, category_options,
                 branch_options=None) -> None:
        super().__init__(parent, title="Aplicar precio en lote")
        self._list = _combo(list_options)
        self._category = _combo(category_options)
        # Mismo criterio que arriba: este diálogo ya decía en su docstring que
        # pedir un identificador escrito a mano es pedir un dato que el usuario
        # no puede conocer. Lo decía de la categoría; la sucursal justo debajo
        # era exactamente eso.
        self._branch = _combo(list(branch_options or [("", "Todas las sucursales")]))
        self._price = MoneyInput()
        self.form.addRow("Lista *", self._list)
        self.form.addRow("Categoría *", self._category)
        self.form.addRow("Sucursal", self._branch)
        self.form.addRow("Precio de venta *", self._price)
        self._finish("Aplicar")

    def _error(self) -> str | None:
        if self._list.current_id() is None:
            return "Elige una lista de precios editable."
        if self._category.current_id() is None:
            return "Elige la categoría a la que se aplica el precio."
        if self._price.decimal_value() <= 0:
            return "El precio de venta debe ser mayor a cero."
        return None

    def values(self) -> dict:
        return {"price_list_id": self._list.current_id(),
                "category_id": self._category.current_id(),
                "branch_id": str(self._branch.current_id() or "") or None,
                "sale_price": str(self._price.decimal_value())}


class VolumeTierDialog(_PricingDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Escala por volumen")
        self._quantity = DecimalInput(precision=3, minimum="0")
        self._price = MoneyInput()
        self.form.addRow("Cantidad mínima *", self._quantity)
        self.form.addRow("Precio *", self._price)
        self._finish("Guardar")

    def _error(self) -> str | None:
        if (self._quantity.decimal_value() or 0) <= 0:
            return "La cantidad mínima debe ser mayor a cero."
        if self._price.decimal_value() <= 0:
            return "El precio debe ser mayor a cero."
        return None

    def values(self) -> dict:
        return {"min_quantity": str(self._quantity.decimal_value()),
                "price": str(self._price.decimal_value())}
