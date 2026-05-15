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
from application.purchases.states import DocumentType, PRState, POState, DirectPurchaseState
from application.purchases.traditional_purchase_uc import TraditionalPurchaseUC
from application.purchases.purchase_request_uc import PurchaseRequestUC, PRResult
from application.purchases.purchase_order_uc import PurchaseOrderUC, POResult

__all__ = [
    "RegisterPurchaseCommand",
    "PurchaseItemCommand",
    "PurchaseResult",
    "DocumentType",
    "PRState",
    "POState",
    "DirectPurchaseState",
    "TraditionalPurchaseUC",
    "PurchaseRequestUC",
    "PRResult",
    "PurchaseOrderUC",
    "POResult",
]
