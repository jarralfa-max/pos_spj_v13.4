"""INV-2 — inventory domain base tests.

Warehouse/zone/location entities, Quantity/Weight VOs, the movement (+line)
ledger entry, the balance projection, the negative-inventory and
movement-validation policies, and the canonical event vocabulary. Pure domain.
"""

from decimal import Decimal

import pytest

from backend.domain.inventory.entities import (
    InventoryBalance,
    InventoryMovement,
    InventoryMovementLine,
    StorageLocation,
    Warehouse,
    WarehouseZone,
)
from backend.domain.inventory.enums import (
    InventoryStatus,
    MovementDirection,
    MovementStatus,
    MovementType,
    WarehouseStatus,
    WarehouseType,
    WarehouseZoneType,
    movement_direction,
)
from backend.domain.inventory.events import (
    ALL_INVENTORY_EVENTS,
    InventoryEvents,
    build_event_payload,
)
from backend.domain.inventory.exceptions import (
    InventoryAuthorizationRequiredError,
    InventoryDomainError,
)
from backend.domain.inventory.policies import (
    MovementValidationPolicy,
    NegativeInventoryPolicy,
)
from backend.domain.inventory.value_objects import Quantity, Weight

UUID_LEN = 36


def _line(**kw):
    base = dict(product_id="p1", quantity=Decimal("5"), to_location_id="loc-dest")
    base.update(kw)
    return InventoryMovementLine.create(**base)


def _movement(mtype=MovementType.PURCHASE_RECEIPT, lines=None):
    return InventoryMovement.create(
        movement_type=mtype, branch_id="b1", warehouse_id="w1",
        source_module="procurement", source_document_type="GOODS_RECEIPT",
        source_document_id="gr1", operation_id="op1", created_by_user_id="u1",
        lines=lines if lines is not None else [_line()])


# ── value objects ───────────────────────────────────────────────────────────
class TestValueObjects:
    def test_quantity_rejects_float(self):
        with pytest.raises(InventoryDomainError):
            Quantity(5.0)

    def test_quantity_rejects_negative(self):
        with pytest.raises(InventoryDomainError):
            Quantity(Decimal("-1"))

    def test_quantity_add_subtract_same_unit(self):
        assert Quantity(Decimal("3"), "KG").add(Quantity(Decimal("2"), "KG")).value \
            == Decimal("5")
        with pytest.raises(InventoryDomainError):
            Quantity(Decimal("3"), "KG").add(Quantity(Decimal("2"), "PZA"))

    def test_weight_rejects_float(self):
        with pytest.raises(InventoryDomainError):
            Weight(1.5)


# ── warehouse / zone / location ─────────────────────────────────────────────
class TestWarehouse:
    def test_create_generates_uuid(self):
        wh = Warehouse.create(code="CD01", name="Central", branch_id="b1",
                              warehouse_type=WarehouseType.CENTRAL)
        assert len(wh.id) == UUID_LEN and wh.is_active

    def test_requires_branch(self):
        with pytest.raises(InventoryDomainError):
            Warehouse.create(code="X", name="Y", branch_id="",
                             warehouse_type=WarehouseType.STORE)

    def test_block_activate(self):
        wh = Warehouse.create(code="C", name="N", branch_id="b1",
                             warehouse_type=WarehouseType.STORE)
        wh.block()
        assert wh.status is WarehouseStatus.BLOCKED and not wh.is_active
        wh.activate()
        assert wh.is_active

    def test_zone_and_location_hierarchy(self):
        zone = WarehouseZone.create(warehouse_id="w1", code="COLD", name="Cámara",
                                    zone_type=WarehouseZoneType.COLD)
        loc = StorageLocation.create(warehouse_id="w1", zone_id=zone.id,
                                     code="A-01-01", name="Rack A", level=2)
        assert loc.zone_id == zone.id and loc.level == 2 and loc.is_active

    def test_location_requires_warehouse(self):
        with pytest.raises(InventoryDomainError):
            StorageLocation.create(warehouse_id="", code="A", name="B")


# ── movement (ledger) ───────────────────────────────────────────────────────
class TestMovement:
    def test_line_requires_product(self):
        with pytest.raises(InventoryDomainError):
            InventoryMovementLine.create(product_id="", quantity=Decimal("1"))

    def test_line_requires_positive_quantity_or_weight(self):
        with pytest.raises(InventoryDomainError):
            InventoryMovementLine.create(product_id="p1", quantity=0, weight=0)

    def test_line_rejects_float(self):
        with pytest.raises(InventoryDomainError):
            InventoryMovementLine.create(product_id="p1", quantity=5.0)

    def test_post_requires_lines(self):
        mv = InventoryMovement.create(
            movement_type=MovementType.ADJUSTMENT_IN, branch_id="b1", warehouse_id="w1",
            source_module="inventory", source_document_type="ADJ", source_document_id="a1",
            operation_id="op", created_by_user_id="u1", lines=[])
        with pytest.raises(InventoryDomainError):
            mv.post()

    def test_post_and_reverse_lifecycle(self):
        mv = _movement()
        mv.post()
        assert mv.status is MovementStatus.POSTED
        mv.mark_reversed()
        assert mv.status is MovementStatus.REVERSED
        with pytest.raises(InventoryDomainError):
            mv.post()  # reversed cannot be re-posted

    def test_cannot_add_line_after_post(self):
        mv = _movement()
        mv.post()
        with pytest.raises(InventoryDomainError):
            mv.add_line(_line())

    def test_every_movement_type_has_direction(self):
        for mt in MovementType:
            assert isinstance(movement_direction(mt), MovementDirection)


# ── movement validation policy ──────────────────────────────────────────────
class TestMovementValidation:
    def setup_method(self):
        self.pol = MovementValidationPolicy()

    def test_valid_increase(self):
        self.pol.enforce_valid(_movement())

    def test_missing_source_document(self):
        mv = _movement()
        mv.source_document_id = ""
        with pytest.raises(InventoryDomainError):
            self.pol.enforce_valid(mv)

    def test_increase_requires_destination(self):
        mv = _movement(lines=[_line(to_location_id=None)])
        with pytest.raises(InventoryDomainError):
            self.pol.enforce_valid(mv)

    def test_decrease_requires_origin(self):
        line = InventoryMovementLine.create(
            product_id="p1", quantity=Decimal("2"), from_location_id=None)
        mv = _movement(mtype=MovementType.SALE_ISSUE, lines=[line])
        with pytest.raises(InventoryDomainError):
            self.pol.enforce_valid(mv)

    def test_status_transfer_requires_distinct_statuses(self):
        line = InventoryMovementLine.create(
            product_id="p1", quantity=Decimal("2"),
            from_status=InventoryStatus.AVAILABLE, to_status=InventoryStatus.AVAILABLE)
        mv = _movement(mtype=MovementType.QUALITY_BLOCK, lines=[line])
        with pytest.raises(InventoryDomainError):
            self.pol.enforce_valid(mv)

    def test_status_transfer_ok(self):
        line = InventoryMovementLine.create(
            product_id="p1", quantity=Decimal("2"),
            from_status=InventoryStatus.AVAILABLE,
            to_status=InventoryStatus.QUARANTINED)
        mv = _movement(mtype=MovementType.QUARANTINE_ENTRY, lines=[line])
        self.pol.enforce_valid(mv)


# ── negative inventory policy ───────────────────────────────────────────────
class TestNegativeInventory:
    def setup_method(self):
        self.pol = NegativeInventoryPolicy()

    def test_stays_non_negative_ok(self):
        self.pol.enforce_can_decrease(current_on_hand=Decimal("10"), decrease_by=Decimal("4"))

    def test_negative_not_allowed_blocks(self):
        with pytest.raises(InventoryDomainError):
            self.pol.enforce_can_decrease(
                current_on_hand=Decimal("3"), decrease_by=Decimal("5"))

    def test_negative_allowed_needs_authorization(self):
        with pytest.raises(InventoryAuthorizationRequiredError):
            self.pol.enforce_can_decrease(
                current_on_hand=Decimal("3"), decrease_by=Decimal("5"), allowed=True)

    def test_negative_allowed_and_authorized_ok(self):
        self.pol.enforce_can_decrease(
            current_on_hand=Decimal("3"), decrease_by=Decimal("5"),
            allowed=True, authorized=True)


# ── balance projection ──────────────────────────────────────────────────────
class TestBalance:
    def test_available_is_on_hand_minus_reserved(self):
        bal = InventoryBalance.empty(product_id="p1", branch_id="b1", warehouse_id="w1")
        bal.apply_delta(quantity=Decimal("10"))
        bal.reserve(quantity=Decimal("3"))
        assert bal.available_quantity == Decimal("7")

    def test_non_available_status_is_not_sellable(self):
        bal = InventoryBalance.empty(
            product_id="p1", branch_id="b1", warehouse_id="w1",
            inventory_status=InventoryStatus.QUARANTINED)
        bal.apply_delta(quantity=Decimal("10"))
        assert bal.available_quantity == Decimal("0")

    def test_reserve_beyond_available_raises(self):
        bal = InventoryBalance.empty(product_id="p1", branch_id="b1", warehouse_id="w1")
        bal.apply_delta(quantity=Decimal("5"))
        with pytest.raises(InventoryDomainError):
            bal.reserve(quantity=Decimal("6"))

    def test_release_reservation_floors_at_zero(self):
        bal = InventoryBalance.empty(product_id="p1", branch_id="b1", warehouse_id="w1")
        bal.apply_delta(quantity=Decimal("5"))
        bal.reserve(quantity=Decimal("3"))
        bal.release_reservation(quantity=Decimal("10"))
        assert bal.reserved_quantity == Decimal("0")

    def test_version_increments(self):
        bal = InventoryBalance.empty(product_id="p1", branch_id="b1", warehouse_id="w1")
        v0 = bal.version
        bal.apply_delta(quantity=Decimal("1"))
        assert bal.version == v0 + 1

    def test_balance_rejects_float(self):
        with pytest.raises(InventoryDomainError):
            InventoryBalance.empty(product_id="p1", branch_id="b1",
                                   warehouse_id="w1").apply_delta(quantity=1.0)


# ── events ──────────────────────────────────────────────────────────────────
class TestEvents:
    def test_canonical_events_present(self):
        for e in (InventoryEvents.INVENTORY_MOVEMENT_POSTED,
                  InventoryEvents.INVENTORY_BALANCE_CHANGED,
                  InventoryEvents.INVENTORY_TRANSFER_DISPATCHED,
                  InventoryEvents.INVENTORY_NEGATIVE_DETECTED):
            assert e in ALL_INVENTORY_EVENTS

    def test_legacy_event_names_absent(self):
        for legacy in ("STOCK_ACTUALIZADO", "INVENTARIO_CAMBIADO",
                       "TRASPASO_REALIZADO", "RECEPCION_COMPLETADA"):
            assert legacy not in ALL_INVENTORY_EVENTS

    def test_payload_has_minimum_fields_and_distinct_ids(self):
        p = build_event_payload(
            InventoryEvents.INVENTORY_MOVEMENT_POSTED, operation_id="op1",
            entity_id="mv1", product_id="p1", branch_id="b1", warehouse_id="w1",
            user_id="u1")
        for key in ("event_id", "operation_id", "entity_id", "product_id",
                    "branch_id", "warehouse_id", "user_id", "timestamp", "source_module"):
            assert key in p
        assert p["event_id"] != p["operation_id"] != p["entity_id"]

    def test_unknown_event_rejected(self):
        with pytest.raises(ValueError):
            build_event_payload("NOPE", operation_id="o", entity_id="e")
