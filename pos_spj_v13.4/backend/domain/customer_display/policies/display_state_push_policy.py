"""DisplayStatePushPolicy — SET-17 "Gateway": composes a `CustomerDisplay`
+ its resolved `DisplayLayout` + raw content into what actually reaches
`CustomerDisplayGatewayPort.push()` — content is filtered down to only
the fields the layout's enabled sections request, the same "layout
governs what actually gets sent" discipline
`value_objects.ticket_data.TicketData.to_render_data()`'s `sections` list
established for Document Output (SET-12), independently reimplemented
here (bounded-context independence).
"""

from __future__ import annotations

from backend.domain.customer_display.entities.customer_display import CustomerDisplay
from backend.domain.customer_display.entities.display_layout import DisplayLayout
from backend.domain.customer_display.gateway_ports import CustomerDisplayGatewayPort


def push_state(
    gateway: CustomerDisplayGatewayPort, *, display: CustomerDisplay, layout: DisplayLayout, content: dict,
) -> None:
    enabled_codes = {code.value for code in layout.enabled_codes()}
    filtered_content = {key: value for key, value in content.items() if key in enabled_codes}
    gateway.push(display_id=display.id, mode=layout.mode, content=filtered_content)
