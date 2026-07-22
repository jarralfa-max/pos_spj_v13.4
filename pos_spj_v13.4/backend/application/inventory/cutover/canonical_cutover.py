"""CanonicalInventoryCutover — flag-gated live wiring of the canonical handlers.

While the flag is OFF (default), ``wire`` is a no-op and the legacy stock path
stays authoritative. When ON, it subscribes each canonical handler to the live
event it already declares (``handler.event_name``) and, given the legacy handler
callables, unsubscribes them so stock is not double-counted. Reversible:
``unwire`` removes exactly what ``wire`` added.
"""

from __future__ import annotations

import logging
import os

from backend.application.event_handlers.inventory import (
    CustomerReturnHandler,
    DirectPurchaseReceiptHandler,
    GoodsReceiptReversedHandler,
    ProductionExecutionHandler,
    PurchaseReceiptHandler,
    SaleIssueHandler,
    SupplierReturnHandler,
)

logger = logging.getLogger("spj.inventory.cutover")

_ENV_FLAG = "INVENTORY_CANONICAL_CUTOVER"
_SETTING_KEY = "canonical_cutover_enabled"
_TRUTHY = {"1", "true", "yes", "on"}

#: The canonical handler classes that take over at cutover, each keyed by the
#: live event it consumes (via its ``event_name``).
CANONICAL_HANDLER_CLASSES = (
    SaleIssueHandler,
    CustomerReturnHandler,
    PurchaseReceiptHandler,
    DirectPurchaseReceiptHandler,
    SupplierReturnHandler,
    GoodsReceiptReversedHandler,
    ProductionExecutionHandler,
)


def is_cutover_enabled(connection=None, *, env=None) -> bool:
    """OFF by default. Enabled by env ``INVENTORY_CANONICAL_CUTOVER`` truthy, or by
    the GLOBAL inventory setting ``canonical_cutover_enabled``."""
    env = os.environ if env is None else env
    if str(env.get(_ENV_FLAG, "")).strip().lower() in _TRUTHY:
        return True
    if connection is not None:
        try:
            from backend.infrastructure.db.repositories.inventory.support_repositories import (
                InventorySettingsRepository,
            )
            value = InventorySettingsRepository(connection).get(setting_key=_SETTING_KEY)
            if value is not None and str(value).strip().lower() in _TRUTHY:
                return True
        except Exception:  # noqa: BLE001 — missing table/setting → treat as disabled
            return False
    return False


class CanonicalInventoryCutover:
    def __init__(self, connection, *, env=None) -> None:
        self._conn = connection
        self._env = env
        self._handlers = [cls(connection) for cls in CANONICAL_HANDLER_CLASSES]

    def enabled(self) -> bool:
        return is_cutover_enabled(self._conn, env=self._env)

    def wire(self, bus, *, legacy_handlers=(), priority: int = 100) -> dict:
        """Subscribe canonical handlers (if enabled) and drop the legacy ones.

        Returns a report dict; when disabled the report says so and the bus is
        left untouched (legacy stays live)."""
        if not self.enabled():
            logger.info("Inventory cutover DISABLED; legacy stock path stays live.")
            return {"enabled": False, "subscribed": [], "neutralized": 0}

        subscribed = []
        for handler in self._handlers:
            bus.subscribe(handler.event_name, handler.handle, priority=priority,
                          label=f"canonical_{type(handler).__name__}")
            subscribed.append(handler.event_name)

        neutralized = self.neutralize_legacy(bus, legacy_handlers)
        logger.warning("Inventory cutover ENABLED: %d canonical handlers wired, "
                       "%d legacy handlers neutralized.", len(subscribed), neutralized)
        return {"enabled": True, "subscribed": subscribed, "neutralized": neutralized}

    def unwire(self, bus) -> int:
        removed = 0
        for handler in self._handlers:
            if bus.unsubscribe(handler.event_name, handler.handle):
                removed += 1
        return removed

    @staticmethod
    def neutralize_legacy(bus, legacy_handlers) -> int:
        """Unsubscribe the given (event_name, callable) legacy pairs so the legacy
        path stops writing stock once the canonical path owns it."""
        count = 0
        for event_name, callable_ in legacy_handlers:
            if bus.unsubscribe(event_name, callable_):
                count += 1
        return count
