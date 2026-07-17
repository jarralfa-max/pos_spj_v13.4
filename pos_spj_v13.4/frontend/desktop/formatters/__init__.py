"""Shared display formatters (FASE DS-6).

Single source for turning domain values into user-facing strings (es-MX).
Modules must not repeat ``f"${v:,.2f}"`` / ``f"{p:.1f}%"`` etc. — import from
here. Formatters are pure (no Qt, no I/O) and never mutate their inputs.
"""

from frontend.desktop.formatters.money_formatter import format_money
from frontend.desktop.formatters.quantity_formatter import format_quantity
from frontend.desktop.formatters.percentage_formatter import format_percentage
from frontend.desktop.formatters.date_formatter import format_date
from frontend.desktop.formatters.time_formatter import format_time
from frontend.desktop.formatters.duration_formatter import format_duration
from frontend.desktop.formatters.phone_formatter import format_phone
from frontend.desktop.formatters.address_formatter import format_address
from frontend.desktop.formatters.status_formatter import format_status

__all__ = [
    "format_money", "format_quantity", "format_percentage", "format_date",
    "format_time", "format_duration", "format_phone", "format_address",
    "format_status",
]
