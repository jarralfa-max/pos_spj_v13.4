# core/events/handlers/__init__.py
"""Event handlers package for SPJ POS v13.6 - Domain-Driven Events"""

from .inventory_handler import handle_sale_inventory, handle_stock_transfer
from .finance_handler import handle_sale_finance
from .purchase_handler import handle_purchase_inventory
from .production_handler import handle_production_completion
from .stock_policy import (
    handle_stock_level_critical,
    handle_recipe_deviation,
    handle_quote_expired
)

__all__ = [
    # Sales handlers
    "handle_sale_inventory",
    "handle_sale_finance",
    
    # Purchase handlers
    "handle_purchase_inventory",
    
    # Production handlers
    "handle_production_completion",
    
    # Inventory handlers
    "handle_stock_transfer",
    
    # Policy handlers (business rules)
    "handle_stock_level_critical",
    "handle_recipe_deviation",
    "handle_quote_expired",
]
