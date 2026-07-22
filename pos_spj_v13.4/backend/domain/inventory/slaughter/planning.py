"""SlaughterPlanningService — pure mapping of a future faena onto primitives.

Given the slaughter contracts, produce the *planned* canonical movements and
genealogy edges the future module will post — WITHOUT persisting anything. This
proves today that the slaughter flow slots onto the born-clean ledger:

  livestock lot  --SLAUGHTER_INPUT_FUTURE-->  (consumed)
                 --SLAUGHTER_OUTPUT_FUTURE-->  carcass lot        [genealogy]
  carcass lot    --SLAUGHTER_INPUT_FUTURE-->  (disassembled)
                 --SLAUGHTER_OUTPUT_FUTURE-->  each output lot    [genealogy]

WASTE outputs never become stock (process loss); they are surfaced separately so
the future module records them as classified waste (INV-16). Nothing here is
wired to the bus — ``SLAUGHTER_ENABLED`` gates the real module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from backend.domain.inventory.enums import (
    MOVEMENT_DIRECTION,
    MovementDirection,
    MovementType,
    SLAUGHTER_STOCK_OUTPUTS,
    TraceabilityLinkType,
)
from backend.domain.inventory.slaughter.contracts import (
    CarcassContract,
    SlaughterOrderContract,
    SlaughterOutputContract,
)

#: The slaughter module is not implemented; this stays False until it lands.
SLAUGHTER_ENABLED = False


@dataclass(frozen=True, slots=True)
class PlannedMovement:
    movement_type: MovementType
    lot_id: str
    product_id: str
    quantity: Decimal = Decimal("0")
    weight: Decimal = Decimal("0")
    location_id: str | None = None

    @property
    def direction(self) -> MovementDirection:
        return MOVEMENT_DIRECTION[self.movement_type]


@dataclass(frozen=True, slots=True)
class PlannedGenealogyEdge:
    parent_lot_id: str
    child_lot_id: str
    link_type: TraceabilityLinkType = TraceabilityLinkType.SLAUGHTER


@dataclass(frozen=True, slots=True)
class SlaughterPlan:
    order_id: str
    movements: tuple[PlannedMovement, ...] = ()
    genealogy: tuple[PlannedGenealogyEdge, ...] = ()
    waste_outputs: tuple[SlaughterOutputContract, ...] = ()


class SlaughterPlanningService:
    def plan(self, order: SlaughterOrderContract, carcass: CarcassContract,
             outputs: list[SlaughterOutputContract]) -> SlaughterPlan:
        movements: list[PlannedMovement] = []
        genealogy: list[PlannedGenealogyEdge] = []
        waste: list[SlaughterOutputContract] = []

        # Phase A — consume livestock, produce the carcass.
        movements.append(PlannedMovement(
            movement_type=MovementType.SLAUGHTER_INPUT_FUTURE,
            lot_id=order.livestock_lot_id, product_id=order.livestock_product_id,
            quantity=order.livestock_quantity, weight=order.livestock_weight))
        movements.append(PlannedMovement(
            movement_type=MovementType.SLAUGHTER_OUTPUT_FUTURE,
            lot_id=carcass.carcass_lot_id, product_id=carcass.carcass_product_id,
            weight=carcass.weight))
        genealogy.append(PlannedGenealogyEdge(
            parent_lot_id=order.livestock_lot_id, child_lot_id=carcass.carcass_lot_id))

        stock_outputs = [o for o in outputs if o.output_type in SLAUGHTER_STOCK_OUTPUTS]
        waste = [o for o in outputs if o.output_type not in SLAUGHTER_STOCK_OUTPUTS]

        # Phase B — disassemble the carcass into classified outputs.
        if stock_outputs:
            movements.append(PlannedMovement(
                movement_type=MovementType.SLAUGHTER_INPUT_FUTURE,
                lot_id=carcass.carcass_lot_id, product_id=carcass.carcass_product_id,
                weight=carcass.weight))
            for out in stock_outputs:
                movements.append(PlannedMovement(
                    movement_type=MovementType.SLAUGHTER_OUTPUT_FUTURE,
                    lot_id=out.output_lot_id, product_id=out.product_id,
                    quantity=out.quantity, weight=out.weight,
                    location_id=out.to_location_id))
                genealogy.append(PlannedGenealogyEdge(
                    parent_lot_id=carcass.carcass_lot_id,
                    child_lot_id=out.output_lot_id))

        return SlaughterPlan(
            order_id=order.order_id, movements=tuple(movements),
            genealogy=tuple(genealogy), waste_outputs=tuple(waste))
