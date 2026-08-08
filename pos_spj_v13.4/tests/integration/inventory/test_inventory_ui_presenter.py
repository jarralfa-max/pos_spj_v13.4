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
    CreateLocationUseCase,
    CreateWarehouseUseCase,
    DisposeQuarantineUseCase,
    GenerateReplenishmentSuggestionsUseCase,
    PostInventoryMovementUseCase,
    QuarantineStockUseCase,
    ReleaseQuarantineUseCase,
    SetReplenishmentRuleUseCase,
)
from backend.domain.inventory.enums import WarehouseType
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import MovementType
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from frontend.desktop.modules.inventory.presenter import InventoryPresenter


class _Session:
    user_id = "u1"
    branch_id = "b1"
    warehouse_id = "w1"


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


def _presenter(conn):
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
        session_context=_Session())


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
        CreateCountUseCase().execute(
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
        assert tree.total == 2 and tree.rows[1][0].startswith("· ")


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
        assert loc_page._table.rowCount() == 1

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
