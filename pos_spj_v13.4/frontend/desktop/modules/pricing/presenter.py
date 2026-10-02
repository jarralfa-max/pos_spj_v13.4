"""PricingPresenter — bridge between the enterprise pricing UI and backend.

Wires the read/query service into display-ready view models. Never touches SQL/
connections directly — it calls a ``read_service_factory`` (the application
``PricingReadService``). Presentation-only pages depend on this, so all
orchestration/formatting stays out of Qt.
"""

from __future__ import annotations

import logging

from backend.application.products.queries.product_selection_query_service import (
    ProductSearchQuery,
)
from backend.shared.ids import new_uuid
from frontend.desktop.modules.pricing.view_models import (
    KpiViewModel,
    TableViewModel,
    costs_table,
    history_table,
    price_lists_table,
    product_prices_table,
    settings_table,
)

logger = logging.getLogger("spj.pricing.presenter")


class PricingPresenter:
    def __init__(self, *, read_service_factory, connection_provider=None,
                 use_cases=None, product_search_factory=None,
                 category_query_factory=None, session_context=None) -> None:
        self._read_factory = read_service_factory
        self._conn = connection_provider
        #: Casos de uso de escritura. Opcionales para que las pruebas que sólo
        #: ejercitan lectura sigan construyendo el presentador con un servicio
        #: falso; la composición viva siempre los inyecta.
        self._use_cases = dict(use_cases or {})
        self._product_search = product_search_factory
        self._category_query = category_query_factory
        self._session = session_context

    # ── identidad y ejecución ─────────────────────────────────────────────
    def _actor(self) -> str:
        """Identidad REAL del usuario. Nunca se inventa una.

        Importa más de lo normal aquí: `ensure_segregation` compara al aprobador
        contra el creador de la lista, así que un actor ficticio compartido
        volvería esa protección inútil — exactamente lo que pasaba en
        Proveedores con el literal "desktop".
        """
        user_id = str(getattr(self._session, "user_id", "") or "").strip()
        if not user_id:
            raise PermissionError("Se requiere una sesión autenticada de Precios")
        return user_id

    def can(self, permission_code: str) -> bool:
        """Para habilitar botones. Ocultar no es seguridad —el caso de uso
        revalida— pero ofrecer una acción que va a denegarse es peor."""
        check = getattr(self._session, "tiene_permiso", None)
        return bool(callable(check) and check(permission_code))

    def _run(self, key: str, **kwargs) -> tuple[bool, str, dict]:
        use_case = self._use_cases.get(key)
        if use_case is None or self._conn is None:
            return False, "Acción no disponible en esta pantalla.", {}
        try:
            result = use_case.execute(self._conn(), actor_user_id=self._actor(),
                                      operation_id=new_uuid(), **kwargs)
            return bool(result.success), result.message, dict(result.data)
        except PermissionError as exc:
            return False, str(exc), {}
        except Exception:
            logger.exception("PricingPresenter: error inesperado en %s", key)
            return False, "Error inesperado; revise el log.", {}

    # ── búsqueda de productos (contrato compartido) ───────────────────────
    def product_options(self, query: str):
        """Precios sólo restringe a ACTIVE, que es lo que definiste para este
        módulo; el resto del criterio lo pone el contrato compartido."""
        from frontend.desktop.components.search_selector import SearchOption
        if self._product_search is None:
            return []
        try:
            dtos = self._product_search().search(
                ProductSearchQuery(text=(query or "").strip() or None))
        except Exception:
            logger.exception("No se pudieron buscar productos")
            return []
        return [SearchOption(id=d.product_id, label=d.name, subtitle=d.code or "")
                for d in dtos]

    def product_search_reason(self, query: str):
        if self._product_search is None:
            return None
        try:
            razon = self._product_search().explain_empty(
                ProductSearchQuery(text=(query or "").strip() or None))
        except Exception:
            return None
        return razon.message if razon is not None else None

    # ── acciones: listas de precio ────────────────────────────────────────
    def create_price_list(self, **fields) -> tuple[bool, str, dict]:
        return self._run("create_list", **fields)

    def submit_price_list(self, price_list_id: str) -> tuple[bool, str, dict]:
        return self._run("submit_list", price_list_id=price_list_id)

    def approve_price_list(self, price_list_id: str) -> tuple[bool, str, dict]:
        return self._run("approve_list", price_list_id=price_list_id)

    def activate_price_list(self, price_list_id: str) -> tuple[bool, str, dict]:
        return self._run("activate_list", price_list_id=price_list_id)

    def deactivate_price_list(self, price_list_id: str) -> tuple[bool, str, dict]:
        return self._run("deactivate_list", price_list_id=price_list_id)

    def duplicate_price_list(self, **fields) -> tuple[bool, str, dict]:
        return self._run("duplicate_list", **fields)

    # ── acciones: precios ─────────────────────────────────────────────────
    def set_product_price(self, **fields) -> tuple[bool, str, dict]:
        return self._run("set_price", **fields)

    def set_volume_price(self, **fields) -> tuple[bool, str, dict]:
        return self._run("set_volume", **fields)

    def apply_price_in_bulk(self, **fields) -> tuple[bool, str, dict]:
        return self._run("apply_bulk", **fields)

    def price_details(self, price_id: str) -> dict | None:
        """Una fila de precio para precargar el diálogo de edición."""
        try:
            return self._read_factory().get_product_price(price_id)
        except Exception:
            logger.exception("No se pudo cargar el precio %s", price_id)
            return None

    def category_options(self) -> list[tuple[str, str]]:
        """Categorías activas, sangradas por nivel, guardando el UUID."""
        if self._category_query is None:
            return []
        try:
            return [(o["id"], o["label"])
                    for o in self._category_query().flat_options()]
        except Exception:
            logger.exception("No se pudieron listar las categorías de producto")
            return []

    def price_list_options(self) -> list[tuple[str, str]]:
        """Listas EDITABLES para el diálogo de precios: una lista aprobada o
        activa es inmutable, así que ofrecerla sería ofrecer un error."""
        try:
            filas = self._read_factory().list_price_lists()
        except Exception:  # pragma: no cover - defensivo
            logger.exception("No se pudieron listar las listas de precio")
            return []
        return [(f["id"], f'{f["code"]} · {f["name"]}') for f in filas
                if str(f.get("status") or "") in ("DRAFT", "UNDER_REVIEW")]

    def overview_kpis(self) -> list[KpiViewModel]:
        try:
            c = self._read_factory().overview_counts()
        except Exception:  # pragma: no cover - defensive; UI shows empty state
            logger.exception("No se pudieron obtener KPIs de precios")
            return []
        return [
            KpiViewModel("lists_active", "Listas activas", str(c["lists_active"]), "success"),
            KpiViewModel("lists_pending", "Listas por aprobar", str(c["lists_pending"]),
                         "warning" if c["lists_pending"] else "neutral"),
            KpiViewModel("priced", "Productos con precio", str(c["priced"]), "info"),
            KpiViewModel("costed", "Productos con costo", str(c["costed"]), "info"),
            KpiViewModel("volume_tiers", "Escalas por volumen", str(c["volume_tiers"]),
                         "neutral"),
            KpiViewModel("below_min", "Precios bajo mínimo", str(c["below_min"]),
                         "danger" if c["below_min"] else "success"),
        ]

    def price_lists(self, *, kind: str | None = None) -> TableViewModel:
        return price_lists_table(self._read_factory().list_price_lists(kind=kind))

    def product_prices(self, *, query: str | None = None, list_id: str | None = None
                       ) -> TableViewModel:
        return product_prices_table(
            self._read_factory().list_product_prices(query=query, list_id=list_id))

    def costs(self) -> TableViewModel:
        return costs_table(self._read_factory().list_costs())

    def price_history(self, *, product_id: str | None = None) -> TableViewModel:
        return history_table(self._read_factory().list_price_history(product_id=product_id))

    def branch_options(self) -> list[tuple[str, str]]:
        """Sucursales que este usuario PUEDE ver, con "Todas" al frente.

        Los diálogos de precio pedían la sucursal en una CAJA DE TEXTO LIBRE
        ("Sucursal (vacío = todas)"), es decir, el UUID escrito a mano. El
        propio diálogo de lote dice en su docstring que pedir un identificador
        a mano es pedir un dato que el usuario no puede conocer — lo decía de la
        categoría, mientras la sucursal justo debajo era exactamente eso.

        La opción vacía se conserva porque aquí SIGNIFICA algo: un precio sin
        sucursal rige en todas. Va explícita en la lista en vez de depender de
        que el usuario deje el campo en blanco.

        Acotado al alcance del usuario, mismo orden que en Transferencias y
        Compras: `usuario -> permitidas -> consulta -> resultados`.
        """
        from backend.application.security.branch_scope_query_service import (
            BranchScopeQueryService, BranchSearchQuery,
        )
        todas = [("", "Todas las sucursales")]
        if self._conn is None:
            return todas
        actor = str(getattr(self._session, "user_id", "") or "").strip()
        if not actor:
            return todas
        try:
            encontradas = BranchScopeQueryService(self._conn()).search(
                BranchSearchQuery(allowed_for_user=actor, page_size=200))
        except Exception:
            logger.exception("PricingPresenter.branch_options failed")
            return todas
        return todas + [(o.branch_id, o.name) for o in encontradas]

    # ── política de costo (§32) ───────────────────────────────────────────
    def cost_policy_options(self) -> list[tuple[str, str]]:
        from backend.application.pricing.cost_policy import COST_POLICY_LABELS
        return [(policy.value, label) for policy, label in COST_POLICY_LABELS.items()]

    def current_cost_policy(self) -> str:
        from backend.application.pricing.cost_policy import CostPolicy, CostPolicySettings
        if self._conn is None:
            return CostPolicy.GLOBAL.value
        try:
            return CostPolicySettings(self._conn()).current().value
        except Exception:  # pragma: no cover - defensivo
            logger.exception("No se pudo leer la política de costo")
            return CostPolicy.GLOBAL.value

    @property
    def can_manage_cost_policy(self) -> bool:
        from backend.application.pricing.permissions import PricingPermissions
        return "set_cost_policy" in self._use_cases and self.can(
            PricingPermissions.SETTINGS_MANAGE)

    def set_cost_policy(self, policy: str) -> tuple[bool, str, dict]:
        return self._run("set_cost_policy", policy=policy)

    def settings(self) -> TableViewModel:
        """Parámetros efectivos del módulo, como `Parámetro · Valor · Nota`.

        La columna de nota no es decorativa: es donde se dice que algo está mal
        configurado. Un valor solo —"Moneda: MXN, USD"— no le comunica a nadie
        que dos monedas conviviendo hacen que los totales no cuadren.
        """
        try:
            s = self._read_factory().settings_summary()
        except Exception:  # pragma: no cover - defensivo; la página cae a vacío
            logger.exception("No se pudo leer la configuración de precios")
            return TableViewModel()
        return settings_table(s)
