"""NewOrderDialog — alta rápida de "Todos los pedidos" (SDLC-ORD-005).

El responsable decidió conservarla, con el mismo flujo: envuelve la página
"Nuevo pedido" en lugar de tener su propia captura. Antes pedía el UUID del
producto y un precio libre que terminaba cobrándose, sin pasar por Pricing ni
por la autorización de precio mínimo.
"""

from __future__ import annotations

from frontend.desktop.components.dialogs import StandardDialog
from frontend.desktop.themes.tokens import DialogMetrics
from frontend.desktop.modules.orders_delivery.pages.new_order_page import NewOrderPage


class NewOrderDialog(StandardDialog):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent, title="Nuevo pedido", width=DialogMetrics.WIDTH_LG)
        self.message = ""
        self.capture = NewOrderPage(
            presenter, title="Datos del pedido",
            subtitle="Busca el producto: el precio lo fija Pricing.", parent=self)
        self.capture.order_created.connect(self._on_created)
        self._root.addWidget(self.capture)

    def _on_created(self, message: str) -> None:
        self.message = message
        self.accept()
