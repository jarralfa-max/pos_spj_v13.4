"""INV-21 — slaughter (faena) preparation stub: contracts, planner, events (§33).

This is a FUTURE stub: no schema, no live wiring. The tests prove the vocabulary
exists and that a slaughter flow maps cleanly onto the born-clean primitives.
"""

from decimal import Decimal

import pytest

from backend.application.event_handlers.inventory import SlaughterExecutedStubHandler
from backend.domain.inventory.enums import (
    CarcassState,
    MovementDirection,
    MovementType,
    SlaughterOutputType,
    SlaughterSpecies,
)
from backend.domain.inventory.exceptions import InventoryDomainError
from backend.domain.inventory.slaughter import (
    ALL_SLAUGHTER_EVENTS,
    SLAUGHTER_ENABLED,
    CarcassContract,
    SlaughterEvents,
    SlaughterOrderContract,
    SlaughterOutputContract,
    SlaughterPlanningService,
)


def _order(**kw):
    base = dict(order_id="so1", species=SlaughterSpecies.BOVINE, branch_id="b1",
                warehouse_id="w1", livestock_lot_id="live-lot", livestock_product_id="steer",
                livestock_quantity=Decimal("1"), livestock_weight=Decimal("480"))
    base.update(kw)
    return SlaughterOrderContract(**base)


def _carcass(**kw):
    base = dict(carcass_lot_id="carc-lot", carcass_product_id="carcass",
                state=CarcassState.WHOLE, weight=Decimal("260"))
    base.update(kw)
    return CarcassContract(**base)


class TestContracts:
    def test_order_requires_livestock_lot(self):
        with pytest.raises(InventoryDomainError):
            _order(livestock_lot_id="")

    def test_float_weight_rejected(self):
        with pytest.raises(InventoryDomainError):
            _order(livestock_weight=480.0)

    def test_output_requires_lot_and_product(self):
        with pytest.raises(InventoryDomainError):
            SlaughterOutputContract(output_lot_id="", product_id="cut",
                                    output_type=SlaughterOutputType.PRIMARY_CUT)


class TestPlanning:
    def setup_method(self):
        self.svc = SlaughterPlanningService()

    def test_plan_maps_onto_future_movements_and_genealogy(self):
        outputs = [
            SlaughterOutputContract(output_lot_id="cut1", product_id="ribeye",
                                    output_type=SlaughterOutputType.PRIMARY_CUT,
                                    weight=Decimal("12"), to_location_id="loc1"),
            SlaughterOutputContract(output_lot_id="op1", product_id="liver",
                                    output_type=SlaughterOutputType.CO_PRODUCT,
                                    weight=Decimal("6")),
            SlaughterOutputContract(output_lot_id="bp1", product_id="bones",
                                    output_type=SlaughterOutputType.WASTE,
                                    weight=Decimal("30")),
        ]
        plan = self.svc.plan(_order(), _carcass(), outputs)

        # livestock consumed, carcass produced, carcass consumed, 2 cuts produced
        types = [(m.movement_type, m.lot_id) for m in plan.movements]
        assert (MovementType.SLAUGHTER_INPUT_FUTURE, "live-lot") in types
        assert (MovementType.SLAUGHTER_OUTPUT_FUTURE, "carc-lot") in types
        assert (MovementType.SLAUGHTER_INPUT_FUTURE, "carc-lot") in types
        assert (MovementType.SLAUGHTER_OUTPUT_FUTURE, "cut1") in types
        assert (MovementType.SLAUGHTER_OUTPUT_FUTURE, "op1") in types
        # WASTE never becomes stock
        assert all(m.lot_id != "bp1" for m in plan.movements)
        assert len(plan.waste_outputs) == 1 and plan.waste_outputs[0].output_lot_id == "bp1"

    def test_directions_are_consistent(self):
        plan = self.svc.plan(_order(), _carcass(), [])
        for m in plan.movements:
            if m.movement_type is MovementType.SLAUGHTER_INPUT_FUTURE:
                assert m.direction is MovementDirection.DECREASE
            else:
                assert m.direction is MovementDirection.INCREASE

    def test_genealogy_links_livestock_to_carcass_to_cuts(self):
        outputs = [SlaughterOutputContract(output_lot_id="cut1", product_id="ribeye",
                                           output_type=SlaughterOutputType.PRIMARY_CUT,
                                           weight=Decimal("12"))]
        plan = self.svc.plan(_order(), _carcass(), outputs)
        edges = {(e.parent_lot_id, e.child_lot_id) for e in plan.genealogy}
        assert ("live-lot", "carc-lot") in edges
        assert ("carc-lot", "cut1") in edges


class TestStubIsInert:
    def test_flag_is_disabled(self):
        assert SLAUGHTER_ENABLED is False

    def test_events_contract_exists(self):
        assert SlaughterEvents.SLAUGHTER_EXECUTED in ALL_SLAUGHTER_EVENTS
        assert "SLAUGHTER_EXECUTED" not in _inventory_events()

    def test_handler_is_a_noop_while_disabled(self):
        # No connection use, no exception: a safe no-op preparation seam.
        SlaughterExecutedStubHandler(connection=None).handle(
            {"event_name": "SLAUGHTER_EXECUTED"})


def _inventory_events():
    from backend.domain.inventory.events import ALL_INVENTORY_EVENTS
    return ALL_INVENTORY_EVENTS
