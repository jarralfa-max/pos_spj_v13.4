# modulos/compras/__init__.py — SPJ POS v13.4
"""
Compras sub-package: clean, standalone UI components for the purchase module.
Each component is a self-contained QWidget with no direct SQL.
Data access is delegated to repositories via the parent's container.

Components:
    ProveedorPanel   — provider search + info display + condicion pago
    ItemsTable       — cart table + product search bar
    TotalsPanel      — subtotal / IVA / total + payment form
    ActionsBar       — dynamic action button + secondary draft/send buttons

Usage (from ModuloComprasPro):
    from modulos.compras import ProveedorPanel, ItemsTable, TotalsPanel, ActionsBar
"""
from modulos.compras.proveedor_panel import ProveedorPanel
from modulos.compras.items_table import ItemsTable
from modulos.compras.totals_panel import TotalsPanel
from modulos.compras.actions_bar import ActionsBar

__all__ = ["ProveedorPanel", "ItemsTable", "TotalsPanel", "ActionsBar"]
