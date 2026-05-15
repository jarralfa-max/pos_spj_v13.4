"""
application/purchases — Capa de aplicación para el módulo de Compras.

Paquete oficial de casos de uso, comandos y resultados de compras.

Ruta canónica de Compra Tradicional:
    UI → TraditionalPurchaseUC.execute(RegisterPurchaseCommand)
           → RegistrarCompraUC (delegado)
             → PurchaseService
               → PURCHASE_ITEMS_PROCESS (inventario, sync)
               → PURCHASE_CREATED (finanzas, async)
"""
from application.purchases.commands import RegisterPurchaseCommand, PurchaseItemCommand
from application.purchases.results import PurchaseResult
from application.purchases.states import DocumentType, PRState, POState
from application.purchases.traditional_purchase_uc import TraditionalPurchaseUC

__all__ = [
    "RegisterPurchaseCommand",
    "PurchaseItemCommand",
    "PurchaseResult",
    "DocumentType",
    "PRState",
    "POState",
    "TraditionalPurchaseUC",
]
