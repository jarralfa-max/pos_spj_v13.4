"""Wrapper legacy: módulo CLIENTES_CRM.

La implementación vive en ``frontend/desktop/modules/customers_crm``
(bounded context Customer Master/CRM). A diferencia de
``modulos/finanzas.py`` (que delega el desempaquetado del contenedor a
``finance_routes.create_finance_view``), aquí el desempaquetado ocurre EN
ESTE archivo: ``frontend/desktop/modules/customers_crm/composition.py``
tiene prohibido, por guardrail CRM-1, recibir o referenciar el contenedor
de la app de cualquier forma — solo acepta una conexión y un contexto de
sesión ya extraídos.

Este es un módulo NUEVO, adicional al legacy ``modulos/clientes.py``
(``_conectar("CLIENTES", ...)``) — no lo reemplaza todavía. Ver
docs/refactor/ para el plan de retiro completo del módulo legacy.
"""
from __future__ import annotations

from frontend.desktop.modules.customers_crm.composition import create_customers_crm_view


class ModuloClientesCrm:
    """Factory-compatible: ``ModuloClientesCrm(container)`` devuelve la vista nueva."""

    def __new__(cls, container, parent=None):
        connection = getattr(container, "db", None) or getattr(container, "db_conn", None)
        # AppContainer's real attribute is `.session` (core/app_container.py,
        # `self.session = SessionContext()`) — NOT `.session_context`, which
        # doesn't exist on it (confirmed by direct inspection; finance's own
        # `create_finance_view` references `.session_context` too, which
        # means it silently gets None in production — a pre-existing gap in
        # finance's own composition root, not copied here on purpose).
        session_context = getattr(container, "session", None)
        return create_customers_crm_view(connection, session_context, parent)
