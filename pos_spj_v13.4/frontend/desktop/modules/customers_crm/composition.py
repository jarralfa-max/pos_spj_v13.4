"""Punto de entrada de la vista de Clientes y CRM.

CRM-43: la raíz de composición (casos de uso, lectores, políticas de la
sesión) vive en ``backend/infrastructure/desktop/customers_crm_factory.py``,
como la de Caja. Esta capa de UI sólo recibe valores explícitos
(``connection``, ``session_context``) — nunca el contenedor completo de la
aplicación (guarda CRM-1) — y arma el workspace.
"""

from __future__ import annotations

from backend.infrastructure.desktop.customers_crm_factory import (
    build_customers_crm_presenter,
)

__all__ = ["build_customers_crm_presenter", "create_customers_crm_view"]


def create_customers_crm_view(connection, session_context=None, parent=None):
    from frontend.desktop.modules.customers_crm.customers_crm_workspace import (
        CustomersCrmWorkspace,
    )

    presenter = build_customers_crm_presenter(connection, session_context)
    return CustomersCrmWorkspace(presenter, parent)
