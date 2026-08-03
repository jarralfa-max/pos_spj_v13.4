"""ModuloInventarioEnterprise — INV-27 corte: reemplazo de la UI legacy de
inventario (modulos/inventario_local.py) por el módulo enterprise INV-25.

Monta el shell ``InventoryView`` (navegación lateral con las 21 secciones
canónicas del Design System, §54) sobre el ``InventoryPresenter``, cableado a los
query services canónicos (ledger). Sin SQL ni lógica de negocio en la UI. Las
páginas se construyen de forma perezosa al navegar (arranque liviano).
"""

from __future__ import annotations

import logging

from PyQt5.QtWidgets import QVBoxLayout, QWidget

logger = logging.getLogger("spj.ui.inventario_enterprise")


class _Session:
    def __init__(self, user_id, branch_id, warehouse_id):
        self.user_id = user_id
        self.branch_id = branch_id
        self.warehouse_id = warehouse_id


class ModuloInventarioEnterprise(QWidget):
    """Contenedor PyQt5 del inventario enterprise (INV-25) para el shell del POS."""

    def __init__(self, container, parent=None):
        super().__init__(parent)
        conn = getattr(container, "db", container)
        # §5.4/§21.2 fail-closed: NO se inventa identidad ("desktop"/"1"). Sin sesión
        # autenticada el user/branch quedan en None y las mutaciones se niegan aguas
        # abajo (la política real exige usuario y checker).
        user_id = (getattr(container, "usuario", None)
                   or getattr(container, "usuario_actual", None))
        _branch = (getattr(container, "sucursal_id", None)
                   or getattr(container, "branch_id", None))
        branch_id = str(_branch) if _branch else None
        session = _Session(user_id, branch_id, branch_id)
        self._session = session  # expuesto para pruebas de identidad
        # Sesión viva (con tiene_permiso) para el checker granular real; None en tests.
        self._live_session = (getattr(container, "session", None)
                              or getattr(container, "sesion", None))

        presenter = self._build_presenter(conn, session)
        self._presenter = presenter

        from frontend.desktop.modules.inventory.inventory_view import InventoryView
        from frontend.desktop.modules.inventory.page_registry import build_page_specs

        self._view = InventoryView(presenter, build_page_specs())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

    # ── construcción ─────────────────────────────────────────────────────────
    def _build_presenter(self, conn, session):
        from backend.application.inventory.analytics import InventoryAnalyticsService
        from backend.application.inventory.queries import (
            ColdChainQueryService,
            ExpiryQueryService,
            InventoryAvailabilityQueryService,
            LotQueryService,
            MovementQueryService,
            QuarantineQueryService,
            ReplenishmentQueryService,
            ReservationQueryService,
            StockQueryService,
            TraceabilityQueryService,
            WarehouseQueryService,
        )
        from backend.application.inventory.use_cases import (
            GenerateReplenishmentSuggestionsUseCase,
        )
        from frontend.desktop.modules.inventory.presenter import InventoryPresenter

        # §5.2 composition root: con sesión viva, el caso de uso sensible se
        # construye desde InventoryUseCaseFactory con el checker RBAC real (no el
        # default permisivo). Sin sesión viva (pruebas), cae al default explícito.
        if self._live_session is not None:
            from backend.application.inventory.composition import (
                InventoryUseCaseFactory,
            )
            factory = InventoryUseCaseFactory.from_session(self._live_session)
            generate_uc = factory.generate_replenishment_suggestions()
        else:
            generate_uc = GenerateReplenishmentSuggestionsUseCase()

        return InventoryPresenter(
            connection_provider=lambda: conn,
            availability_service_factory=InventoryAvailabilityQueryService,
            replenishment_query_factory=ReplenishmentQueryService,
            generate_suggestions_uc=generate_uc,
            warehouse_query_factory=WarehouseQueryService,
            analytics_factory=InventoryAnalyticsService,
            lot_query_factory=LotQueryService,
            movement_query_factory=MovementQueryService,
            expiry_query_factory=ExpiryQueryService,
            traceability_query_factory=TraceabilityQueryService,
            stock_query_factory=StockQueryService,
            quarantine_query_factory=QuarantineQueryService,
            reservation_query_factory=ReservationQueryService,
            cold_chain_query_factory=ColdChainQueryService,
            session_context=session,
        )
