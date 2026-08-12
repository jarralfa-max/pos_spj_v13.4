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

        # §16 navegación permission-aware: con sesión viva, sólo se listan las
        # secciones cuyo permiso granular la sesión tiene (ocultar es UX, el
        # backend revalida cada acción igualmente). Sin sesión (arneses de
        # prueba/diagnóstico) se listan todas, como antes.
        has_permission = getattr(session, "tiene_permiso", None) if session else None
        self._view = InventoryView(presenter, build_page_specs(has_permission))

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
            AllocateReservationUseCase,
            ApproveAdjustmentUseCase,
            ApproveCountUseCase,
            ConfirmCountUseCase,
            CreateAdjustmentFromCountUseCase,
            CreateAdjustmentUseCase,
            CreateCountUseCase,
            CreateLocationUseCase,
            CreateReservationUseCase,
            CreateWarehouseUseCase,
            CreateZoneUseCase,
            DeactivateLocationUseCase,
            DeactivateWarehouseUseCase,
            DisposeQuarantineUseCase,
            ExpireInventoryUseCase,
            GenerateExpiryAlertsUseCase,
            GenerateReplenishmentSuggestionsUseCase,
            InspectReceiptUseCase,
            PostAdjustmentUseCase,
            QuarantineStockUseCase,
            RecordCatchWeightUseCase,
            RecordCountUseCase,
            RecordTemperatureReadingUseCase,
            RegisterInventoryLotUseCase,
            ReleaseQuarantineUseCase,
            ReleaseReservationUseCase,
            ResolveTemperatureExcursionUseCase,
            ReverseAdjustmentUseCase,
            ReverseInventoryMovementUseCase,
            SetLocationStatusUseCase,
            SetLotQualityStatusUseCase,
            SetWarehouseStatusUseCase,
            UpdateLocationUseCase,
            UpdateLotUseCase,
            UpdateWarehouseUseCase,
        )
        from backend.application.inventory.labels.print_service import (
            InventoryLabelPrintService,
        )
        from backend.application.queries.product_query_service import (
            ProductQueryService,
        )
        from backend.infrastructure.hardware.scale_gateway import StubScaleGateway
        from frontend.desktop.modules.inventory.presenter import InventoryPresenter

        # §18/§28-29 báscula: sin driver de hardware concreto todavía (pendiente),
        # se cablea el StubScaleGateway como el punto de integración documentado —
        # una sola instancia por módulo para que una lectura encolada persista
        # entre "Leer báscula" y la confirmación de "Capturar peso".
        _scale_gateway = StubScaleGateway()
        scale_gateway_factory = lambda: _scale_gateway  # noqa: E731

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
            update_warehouse_uc = factory.update_warehouse()
            set_warehouse_status_uc = factory.set_warehouse_status()
            deactivate_warehouse_uc = factory.deactivate_warehouse()
            create_zone_uc = factory.create_zone()
            create_location_uc = factory.create_location()
            update_location_uc = factory.update_location()
            set_location_status_uc = factory.set_location_status()
<<<<<<< HEAD
            inspect_receipt_uc = factory.inspect_receipt()
=======
            deactivate_location_uc = factory.deactivate_location()
            reverse_movement_uc = factory.reverse_movement()
            register_lot_uc = factory.register_lot()
            update_lot_uc = factory.update_lot()
            set_lot_quality_status_uc = factory.set_lot_quality_status()
            generate_expiry_alerts_uc = factory.generate_expiry_alerts()
            expire_inventory_uc = factory.expire_inventory()
            record_catch_weight_uc = factory.record_catch_weight()
            record_temperature_reading_uc = factory.record_temperature_reading()
            resolve_temperature_excursion_uc = factory.resolve_temperature_excursion()
            create_reservation_uc = factory.create_reservation()
            allocate_reservation_uc = factory.allocate_reservation()
            release_reservation_uc = factory.release_reservation()
            _label_policy = factory.authorization_policy
            label_print_service_factory = (
                lambda c, _pol=_label_policy: InventoryLabelPrintService(
                    c, authorization=_pol))
>>>>>>> 42f747f4 (Refactir de modulo de Caja y merma)
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
            update_warehouse_uc = UpdateWarehouseUseCase()
            set_warehouse_status_uc = SetWarehouseStatusUseCase()
            deactivate_warehouse_uc = DeactivateWarehouseUseCase()
            create_zone_uc = CreateZoneUseCase()
            create_location_uc = CreateLocationUseCase()
            update_location_uc = UpdateLocationUseCase()
            set_location_status_uc = SetLocationStatusUseCase()
<<<<<<< HEAD
            inspect_receipt_uc = InspectReceiptUseCase()
=======
            deactivate_location_uc = DeactivateLocationUseCase()
            reverse_movement_uc = ReverseInventoryMovementUseCase()
            register_lot_uc = RegisterInventoryLotUseCase()
            update_lot_uc = UpdateLotUseCase()
            set_lot_quality_status_uc = SetLotQualityStatusUseCase()
            generate_expiry_alerts_uc = GenerateExpiryAlertsUseCase()
            expire_inventory_uc = ExpireInventoryUseCase()
            record_catch_weight_uc = RecordCatchWeightUseCase()
            record_temperature_reading_uc = RecordTemperatureReadingUseCase()
            resolve_temperature_excursion_uc = ResolveTemperatureExcursionUseCase()
            create_reservation_uc = CreateReservationUseCase()
            allocate_reservation_uc = AllocateReservationUseCase()
            release_reservation_uc = ReleaseReservationUseCase()
            label_print_service_factory = lambda c: InventoryLabelPrintService(c)  # noqa: E731
>>>>>>> 42f747f4 (Refactir de modulo de Caja y merma)

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
            update_warehouse_uc=update_warehouse_uc,
            set_warehouse_status_uc=set_warehouse_status_uc,
            deactivate_warehouse_uc=deactivate_warehouse_uc,
            create_zone_uc=create_zone_uc,
            create_location_uc=create_location_uc,
            update_location_uc=update_location_uc,
            set_location_status_uc=set_location_status_uc,
<<<<<<< HEAD
            inspect_receipt_uc=inspect_receipt_uc,
=======
            deactivate_location_uc=deactivate_location_uc,
            reverse_movement_uc=reverse_movement_uc,
            register_lot_uc=register_lot_uc,
            update_lot_uc=update_lot_uc,
            set_lot_quality_status_uc=set_lot_quality_status_uc,
            label_print_service_factory=label_print_service_factory,
            generate_expiry_alerts_uc=generate_expiry_alerts_uc,
            expire_inventory_uc=expire_inventory_uc,
            record_catch_weight_uc=record_catch_weight_uc,
            scale_gateway_factory=scale_gateway_factory,
            record_temperature_reading_uc=record_temperature_reading_uc,
            resolve_temperature_excursion_uc=resolve_temperature_excursion_uc,
            create_reservation_uc=create_reservation_uc,
            allocate_reservation_uc=allocate_reservation_uc,
            release_reservation_uc=release_reservation_uc,
>>>>>>> 42f747f4 (Refactir de modulo de Caja y merma)
            session_context=session,
        )
