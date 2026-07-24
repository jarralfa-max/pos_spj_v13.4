"""ProductsPresenter — bridge between the enterprise products UI and backend.

Wires the read/query services into display-ready view models and
``(ok, message, data)`` tuples. Never touches SQL/connections directly — it calls
a ``read_service_factory`` (an application query service) and the injected backend
services. Presentation-only pages depend on this, so all orchestration/formatting
stays out of Qt.
"""

from __future__ import annotations

import logging

from frontend.desktop.modules.products.view_models import (
    KpiViewModel,
    TableViewModel,
    alerts_table,
    catalog_table,
)

logger = logging.getLogger("spj.products.presenter")


class ProductsPresenter:
    def __init__(self, *, read_service_factory, session_context=None) -> None:
        self._read_factory = read_service_factory
        self._session = session_context

    # ── overview (§43) ────────────────────────────────────────────────────
    def overview_kpis(self) -> list[KpiViewModel]:
        try:
            counts = self._read_factory().overview_counts()
        except Exception:  # pragma: no cover - defensive; UI shows empty state
            logger.exception("No se pudieron obtener KPIs de productos")
            return []
        return [
            KpiViewModel("active", "Productos activos", str(counts["active"]), "success"),
            KpiViewModel("meat", "Productos cárnicos", str(counts["meat"]), "info"),
            KpiViewModel("internal", "Productos internos", str(counts["internal"]), "neutral"),
            KpiViewModel("incomplete", "Incompletos", str(counts["incomplete"]),
                         "danger" if counts["incomplete"] else "success"),
            KpiViewModel("recipes_unapproved", "Recetas sin aprobar",
                         str(counts["recipes_unapproved"]),
                         "warning" if counts["recipes_unapproved"] else "success"),
            KpiViewModel("yield_pending", "Rendimientos pendientes",
                         str(counts["yield_pending"]),
                         "warning" if counts["yield_pending"] else "success"),
        ]

    # ── catálogo (§43) ────────────────────────────────────────────────────
    def catalog(self, *, query: str | None = None, product_type: str | None = None
                ) -> TableViewModel:
        rows = self._read_factory().list_catalog(query=query, product_type=product_type)
        return catalog_table(rows)

    # ── alertas (§35) ─────────────────────────────────────────────────────
    def recent_alerts(self) -> TableViewModel:
        return alerts_table(self._read_factory().list_recent_alerts())
