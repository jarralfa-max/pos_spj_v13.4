"""OrderDeduplicationPolicy (master prompt §18). Avoids duplicate orders from
retries — a WhatsApp webhook retry, a flaky POS submit, a duplicate API
call — by requiring the caller to check for an existing order keyed by
`operation_id` (always) and, when the channel provides one, an
`external_order_reference` (WhatsApp message id, marketplace order id, etc.)
before creating a new one.

Pure policy: it does not query the database itself (no I/O in domain layer)
— the application-layer use case looks up candidates via
`CustomerOrderRepository.find_by_operation_id`/`find_by_channel_reference`
and asks this policy what to do with what it found.
"""

from __future__ import annotations

from backend.domain.orders_delivery.entities import CustomerOrder


class OrderDeduplicationPolicy:
    @staticmethod
    def resolve_existing(
        *, existing_by_operation_id: CustomerOrder | None,
        existing_by_channel_reference: CustomerOrder | None,
    ) -> CustomerOrder | None:
        """Idempotent create: if a matching order already exists (same
        `operation_id`, or the same channel + `external_order_reference` —
        e.g. a WhatsApp webhook retry replaying the same message id), return
        it instead of creating a second one. A retried request must get back
        the SAME order, never an error and never a duplicate."""
        return existing_by_operation_id or existing_by_channel_reference
