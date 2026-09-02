"""ModuloInventarioEnterprise — INV-27 corte: reemplazo de la UI legacy de
inventario (modulos/inventario_local.py) por el módulo enterprise INV-25.

SHELL-16: la lógica de composición (wiring de use cases/query services)
que antes vivía en este archivo fue extraída a
``frontend/desktop/modules/inventory/composition.py`` — este archivo ahora
solo desempaqueta el contenedor legacy y delega, igual que
``modulos/ventas_pos.py``/``modulos/clientes_crm.py`` para sus propios
módulos. Comportamiento sin cambios (ver
``tests/integration/inventory/test_inventory_enterprise_session_wiring.py``,
escrito contra la ubicación anterior y sigue pasando sin modificar).
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.modules.inventory.composition import build_inventory_presenter
from frontend.desktop.modules.inventory.inventory_view import InventoryView
from frontend.desktop.modules.inventory.page_registry import build_page_specs


class ModuloInventarioEnterprise(QWidget):
    """Contenedor PyQt5 del inventario enterprise (INV-25) para el shell del POS."""

    def __init__(self, container, parent=None):
        super().__init__(parent)
        conn = getattr(container, "db", container)
        # §5.4/§21.2 fail-closed: se usa la sesión VIVA del sistema (SessionContext),
        # NUNCA una copia congelada ni identidad fabricada ("desktop"/"1", ni
        # warehouse_id = branch_id). Antes de completar el login (o en arneses de
        # prueba mínimos sin `.session`), queda en None: las lecturas devuelven vacío
        # y las mutaciones se niegan aguas abajo (la política real exige usuario y
        # checker). Al ser la misma instancia que ve el resto del sistema, el login
        # posterior la actualiza in-place — no hace falta reconstruir el módulo.
        session = (getattr(container, "session", None)
                   or getattr(container, "sesion", None))
        self._session = session  # expuesta para pruebas/diagnóstico

        presenter = build_inventory_presenter(conn, session)
        self._presenter = presenter

        # §16 navegación permission-aware: con sesión viva, sólo se listan las
        # secciones cuyo permiso granular la sesión tiene (ocultar es UX, el
        # backend revalida cada acción igualmente). Sin sesión (arneses de
        # prueba/diagnóstico) se listan todas, como antes.
        has_permission = getattr(session, "tiene_permiso", None) if session else None
        self._view = InventoryView(presenter, build_page_specs(has_permission))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)
