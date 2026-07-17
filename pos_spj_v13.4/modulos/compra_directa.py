"""Compra directa — entrada a la página de compra directa dentro de Compras.

La compra directa es una operación de Compras (NO del POS): el POS solo detecta
necesidades. Este wrapper abre la página enterprise de compra directa, construida
sobre el Design System, delegando toda la lógica a la capa de aplicación.
"""

from __future__ import annotations

from frontend.desktop.modules.purchasing.direct_purchase_routes import (
    create_direct_purchase_view,
)


class ModuloCompraDirecta:
    def __new__(cls, container, parent=None):
        return create_direct_purchase_view(container, parent)
