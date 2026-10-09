"""Doble del presentador de Clientes y CRM para pruebas de UI (CRM-43).

Cumple el contrato que usan las páginas: ``can``, ``capabilities``, ``read``,
``has_reader``, ``run``, ``users``, ``user_name``, ``customer_names``,
``customer_search_options``, ``branch_id``, ``current_user_id``. Las lecturas
se configuran con ``readers={"leads": lambda **kw: [...]}`` y cada ``run``
queda registrado en ``commands`` y responde con ``results`` (por comando) o
con éxito.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FakeResult:
    success: bool = True
    message: str = "Listo"
    entity_id: str | None = "id-1"
    error_code: str | None = None
    data: dict = field(default_factory=dict)


class CrmFakePresenter:
    def __init__(self, capabilities=None, *, permissions=None, readers=None, results=None,
                 users=(("u1", "Ana"), ("u2", "Beto"))) -> None:
        from frontend.desktop.modules.customers_crm.view_models import CustomerCrmCapabilities
        self._capabilities = capabilities or CustomerCrmCapabilities(
            module_view=True, clientes=True, prospectos=True, oportunidades=True,
            actividades=True, atencion=True, comercial=True, credito=True, segmentacion=True,
            comunicaciones=True, privacidad=True, control=True)
        #: ``None`` = todo permitido; un conjunto = sólo esos códigos.
        self._permissions = permissions
        self._readers = dict(readers or {})
        self._results = dict(results or {})
        self._users = list(users)
        self.commands: list[tuple[str, dict]] = []

    # contrato -------------------------------------------------------------------
    def can(self, code: str) -> bool:
        return self._permissions is None or code in self._permissions

    def capabilities(self):
        return self._capabilities

    def has_reader(self, name: str) -> bool:
        return name in self._readers

    def read(self, name: str, /, **kwargs):
        if name not in self._readers:
            raise RuntimeError(f"lectura no configurada: {name}")
        return self._readers[name](**kwargs)

    def run(self, command: str, /, **kwargs):
        self.commands.append((command, kwargs))
        return self._results.get(command, FakeResult())

    def users(self):
        return list(self._users)

    def user_name(self, user_id):
        return dict(self._users).get(user_id, "Sin asignar" if not user_id else "Otro usuario")

    def customer_names(self, ids):
        return {i: f"Cliente {i}" for i in ids if i}

    def customer_search_options(self, _query):
        return []

    def branch_id(self):
        return "b1"

    def current_user_id(self):
        return "u1"

    # lo que usan las páginas de la primera generación ------------------------------
    def dashboard(self):
        from backend.application.crm.queries.customer_dashboard_query_service import (
            CustomerDashboardView,
        )
        return CustomerDashboardView()

    def address_search_service(self):
        return None

    def can_add_address(self) -> bool:
        return self.can("CLIENTES.direccion.crear")
