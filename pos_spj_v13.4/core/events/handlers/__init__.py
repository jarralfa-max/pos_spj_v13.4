# core/events/handlers — domain event handlers.
# INV-27 corte: los *InventoryHandler legacy (Sale/Production/Purchase/Transfer)
# fueron eliminados; el inventario se mueve por el ledger canónico (bridges en
# backend/application/event_handlers/inventory). Solo quedan los handlers de
# finanzas.
from core.events.handlers.finance_handler import SaleFinanceHandler
from core.events.handlers.purchase_handler import PurchaseFinanceHandler

__all__ = [
    "SaleFinanceHandler",
    "PurchaseFinanceHandler",
]
