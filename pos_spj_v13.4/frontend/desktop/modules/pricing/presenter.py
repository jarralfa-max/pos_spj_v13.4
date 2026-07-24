"""PricingPresenter — bridge between the enterprise pricing UI and backend.

Wires the read/query service into display-ready view models. Never touches SQL/
connections directly — it calls a ``read_service_factory`` (the application
``PricingReadService``). Presentation-only pages depend on this, so all
orchestration/formatting stays out of Qt.
"""

from __future__ import annotations

import logging

from frontend.desktop.modules.pricing.view_models import (
    KpiViewModel,
    TableViewModel,
    costs_table,
    history_table,
    price_lists_table,
    product_prices_table,
)

logger = logging.getLogger("spj.pricing.presenter")


class PricingPresenter:
    def __init__(self, *, read_service_factory, session_context=None) -> None:
        self._read_factory = read_service_factory
        self._session = session_context

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
