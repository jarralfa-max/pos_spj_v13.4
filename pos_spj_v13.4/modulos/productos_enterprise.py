"""ModuloProductosEnterprise — PROD-19 FLIP: reemplazo de la UI legacy de Productos
(modulos/productos.py) por el módulo enterprise PRC-7 (frontend/desktop/modules/
products).

SHELL-16: la lógica de composición (wiring de use cases/query services, y la
clase `_Session` de identidad viva) que antes vivía en este archivo fue
extraída a `frontend/desktop/modules/products/composition.py` — este
archivo ahora solo desempaqueta el contenedor legacy y delega, igual que
`modulos/ventas_pos.py`/`modulos/clientes_crm.py` para sus propios
módulos. Comportamiento sin cambios (ver
`tests/integration/products/test_products_enterprise_host.py`, escrito
contra la ubicación anterior y sigue pasando sin modificar).

NOTA (decisión del usuario, corte "borrar ya"): las páginas de alta/edición de
producto aún no están migradas; este host es de sólo lectura. El alta/edición se
reincorporará cuando se construyan los formularios enterprise (los use cases
canónicos CreateProductUseCase/UpdateProductUseCase ya existen).
"""

from __future__ import annotations

import logging

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.modules.products.composition import _Session, build_products_presenter, build_products_view

logger = logging.getLogger("spj.ui.productos_enterprise")


class ModuloProductosEnterprise(QWidget):
    """Contenedor PyQt5 del módulo Productos enterprise (PRC-7) para el shell del POS."""

    def __init__(self, container, parent=None):
        super().__init__(parent)
        conn = getattr(container, "db", container)
        # Sesión viva (con tiene_permiso) para el gating granular; None en tests.
        live_session = (getattr(container, "session", None)
                        or getattr(container, "sesion", None))
        self._live_session = live_session
        # §21.2 fail-closed: NO se inventa identidad (nada de "desktop"/"1"). `_Session`
        # lee EN VIVO de `self._live_session` (ver su propio docstring) — nunca una
        # foto fija. `container.usuario`/`usuario_actual` NUNCA existieron en
        # AppContainer (siempre None) — la identidad real vive en
        # `SessionContext.user_id`.
        _branch = (getattr(container, "sucursal_id", None)
                   or getattr(container, "branch_id", None))
        branch_fallback = str(_branch) if _branch else None
        session = _Session(live_session, branch_fallback)
        self._session = session  # expuesto para pruebas de identidad (§21.2)

        presenter = build_products_presenter(conn, session, live_session=live_session)
        self._view = build_products_view(presenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)
