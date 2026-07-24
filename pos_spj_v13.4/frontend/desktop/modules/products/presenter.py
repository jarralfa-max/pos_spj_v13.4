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
    def __init__(self, *, read_service_factory, write_service_factory=None,
                 session_context=None) -> None:
        self._read_factory = read_service_factory
        self._write_factory = write_service_factory
        self._session = session_context

    # ── alta / edición del maestro (PROD-19 7b) ───────────────────────────
    @property
    def can_write(self) -> bool:
        return self._write_factory is not None

    def get_product(self, product_id: str) -> dict | None:
        """Fila del maestro para prellenar el formulario de edición."""
        if not self.can_write:
            return None
        create_uc, update_uc, repo = self._write_factory()
        return repo.get(product_id)

    def save_product(self, *, product_id: str | None, fields: dict) -> tuple[bool, str, str | None]:
        """Alta (product_id None) o edición. Devuelve (ok, mensaje, product_id)."""
        if not self.can_write:
            return False, "Sin permisos de escritura", None
        from backend.application.products.commands.product_master_commands import (
            CreateProductMasterCommand,
            UpdateProductMasterCommand,
        )
        from backend.shared.ids import new_uuid

        user_id = getattr(self._session, "user_id", None)
        create_uc, update_uc, _repo = self._write_factory()
        try:
            if product_id:
                cmd = UpdateProductMasterCommand(
                    operation_id=new_uuid(), user_id=user_id, product_id=product_id, **fields)
                result = update_uc.execute(cmd)
            else:
                cmd = CreateProductMasterCommand(
                    operation_id=new_uuid(), user_id=user_id, **fields)
                result = create_uc.execute(cmd)
        except Exception as exc:  # noqa: BLE001 — el error se muestra en la UI
            logger.exception("Guardado de producto falló")
            return False, f"Error: {exc}", None
        return result.success, result.message, result.product_id

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
