"""Kanban column configuration for the Delivery module.

Single source of truth for column → status mapping.
Both Kanban and List views import this constant — never define it twice.
"""
from __future__ import annotations

from core.delivery.domain.value_objects import DeliveryStatus

# Exactly 4 visual columns.
# Each entry: (column_label_es, [DeliveryStatus values that appear in this column])
KANBAN_COLUMNS: list[tuple[str, list[DeliveryStatus]]] = [
    (
        "Pendiente",
        [DeliveryStatus.PENDING],
    ),
    (
        "Preparación",
        [DeliveryStatus.PREPARING],
    ),
    (
        "En reparto / Para entregar",
        [
            DeliveryStatus.READY_FOR_PICKUP,
            DeliveryStatus.READY_FOR_DISPATCH,
            DeliveryStatus.ASSIGNED,
            DeliveryStatus.IN_TRANSIT,
        ],
    ),
    (
        "Entrega",
        [DeliveryStatus.DELIVERED],
    ),
]
