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
            AdjustmentQueryService,
            AlertQueryService,
            AuditQueryService,
            ColdChainQueryService,
            CountQueryService,
            ExpiryQueryService,
            InventoryAvailabilityQueryService,
            LotQueryService,
            MovementQueryService,
            QuarantineQueryService,
            ReceiptQueryService,
            ReplenishmentQueryService,
            ReservationQueryService,
            SettingsQueryService,
            StockQueryService,
            TraceabilityQueryService,
            TransferQueryService,
            WarehouseQueryService,
            WeightQueryService,
        )
        from backend.application.inventory.use_cases import (
            ApproveAdjustmentUseCase,
            ApproveCountUseCase,
            ConfirmCountUseCase,
            CreateAdjustmentFromCountUseCase,
            CreateAdjustmentUseCase,
            CreateCountUseCase,
            CreateLocationUseCase,
            CreateWarehouseUseCase,
            DisposeQuarantineUseCase,
            GenerateReplenishmentSuggestionsUseCase,
            PostAdjustmentUseCase,
            QuarantineStockUseCase,
            RecordCountUseCase,
            ReleaseQuarantineUseCase,
            ReverseAdjustmentUseCase,
            SetLocationStatusUseCase,
            SetWarehouseStatusUseCase,
        )
        from backend.application.queries.product_query_service import (
            ProductQueryService,
        )
        from frontend.desktop.modules.inventory.presenter import InventoryPresenter

        # §5.2 composition root: con sesión viva, los casos de uso sensibles se
        # construyen desde InventoryUseCaseFactory con el checker RBAC real (no el
        # default permisivo). Sin sesión viva (pruebas), caen al default explícito.
        if session is not None:
            from backend.application.inventory.composition import (
                InventoryUseCaseFactory,
            )
            factory = InventoryUseCaseFactory.from_session(session)
            generate_uc = factory.generate_replenishment_suggestions()
            release_quarantine_uc = factory.release_quarantine()
            dispose_quarantine_uc = factory.dispose_quarantine()
            open_quarantine_uc = factory.quarantine_stock()
            create_adjustment_uc = factory.create_adjustment()
            approve_adjustment_uc = factory.approve_adjustment()
            post_adjustment_uc = factory.post_adjustment()
            reverse_adjustment_uc = factory.reverse_adjustment()
            create_count_uc = factory.create_count()
            record_count_uc = factory.record_count()
            confirm_count_uc = factory.confirm_count()
            approve_count_uc = factory.approve_count()
            create_adjustment_from_count_uc = factory.create_adjustment_from_count()
            create_warehouse_uc = factory.create_warehouse()
            set_warehouse_status_uc = factory.set_warehouse_status()
            create_location_uc = factory.create_location()
            set_location_status_uc = factory.set_location_status()
        else:
            generate_uc = GenerateReplenishmentSuggestionsUseCase()
            release_quarantine_uc = ReleaseQuarantineUseCase()
            dispose_quarantine_uc = DisposeQuarantineUseCase()
            open_quarantine_uc = QuarantineStockUseCase()
            create_adjustment_uc = CreateAdjustmentUseCase()
            approve_adjustment_uc = ApproveAdjustmentUseCase()
            post_adjustment_uc = PostAdjustmentUseCase()
            reverse_adjustment_uc = ReverseAdjustmentUseCase()
            create_count_uc = CreateCountUseCase()
            record_count_uc = RecordCountUseCase()
            confirm_count_uc = ConfirmCountUseCase()
            approve_count_uc = ApproveCountUseCase()
            create_adjustment_from_count_uc = CreateAdjustmentFromCountUseCase()
            create_warehouse_uc = CreateWarehouseUseCase()
            set_warehouse_status_uc = SetWarehouseStatusUseCase()
            create_location_uc = CreateLocationUseCase()
            set_location_status_uc = SetLocationStatusUseCase()

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
            audit_query_factory=AuditQueryService,
            transfer_query_factory=TransferQueryService,
            weight_query_factory=WeightQueryService,
            receipt_query_factory=ReceiptQueryService,
            count_query_factory=CountQueryService,
            adjustment_query_factory=AdjustmentQueryService,
            alert_query_factory=AlertQueryService,
            settings_query_factory=SettingsQueryService,
            release_quarantine_uc=release_quarantine_uc,
            dispose_quarantine_uc=dispose_quarantine_uc,
            open_quarantine_uc=open_quarantine_uc,
            product_query_factory=ProductQueryService.from_connection,
            create_adjustment_uc=create_adjustment_uc,
            approve_adjustment_uc=approve_adjustment_uc,
            post_adjustment_uc=post_adjustment_uc,
            reverse_adjustment_uc=reverse_adjustment_uc,
            create_count_uc=create_count_uc,
            record_count_uc=record_count_uc,
            confirm_count_uc=confirm_count_uc,
            approve_count_uc=approve_count_uc,
            create_adjustment_from_count_uc=create_adjustment_from_count_uc,
            create_warehouse_uc=create_warehouse_uc,
            set_warehouse_status_uc=set_warehouse_status_uc,
            create_location_uc=create_location_uc,
            set_location_status_uc=set_location_status_uc,
            session_context=session,
        )
