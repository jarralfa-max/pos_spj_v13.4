"""Compras (enterprise) — panel, compra directa, solicitudes, órdenes y facturas.

Módulo enterprise de Compras sobre el Design System. El POS solo detecta
necesidades; aquí Compras las ejecuta. Toda la lógica se delega a la capa de
aplicación (casos de uso + servicios de consulta); la UI no toca SQL.
"""

from __future__ import annotations

from frontend.desktop.modules.purchasing.enterprise_routes import (
    create_enterprise_purchasing_view,
)


class ModuloComprasEnterprise:
    def __new__(cls, container, parent=None):
        return create_enterprise_purchasing_view(container, parent)
