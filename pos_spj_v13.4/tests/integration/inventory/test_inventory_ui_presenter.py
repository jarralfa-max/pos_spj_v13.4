"""INV-25 — InventoryPresenter over the real backend + Qt page smoke (offscreen)."""

from decimal import Decimal

import sqlite3

import pytest

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
    PostAdjustmentUseCase,
    PostInventoryMovementUseCase,
    ReverseInventoryMovementUseCase,
    QuarantineStockUseCase,
    RecordCatchWeightUseCase,
    RecordCountUseCase,
    RecordTemperatureReadingUseCase,
    RegisterInventoryLotUseCase,
    ReleaseQuarantineUseCase,
    ReleaseReservationUseCase,
    ResolveTemperatureExcursionUseCase,
    ReverseAdjustmentUseCase,
    SetLocationStatusUseCase,
    SetLotQualityStatusUseCase,
    SetReplenishmentRuleUseCase,
    SetWarehouseStatusUseCase,
    UpdateLocationUseCase,
    UpdateLotUseCase,
    UpdateWarehouseUseCase,
)
from backend.application.inventory.labels.print_service import (
    InventoryLabelPrintService,
)
from backend.domain.inventory.enums import TechnicalLocationType, WarehouseType
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import MovementType
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.hardware.scale_gateway import StubScaleGateway
from frontend.desktop.modules.inventory.presenter import InventoryPresenter


class _Session:
    user_id = "u1"
    branch_id = "b1"
    warehouse_id = "w1"

    def __init__(self, grants: frozenset = frozenset()) -> None:
        self._grants = grants

    def tiene_permiso(self, code: str) -> bool:
        return code in self._grants


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def _seed(conn):
    SetReplenishmentRuleUseCase().execute(
        conn, product_id="p1", branch_id="b1", warehouse_id="w1",
        reorder_point=Decimal("10"), target_quantity=Decimal("30"), actor_user_id="u1")
    line = InventoryMovementLine.create(product_id="p1", quantity=Decimal("5"),
                                        to_location_id="loc1")
    mv = InventoryMovement.create(
        movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1", warehouse_id="w1",
        source_module="procurement", source_document_type="GR", source_document_id="g1",
        operation_id="g1", created_by_user_id="u1", lines=[line])
    PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")


def _presenter(conn, *, session=None, scale_gateway_factory=None):
    return InventoryPresenter(
        connection_provider=lambda: conn,
        availability_service_factory=InventoryAvailabilityQueryService,
        replenishment_query_factory=ReplenishmentQueryService,
        generate_suggestions_uc=GenerateReplenishmentSuggestionsUseCase(),
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
        release_quarantine_uc=ReleaseQuarantineUseCase(),
        dispose_quarantine_uc=DisposeQuarantineUseCase(),
        create_adjustment_uc=CreateAdjustmentUseCase(),
        approve_adjustment_uc=ApproveAdjustmentUseCase(),
        post_adjustment_uc=PostAdjustmentUseCase(),
        reverse_adjustment_uc=ReverseAdjustmentUseCase(),
        create_count_uc=CreateCountUseCase(),
        record_count_uc=RecordCountUseCase(),
        confirm_count_uc=ConfirmCountUseCase(),
        approve_count_uc=ApproveCountUseCase(),
        create_adjustment_from_count_uc=CreateAdjustmentFromCountUseCase(),
        create_warehouse_uc=CreateWarehouseUseCase(),
        update_warehouse_uc=UpdateWarehouseUseCase(),
        set_warehouse_status_uc=SetWarehouseStatusUseCase(),
        deactivate_warehouse_uc=DeactivateWarehouseUseCase(),
        create_zone_uc=CreateZoneUseCase(),
        create_location_uc=CreateLocationUseCase(),
        update_location_uc=UpdateLocationUseCase(),
        set_location_status_uc=SetLocationStatusUseCase(),
        deactivate_location_uc=DeactivateLocationUseCase(),
        reverse_movement_uc=ReverseInventoryMovementUseCase(),
        register_lot_uc=RegisterInventoryLotUseCase(),
        update_lot_uc=UpdateLotUseCase(),
        set_lot_quality_status_uc=SetLotQualityStatusUseCase(),
        label_print_service_factory=lambda c: InventoryLabelPrintService(c),
        generate_expiry_alerts_uc=GenerateExpiryAlertsUseCase(),
        expire_inventory_uc=ExpireInventoryUseCase(),
        record_catch_weight_uc=RecordCatchWeightUseCase(),
        scale_gateway_factory=scale_gateway_factory,
        record_temperature_reading_uc=RecordTemperatureReadingUseCase(),
        resolve_temperature_excursion_uc=ResolveTemperatureExcursionUseCase(),
        create_reservation_uc=CreateReservationUseCase(),
        allocate_reservation_uc=AllocateReservationUseCase(),
        release_reservation_uc=ReleaseReservationUseCase(),
        session_context=session or _Session())


def _seed_alert(conn, *, event_name, severity, channel, status, message,
                branch_id="b1"):
    from backend.shared.ids import new_uuid
    conn.execute(
        "INSERT INTO inventory_notification_log (id, event_id, event_name, channel,"
        " recipient_ref, severity, status, dedupe_key, message, branch_id,"
        " created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (new_uuid(), new_uuid(), event_name, channel, "u1", severity, status,
         new_uuid(), message, branch_id, "2026-08-03T10:00:00"))
    conn.commit()


def _seed_transfer(conn, *, number, ttype, origin, destination, status,
                   updated_at):
    from backend.shared.ids import new_uuid
    conn.execute(
        "INSERT INTO stock_transfers (id, transfer_number, transfer_type,"
        " source_channel, source_module, origin_node_type, origin_branch_id,"
        " destination_node_type, destination_branch_id, requested_by_user_id,"
        " priority, status, operation_id, created_at, updated_at) VALUES"
        " (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (new_uuid(), number, ttype, "DESKTOP", "inventory", "BRANCH", origin,
         "BRANCH", destination, "u1", "NORMAL", status, new_uuid(),
         updated_at, updated_at))
    conn.commit()


class TestPresenter:
    def test_availability_view_model(self, conn):
        _seed(conn)
        vm = _presenter(conn).availability(product_ids=["p1"])
        assert vm.total == 1 and vm.rows[0][0] == "p1"
        assert vm.rows[0][3].startswith("5")  # available

    def test_availability_breakdown_view_model(self, conn):
        _seed(conn)  # 5 disponibles de p1 en b1
        vm = _presenter(conn).availability_breakdown(product_id="p1")
        by_concept = {row[0]: row[1] for row in vm.rows}
        assert by_concept["Total en mano"].startswith("5")
        assert by_concept["Disponible"].startswith("5")
        assert by_concept["Reservado"].startswith("0")
        # el desglose incluye todos los buckets físicos (§9.3)
        assert "En cuarentena" in by_concept and "Bloqueado calidad" in by_concept

    def test_availability_breakdown_empty_without_product(self, conn):
        vm = _presenter(conn).availability_breakdown(product_id="")
        assert vm.total == 0 and vm.rows == []

    def test_lots_view_model(self, conn):
        from backend.application.inventory.use_cases import RegisterInventoryLotUseCase
        from backend.domain.inventory.enums import LotOrigin
        RegisterInventoryLotUseCase().execute(
            conn, product_id="p1", lot_code="L-9", origin_type=LotOrigin.PURCHASE,
            operation_id="lot-9", actor_user_id="u1", branch_id="b1",
            expiration_date="2027-01-15")
        vm = _presenter(conn).lots(product_id="p1")
        assert vm.total == 1
        assert vm.rows[0][0] == "L-9"          # código
        assert vm.rows[0][1] == "Compra"       # origen es-MX
        assert vm.rows[0][2] == "Por inspección"  # calidad por defecto es-MX
        assert vm.rows[0][3] == "2027-01-15"

    def test_lots_empty_without_product(self, conn):
        vm = _presenter(conn).lots(product_id="")
        assert vm.total == 0 and vm.rows == []

    def test_register_lot_via_presenter(self, conn):
        pres = _presenter(conn)
        ok, message, data = pres.register_lot(
            product_id="p1", lot_code="L-1", origin_type="PURCHASE",
            expiration_date="2026-08-01")
        assert ok, message
        assert data.get("entity_id")
        header = pres.lot_detail(lot_id=data["entity_id"])
        assert header["lot_code"] == "L-1"
        assert header["expiration_date"] == "2026-08-01"

    def test_register_lot_without_code_fails(self, conn):
        ok, message, _ = _presenter(conn).register_lot(
            product_id="p1", lot_code="", origin_type="PURCHASE")
        assert not ok
        assert "código" in message.lower()

    def test_register_lot_invalid_origin_fails(self, conn):
        ok, message, _ = _presenter(conn).register_lot(
            product_id="p1", lot_code="L-1", origin_type="NOT_A_TYPE")
        assert not ok
        assert "Origen" in message

    def test_lot_detail_unknown_returns_none(self, conn):
        assert _presenter(conn).lot_detail(lot_id="nope") is None

    def test_update_lot_via_presenter(self, conn):
        pres = _presenter(conn)
        lot_id = pres.register_lot(
            product_id="p1", lot_code="L-1", origin_type="PURCHASE")[2]["entity_id"]
        ok, message, _ = pres.update_lot(
            lot_id=lot_id, supplier_lot_code="SUP-9", expiration_date="2026-09-01")
        assert ok, message
        header = pres.lot_detail(lot_id=lot_id)
        assert header["supplier_lot_code"] == "SUP-9"
        assert header["expiration_date"] == "2026-09-01"

    def test_update_lot_without_selection(self, conn):
        ok, message, _ = _presenter(conn).update_lot(lot_id="", supplier_lot_code="x")
        assert not ok
        assert "Selecciona" in message

    def test_set_lot_quality_status_via_presenter(self, conn):
        pres = _presenter(conn)
        lot_id = pres.register_lot(
            product_id="p1", lot_code="L-1", origin_type="PURCHASE")[2]["entity_id"]
        ok, message, _ = pres.set_lot_quality_status(
            lot_id=lot_id, new_status="BLOCKED", reason="temperatura")
        assert ok, message
        assert pres.lot_detail(lot_id=lot_id)["quality_status"] == "BLOCKED"
        ok, message, _ = pres.set_lot_quality_status(lot_id=lot_id, new_status="RELEASED")
        assert ok, message
        assert pres.lot_detail(lot_id=lot_id)["quality_status"] == "RELEASED"

    def test_set_lot_quality_status_invalid_status_fails(self, conn):
        pres = _presenter(conn)
        lot_id = pres.register_lot(
            product_id="p1", lot_code="L-1", origin_type="PURCHASE")[2]["entity_id"]
        ok, message, _ = pres.set_lot_quality_status(lot_id=lot_id, new_status="NOT_A_STATUS")
        assert not ok
        assert "Estado" in message

    def test_lot_stock_and_movements(self, conn):
        pres = _presenter(conn)
        lot_id = pres.register_lot(
            product_id="p1", lot_code="L-1", origin_type="PURCHASE")[2]["entity_id"]
        line = InventoryMovementLine.create(
            product_id="p1", quantity=Decimal("8"), to_location_id="loc1", lot_id=lot_id)
        mv = InventoryMovement.create(
            movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1", warehouse_id="w1",
            source_module="procurement", source_document_type="GR",
            source_document_id="gr1", operation_id="op-r", created_by_user_id="u1",
            lines=[line])
        PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")

        stock = pres.lot_stock(lot_id=lot_id)
        assert stock.total == 1

        moves = pres.lot_movements(lot_id=lot_id)
        assert moves.total == 1

    def test_print_lot_label(self, conn):
        pres = _presenter(conn)
        lot_id = pres.register_lot(
            product_id="p1", lot_code="L-1", origin_type="PURCHASE")[2]["entity_id"]
        ok, message, _ = pres.print_lot_label(lot_id=lot_id)
        assert ok, message
        ok, message, _ = pres.print_lot_label(lot_id=lot_id, is_reprint=True)
        assert ok, message

    def test_print_lot_label_unknown_lot_fails(self, conn):
        ok, message, _ = _presenter(conn).print_lot_label(lot_id="nope")
        assert not ok
        assert "no encontrado" in message.lower()

    def test_generate_expiry_alerts_via_presenter(self, conn):
        ok, message, _ = _presenter(conn).generate_expiry_alerts()
        assert ok, message

    def test_process_expired_lots_via_presenter(self, conn):
        ok, message, _ = _presenter(conn).process_expired_lots()
        assert ok, message

    def test_movements_view_model(self, conn):
        _seed(conn)  # postea un PURCHASE_RECEIPT
        vm = _presenter(conn).movements()
        assert vm.total == 1
        assert vm.rows[0][1] == "Recepción de compra"  # tipo es-MX
        assert vm.rows[0][2] == "procurement"          # módulo
        assert vm.rows[0][4] == "Posteado"             # estado es-MX

    def test_movements_empty_ledger(self, conn):
        vm = _presenter(conn).movements()
        assert vm.total == 0 and vm.rows == []

    def test_movement_detail_and_lines(self, conn):
        _seed(conn)  # postea un PURCHASE_RECEIPT de p1 (qty 5) a loc1
        pres = _presenter(conn)
        mv_id = pres.movements().row_ids[0]
        header = pres.movement_detail(movement_id=mv_id)
        assert header["movement_type"] == "PURCHASE_RECEIPT"
        assert header["status"] == "POSTED"
        lines = pres.movement_lines(movement_id=mv_id)
        assert lines.total == 1
        assert lines.rows[0][2] == "5 PZA"  # cantidad + unidad

    def test_movement_detail_unknown_returns_none(self, conn):
        assert _presenter(conn).movement_detail(movement_id="nope") is None

    def test_movement_source_document_finds_siblings(self, conn):
        _seed(conn)
        pres = _presenter(conn)
        mv_id = pres.movements().row_ids[0]
        related = pres.movement_source_document(movement_id=mv_id)
        assert related.total == 1  # sólo el propio movimiento comparte el documento

    def test_movement_audit_shows_posted_entry(self, conn):
        _seed(conn)
        pres = _presenter(conn)
        mv_id = pres.movements().row_ids[0]
        trail = pres.movement_audit(movement_id=mv_id)
        assert trail.total == 1
        assert trail.rows[0][2] == "POSTED"

    def test_reverse_movement_via_presenter(self, conn):
        _seed(conn)
        pres = _presenter(conn)
        mv_id = pres.movements().row_ids[0]
        ok, message, _ = pres.reverse_movement(movement_id=mv_id, reason="error de captura")
        assert ok, message
        header = pres.movement_detail(movement_id=mv_id)
        assert header["status"] == "REVERSED"
        trail = pres.movement_audit(movement_id=mv_id)
        assert {r[2] for r in trail.rows} == {"POSTED", "REVERSED"}

    def test_reverse_movement_requires_reason(self, conn):
        _seed(conn)
        pres = _presenter(conn)
        mv_id = pres.movements().row_ids[0]
        ok, message, _ = pres.reverse_movement(movement_id=mv_id, reason="  ")
        assert not ok
        assert "motivo" in message.lower()

    def test_reverse_movement_without_selection(self, conn):
        ok, message, _ = _presenter(conn).reverse_movement(movement_id="", reason="x")
        assert not ok
        assert "Selecciona" in message

    def test_reverse_movement_unavailable_when_not_wired(self, conn):
        pres = InventoryPresenter(
            connection_provider=lambda: conn,
            availability_service_factory=InventoryAvailabilityQueryService,
            replenishment_query_factory=ReplenishmentQueryService)
        ok, message, _ = pres.reverse_movement(movement_id="m-1", reason="x")
        assert not ok
        assert "no disponible" in message

    def test_reverse_movement_requires_permission(self, conn):
        from backend.application.inventory.authorization import (
            DenyAllInventoryPermissionCheckerForTests,
            InventoryAuthorizationPolicy,
        )
        _seed(conn)
        pres = _presenter(conn)
        mv_id = pres.movements().row_ids[0]
        denied_uc = ReverseInventoryMovementUseCase(
            InventoryAuthorizationPolicy(DenyAllInventoryPermissionCheckerForTests()))
        pres._reverse_movement_uc = denied_uc  # noqa: SLF001 — sólo para esta prueba
        ok, message, _ = pres.reverse_movement(movement_id=mv_id, reason="x")
        assert not ok
        assert "no tiene el permiso" in message

    def test_expiring_view_model(self, conn):
        from datetime import date, timedelta
        from backend.application.inventory.use_cases import RegisterInventoryLotUseCase
        from backend.domain.inventory.enums import LotOrigin
        soon = (date.today() + timedelta(days=3)).isoformat()  # crítico
        reg = RegisterInventoryLotUseCase().execute(
            conn, product_id="p1", lot_code="L-EXP", origin_type=LotOrigin.PURCHASE,
            operation_id="lot-exp", actor_user_id="u1", branch_id="b1",
            expiration_date=soon)
        line = InventoryMovementLine.create(product_id="p1", quantity=Decimal("4"),
                                            to_location_id="loc1", lot_id=reg.entity_id)
        mv = InventoryMovement.create(
            movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1",
            warehouse_id="w1", source_module="procurement", source_document_type="GR",
            source_document_id="gr-exp", operation_id="rcv-exp",
            created_by_user_id="u1", lines=[line])
        PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")
        vm = _presenter(conn).expiring()
        assert vm.total == 1
        assert vm.rows[0][1] == "L-EXP"      # lote
        assert vm.rows[0][2].startswith("4")  # cantidad
        assert vm.rows[0][4] in ("Crítico", "Próximo a vencer", "Vencido")

    def test_expiring_empty_when_all_fresh(self, conn):
        _seed(conn)  # stock sin lote / sin caducidad próxima
        vm = _presenter(conn).expiring()
        assert vm.total == 0

    def test_traceability_view_model(self, conn):
        from backend.application.inventory.use_cases import RegisterInventoryLotUseCase
        from backend.domain.inventory.enums import LotOrigin
        reg = RegisterInventoryLotUseCase().execute(
            conn, product_id="p1", lot_code="L-TR", origin_type=LotOrigin.PURCHASE,
            operation_id="lot-tr", actor_user_id="u1", branch_id="b1")
        line = InventoryMovementLine.create(product_id="p1", quantity=Decimal("6"),
                                            to_location_id="loc1", lot_id=reg.entity_id)
        mv = InventoryMovement.create(
            movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1",
            warehouse_id="w1", source_module="procurement", source_document_type="GR",
            source_document_id="gr-tr", operation_id="rcv-tr",
            created_by_user_id="u1", lines=[line])
        PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")
        vm = _presenter(conn).traceability(lot_id=reg.entity_id)
        assert vm.total == 1
        assert vm.rows[0][1] == "Recepción de compra"  # movimiento es-MX
        assert vm.rows[0][2] == "Entrada"              # dirección es-MX

    def test_traceability_empty_without_lot(self, conn):
        vm = _presenter(conn).traceability(lot_id="")
        assert vm.total == 0 and vm.rows == []

    def test_stock_view_model(self, conn):
        _seed(conn)  # 5 disponibles de p1 en w1/loc1
        vm = _presenter(conn).stock()
        assert vm.total == 1
        assert vm.rows[0][0] == "p1"          # producto
        assert vm.rows[0][1] == "w1"          # almacén
        assert vm.rows[0][2] == "Disponible"  # estado/bucket es-MX
        assert vm.rows[0][3].startswith("5")  # cantidad

    def test_stock_empty_when_no_balances(self, conn):
        vm = _presenter(conn).stock()
        assert vm.total == 0 and vm.rows == []

    def test_quarantines_view_model(self, conn):
        from backend.domain.inventory.enums import QuarantineReason
        _seed(conn)  # 5 disponibles de p1 en loc1
        result = QuarantineStockUseCase().execute(
            conn, product_id="p1", branch_id="b1", warehouse_id="w1",
            reason=QuarantineReason.QUALITY_FAILURE, quantity=Decimal("2"),
            operation_id="q-1", actor_user_id="qa", location_id="loc1")
        vm = _presenter(conn).quarantines()
        assert vm.total == 1
        assert vm.rows[0][0] == "p1"                 # producto
        assert vm.rows[0][2] == "Falla de calidad"   # motivo es-MX
        assert vm.rows[0][4] == "Abierta"            # estado es-MX
        # row_ids llevan el id de la cuarentena (release/dispose actúan sobre
        # él), no producto/lote — esos se repiten entre filas.
        assert vm.row_ids[0] == result.entity_id

    def test_quarantines_empty(self, conn):
        vm = _presenter(conn).quarantines()
        assert vm.total == 0 and vm.rows == []

    def test_reservations_view_model(self, conn):
        from backend.application.inventory.use_cases import CreateReservationUseCase
        from backend.domain.inventory.enums import ReservationSource
        _seed(conn)  # 5 disponibles de p1 en loc1
        CreateReservationUseCase().execute(
            conn, product_id="p1", branch_id="b1", warehouse_id="w1",
            source=ReservationSource.SALE, source_document_id="S-1",
            quantity=Decimal("2"), operation_id="res-1", actor_user_id="u1",
            location_id="loc1")
        vm = _presenter(conn).reservations(product_id="p1")
        assert vm.total == 1
        assert vm.rows[0][0] == "Venta"       # origen es-MX
        assert vm.rows[0][1] == "S-1"         # documento
        assert vm.rows[0][3].startswith("2")  # cantidad
        assert vm.rows[0][4] == "Confirmada"  # estado es-MX

    def test_reservations_empty_without_product(self, conn):
        vm = _presenter(conn).reservations(product_id="")
        assert vm.total == 0 and vm.rows == []

    def test_cold_chain_view_model(self, conn):
        from backend.application.inventory.use_cases import (
            RecordTemperatureReadingUseCase,
        )
        from backend.domain.inventory.enums import TemperaturePoint
        RecordTemperatureReadingUseCase().execute(
            conn, sensor_id="s1", warehouse_id="w1", temperature=Decimal("9"),
            reading_point=TemperaturePoint.STORAGE, min_temp=Decimal("0"),
            max_temp=Decimal("4"), operation_id="tmp-1", actor_user_id="u1")
        vm = _presenter(conn).cold_chain_excursions()
        assert vm.total == 1
        assert vm.rows[0][0] == "w1"                 # almacén
        assert vm.rows[0][4] == "Fuera de rango"     # estado es-MX

    def test_cold_chain_empty(self, conn):
        vm = _presenter(conn).cold_chain_excursions()
        assert vm.total == 0 and vm.rows == []

    def test_audit_view_model(self, conn):
        _seed(conn)  # postea un MOVEMENT (+regla de reposición) → bitácora en b1
        vm = _presenter(conn).audit()
        # la entrada más reciente es el posteo del movimiento
        assert vm.total >= 1
        assert vm.rows[0][1] == "Movimiento"  # entidad es-MX
        assert vm.rows[0][2] == "POSTED"      # acción
        assert vm.rows[0][3] == "u1"          # usuario

    def test_audit_empty(self, conn):
        vm = _presenter(conn).audit()
        assert vm.total == 0 and vm.rows == []

    def test_transfers_view_model_scoped_and_localized(self, conn):
        from backend.infrastructure.db.schema.transfers_schema import (
            create_transfers_schema,
        )
        create_transfers_schema(conn)
        # b1 como origen (matchea) y como destino (matchea); una ajena (b9→b8).
        _seed_transfer(conn, number="TR-1", ttype="BRANCH_TO_BRANCH", origin="b1",
                       destination="b2", status="IN_TRANSIT",
                       updated_at="2026-08-03T10:00:00")
        _seed_transfer(conn, number="TR-2", ttype="EMERGENCY_TRANSFER", origin="b3",
                       destination="b1", status="RECEIVED",
                       updated_at="2026-08-03T12:00:00")
        _seed_transfer(conn, number="TR-9", ttype="BRANCH_TO_BRANCH", origin="b9",
                       destination="b8", status="DRAFT",
                       updated_at="2026-08-03T13:00:00")
        vm = _presenter(conn).transfers()  # default_branch = b1
        assert vm.total == 2                      # sólo las que tocan b1
        assert vm.rows[0][0] == "TR-2"            # más reciente primero
        assert vm.rows[0][1] == "Emergencia"      # tipo es-MX
        assert vm.rows[0][4] == "Recibida"        # estado es-MX
        assert vm.rows[1][0] == "TR-1"
        assert vm.rows[1][4] == "En tránsito"

    def test_transfers_empty(self, conn):
        from backend.infrastructure.db.schema.transfers_schema import (
            create_transfers_schema,
        )
        create_transfers_schema(conn)
        vm = _presenter(conn).transfers()
        assert vm.total == 0 and vm.rows == []

    def test_catch_weight_view_model(self, conn):
        # recepción de peso variable: 3 piezas, 7.5 kg de p1 en w1/loc1
        line = InventoryMovementLine.create(product_id="p1", quantity=Decimal("3"),
                                            weight=Decimal("7.5"),
                                            to_location_id="loc1")
        mv = InventoryMovement.create(
            movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1",
            warehouse_id="w1", source_module="procurement",
            source_document_type="GR", source_document_id="gr-w",
            operation_id="rcv-w", created_by_user_id="u1", lines=[line])
        PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")
        vm = _presenter(conn).catch_weight()
        assert vm.total == 1
        assert vm.rows[0][0] == "p1"           # producto
        assert vm.rows[0][1] == "w1"           # almacén
        assert vm.rows[0][2] == "Disponible"   # bucket es-MX
        assert vm.rows[0][3].startswith("3")   # piezas
        assert "7.5" in vm.rows[0][4]          # peso

    def test_catch_weight_empty_when_no_weight(self, conn):
        _seed(conn)  # stock por piezas (weight = 0) → no aparece en peso variable
        vm = _presenter(conn).catch_weight()
        assert vm.total == 0 and vm.rows == []

    def test_receipts_view_model_lists_inbound_only(self, conn):
        _seed(conn)  # postea un PURCHASE_RECEIPT (5 pzas de p1 en w1/loc1)
        # una salida de venta NO es recepción → debe quedar excluida
        issue = InventoryMovementLine.create(product_id="p1", quantity=Decimal("2"),
                                             from_location_id="loc1")
        mv = InventoryMovement.create(
            movement_type=MovementType.SALE_ISSUE, branch_id="b1", warehouse_id="w1",
            source_module="pos", source_document_type="TICKET",
            source_document_id="t-1", operation_id="iss-1",
            created_by_user_id="u1", lines=[issue])
        PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")
        vm = _presenter(conn).receipts()
        assert vm.total == 1                              # sólo la recepción
        assert vm.rows[0][1] == "Recepción de compra"    # tipo es-MX
        assert vm.rows[0][2] == "procurement"            # módulo
        assert vm.rows[0][4] == "Posteado"               # estado es-MX

    def test_receipts_empty_ledger(self, conn):
        vm = _presenter(conn).receipts()
        assert vm.total == 0 and vm.rows == []

    def test_counts_view_model(self, conn):
        from backend.application.inventory.use_cases import CreateCountUseCase
        from backend.domain.inventory.enums import CountType
        _seed(conn)  # 5 pzas de p1 en w1/loc1
        result = CreateCountUseCase().execute(
            conn, folio="CT-1", count_type=CountType.CYCLE_COUNT, branch_id="b1",
            warehouse_id="w1", scope_lines=[{"product_id": "p1"}],
            operation_id="cnt-1", actor_user_id="u1", blind=True)
        vm = _presenter(conn).counts()
        assert vm.total == 1
        assert vm.rows[0][0] == "CT-1"        # folio
        assert vm.rows[0][1] == "Cíclico"     # tipo es-MX
        assert vm.rows[0][2] == "w1"          # almacén
        assert vm.rows[0][3] == "A ciegas"    # modalidad
        assert vm.rows[0][4] == "En proceso"  # estado es-MX (start())
        assert vm.row_ids[0] == result.entity_id  # id real, no "folio:índice"

    def test_counts_empty(self, conn):
        vm = _presenter(conn).counts()
        assert vm.total == 0 and vm.rows == []

    def test_adjustments_view_model(self, conn):
        from backend.application.inventory.use_cases import CreateAdjustmentUseCase
        from backend.domain.inventory.enums import AdjustmentReason
        _seed(conn)  # 5 pzas de p1 en w1/loc1
        result = CreateAdjustmentUseCase().execute(
            conn, folio="AJ-1", branch_id="b1", warehouse_id="w1",
            reason=AdjustmentReason.DAMAGE,
            lines=[{"product_id": "p1", "quantity_delta": -1, "location_id": "loc1"}],
            operation_id="adj-1", actor_user_id="u1")
        vm = _presenter(conn).adjustments()
        assert vm.total == 1
        assert vm.rows[0][0] == "AJ-1"       # folio
        assert vm.rows[0][1] == "Daño"       # motivo es-MX
        assert vm.rows[0][2] == "w1"         # almacén
        assert vm.rows[0][3] in ("Borrador", "Por aprobar")  # estado es-MX
        # row_ids llevan el id del ajuste (approve/post/reverse actúan sobre
        # él), no el folio — necesario para que la UI pueda operar la fila.
        assert vm.row_ids[0] == result.entity_id

    def test_adjustments_empty(self, conn):
        vm = _presenter(conn).adjustments()
        assert vm.total == 0 and vm.rows == []

    def test_alerts_view_model(self, conn):
        _seed_alert(conn, event_name="INVENTORY_LOW_STOCK", severity="CRITICAL",
                    channel="IN_APP", status="SENT", message="p1 bajo mínimo")
        # una alerta de otra sucursal no debe aparecer (alcance por sucursal)
        _seed_alert(conn, event_name="INVENTORY_LOT_EXPIRING", severity="WARNING",
                    channel="WHATSAPP", status="SENT", message="lote ajeno",
                    branch_id="b9")
        vm = _presenter(conn).alerts()  # default_branch = b1
        assert vm.total == 1
        assert vm.rows[0][1] == "Crítica"     # severidad es-MX
        assert vm.rows[0][2] == "Stock bajo"  # evento es-MX
        assert vm.rows[0][5] == "p1 bajo mínimo"

    def test_alerts_empty(self, conn):
        vm = _presenter(conn).alerts()
        assert vm.total == 0 and vm.rows == []

    def test_alerts_severity_filter(self, conn):
        _seed_alert(conn, event_name="INVENTORY_LOW_STOCK", severity="CRITICAL",
                    channel="IN_APP", status="SENT", message="crítica p1")
        _seed_alert(conn, event_name="INVENTORY_LOT_EXPIRING", severity="WARNING",
                    channel="IN_APP", status="SENT", message="advertencia p2")
        pres = _presenter(conn)
        assert pres.alerts().total == 2                       # sin filtro
        only_crit = pres.alerts(severity="CRITICAL")
        assert only_crit.total == 1
        assert only_crit.rows[0][1] == "Crítica"
        assert pres.alerts(severity="WARNING").total == 1

    def test_alert_kpis(self, conn):
        _seed_alert(conn, event_name="INVENTORY_LOW_STOCK", severity="CRITICAL",
                    channel="IN_APP", status="SENT", message="c1")
        _seed_alert(conn, event_name="INVENTORY_LOW_STOCK", severity="CRITICAL",
                    channel="IN_APP", status="SENT", message="c2")
        _seed_alert(conn, event_name="INVENTORY_LOT_EXPIRING", severity="WARNING",
                    channel="IN_APP", status="SENT", message="w1")
        kpis = {k.key: k.value for k in _presenter(conn).alert_kpis()}
        assert kpis["total"] == "3"
        assert kpis["critical"] == "2"
        assert kpis["warning"] == "1"
        assert kpis["info"] == "0"

    def test_settings_view_model(self, conn):
        from backend.shared.ids import new_uuid
        conn.execute(
            "INSERT INTO inventory_notification_rule (id, event_name, scope_type,"
            " scope_id, channel, recipient_type, recipient_ref, min_severity,"
            " throttle_seconds, active, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (new_uuid(), "INVENTORY_LOW_STOCK", "GLOBAL", "", "IN_APP", "ROLE",
             "manager", "WARNING", 300, 1, "2026-08-03T10:00:00"))
        conn.commit()
        vm = _presenter(conn).settings()
        assert vm.total == 1
        assert vm.rows[0][0] == "Stock bajo"    # evento es-MX
        assert vm.rows[0][1] == "Global"        # ámbito es-MX
        assert vm.rows[0][3] == "Advertencia"   # severidad mínima es-MX
        assert vm.rows[0][4] == "300s"          # throttle
        assert vm.rows[0][5] == "Sí"            # activa

    def test_settings_empty(self, conn):
        vm = _presenter(conn).settings()
        assert vm.total == 0 and vm.rows == []

    def test_generate_then_list_suggestions(self, conn):
        _seed(conn)
        pres = _presenter(conn)
        ok, _msg, data = pres.generate_suggestions()
        assert ok and data["count"] == 1
        vm = pres.open_suggestions()
        assert vm.total == 1 and vm.rows[0][3] == "Compra"  # source localized

    def test_replenishment_kpis(self, conn):
        _seed(conn)
        pres = _presenter(conn)
        pres.generate_suggestions()
        kpis = {k.key: k.value for k in pres.replenishment_kpis()}
        assert kpis["open"] == "1"

    def test_analytics_kpis_and_export(self, conn):
        _seed(conn)
        pres = _presenter(conn)
        kpis = {k.key: k.value for k in pres.inventory_kpis()}
        assert kpis["available"] == "5"
        charts = pres.analytics_charts()
        assert len(charts) == 4
        assert "product_id" in pres.export_availability_csv()
        assert pres.freshness().state in ("LIVE", "FRESH")

    def test_warehouses_and_location_tree(self, conn):
        wid = CreateWarehouseUseCase().execute(
            conn, code="WH1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id
        aisle = CreateLocationUseCase().execute(
            conn, warehouse_id=wid, code="A1", name="Pasillo", actor_user_id="u1").entity_id
        CreateLocationUseCase().execute(
            conn, warehouse_id=wid, code="A1-R1", name="Rack", actor_user_id="u1",
            parent_location_id=aisle, level=1)
        pres = _presenter(conn)
        assert pres.warehouses().rows[0][0] == "WH1"
        tree = pres.location_tree(warehouse_id=wid)
        # §20: + las ubicaciones técnicas auto-aprovisionadas al crear el almacén.
        assert tree.total == 2 + len(TechnicalLocationType)
        assert tree.rows[0][0] == "A1" and tree.rows[1][0].startswith("· ")


class TestQuarantineCommands:
    """P0-B pilot — release/dispose are real authorized commands, not reads."""

    def _open_quarantine(self, conn, *, operation_id="q-1"):
        from backend.domain.inventory.enums import QuarantineReason
        _seed(conn)  # 5 disponibles de p1 en loc1
        result = QuarantineStockUseCase().execute(
            conn, product_id="p1", branch_id="b1", warehouse_id="w1",
            reason=QuarantineReason.QUALITY_FAILURE, quantity=Decimal("2"),
            operation_id=operation_id, actor_user_id="qa", location_id="loc1")
        assert result.success, result.message
        return result.entity_id

    def test_release_quarantine_returns_stock_and_closes_it(self, conn):
        qid = self._open_quarantine(conn)
        pres = _presenter(conn)
        ok, message, _ = pres.release_quarantine(quarantine_id=qid)
        assert ok, message
        assert pres.quarantines().total == 0

    def test_dispose_quarantine_issues_stock_and_closes_it(self, conn):
        qid = self._open_quarantine(conn, operation_id="q-2")
        pres = _presenter(conn)
        ok, message, _ = pres.dispose_quarantine(
            quarantine_id=qid, reason="Producto contaminado")
        assert ok, message
        assert pres.quarantines().total == 0

    def test_release_quarantine_without_selection_does_not_call_backend(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.release_quarantine(quarantine_id="")
        assert not ok
        assert "Selecciona" in message

    def test_dispose_quarantine_without_selection_does_not_call_backend(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.dispose_quarantine(quarantine_id="")
        assert not ok
        assert "Selecciona" in message

    def test_release_quarantine_unavailable_when_not_wired(self, conn):
        pres = InventoryPresenter(
            connection_provider=lambda: conn,
            availability_service_factory=InventoryAvailabilityQueryService,
            replenishment_query_factory=ReplenishmentQueryService,
            quarantine_query_factory=QuarantineQueryService)
        ok, message, _ = pres.release_quarantine(quarantine_id="q-1")
        assert not ok
        assert "no disponible" in message

    def test_dispose_quarantine_unavailable_when_not_wired(self, conn):
        pres = InventoryPresenter(
            connection_provider=lambda: conn,
            availability_service_factory=InventoryAvailabilityQueryService,
            replenishment_query_factory=ReplenishmentQueryService,
            quarantine_query_factory=QuarantineQueryService)
        ok, message, _ = pres.dispose_quarantine(quarantine_id="q-1")
        assert not ok
        assert "no disponible" in message


class TestAdjustmentCommands:
    """P0-C resumption — create/approve/post/reverse are real authorized
    commands, not reads. Segregation of duties (creator != approver) is
    enforced by the domain, so setup adjustments are created by a different
    actor ("qa") than the presenter's session user ("u1")."""

    def _created_adjustment(self, conn, *, operation_id="adj-1"):
        from backend.domain.inventory.enums import AdjustmentReason
        result = CreateAdjustmentUseCase().execute(
            conn, folio=f"AJ-{operation_id}", branch_id="b1", warehouse_id="w1",
            reason=AdjustmentReason.SYSTEM_CORRECTION, operation_id=operation_id,
            actor_user_id="qa",
            lines=[{"product_id": "p1", "quantity_delta": Decimal("3")}])
        assert result.success, result.message
        return result.entity_id

    def test_create_adjustment_via_presenter_creates_draft(self, conn):
        pres = _presenter(conn)
        ok, message, data = pres.create_adjustment(
            product_id="p1", reason="SYSTEM_CORRECTION", quantity_delta=Decimal("3"))
        assert ok, message
        assert data.get("entity_id")
        assert pres.adjustments().total == 1

    def test_create_adjustment_without_product_does_not_call_backend(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.create_adjustment(
            product_id="", reason="SYSTEM_CORRECTION", quantity_delta=Decimal("3"))
        assert not ok
        assert "Selecciona" in message

    def test_create_adjustment_with_invalid_reason_fails(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.create_adjustment(
            product_id="p1", reason="NOT_A_REASON", quantity_delta=Decimal("3"))
        assert not ok
        assert "Motivo" in message

    def test_create_adjustment_without_quantity_fails(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.create_adjustment(
            product_id="p1", reason="SYSTEM_CORRECTION", quantity_delta=0)
        assert not ok
        assert "Captura" in message

    def test_approve_adjustment_transitions_to_approved(self, conn):
        aid = self._created_adjustment(conn)
        pres = _presenter(conn)
        ok, message, _ = pres.approve_adjustment(adjustment_id=aid)
        assert ok, message

    def test_post_adjustment_applies_movement_and_marks_posted(self, conn):
        aid = self._created_adjustment(conn, operation_id="adj-2")
        pres = _presenter(conn)
        ok, message, _ = pres.post_adjustment(adjustment_id=aid)
        assert ok, message
        dto = InventoryAvailabilityQueryService(conn).get_availability(
            product_id="p1", branch_id="b1", warehouse_id="w1")
        assert dto.on_hand == Decimal("3")

    def test_reverse_adjustment_undoes_posted_movement(self, conn):
        aid = self._created_adjustment(conn, operation_id="adj-3")
        pres = _presenter(conn)
        ok, message, _ = pres.post_adjustment(adjustment_id=aid)
        assert ok, message
        ok, message, _ = pres.reverse_adjustment(adjustment_id=aid, reason="Error de captura")
        assert ok, message
        dto = InventoryAvailabilityQueryService(conn).get_availability(
            product_id="p1", branch_id="b1", warehouse_id="w1")
        assert dto.on_hand == Decimal("0")

    def test_approve_adjustment_without_selection_does_not_call_backend(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.approve_adjustment(adjustment_id="")
        assert not ok
        assert "Selecciona" in message

    def test_post_adjustment_without_selection_does_not_call_backend(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.post_adjustment(adjustment_id="")
        assert not ok
        assert "Selecciona" in message

    def test_reverse_adjustment_without_selection_does_not_call_backend(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.reverse_adjustment(adjustment_id="")
        assert not ok
        assert "Selecciona" in message

    def test_create_adjustment_unavailable_when_not_wired(self, conn):
        pres = InventoryPresenter(
            connection_provider=lambda: conn,
            availability_service_factory=InventoryAvailabilityQueryService,
            replenishment_query_factory=ReplenishmentQueryService,
            adjustment_query_factory=AdjustmentQueryService)
        ok, message, _ = pres.create_adjustment(
            product_id="p1", reason="SYSTEM_CORRECTION", quantity_delta=Decimal("3"))
        assert not ok
        assert "no disponible" in message

    def test_approve_adjustment_unavailable_when_not_wired(self, conn):
        pres = InventoryPresenter(
            connection_provider=lambda: conn,
            availability_service_factory=InventoryAvailabilityQueryService,
            replenishment_query_factory=ReplenishmentQueryService,
            adjustment_query_factory=AdjustmentQueryService)
        ok, message, _ = pres.approve_adjustment(adjustment_id="a-1")
        assert not ok
        assert "no disponible" in message

    def test_post_adjustment_unavailable_when_not_wired(self, conn):
        pres = InventoryPresenter(
            connection_provider=lambda: conn,
            availability_service_factory=InventoryAvailabilityQueryService,
            replenishment_query_factory=ReplenishmentQueryService,
            adjustment_query_factory=AdjustmentQueryService)
        ok, message, _ = pres.post_adjustment(adjustment_id="a-1")
        assert not ok
        assert "no disponible" in message

    def test_reverse_adjustment_unavailable_when_not_wired(self, conn):
        pres = InventoryPresenter(
            connection_provider=lambda: conn,
            availability_service_factory=InventoryAvailabilityQueryService,
            replenishment_query_factory=ReplenishmentQueryService,
            adjustment_query_factory=AdjustmentQueryService)
        ok, message, _ = pres.reverse_adjustment(adjustment_id="a-1")
        assert not ok
        assert "no disponible" in message


class TestCatchWeightCommands:
    """INV-8 (§18/§28-29) — capturar peso (báscula/manual), leer báscula y el
    historial (ajustes con motivo WEIGHT_VARIANCE), vía el presenter."""

    def test_record_catch_weight_manual_in_range(self, conn):
        pres = _presenter(conn)
        ok, message, data = pres.record_catch_weight(
            product_id="p1", use_scale=False, gross=Decimal("5"))
        assert ok, message
        assert data.get("entity_id")
        assert pres.weight_history().total == 1

    def test_record_catch_weight_without_product_does_not_call_backend(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.record_catch_weight(
            product_id="", use_scale=False, gross=Decimal("5"))
        assert not ok
        assert "Selecciona" in message

    def test_record_catch_weight_scale_reads_from_gateway(self, conn):
        from backend.domain.inventory.value_objects.catch_weight import WeightReading

        gateway = StubScaleGateway([WeightReading(gross=Decimal("12.5"), stable=True)])
        pres = _presenter(conn, scale_gateway_factory=lambda: gateway)
        ok, message, data = pres.record_catch_weight(product_id="p1", use_scale=True)
        assert ok, message
        assert data["weight_reading"]["net"] == "12.5"

    def test_record_catch_weight_scale_without_gateway_fails(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.record_catch_weight(product_id="p1", use_scale=True)
        assert not ok
        assert "báscula" in message

    def test_read_scale_returns_none_without_gateway(self, conn):
        pres = _presenter(conn)
        assert pres.read_scale() is None

    def test_read_scale_returns_none_when_queue_empty(self, conn):
        pres = _presenter(conn, scale_gateway_factory=lambda: StubScaleGateway())
        assert pres.read_scale() is None

    def test_read_scale_returns_pending_reading(self, conn):
        from backend.domain.inventory.value_objects.catch_weight import WeightReading

        gateway = StubScaleGateway([WeightReading(gross=Decimal("30"), stable=True)])
        pres = _presenter(conn, scale_gateway_factory=lambda: gateway)
        reading = pres.read_scale()
        assert reading is not None
        assert reading["net"] == Decimal("30") and reading["stable"] is True

    def test_record_catch_weight_unavailable_when_not_wired(self, conn):
        pres = InventoryPresenter(
            connection_provider=lambda: conn,
            availability_service_factory=InventoryAvailabilityQueryService,
            replenishment_query_factory=ReplenishmentQueryService)
        ok, message, _ = pres.record_catch_weight(
            product_id="p1", use_scale=False, gross=Decimal("5"))
        assert not ok
        assert "no disponible" in message


class TestColdChainCommands:
    """INV-9 (§21) — registrar lectura y resolver una excursión abierta, vía
    el presenter."""

    def test_record_temperature_reading_compliant(self, conn):
        pres = _presenter(conn)
        ok, message, data = pres.record_temperature_reading(
            sensor_id="s1", temperature=Decimal("2"), reading_point="STORAGE",
            min_temp=Decimal("0"), max_temp=Decimal("4"))
        assert ok, message
        assert data.get("status") == "COMPLIANT"
        assert pres.cold_chain_excursions().total == 0

    def test_record_temperature_reading_excursion(self, conn):
        pres = _presenter(conn)
        ok, message, data = pres.record_temperature_reading(
            sensor_id="s1", temperature=Decimal("9"), reading_point="STORAGE",
            min_temp=Decimal("0"), max_temp=Decimal("4"))
        assert ok, message
        assert pres.cold_chain_excursions().total == 1

    def test_record_temperature_reading_without_sensor_does_not_call_backend(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.record_temperature_reading(
            sensor_id="", temperature=Decimal("2"), reading_point="STORAGE",
            min_temp=Decimal("0"), max_temp=Decimal("4"))
        assert not ok
        assert "sensor" in message.lower()

    def test_record_temperature_reading_invalid_point_fails(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.record_temperature_reading(
            sensor_id="s1", temperature=Decimal("2"), reading_point="NOPE",
            min_temp=Decimal("0"), max_temp=Decimal("4"))
        assert not ok
        assert "inválido" in message.lower()

    def test_record_temperature_reading_unavailable_when_not_wired(self, conn):
        pres = InventoryPresenter(
            connection_provider=lambda: conn,
            availability_service_factory=InventoryAvailabilityQueryService,
            replenishment_query_factory=ReplenishmentQueryService)
        ok, message, _ = pres.record_temperature_reading(
            sensor_id="s1", temperature=Decimal("2"), reading_point="STORAGE",
            min_temp=Decimal("0"), max_temp=Decimal("4"))
        assert not ok
        assert "no disponible" in message

    def _open_excursion(self, pres):
        eid = pres.cold_chain_excursions().row_ids[0]
        return eid

    def test_resolve_temperature_excursion_release(self, conn):
        pres = _presenter(conn)
        pres.record_temperature_reading(
            sensor_id="s1", temperature=Decimal("9"), reading_point="STORAGE",
            min_temp=Decimal("0"), max_temp=Decimal("4"))
        eid = self._open_excursion(pres)
        ok, message, _ = pres.resolve_temperature_excursion(
            excursion_id=eid, resolution="RELEASE", resolution_note="Revisado")
        assert ok, message
        assert pres.cold_chain_excursions().total == 0

    def test_resolve_temperature_excursion_without_selection_does_not_call_backend(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.resolve_temperature_excursion(
            excursion_id="", resolution="RELEASE")
        assert not ok
        assert "Selecciona" in message

    def test_resolve_temperature_excursion_invalid_action_fails(self, conn):
        pres = _presenter(conn)
        pres.record_temperature_reading(
            sensor_id="s1", temperature=Decimal("9"), reading_point="STORAGE",
            min_temp=Decimal("0"), max_temp=Decimal("4"))
        eid = self._open_excursion(pres)
        ok, message, _ = pres.resolve_temperature_excursion(
            excursion_id=eid, resolution="NOPE")
        assert not ok
        assert "inválida" in message.lower()

    def test_resolve_temperature_excursion_unavailable_when_not_wired(self, conn):
        pres = InventoryPresenter(
            connection_provider=lambda: conn,
            availability_service_factory=InventoryAvailabilityQueryService,
            replenishment_query_factory=ReplenishmentQueryService)
        ok, message, _ = pres.resolve_temperature_excursion(
            excursion_id="x", resolution="RELEASE")
        assert not ok
        assert "no disponible" in message


class TestReservationCommands:
    """INV-10 (§22) — crear, asignar (FEFO) y liberar reservas, vía el presenter."""

    def test_create_reservation_success(self, conn):
        _seed(conn)
        pres = _presenter(conn)
        ok, message, data = pres.create_reservation(
            product_id="p1", source="SALE", source_document_id="S-1",
            quantity=Decimal("2"), location_id="loc1")
        assert ok, message
        assert data.get("entity_id")
        assert pres.reservations(product_id="p1").total == 1

    def test_create_reservation_without_product_does_not_call_backend(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.create_reservation(
            product_id="", source="SALE", source_document_id="S-1", quantity=Decimal("2"))
        assert not ok
        assert "Selecciona" in message

    def test_create_reservation_without_quantity_fails(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.create_reservation(
            product_id="p1", source="SALE", source_document_id="S-1", quantity=0)
        assert not ok
        assert "cantidad" in message.lower()

    def test_create_reservation_invalid_source_fails(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.create_reservation(
            product_id="p1", source="NOPE", source_document_id="S-1",
            quantity=Decimal("2"))
        assert not ok
        assert "inválido" in message.lower()

    def test_create_reservation_unavailable_when_not_wired(self, conn):
        pres = InventoryPresenter(
            connection_provider=lambda: conn,
            availability_service_factory=InventoryAvailabilityQueryService,
            replenishment_query_factory=ReplenishmentQueryService)
        ok, message, _ = pres.create_reservation(
            product_id="p1", source="SALE", source_document_id="S-1", quantity=Decimal("2"))
        assert not ok
        assert "no disponible" in message

    def test_allocate_reservation_success(self, conn):
        from backend.domain.inventory.enums import LotOrigin
        from backend.infrastructure.db.repositories.inventory.unit_of_work import (
            InventoryUnitOfWork,
        )
        _seed(conn)
        RegisterInventoryLotUseCase().execute(
            conn, product_id="p1", lot_code="L1", origin_type=LotOrigin.PURCHASE,
            operation_id="lot-1", actor_user_id="u1")
        with InventoryUnitOfWork(conn) as uow:
            lot_id = uow.lots.get_by_code("p1", "L1").id
        line = InventoryMovementLine.create(
            product_id="p1", quantity=Decimal("5"), to_location_id="loc2", lot_id=lot_id)
        mv = InventoryMovement.create(
            movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1", warehouse_id="w1",
            source_module="procurement", source_document_type="GR",
            source_document_id="gr2", operation_id="rcv-lot", created_by_user_id="u1",
            lines=[line])
        PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")
        pres = _presenter(conn)
        ok, message, data = pres.create_reservation(
            product_id="p1", source="SALE", source_document_id="S-1",
            quantity=Decimal("2"), location_id="loc1")
        assert ok, message
        rid = data["entity_id"]
        ok2, message2, data2 = pres.allocate_reservation(reservation_id=rid)
        assert ok2, message2
        assert data2.get("allocations") == 1

    def test_allocate_reservation_without_selection_does_not_call_backend(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.allocate_reservation(reservation_id="")
        assert not ok
        assert "Selecciona" in message

    def test_allocate_reservation_unavailable_when_not_wired(self, conn):
        pres = InventoryPresenter(
            connection_provider=lambda: conn,
            availability_service_factory=InventoryAvailabilityQueryService,
            replenishment_query_factory=ReplenishmentQueryService)
        ok, message, _ = pres.allocate_reservation(reservation_id="x")
        assert not ok
        assert "no disponible" in message

    def test_release_reservation_restores_availability(self, conn):
        _seed(conn)
        pres = _presenter(conn)
        _, _, data = pres.create_reservation(
            product_id="p1", source="SALE", source_document_id="S-1",
            quantity=Decimal("2"), location_id="loc1")
        rid = data["entity_id"]
        ok, message, _ = pres.release_reservation(reservation_id=rid, reason="cancelada")
        assert ok, message
        assert pres.reservations(product_id="p1").total == 0

    def test_release_reservation_without_selection_does_not_call_backend(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.release_reservation(reservation_id="")
        assert not ok
        assert "Selecciona" in message

    def test_release_reservation_unavailable_when_not_wired(self, conn):
        pres = InventoryPresenter(
            connection_provider=lambda: conn,
            availability_service_factory=InventoryAvailabilityQueryService,
            replenishment_query_factory=ReplenishmentQueryService)
        ok, message, _ = pres.release_reservation(reservation_id="x")
        assert not ok
        assert "no disponible" in message


class TestCountCommands:
    """P0-C (Conteos) — iniciar/capturar/confirmar/aprobar/generar ajuste son
    comandos reales. Segregación (contador != aprobador en varianza crítica)
    se cubre iniciando el conteo con actor "qa" y aprobando con la sesión
    "u1" del presenter, igual que el patrón ya usado para Ajustes."""

    def _started_count(self, conn, *, operation_id="cnt-1"):
        from backend.domain.inventory.enums import CountType
        _seed(conn)  # 5 pzas de p1 en w1/loc1
        result = CreateCountUseCase().execute(
            conn, folio=f"CT-{operation_id}", count_type=CountType.CYCLE_COUNT,
            branch_id="b1", warehouse_id="w1", scope_lines=[{"product_id": "p1"}],
            operation_id=operation_id, actor_user_id="qa", blind=True)
        assert result.success, result.message
        return result.entity_id

    def test_create_count_via_presenter_starts_in_progress(self, conn):
        _seed(conn)
        pres = _presenter(conn)
        ok, message, data = pres.create_count(product_id="p1", count_type="CYCLE_COUNT")
        assert ok, message
        assert data.get("entity_id")
        assert pres.counts().total == 1

    def test_create_count_without_product_does_not_call_backend(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.create_count(product_id="", count_type="CYCLE_COUNT")
        assert not ok
        assert "Selecciona" in message

    def test_create_count_with_invalid_type_fails(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.create_count(product_id="p1", count_type="NOT_A_TYPE")
        assert not ok
        assert "Tipo" in message

    def test_record_count_captures_the_single_line(self, conn):
        cid = self._started_count(conn)
        pres = _presenter(conn)
        ok, message, _ = pres.record_count(count_id=cid, counted_quantity=Decimal("4"))
        assert ok, message
        lines = CountQueryService(conn).list_lines(count_id=cid)
        assert lines[0]["counted"] is True

    def test_record_count_without_selection_does_not_call_backend(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.record_count(count_id="", counted_quantity=Decimal("1"))
        assert not ok
        assert "Selecciona" in message

    def test_record_count_without_quantity_fails(self, conn):
        cid = self._started_count(conn, operation_id="cnt-2")
        pres = _presenter(conn)
        ok, message, _ = pres.record_count(count_id=cid, counted_quantity=None)
        assert not ok
        assert "Captura" in message

    def test_confirm_count_computes_variance_and_requires_approval(self, conn):
        cid = self._started_count(conn, operation_id="cnt-3")
        pres = _presenter(conn)
        ok, message, _ = pres.record_count(count_id=cid, counted_quantity=Decimal("4"))
        assert ok, message
        ok, message, _ = pres.confirm_count(count_id=cid)
        assert ok, message
        rows = CountQueryService(conn).list_recent(branch_id="b1")
        assert rows[0]["status"] == "PENDING_APPROVAL"  # 4 contado vs 5 esperado

    def test_confirm_count_without_selection_does_not_call_backend(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.confirm_count(count_id="")
        assert not ok
        assert "Selecciona" in message

    def test_approve_count_transitions_to_approved(self, conn):
        cid = self._started_count(conn, operation_id="cnt-4")
        lines = CountQueryService(conn).list_lines(count_id=cid)
        record = RecordCountUseCase().execute(
            conn, count_id=cid, line_id=lines[0]["id"], counted_quantity=Decimal("4"),
            operation_id="cnt-4-rec", actor_user_id="qa")  # contador != aprobador (u1)
        assert record.success, record.message
        ConfirmCountUseCase().execute(
            conn, count_id=cid, operation_id="cnt-4-confirm", actor_user_id="qa")
        pres = _presenter(conn)
        ok, message, _ = pres.approve_count(count_id=cid)
        assert ok, message
        rows = CountQueryService(conn).list_recent(branch_id="b1")
        assert rows[0]["status"] == "APPROVED"

    def test_approve_count_without_selection_does_not_call_backend(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.approve_count(count_id="")
        assert not ok
        assert "Selecciona" in message

    def test_generate_adjustment_from_count_creates_adjustment(self, conn):
        cid = self._started_count(conn, operation_id="cnt-5")
        lines = CountQueryService(conn).list_lines(count_id=cid)
        RecordCountUseCase().execute(
            conn, count_id=cid, line_id=lines[0]["id"], counted_quantity=Decimal("4"),
            operation_id="cnt-5-rec", actor_user_id="qa")
        ConfirmCountUseCase().execute(
            conn, count_id=cid, operation_id="cnt-5-confirm", actor_user_id="qa")
        pres = _presenter(conn)
        ok, message, _ = pres.approve_count(count_id=cid)  # actor u1 != contador qa
        assert ok, message
        ok, message, data = pres.generate_adjustment_from_count(count_id=cid)
        assert ok, message
        assert data.get("entity_id")
        assert pres.adjustments().total == 1

    def test_generate_adjustment_from_count_without_selection_does_not_call_backend(
            self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.generate_adjustment_from_count(count_id="")
        assert not ok
        assert "Selecciona" in message

    def test_create_count_unavailable_when_not_wired(self, conn):
        pres = InventoryPresenter(
            connection_provider=lambda: conn,
            availability_service_factory=InventoryAvailabilityQueryService,
            replenishment_query_factory=ReplenishmentQueryService,
            count_query_factory=CountQueryService)
        ok, message, _ = pres.create_count(product_id="p1", count_type="CYCLE_COUNT")
        assert not ok
        assert "no disponible" in message

    def test_record_count_unavailable_when_not_wired(self, conn):
        pres = InventoryPresenter(
            connection_provider=lambda: conn,
            availability_service_factory=InventoryAvailabilityQueryService,
            replenishment_query_factory=ReplenishmentQueryService,
            count_query_factory=CountQueryService)
        ok, message, _ = pres.record_count(count_id="c-1", counted_quantity=Decimal("1"))
        assert not ok
        assert "no disponible" in message

    def test_confirm_count_unavailable_when_not_wired(self, conn):
        pres = InventoryPresenter(
            connection_provider=lambda: conn,
            availability_service_factory=InventoryAvailabilityQueryService,
            replenishment_query_factory=ReplenishmentQueryService,
            count_query_factory=CountQueryService)
        ok, message, _ = pres.confirm_count(count_id="c-1")
        assert not ok
        assert "no disponible" in message

    def test_approve_count_unavailable_when_not_wired(self, conn):
        pres = InventoryPresenter(
            connection_provider=lambda: conn,
            availability_service_factory=InventoryAvailabilityQueryService,
            replenishment_query_factory=ReplenishmentQueryService,
            count_query_factory=CountQueryService)
        ok, message, _ = pres.approve_count(count_id="c-1")
        assert not ok
        assert "no disponible" in message

    def test_generate_adjustment_from_count_unavailable_when_not_wired(self, conn):
        pres = InventoryPresenter(
            connection_provider=lambda: conn,
            availability_service_factory=InventoryAvailabilityQueryService,
            replenishment_query_factory=ReplenishmentQueryService,
            count_query_factory=CountQueryService)
        ok, message, _ = pres.generate_adjustment_from_count(count_id="c-1")
        assert not ok
        assert "no disponible" in message


class TestWarehouseAndLocationCommands:
    """P0-C (Almacenes/Ubicaciones) — crear/activar/bloquear son comandos
    reales; antes de esta slice la página de Almacenes no tenía alta
    (hallazgo explícito del audit, §7.4) y Ubicaciones no podía elegir
    almacén (quedaba siempre vacía fuera de los tests)."""

    def test_create_warehouse_via_presenter(self, conn):
        pres = _presenter(conn)
        ok, message, data = pres.create_warehouse(
            code="WH-9", name="Bodega 9", warehouse_type="CENTRAL")
        assert ok, message
        assert data.get("entity_id")
        options = pres.warehouse_options()
        assert any(o.id == data["entity_id"] for o in options)

    def test_create_warehouse_without_code_or_name_fails(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.create_warehouse(
            code="", name="Bodega 9", warehouse_type="CENTRAL")
        assert not ok
        assert "Captura" in message

    def test_create_warehouse_invalid_type_fails(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.create_warehouse(
            code="WH-9", name="Bodega 9", warehouse_type="NOT_A_TYPE")
        assert not ok
        assert "Tipo" in message

    def test_create_warehouse_unavailable_when_not_wired(self, conn):
        pres = InventoryPresenter(
            connection_provider=lambda: conn,
            availability_service_factory=InventoryAvailabilityQueryService,
            replenishment_query_factory=ReplenishmentQueryService)
        ok, message, _ = pres.create_warehouse(
            code="WH-9", name="Bodega 9", warehouse_type="CENTRAL")
        assert not ok
        assert "no disponible" in message

    def test_set_warehouse_status_blocks_and_activates(self, conn):
        pres = _presenter(conn)
        wid = CreateWarehouseUseCase().execute(
            conn, code="WH-1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id
        ok, message, _ = pres.set_warehouse_status(
            warehouse_id=wid, activate=False, reason="Mantenimiento")
        assert ok, message
        rows = WarehouseQueryService(conn).list_warehouses(branch_id="b1")
        assert rows[0]["status"] == "BLOCKED"
        ok, message, _ = pres.set_warehouse_status(warehouse_id=wid, activate=True)
        assert ok, message
        rows = WarehouseQueryService(conn).list_warehouses(branch_id="b1")
        assert rows[0]["status"] == "ACTIVE"

    def test_set_warehouse_status_without_selection_does_not_call_backend(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.set_warehouse_status(warehouse_id="", activate=True)
        assert not ok
        assert "Selecciona" in message

    def test_set_warehouse_status_unavailable_when_not_wired(self, conn):
        pres = InventoryPresenter(
            connection_provider=lambda: conn,
            availability_service_factory=InventoryAvailabilityQueryService,
            replenishment_query_factory=ReplenishmentQueryService)
        ok, message, _ = pres.set_warehouse_status(warehouse_id="w-1", activate=True)
        assert not ok
        assert "no disponible" in message

    def test_warehouse_options_lists_branch_warehouses(self, conn):
        pres = _presenter(conn)
        CreateWarehouseUseCase().execute(
            conn, code="WH-1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1")
        options = pres.warehouse_options()
        assert len(options) == 1
        assert "WH-1" in options[0].label

    def test_create_warehouse_persists_temperature_and_capacity(self, conn):
        pres = _presenter(conn)
        ok, message, data = pres.create_warehouse(
            code="WH-COLD", name="Frío", warehouse_type="COLD_STORAGE",
            temperature_profile="0-4C", capacity=Decimal("30"), capacity_uom="m3")
        assert ok, message
        row = pres.warehouse_detail(warehouse_id=data["entity_id"])
        assert row["temperature_profile"] == "0-4C"
        assert row["capacity"] == "30"
        assert row["capacity_uom"] == "m3"

    def test_update_warehouse_via_presenter(self, conn):
        pres = _presenter(conn)
        wid = CreateWarehouseUseCase().execute(
            conn, code="WH-1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id
        ok, message, _ = pres.update_warehouse(
            warehouse_id=wid, name="Central renombrado", capacity=Decimal("15"))
        assert ok, message
        row = pres.warehouse_detail(warehouse_id=wid)
        assert row["name"] == "Central renombrado"
        assert row["capacity"] == "15"

    def test_update_warehouse_without_selection_does_not_call_backend(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.update_warehouse(warehouse_id="", name="x")
        assert not ok
        assert "Selecciona" in message

    def test_deactivate_warehouse_via_presenter(self, conn):
        pres = _presenter(conn)
        wid = CreateWarehouseUseCase().execute(
            conn, code="WH-1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id
        ok, message, _ = pres.deactivate_warehouse(warehouse_id=wid, reason="cierre")
        assert ok, message
        rows = WarehouseQueryService(conn).list_warehouses(branch_id="b1")
        assert rows[0]["status"] == "INACTIVE"

    def test_zones_and_create_zone_via_presenter(self, conn):
        pres = _presenter(conn)
        wid = CreateWarehouseUseCase().execute(
            conn, code="WH-1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id
        assert pres.zones(warehouse_id=wid).total == 0
        ok, message, _ = pres.create_zone(
            warehouse_id=wid, code="Z1", name="Recepción", zone_type="RECEIVING")
        assert ok, message
        assert pres.zones(warehouse_id=wid).total == 1

    def test_create_zone_invalid_type_fails(self, conn):
        pres = _presenter(conn)
        wid = CreateWarehouseUseCase().execute(
            conn, code="WH-1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id
        ok, message, _ = pres.create_zone(
            warehouse_id=wid, code="Z1", name="x", zone_type="NOT_A_TYPE")
        assert not ok
        assert "Tipo" in message

    def test_capabilities_reflect_session_grants(self, conn):
        from backend.application.inventory.permissions import InventoryPermissions

        session = _Session(frozenset({InventoryPermissions.WAREHOUSE_CREATE}))
        pres = _presenter(conn, session=session)
        caps = pres.capabilities()
        assert caps.warehouse_create
        assert not caps.warehouse_edit
        assert not caps.warehouse_deactivate

    def test_capabilities_without_session_are_all_false(self, conn):
        pres = InventoryPresenter(
            connection_provider=lambda: conn,
            availability_service_factory=InventoryAvailabilityQueryService,
            replenishment_query_factory=ReplenishmentQueryService)
        caps = pres.capabilities()
        assert not caps.module_view and not caps.warehouse_create

    def test_create_location_via_presenter(self, conn):
        pres = _presenter(conn)
        wid = CreateWarehouseUseCase().execute(
            conn, code="WH-1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id
        ok, message, data = pres.create_location(
            warehouse_id=wid, code="A1", name="Pasillo 1")
        assert ok, message
        assert data.get("entity_id")
        options = pres.location_options(warehouse_id=wid)
        assert any(o.id == data["entity_id"] for o in options)

    def test_create_sub_location_with_parent(self, conn):
        pres = _presenter(conn)
        wid = CreateWarehouseUseCase().execute(
            conn, code="WH-1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id
        parent_id = CreateLocationUseCase().execute(
            conn, warehouse_id=wid, code="A1", name="Pasillo 1",
            actor_user_id="u1").entity_id
        ok, message, data = pres.create_location(
            warehouse_id=wid, code="A1-R1", name="Rack 1", level=1,
            parent_location_id=parent_id)
        assert ok, message
        tree = pres.location_tree(warehouse_id=wid)
        # §20: + las ubicaciones técnicas auto-aprovisionadas al crear el almacén.
        assert tree.total == 2 + len(TechnicalLocationType)

    def test_create_location_without_code_or_name_fails(self, conn):
        pres = _presenter(conn)
        wid = CreateWarehouseUseCase().execute(
            conn, code="WH-1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id
        ok, message, _ = pres.create_location(warehouse_id=wid, code="", name="Pasillo 1")
        assert not ok
        assert "Captura" in message

    def test_create_location_without_warehouse_fails(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.create_location(warehouse_id="", code="A1", name="Pasillo 1")
        assert not ok
        assert "Selecciona" in message

    def test_create_location_unavailable_when_not_wired(self, conn):
        pres = InventoryPresenter(
            connection_provider=lambda: conn,
            availability_service_factory=InventoryAvailabilityQueryService,
            replenishment_query_factory=ReplenishmentQueryService)
        ok, message, _ = pres.create_location(warehouse_id="w-1", code="A1", name="Pasillo 1")
        assert not ok
        assert "no disponible" in message

    def test_create_location_persists_capacity(self, conn):
        pres = _presenter(conn)
        wid = CreateWarehouseUseCase().execute(
            conn, code="WH-1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id
        ok, message, data = pres.create_location(
            warehouse_id=wid, code="A1", name="Pasillo 1", capacity=Decimal("9.5"))
        assert ok, message
        row = pres.location_detail(location_id=data["entity_id"])
        assert row["capacity"] == "9.5"

    def test_update_location_via_presenter(self, conn):
        pres = _presenter(conn)
        wid = CreateWarehouseUseCase().execute(
            conn, code="WH-1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id
        lid = CreateLocationUseCase().execute(
            conn, warehouse_id=wid, code="A1", name="Pasillo 1",
            actor_user_id="u1").entity_id
        ok, message, _ = pres.update_location(
            location_id=lid, name="Pasillo 1 renombrado", capacity=Decimal("3"))
        assert ok, message
        row = pres.location_detail(location_id=lid)
        assert row["name"] == "Pasillo 1 renombrado"
        assert row["capacity"] == "3"

    def test_deactivate_location_via_presenter(self, conn):
        pres = _presenter(conn)
        wid = CreateWarehouseUseCase().execute(
            conn, code="WH-1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id
        lid = CreateLocationUseCase().execute(
            conn, warehouse_id=wid, code="A1", name="Pasillo 1",
            actor_user_id="u1").entity_id
        ok, message, _ = pres.deactivate_location(location_id=lid, reason="fuera de uso")
        assert ok, message
        row = pres.location_detail(location_id=lid)
        assert row["status"] == "INACTIVE"

    def test_set_location_status_blocks_and_activates(self, conn):
        pres = _presenter(conn)
        wid = CreateWarehouseUseCase().execute(
            conn, code="WH-1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id
        lid = CreateLocationUseCase().execute(
            conn, warehouse_id=wid, code="A1", name="Pasillo 1",
            actor_user_id="u1").entity_id
        # §20: el almacén también trae sus ubicaciones técnicas auto-aprovisionadas
        # (siempre activas) — se filtra a la manual "A1" para no confundirlas.
        def manual_options():
            return [o for o in pres.location_options(warehouse_id=wid)
                    if not o.label.startswith("TECH:")]

        ok, message, _ = pres.set_location_status(
            location_id=lid, activate=False, reason="Reacomodo")
        assert ok, message
        assert manual_options() == []  # bloqueada, ya no activa
        ok, message, _ = pres.set_location_status(location_id=lid, activate=True)
        assert ok, message
        assert len(manual_options()) == 1

    def test_set_location_status_without_selection_does_not_call_backend(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.set_location_status(location_id="", activate=True)
        assert not ok
        assert "Selecciona" in message

    def test_set_location_status_unavailable_when_not_wired(self, conn):
        pres = InventoryPresenter(
            connection_provider=lambda: conn,
            availability_service_factory=InventoryAvailabilityQueryService,
            replenishment_query_factory=ReplenishmentQueryService)
        ok, message, _ = pres.set_location_status(location_id="l-1", activate=True)
        assert not ok
        assert "no disponible" in message

    def test_warehouse_options_empty_when_not_wired(self, conn):
        pres = InventoryPresenter(
            connection_provider=lambda: conn,
            availability_service_factory=InventoryAvailabilityQueryService,
            replenishment_query_factory=ReplenishmentQueryService)
        assert pres.warehouse_options() == []


class TestPagesSmoke:
    def test_pages_build_and_refresh(self, conn):
        pytest.importorskip("PyQt5")
        from PyQt5.QtWidgets import QApplication
        # NOTE: InventoryAnalyticsPage is intentionally excluded — it builds
        # HtmlChartView (QtWebEngine), which hangs under headless offscreen. Its
        # data path is covered by test_analytics_kpis_and_export via the presenter.
        from frontend.desktop.modules.inventory.pages import (
            InventoryDashboardPage,
            LocationsPage,
            ReplenishmentPage,
            WarehousesPage,
        )
        _seed(conn)
        wid = CreateWarehouseUseCase().execute(
            conn, code="WH1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id
        CreateLocationUseCase().execute(
            conn, warehouse_id=wid, code="A1", name="Pasillo", actor_user_id="u1")
        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        pres.generate_suggestions()
        dash = InventoryDashboardPage(pres, product_ids=["p1"])
        dash.refresh()
        assert dash._table.rowCount() == 1
        page = ReplenishmentPage(pres)
        page.refresh()
        assert page._table.rowCount() == 1
        wh_page = WarehousesPage(pres)
        wh_page.refresh()
        assert wh_page._table.rowCount() == 1
        loc_page = LocationsPage(pres, warehouse_id=wid)
        loc_page.refresh()
        # §20: + las ubicaciones técnicas auto-aprovisionadas al crear el almacén.
        assert loc_page._table.rowCount() == 1 + len(TechnicalLocationType)

    def test_quarantine_page_release_action_calls_presenter_and_refreshes(self, conn):
        """P0-B: clicking Liberar with a row selected posts the real command
        and the table drops the row — no manual refresh() call needed after."""
        pytest.importorskip("PyQt5")
        from unittest.mock import patch

        from PyQt5.QtWidgets import QApplication, QDialog

        from backend.domain.inventory.enums import QuarantineReason
        from frontend.desktop.modules.inventory.pages import QuarantinePage

        _seed(conn)
        result = QuarantineStockUseCase().execute(
            conn, product_id="p1", branch_id="b1", warehouse_id="w1",
            reason=QuarantineReason.QUALITY_FAILURE, quantity=Decimal("2"),
            operation_id="q-page-1", actor_user_id="qa", location_id="loc1")
        assert result.success, result.message

        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        page = QuarantinePage(pres)
        page.refresh()
        assert page._table.rowCount() == 1
        page._table.selectRow(0)

        with patch("frontend.desktop.modules.inventory.pages.quarantine_page"
                   ".ConfirmationDialog.exec_", return_value=QDialog.Accepted), \
             patch("frontend.desktop.modules.inventory.pages.quarantine_page"
                   ".QMessageBox.information"):
            page._on_release()

        assert page._table.rowCount() == 0
        assert pres.quarantines().total == 0

    def test_quarantine_page_requires_selection_before_acting(self, conn):
        """No row selected → the page warns and never calls the presenter."""
        pytest.importorskip("PyQt5")
        from unittest.mock import patch

        from PyQt5.QtWidgets import QApplication

        from frontend.desktop.modules.inventory.pages import QuarantinePage

        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        page = QuarantinePage(pres)
        page.refresh()

        with patch("frontend.desktop.modules.inventory.pages.quarantine_page"
                   ".QMessageBox.information") as info, \
             patch.object(pres, "release_quarantine") as release:
            page._on_release()
        info.assert_called_once()
        release.assert_not_called()
        del app

    def test_adjustments_page_approve_action_calls_presenter_and_refreshes(self, conn):
        """P0-C: clicking Aprobar with a row selected posts the real command
        and the table reflects the posted status after refresh."""
        pytest.importorskip("PyQt5")
        from unittest.mock import patch

        from PyQt5.QtWidgets import QApplication, QDialog

        from backend.domain.inventory.enums import AdjustmentReason
        from frontend.desktop.modules.inventory.pages import AdjustmentsPage

        result = CreateAdjustmentUseCase().execute(
            conn, folio="AJ-PAGE-1", branch_id="b1", warehouse_id="w1",
            reason=AdjustmentReason.SYSTEM_CORRECTION, operation_id="adj-page-1",
            actor_user_id="qa",
            lines=[{"product_id": "p1", "quantity_delta": Decimal("3")}])
        assert result.success, result.message

        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        page = AdjustmentsPage(pres)
        page.refresh()
        assert page._table.rowCount() == 1
        page._table.selectRow(0)

        with patch("frontend.desktop.modules.inventory.pages.adjustments_page"
                   ".ConfirmationDialog.exec_", return_value=QDialog.Accepted), \
             patch("frontend.desktop.modules.inventory.pages.adjustments_page"
                   ".QMessageBox.information"):
            page._on_approve()

        rows = AdjustmentQueryService(conn).list_recent(branch_id="b1")
        assert rows[0]["status"] == "APPROVED"

    def test_adjustments_page_requires_selection_before_acting(self, conn):
        """No row selected → the page warns and never calls the presenter."""
        pytest.importorskip("PyQt5")
        from unittest.mock import patch

        from PyQt5.QtWidgets import QApplication

        from frontend.desktop.modules.inventory.pages import AdjustmentsPage

        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        page = AdjustmentsPage(pres)
        page.refresh()

        with patch("frontend.desktop.modules.inventory.pages.adjustments_page"
                   ".QMessageBox.information") as info, \
             patch.object(pres, "approve_adjustment") as approve:
            page._on_approve()
        info.assert_called_once()
        approve.assert_not_called()
        del app

    def test_adjustments_page_create_action_calls_presenter_and_refreshes(self, conn):
        """P0-C: Nuevo ajuste captures product/reason/direction/quantity via
        the dialog and hands the signed delta to the presenter."""
        pytest.importorskip("PyQt5")
        from unittest.mock import MagicMock, patch

        from PyQt5.QtWidgets import QApplication, QDialog

        from frontend.desktop.modules.inventory.pages import AdjustmentsPage

        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        page = AdjustmentsPage(pres)
        page.refresh()

        dlg = MagicMock()
        dlg.exec_.return_value = QDialog.Accepted
        dlg.product_id.return_value = "p1"
        dlg.reason_code.return_value = "SYSTEM_CORRECTION"
        dlg.quantity_delta.return_value = Decimal("4")
        dlg.note.return_value = ""

        with patch("frontend.desktop.modules.inventory.pages.adjustments_page"
                   ".CreateAdjustmentDialog", return_value=dlg), \
             patch("frontend.desktop.modules.inventory.pages.adjustments_page"
                   ".QMessageBox.information"):
            page._on_create()

        assert page._table.rowCount() == 1

    def test_adjustments_page_reverse_action_calls_presenter(self, conn):
        pytest.importorskip("PyQt5")
        from unittest.mock import MagicMock, patch

        from PyQt5.QtWidgets import QApplication, QDialog

        from backend.domain.inventory.enums import AdjustmentReason
        from frontend.desktop.modules.inventory.pages import AdjustmentsPage

        result = CreateAdjustmentUseCase().execute(
            conn, folio="AJ-PAGE-2", branch_id="b1", warehouse_id="w1",
            reason=AdjustmentReason.SYSTEM_CORRECTION, operation_id="adj-page-2",
            actor_user_id="qa",
            lines=[{"product_id": "p1", "quantity_delta": Decimal("3")}])
        assert result.success, result.message
        post = PostAdjustmentUseCase().execute(
            conn, adjustment_id=result.entity_id, operation_id="adj-page-2-post",
            actor_user_id="qa")
        assert post.success, post.message

        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        page = AdjustmentsPage(pres)
        page.refresh()
        page._table.selectRow(0)

        dlg = MagicMock()
        dlg.exec_.return_value = QDialog.Accepted
        dlg.reason.return_value = "Error de captura"

        with patch("frontend.desktop.modules.inventory.pages.adjustments_page"
                   ".ReverseAdjustmentDialog", return_value=dlg), \
             patch("frontend.desktop.modules.inventory.pages.adjustments_page"
                   ".QMessageBox.information"):
            page._on_reverse()

        dto = InventoryAvailabilityQueryService(conn).get_availability(
            product_id="p1", branch_id="b1", warehouse_id="w1")
        assert dto.on_hand == Decimal("0")
        del app

    def test_counts_page_create_action_calls_presenter_and_refreshes(self, conn):
        """P0-C (Conteos): Nuevo conteo captura producto/tipo/modalidad vía el
        diálogo y arranca un conteo real en progreso."""
        pytest.importorskip("PyQt5")
        from unittest.mock import MagicMock, patch

        from PyQt5.QtWidgets import QApplication, QDialog

        from frontend.desktop.modules.inventory.pages import CountsPage

        _seed(conn)
        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        page = CountsPage(pres)
        page.refresh()

        dlg = MagicMock()
        dlg.exec_.return_value = QDialog.Accepted
        dlg.product_id.return_value = "p1"
        dlg.count_type_code.return_value = "CYCLE_COUNT"
        dlg.blind.return_value = True

        with patch("frontend.desktop.modules.inventory.pages.counts_page"
                   ".CreateCountDialog", return_value=dlg), \
             patch("frontend.desktop.modules.inventory.pages.counts_page"
                   ".QMessageBox.information"):
            page._on_create()

        assert page._table.rowCount() == 1

    def test_counts_page_record_action_calls_presenter_and_captures_line(self, conn):
        """P0-C (Conteos): Capturar toma la cantidad del diálogo y la aplica a
        la única línea del conteo seleccionado."""
        pytest.importorskip("PyQt5")
        from unittest.mock import MagicMock, patch

        from PyQt5.QtWidgets import QApplication, QDialog

        from backend.domain.inventory.enums import CountType
        from frontend.desktop.modules.inventory.pages import CountsPage

        _seed(conn)
        result = CreateCountUseCase().execute(
            conn, folio="CT-PAGE-1", count_type=CountType.CYCLE_COUNT,
            branch_id="b1", warehouse_id="w1", scope_lines=[{"product_id": "p1"}],
            operation_id="cnt-page-1", actor_user_id="qa", blind=True)
        assert result.success, result.message

        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        page = CountsPage(pres)
        page.refresh()
        page._table.selectRow(0)

        record_dlg = MagicMock()
        record_dlg.exec_.return_value = QDialog.Accepted
        record_dlg.counted_quantity.return_value = Decimal("4")
        with patch("frontend.desktop.modules.inventory.pages.counts_page"
                   ".RecordCountDialog", return_value=record_dlg), \
             patch("frontend.desktop.modules.inventory.pages.counts_page"
                   ".QMessageBox.information"):
            page._on_record()

        lines = CountQueryService(conn).list_lines(count_id=result.entity_id)
        assert lines[0]["counted"] is True
        del app

    def test_counts_page_confirm_approve_and_generate_adjustment(self, conn):
        """P0-C (Conteos): confirmar, aprobar y generar el ajuste desde la
        página, sobre un conteo ya capturado por otro actor (segregación real:
        quien contó -"qa"- no es quien aprueba desde la sesión del presenter
        -"u1"-)."""
        pytest.importorskip("PyQt5")
        from unittest.mock import patch

        from PyQt5.QtWidgets import QApplication, QDialog

        from backend.domain.inventory.enums import CountType
        from frontend.desktop.modules.inventory.pages import CountsPage

        _seed(conn)
        result = CreateCountUseCase().execute(
            conn, folio="CT-PAGE-2", count_type=CountType.CYCLE_COUNT,
            branch_id="b1", warehouse_id="w1", scope_lines=[{"product_id": "p1"}],
            operation_id="cnt-page-2", actor_user_id="qa", blind=True)
        assert result.success, result.message
        lines = CountQueryService(conn).list_lines(count_id=result.entity_id)
        RecordCountUseCase().execute(
            conn, count_id=result.entity_id, line_id=lines[0]["id"],
            counted_quantity=Decimal("4"), operation_id="cnt-page-2-rec",
            actor_user_id="qa")

        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        page = CountsPage(pres)
        page.refresh()
        page._table.selectRow(0)

        with patch("frontend.desktop.modules.inventory.pages.counts_page"
                   ".ConfirmationDialog.exec_", return_value=QDialog.Accepted), \
             patch("frontend.desktop.modules.inventory.pages.counts_page"
                   ".QMessageBox.information"):
            page._on_confirm()
            page._table.selectRow(0)
            page._on_approve()
            page._table.selectRow(0)
            page._on_generate_adjustment()

        rows = CountQueryService(conn).list_recent(branch_id="b1")
        assert rows[0]["status"] == "POSTED"  # generar ajuste cierra el conteo
        assert pres.adjustments().total == 1
        del app

    def test_counts_page_requires_selection_before_acting(self, conn):
        """No row selected → the page warns and never calls the presenter."""
        pytest.importorskip("PyQt5")
        from unittest.mock import patch

        from PyQt5.QtWidgets import QApplication

        from frontend.desktop.modules.inventory.pages import CountsPage

        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        page = CountsPage(pres)
        page.refresh()

        with patch("frontend.desktop.modules.inventory.pages.counts_page"
                   ".QMessageBox.information") as info, \
             patch.object(pres, "confirm_count") as confirm:
            page._on_confirm()
        info.assert_called_once()
        confirm.assert_not_called()
        del app

    def test_warehouses_page_create_action_calls_presenter_and_refreshes(self, conn):
        pytest.importorskip("PyQt5")
        from unittest.mock import MagicMock, patch

        from PyQt5.QtWidgets import QApplication, QDialog

        from frontend.desktop.modules.inventory.pages import WarehousesPage

        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        page = WarehousesPage(pres)
        page.refresh()

        dlg = MagicMock()
        dlg.exec_.return_value = QDialog.Accepted
        dlg.code.return_value = "WH-9"
        dlg.name.return_value = "Bodega 9"
        dlg.warehouse_type.return_value = "CENTRAL"
        dlg.temperature_profile.return_value = ""
        dlg.capacity.return_value = None
        dlg.capacity_uom.return_value = ""

        with patch("frontend.desktop.modules.inventory.pages.warehouses_page"
                   ".CreateWarehouseDialog", return_value=dlg), \
             patch("frontend.desktop.modules.inventory.pages.warehouses_page"
                   ".QMessageBox.information"):
            page._on_create()

        assert page._table.rowCount() == 1
        del app

    def test_warehouses_page_block_and_activate_via_toolbar(self, conn):
        pytest.importorskip("PyQt5")
        from unittest.mock import MagicMock, patch

        from PyQt5.QtWidgets import QApplication, QDialog

        from frontend.desktop.modules.inventory.pages import WarehousesPage

        wid = CreateWarehouseUseCase().execute(
            conn, code="WH-1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id

        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        page = WarehousesPage(pres)
        page.refresh()
        page._table.selectRow(0)

        block_dlg = MagicMock()
        block_dlg.exec_.return_value = QDialog.Accepted
        block_dlg.reason.return_value = "Mantenimiento"
        with patch("frontend.desktop.modules.inventory.pages.warehouses_page"
                   ".BlockReasonDialog", return_value=block_dlg), \
             patch("frontend.desktop.modules.inventory.pages.warehouses_page"
                   ".QMessageBox.information"):
            page._on_block()
        rows = WarehouseQueryService(conn).list_warehouses(branch_id="b1")
        assert rows[0]["status"] == "BLOCKED"

        page.refresh()
        page._table.selectRow(0)
        with patch("frontend.desktop.modules.inventory.pages.warehouses_page"
                   ".ConfirmationDialog.exec_", return_value=QDialog.Accepted), \
             patch("frontend.desktop.modules.inventory.pages.warehouses_page"
                   ".QMessageBox.information"):
            page._on_activate()
        rows = WarehouseQueryService(conn).list_warehouses(branch_id="b1")
        assert rows[0]["status"] == "ACTIVE"
        assert wid == rows[0]["id"]
        del app

    def test_warehouses_page_double_click_toggles_status(self, conn):
        pytest.importorskip("PyQt5")
        from unittest.mock import patch

        from PyQt5.QtWidgets import QApplication, QDialog

        from frontend.desktop.modules.inventory.pages import WarehousesPage

        CreateWarehouseUseCase().execute(
            conn, code="WH-1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1")

        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        page = WarehousesPage(pres)
        page.refresh()

        with patch("frontend.desktop.modules.inventory.pages.warehouses_page"
                   ".ConfirmationDialog.exec_", return_value=QDialog.Accepted), \
             patch("frontend.desktop.modules.inventory.pages.warehouses_page"
                   ".QMessageBox.information"):
            page._on_double_click(0, 0)  # activo → bloquea con confirmación

        rows = WarehouseQueryService(conn).list_warehouses(branch_id="b1")
        assert rows[0]["status"] == "BLOCKED"
        del app

    def test_warehouses_page_requires_selection_before_acting(self, conn):
        pytest.importorskip("PyQt5")
        from unittest.mock import patch

        from PyQt5.QtWidgets import QApplication

        from frontend.desktop.modules.inventory.pages import WarehousesPage

        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        page = WarehousesPage(pres)
        page.refresh()

        with patch("frontend.desktop.modules.inventory.pages.warehouses_page"
                   ".QMessageBox.information") as info, \
             patch.object(pres, "set_warehouse_status") as set_status:
            page._on_block()
        info.assert_called_once()
        set_status.assert_not_called()
        del app

    def test_locations_page_create_root_action(self, conn):
        pytest.importorskip("PyQt5")
        from unittest.mock import MagicMock, patch

        from PyQt5.QtWidgets import QApplication, QDialog

        from frontend.desktop.modules.inventory.pages import LocationsPage

        wid = CreateWarehouseUseCase().execute(
            conn, code="WH-1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id

        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        page = LocationsPage(pres, warehouse_id=wid)
        page.refresh()
        assert page.warehouse_combo.count() == 2  # placeholder + único almacén

        dlg = MagicMock()
        dlg.exec_.return_value = QDialog.Accepted
        dlg.code.return_value = "A1"
        dlg.name.return_value = "Pasillo 1"
        dlg.level.return_value = 0
        dlg.capacity.return_value = None

        with patch("frontend.desktop.modules.inventory.pages.locations_page"
                   ".CreateLocationDialog", return_value=dlg), \
             patch("frontend.desktop.modules.inventory.pages.locations_page"
                   ".QMessageBox.information"):
            page._on_create()

        # §20: + las ubicaciones técnicas auto-aprovisionadas al crear el almacén.
        assert page._table.rowCount() == 1 + len(TechnicalLocationType)
        del app

    def test_locations_page_context_menu_creates_sub_location(self, conn):
        """P0-C: el menú contextual arma la jerarquía real (parent_location_id),
        no sólo repite el botón de la barra de herramientas."""
        pytest.importorskip("PyQt5")
        from unittest.mock import MagicMock, patch

        from PyQt5.QtWidgets import QApplication, QDialog

        from frontend.desktop.modules.inventory.pages import LocationsPage

        wid = CreateWarehouseUseCase().execute(
            conn, code="WH-1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id
        parent_id = CreateLocationUseCase().execute(
            conn, warehouse_id=wid, code="A1", name="Pasillo 1",
            actor_user_id="u1").entity_id

        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        page = LocationsPage(pres, warehouse_id=wid)
        page.refresh()
        # §20: + las ubicaciones técnicas auto-aprovisionadas al crear el almacén.
        assert page._table.rowCount() == 1 + len(TechnicalLocationType)

        dlg = MagicMock()
        dlg.exec_.return_value = QDialog.Accepted
        dlg.code.return_value = "A1-R1"
        dlg.name.return_value = "Rack 1"
        dlg.level.return_value = 1
        dlg.capacity.return_value = None

        with patch("frontend.desktop.modules.inventory.pages.locations_page"
                   ".CreateLocationDialog", return_value=dlg), \
             patch("frontend.desktop.modules.inventory.pages.locations_page"
                   ".QMessageBox.information"):
            page._on_create(parent_location_id=parent_id, parent_label="A1")

        assert page._table.rowCount() == 2 + len(TechnicalLocationType)
        tree = pres.location_tree(warehouse_id=wid)
        assert tree.total == 2 + len(TechnicalLocationType)
        assert parent_id in tree.row_ids
        del app

    def test_locations_page_block_and_activate(self, conn):
        pytest.importorskip("PyQt5")
        from unittest.mock import MagicMock, patch

        from PyQt5.QtWidgets import QApplication, QDialog

        from frontend.desktop.modules.inventory.pages import LocationsPage

        wid = CreateWarehouseUseCase().execute(
            conn, code="WH-1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id
        CreateLocationUseCase().execute(
            conn, warehouse_id=wid, code="A1", name="Pasillo 1", actor_user_id="u1")

        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        page = LocationsPage(pres, warehouse_id=wid)
        page.refresh()
        page._table.selectRow(0)

        block_dlg = MagicMock()
        block_dlg.exec_.return_value = QDialog.Accepted
        block_dlg.reason.return_value = "Reacomodo"
        with patch("frontend.desktop.modules.inventory.pages.locations_page"
                   ".BlockReasonDialog", return_value=block_dlg), \
             patch("frontend.desktop.modules.inventory.pages.locations_page"
                   ".QMessageBox.information"):
            page._on_block()
        # §20: el almacén también trae ubicaciones técnicas (siempre activas) —
        # se filtra a la manual "A1" para no confundirlas.
        manual = [o for o in pres.location_options(warehouse_id=wid)
                  if not o.label.startswith("TECH:")]
        assert manual == []

        page.refresh()
        page._table.selectRow(0)
        with patch("frontend.desktop.modules.inventory.pages.locations_page"
                   ".ConfirmationDialog.exec_", return_value=QDialog.Accepted), \
             patch("frontend.desktop.modules.inventory.pages.locations_page"
                   ".QMessageBox.information"):
            page._on_activate()
        manual = [o for o in pres.location_options(warehouse_id=wid)
                  if not o.label.startswith("TECH:")]
        assert len(manual) == 1
        del app

    def test_locations_page_double_click_toggles_status(self, conn):
        pytest.importorskip("PyQt5")
        from unittest.mock import patch

        from PyQt5.QtWidgets import QApplication, QDialog

        from frontend.desktop.modules.inventory.pages import LocationsPage

        wid = CreateWarehouseUseCase().execute(
            conn, code="WH-1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id
        CreateLocationUseCase().execute(
            conn, warehouse_id=wid, code="A1", name="Pasillo 1", actor_user_id="u1")

        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        page = LocationsPage(pres, warehouse_id=wid)
        page.refresh()

        with patch("frontend.desktop.modules.inventory.pages.locations_page"
                   ".ConfirmationDialog.exec_", return_value=QDialog.Accepted), \
             patch("frontend.desktop.modules.inventory.pages.locations_page"
                   ".QMessageBox.information"):
            page._on_double_click(0, 0)

        # §20: el almacén también trae ubicaciones técnicas (siempre activas) —
        # se filtra a la manual "A1" para no confundirlas.
        manual = [o for o in pres.location_options(warehouse_id=wid)
                  if not o.label.startswith("TECH:")]
        assert manual == []
        del app

    def test_locations_page_requires_selection_before_acting(self, conn):
        pytest.importorskip("PyQt5")
        from unittest.mock import patch

        from PyQt5.QtWidgets import QApplication

        from frontend.desktop.modules.inventory.pages import LocationsPage

        wid = CreateWarehouseUseCase().execute(
            conn, code="WH-1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id

        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        page = LocationsPage(pres, warehouse_id=wid)
        page.refresh()

        with patch("frontend.desktop.modules.inventory.pages.locations_page"
                   ".QMessageBox.information") as info, \
             patch.object(pres, "set_location_status") as set_status:
            page._on_block()
        info.assert_called_once()
        set_status.assert_not_called()
        del app

    def test_locations_page_warehouse_combo_switches_tree(self, conn):
        pytest.importorskip("PyQt5")
        from PyQt5.QtWidgets import QApplication

        from frontend.desktop.modules.inventory.pages import LocationsPage

        wid1 = CreateWarehouseUseCase().execute(
            conn, code="WH-1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id
        wid2 = CreateWarehouseUseCase().execute(
            conn, code="WH-2", name="Secundario", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id
        CreateLocationUseCase().execute(
            conn, warehouse_id=wid2, code="B1", name="Pasillo B", actor_user_id="u1")

        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        page = LocationsPage(pres, warehouse_id=wid1)
        page.refresh()
        # §20: wid1 no tiene ubicaciones manuales, sólo las técnicas auto-aprovisionadas.
        assert page._table.rowCount() == len(TechnicalLocationType)

        idx = page.warehouse_combo.findData(wid2)
        page.warehouse_combo.setCurrentIndex(idx)
        assert page._table.rowCount() == 1 + len(TechnicalLocationType)
        del app


class TestProductSearchPages:
    """P0-D rollout — Disponibilidad/Lotes/Reservas resolve the product via
    the canonical search (EntitySearchInput + product_options), never a
    hand-typed UUID (§P0-04)."""

    def test_lots_page_refreshes_on_product_selection(self, conn):
        pytest.importorskip("PyQt5")
        from PyQt5.QtWidgets import QApplication

        from backend.application.inventory.use_cases import RegisterInventoryLotUseCase
        from backend.domain.inventory.enums import LotOrigin
        from frontend.desktop.modules.inventory.pages import LotsPage

        RegisterInventoryLotUseCase().execute(
            conn, product_id="p1", lot_code="L-9", origin_type=LotOrigin.PURCHASE,
            operation_id="lot-9", actor_user_id="u1", branch_id="b1",
            expiration_date="2027-01-15")

        app = QApplication.instance() or QApplication([])
        page = LotsPage(_presenter(conn))
        assert page._table.rowCount() == 0  # sin producto seleccionado aún

        page._search.selected.emit("p1")
        assert page._table.rowCount() == 1
        assert page._table.item(0, 0).text() == "L-9"
        del app

    def test_reservations_page_refreshes_on_product_selection(self, conn):
        pytest.importorskip("PyQt5")
        from PyQt5.QtWidgets import QApplication

        from frontend.desktop.modules.inventory.pages import ReservationsPage

        app = QApplication.instance() or QApplication([])
        page = ReservationsPage(_presenter(conn))
        page._search.selected.emit("p1")
        assert page._table.rowCount() == 0  # sin reservas para p1, pero no truena
        assert page._product_id == "p1"
        del app

    def test_availability_page_refreshes_on_product_selection(self, conn):
        pytest.importorskip("PyQt5")
        from PyQt5.QtWidgets import QApplication

        _seed(conn)  # 5 disponibles de p1
        from frontend.desktop.modules.inventory.pages import AvailabilityPage

        app = QApplication.instance() or QApplication([])
        page = AvailabilityPage(_presenter(conn))
        page._search.selected.emit("p1")
        assert page._table.rowCount() > 0
        assert page._product_id == "p1"
        del app

    def test_search_widgets_are_entity_search_not_raw_text(self, conn):
        """§P0-04: Disponibilidad/Lotes/Reservas must resolve the product via
        EntitySearchInput (a real catalog lookup), never a plain SearchInput
        that hands the typed text straight through as product_id."""
        pytest.importorskip("PyQt5")
        from PyQt5.QtWidgets import QApplication

        from frontend.desktop.components.entity_search_input import EntitySearchInput
        from frontend.desktop.modules.inventory.pages import (
            AvailabilityPage,
            LotsPage,
            ReservationsPage,
        )

        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        for page_cls in (AvailabilityPage, LotsPage, ReservationsPage):
            page = page_cls(pres)
            assert isinstance(page._search, EntitySearchInput)
        del app
