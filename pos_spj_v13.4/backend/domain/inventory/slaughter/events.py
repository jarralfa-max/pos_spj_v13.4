"""Future slaughter event contracts (§33, INV-21).

Names the events the future slaughter module will publish, so other contexts can
be designed against a stable vocabulary now. These are NOT registered in
``ALL_INVENTORY_EVENTS`` and nothing emits them yet — they are a contract, not a
live channel.
"""

from __future__ import annotations


class SlaughterEvents:
    SLAUGHTER_ORDER_PLANNED = "SLAUGHTER_ORDER_PLANNED"
    LIVESTOCK_RECEIVED = "LIVESTOCK_RECEIVED"
    SLAUGHTER_EXECUTED = "SLAUGHTER_EXECUTED"
    CARCASS_REGISTERED = "CARCASS_REGISTERED"
    CARCASS_DISASSEMBLED = "CARCASS_DISASSEMBLED"
    SLAUGHTER_OUTPUT_PRODUCED = "SLAUGHTER_OUTPUT_PRODUCED"
    SLAUGHTER_ORDER_CLOSED = "SLAUGHTER_ORDER_CLOSED"


ALL_SLAUGHTER_EVENTS = frozenset(
    v for k, v in vars(SlaughterEvents).items()
    if not k.startswith("_") and isinstance(v, str)
)
