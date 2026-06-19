"""Unit and integration tests for the Delivery module refactor.

Tests 6-37 from the refactor spec.
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from core.delivery.application.action_policy import DeliveryActionPolicy
from core.delivery.application.dto import DeliveryItemViewDTO, DeliveryOrderViewDTO
from core.delivery.application.kanban_config import KANBAN_COLUMNS
from core.delivery.application.quantity_formatter import QuantityFormatter
from core.delivery.application.query_service import (
    DeliveryQueryService,
    _map_legacy_status,
    _map_legacy_unit,
)
from core.delivery.domain.value_objects import (
    DeliveryAction,
    DeliveryStatus,
    FulfillmentType,
    PaymentStatus,
    UnitCode,
)
from core.delivery.domain.workflow_policy import DeliveryWorkflowPolicy

# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def policy() -> DeliveryActionPolicy:
    return DeliveryActionPolicy()


@pytest.fixture
def wf_policy() -> DeliveryWorkflowPolicy:
    return DeliveryWorkflowPolicy()


# ── DeliveryActionPolicy tests (6-13) ────────────────────────────────────────

def test_pending_actions(policy):
    """Test 6: PENDING → [START_PREPARATION, CANCEL]"""
    actions = policy.available_actions(
        DeliveryStatus.PENDING, FulfillmentType.DELIVERY, PaymentStatus.PENDING, has_driver=False
    )
    assert DeliveryAction.START_PREPARATION in actions
    assert DeliveryAction.CANCEL in actions
    assert len(actions) == 2


def test_preparing_delivery_no_driver_includes_assign_driver(policy):
    """Test 7: PREPARING + DELIVERY + no driver → includes ASSIGN_DRIVER"""
    actions = policy.available_actions(
        DeliveryStatus.PREPARING, FulfillmentType.DELIVERY, PaymentStatus.PENDING, has_driver=False
    )
    assert DeliveryAction.ASSIGN_DRIVER in actions


def test_preparing_pickup_no_assign_driver(policy):
    """Test 8: PREPARING + PICKUP → no ASSIGN_DRIVER"""
    actions = policy.available_actions(
        DeliveryStatus.PREPARING, FulfillmentType.PICKUP, PaymentStatus.PENDING, has_driver=False
    )
    assert DeliveryAction.ASSIGN_DRIVER not in actions


def test_ready_for_pickup_includes_complete_delivery(policy):
    """Test 9: READY_FOR_PICKUP → includes COMPLETE_DELIVERY"""
    actions = policy.available_actions(
        DeliveryStatus.READY_FOR_PICKUP, FulfillmentType.PICKUP, PaymentStatus.PENDING, has_driver=False
    )
    assert DeliveryAction.COMPLETE_DELIVERY in actions


def test_ready_for_dispatch_includes_assign_driver(policy):
    """Test 10: READY_FOR_DISPATCH → includes ASSIGN_DRIVER"""
    actions = policy.available_actions(
        DeliveryStatus.READY_FOR_DISPATCH, FulfillmentType.DELIVERY, PaymentStatus.PENDING, has_driver=False
    )
    assert DeliveryAction.ASSIGN_DRIVER in actions


def test_assigned_includes_start_route(policy):
    """Test 11: ASSIGNED → includes START_ROUTE"""
    actions = policy.available_actions(
        DeliveryStatus.ASSIGNED, FulfillmentType.DELIVERY, PaymentStatus.PENDING, has_driver=True
    )
    assert DeliveryAction.START_ROUTE in actions


def test_in_transit_includes_complete_delivery(policy):
    """Test 12: IN_TRANSIT → includes COMPLETE_DELIVERY"""
    actions = policy.available_actions(
        DeliveryStatus.IN_TRANSIT, FulfillmentType.DELIVERY, PaymentStatus.PENDING, has_driver=True
    )
    assert DeliveryAction.COMPLETE_DELIVERY in actions


def test_delivered_includes_view_detail_and_print_ticket(policy):
    """Test 13: DELIVERED → includes VIEW_DETAIL, PRINT_TICKET"""
    actions = policy.available_actions(
        DeliveryStatus.DELIVERED, FulfillmentType.DELIVERY, PaymentStatus.PAID, has_driver=True
    )
    assert DeliveryAction.VIEW_DETAIL in actions
    assert DeliveryAction.PRINT_TICKET in actions


# ── QuantityFormatter tests (14-20) ──────────────────────────────────────────

def test_formatter_kg_unit():
    """Test 14: kg unit shows 'kg'"""
    result = QuantityFormatter.format(Decimal("1.0"), UnitCode.KILOGRAM)
    assert result.endswith("kg")


def test_formatter_gram_unit():
    """Test 15: gram unit shows 'g'"""
    result = QuantityFormatter.format(Decimal("100"), UnitCode.GRAM)
    assert result.endswith("g")


def test_formatter_piece_unit():
    """Test 16: piece unit shows 'pza'"""
    result = QuantityFormatter.format(Decimal("3"), UnitCode.PIECE)
    assert result.endswith("pza")


def test_formatter_unit_unit():
    """Test 17: unit shows 'unidad'"""
    result = QuantityFormatter.format(Decimal("2"), UnitCode.UNIT)
    assert result.endswith("unidad")


def test_formatter_box_unit():
    """Test 18: box shows 'caja'"""
    result = QuantityFormatter.format(Decimal("1"), UnitCode.BOX)
    assert result.endswith("caja")


def test_formatter_pack_unit():
    """Test 19: pack shows 'paquete'"""
    result = QuantityFormatter.format(Decimal("5"), UnitCode.PACK)
    assert result.endswith("paquete")


def test_formatter_decimal_precision():
    """Test 20: 0.750 kg → '0.75 kg' (trailing zeros stripped)"""
    result = QuantityFormatter.format(Decimal("0.750"), UnitCode.KILOGRAM)
    assert result == "0.75 kg"


# ── DeliveryWorkflowPolicy tests (21-22) ─────────────────────────────────────

def test_workflow_policy_pickup_confirm_gives_ready_for_pickup(wf_policy):
    """Test 21: PREPARING + PICKUP → READY_FOR_PICKUP on confirm"""
    next_status = wf_policy.next_status_after_confirm_preparation(FulfillmentType.PICKUP)
    assert next_status == DeliveryStatus.READY_FOR_PICKUP


def test_workflow_policy_delivery_confirm_gives_ready_for_dispatch(wf_policy):
    """Test 22: PREPARING + DELIVERY → READY_FOR_DISPATCH on confirm"""
    next_status = wf_policy.next_status_after_confirm_preparation(FulfillmentType.DELIVERY)
    assert next_status == DeliveryStatus.READY_FOR_DISPATCH


# ── DeliveryOrderViewDTO tests (23-24) ───────────────────────────────────────

def test_dto_is_frozen():
    """Test 23: DTO is frozen (immutable)"""
    dto = DeliveryOrderViewDTO(
        order_id="1",
        folio="DEL-001",
        branch_id="1",
        customer_name="Test",
        customer_tel="",
        fulfillment_type=FulfillmentType.DELIVERY,
        status=DeliveryStatus.PENDING,
        status_label_es="Pendiente",
        payment_status=PaymentStatus.PENDING,
        driver_id=None,
        driver_name=None,
        items=(),
        available_actions=(DeliveryAction.START_PREPARATION,),
        created_at="2024-01-01",
        total=Decimal("100"),
    )
    with pytest.raises((AttributeError, TypeError)):
        dto.status = DeliveryStatus.DELIVERED  # type: ignore[misc]


def test_dto_available_actions_comes_from_policy():
    """Test 24: available_actions is a tuple (from policy, not hardcoded)"""
    p = DeliveryActionPolicy()
    actions = p.available_actions(
        DeliveryStatus.PENDING, FulfillmentType.DELIVERY, PaymentStatus.PENDING, has_driver=False
    )
    dto = DeliveryOrderViewDTO(
        order_id="1",
        folio="DEL-001",
        branch_id="1",
        customer_name="Test",
        customer_tel="",
        fulfillment_type=FulfillmentType.DELIVERY,
        status=DeliveryStatus.PENDING,
        status_label_es="Pendiente",
        payment_status=PaymentStatus.PENDING,
        driver_id=None,
        driver_name=None,
        items=(),
        available_actions=actions,
        created_at="2024-01-01",
        total=Decimal("0"),
    )
    assert isinstance(dto.available_actions, tuple)
    assert DeliveryAction.START_PREPARATION in dto.available_actions


# ── Integration tests: DeliveryQueryService (25-29) ──────────────────────────

@pytest.fixture
def in_memory_db():
    """SQLite in-memory DB with minimal delivery schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE delivery_orders (
            id TEXT PRIMARY KEY,
            folio TEXT,
            sucursal_id TEXT,
            cliente_nombre TEXT,
            cliente_tel TEXT,
            delivery_type TEXT DEFAULT 'domicilio',
            estado TEXT DEFAULT 'pendiente',
            pago_metodo TEXT,
            pago_monto REAL DEFAULT 0,
            driver_id TEXT,
            fecha_solicitud TEXT DEFAULT '2024-01-01 10:00:00',
            total REAL DEFAULT 0,
            adjustment_pending INTEGER DEFAULT 0,
            workflow_type TEXT DEFAULT 'delivery'
        );
        CREATE TABLE delivery_items (
            id TEXT PRIMARY KEY,
            delivery_id TEXT,
            producto_id TEXT,
            nombre TEXT,
            cantidad REAL DEFAULT 1,
            prepared_qty REAL,
            precio_unitario REAL DEFAULT 0,
            subtotal REAL DEFAULT 0,
            unidad TEXT DEFAULT 'pza'
        );
        CREATE TABLE productos (
            id TEXT PRIMARY KEY,
            nombre TEXT,
            unidad TEXT,
            stock REAL DEFAULT 0
        );
        INSERT INTO delivery_orders VALUES
            ('order-1','DEL-001','1','Cliente A','5551234567','domicilio','pendiente',NULL,0,NULL,'2024-01-01 10:00:00',100.0,0,'delivery'),
            ('order-2','DEL-002','1','Cliente B','5559876543','pickup','en_ruta','Efectivo',100.0,'drv-1','2024-01-01 11:00:00',200.0,0,'counter');
        INSERT INTO productos VALUES ('prod-1','Pollo','kg',10.0);
        INSERT INTO delivery_items VALUES
            ('item-1','order-1','prod-1','Pollo',1.5,NULL,80.0,120.0,'kg');
    """)
    return conn


def test_query_service_pending_maps_to_pending(in_memory_db):
    """Test 25: Legacy 'pendiente' maps to DeliveryStatus.PENDING"""
    svc = DeliveryQueryService(in_memory_db)
    orders = svc.list_orders()
    pending = [o for o in orders if o.order_id == "order-1"]
    assert len(pending) == 1
    assert pending[0].status == DeliveryStatus.PENDING


def test_query_service_en_ruta_maps_to_in_transit(in_memory_db):
    """Test 26: Legacy 'en_ruta' maps to DeliveryStatus.IN_TRANSIT"""
    svc = DeliveryQueryService(in_memory_db)
    orders = svc.list_orders()
    in_transit = [o for o in orders if o.order_id == "order-2"]
    assert len(in_transit) == 1
    assert in_transit[0].status == DeliveryStatus.IN_TRANSIT


def test_legacy_unit_kg_maps_to_kilogram():
    """Test 27: Unit 'kg' maps to UnitCode.KILOGRAM"""
    assert _map_legacy_unit("kg") == UnitCode.KILOGRAM


def test_legacy_unit_pza_maps_to_piece():
    """Test 28: Unit 'pza' maps to UnitCode.PIECE"""
    assert _map_legacy_unit("pza") == UnitCode.PIECE


def test_query_service_available_actions_populated(in_memory_db):
    """Test 29: available_actions is populated on DTO"""
    svc = DeliveryQueryService(in_memory_db)
    orders = svc.list_orders()
    pending = [o for o in orders if o.order_id == "order-1"]
    assert len(pending) == 1
    dto = pending[0]
    assert isinstance(dto.available_actions, tuple)
    assert len(dto.available_actions) > 0


# ── Kanban column tests (30-37) ───────────────────────────────────────────────

def test_kanban_has_exactly_4_columns():
    """Test 30: Exactly 4 columns defined in KANBAN_COLUMNS"""
    assert len(KANBAN_COLUMNS) == 4


def _statuses_in_column(col_index: int) -> list[DeliveryStatus]:
    return KANBAN_COLUMNS[col_index][1]


def test_pending_in_column_0():
    """Test 31: PENDING in column 0"""
    assert DeliveryStatus.PENDING in _statuses_in_column(0)


def test_preparing_in_column_1():
    """Test 32: PREPARING in column 1"""
    assert DeliveryStatus.PREPARING in _statuses_in_column(1)


def test_ready_for_pickup_in_column_2():
    """Test 33: READY_FOR_PICKUP in column 2"""
    assert DeliveryStatus.READY_FOR_PICKUP in _statuses_in_column(2)


def test_ready_for_dispatch_in_column_2():
    """Test 34: READY_FOR_DISPATCH in column 2"""
    assert DeliveryStatus.READY_FOR_DISPATCH in _statuses_in_column(2)


def test_assigned_in_column_2():
    """Test 35: ASSIGNED in column 2"""
    assert DeliveryStatus.ASSIGNED in _statuses_in_column(2)


def test_in_transit_in_column_2():
    """Test 36: IN_TRANSIT in column 2"""
    assert DeliveryStatus.IN_TRANSIT in _statuses_in_column(2)


def test_delivered_in_column_3():
    """Test 37: DELIVERED in column 3"""
    assert DeliveryStatus.DELIVERED in _statuses_in_column(3)
