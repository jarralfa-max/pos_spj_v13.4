"""QualityStatusHandler (§34) — Quality blocks/releases a product's commercial state.

Quality publishes PRODUCT_QUALITY_BLOCKED / PRODUCT_QUALITY_RELEASED; Products
updates the commercial state ONLY through this authorized handler (never a direct
UI write). Blocking moves an ACTIVE product to BLOCKED; releasing moves a BLOCKED
product back to ACTIVE. Idempotent by event_id, permission-gated, and every change
writes a product_audit_log row. It never touches stock — that is Inventory's job.
"""

from __future__ import annotations

from backend.application.products.authorization.policy import (
    ProductsAuthorizationPolicy,
)
from backend.application.products.permissions import ProductPermissions
from backend.domain.products.enums import LifecycleStatus
from backend.domain.products.events import ProductEvents
from backend.domain.products.exceptions import (
    InvalidProductStateError,
    ProductNotFoundError,
)
from backend.domain.products.policies.product_lifecycle_policy import can_transition
from backend.shared.ids import new_uuid


class QualityStatusHandler:
    def __init__(self, connection, *, authorization: ProductsAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._authz = authorization or ProductsAuthorizationPolicy()

    def handle(self, event_name: str, payload: dict) -> bool:
        """Return True if a state change was applied, False if a no-op/duplicate."""
        event_id = payload.get("event_id") or new_uuid()
        if self._already_processed(event_id):
            return False

        product_id = payload.get("product_id") or payload.get("entity_id")
        actor = payload.get("user_id") or payload.get("authorized_by") or "quality"
        reason = payload.get("reason") or "Cambio de estado por calidad"
        operation_id = payload.get("operation_id") or event_id

        row = self._conn.execute(
            "SELECT lifecycle_status FROM products WHERE id=?", (product_id,)).fetchone()
        if row is None:
            raise ProductNotFoundError(f"Producto no encontrado: {product_id}")
        current = LifecycleStatus(row["lifecycle_status"])

        if event_name == ProductEvents.PRODUCT_QUALITY_BLOCKED:
            target, permission = LifecycleStatus.BLOCKED, ProductPermissions.BLOCK
        elif event_name == ProductEvents.PRODUCT_QUALITY_RELEASED:
            target, permission = LifecycleStatus.ACTIVE, ProductPermissions.ACTIVATE
        else:
            return False

        if current is target:
            self._mark_processed(event_id, event_name)
            return False  # idempotent no-op

        self._authz.require(actor, permission)
        if not can_transition(current, target):
            raise InvalidProductStateError(
                f"Transición por calidad no permitida: {current.value} → {target.value}")

        self._conn.execute(
            "UPDATE products SET lifecycle_status=?, updated_at=datetime('now') WHERE id=?",
            (target.value, product_id))
        self._audit(product_id, actor, operation_id, event_name, current, target, reason)
        self._mark_processed(event_id, event_name)
        return True

    # ── internals ─────────────────────────────────────────────────────────
    def _already_processed(self, event_id: str) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM product_processed_events WHERE event_id=?",
            (event_id,)).fetchone() is not None

    def _mark_processed(self, event_id: str, event_name: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO product_processed_events (event_id, event_name) VALUES (?,?)",
            (event_id, event_name))

    def _audit(self, product_id, actor, operation_id, action, before, after, reason) -> None:
        self._conn.execute(
            """INSERT INTO product_audit_log
               (id, action, entity_id, user_id, operation_id, before, after, reason, source)
               VALUES (?,?,?,?,?,?,?,?, 'quality')""",
            (new_uuid(), action, product_id, actor, operation_id,
             f'{{"lifecycle_status": "{before.value}"}}',
             f'{{"lifecycle_status": "{after.value}"}}', reason))
