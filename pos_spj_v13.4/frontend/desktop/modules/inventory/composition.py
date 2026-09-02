"""Composition root for the Inventory desktop module — SHELL-16 extraction.

Extracted verbatim (only `conn`→`connection`/`session`→`session_context`
renamed for consistency with `sales_pos`/`customers_crm`/`finance`/`hr`'s
own composition roots) from `modulos/inventario_enterprise.py::ModuloInventarioEnterprise._build_presenter`,
which is where this logic used to live — the one module among the first
five migrated whose composition root wasn't already separable from the
legacy container-taking bridge. Behavior is preserved exactly; the
existing regression tests (`tests/integration/inventory/test_inventory_enterprise_session_wiring.py`)
were written against the old location and still pass unmodified against
this one, since `modulos/inventario_enterprise.py` now just calls through
to this file instead of doing the wiring itself.

Takes only plain arguments — a bare `connection` and a `session_context`
— never the app's whole dependency container. The outer unwrapping step
stays in `modulos/inventario_enterprise.py`, mirroring
`modulos/ventas_pos.py`'s own split for `sales_pos`.

§5.4/§21.2 fail-closed (preserved from the original): the *live*
`SessionContext` instance is used directly, never copied or frozen — a
login/branch switch that happens after this presenter is built is
observed without rebuilding anything. Before login completes (or in a
minimal test harness with no session), `session_context` stays `None`:
reads return empty and mutations are denied downstream (the real policy
requires a user and checker) — never a fabricated identity, and never
`warehouse_id = branch_id`.
"""
from __future__ import annotations

from frontend.desktop.modules.inventory.presenter import InventoryPresenter


def build_inventory_presenter(connection, session_context=None) -> InventoryPresenter:
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
    from backend.infrastructure.hardware.label_rendering.network_label_gateway import (
        NetworkLabelPrintGateway,
    )
    from backend.infrastructure.hardware.scale_gateway import StubScaleGateway

    # §18/§28-29 báscula: sin driver de hardware concreto todavía (pendiente),
    # se cablea el StubScaleGateway como el punto de integración documentado —
    # una sola instancia por módulo para que una lectura encolada persista
    # entre "Leer báscula" y la confirmación de "Capturar peso".
    _scale_gateway = StubScaleGateway()
    scale_gateway_factory = lambda: _scale_gateway  # noqa: E731

    # §5.2 composition root: con sesión viva, los casos de uso sensibles se
    # construyen desde InventoryUseCaseFactory con el checker RBAC real (no el
    # default permisivo). Sin sesión viva (pruebas), caen al default explícito.
    if session_context is not None:
        from backend.application.inventory.composition import (
            InventoryUseCaseFactory,
        )
        factory = InventoryUseCaseFactory.from_session(session_context)
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
        inspect_receipt_uc = factory.inspect_receipt()
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
                c, authorization=_pol, gateway=NetworkLabelPrintGateway(c)))
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
        inspect_receipt_uc = InspectReceiptUseCase()
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
        label_print_service_factory = (
            lambda c: InventoryLabelPrintService(c, gateway=NetworkLabelPrintGateway(c)))

    return InventoryPresenter(
        connection_provider=lambda: connection,
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
        inspect_receipt_uc=inspect_receipt_uc,
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
        session_context=session_context,
    )


def create_inventory_view(connection, session_context=None, parent=None):
    """Factory used by `modulos/inventario_enterprise.py`. Never receives
    the container itself — only what it needs, already unwrapped."""
    from frontend.desktop.modules.inventory.inventory_view import InventoryView
    from frontend.desktop.modules.inventory.page_registry import build_page_specs

    presenter = build_inventory_presenter(connection, session_context)
    has_permission = getattr(session_context, "tiene_permiso", None) if session_context else None
    return InventoryView(presenter, build_page_specs(has_permission), parent)
