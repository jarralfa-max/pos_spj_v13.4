# application/use_cases/__init__.py — shim to core/use_cases for clean architecture
from core.use_cases.venta import ProcesarVentaUC, ResultadoVenta
from core.use_cases.compra import ProcesarCompraUC, ResultadoCompra  # deprecated — ver Phase 2
from core.use_cases.cliente import GestionarClienteUC, ResultadoCliente
from core.use_cases.inventario import GestionarInventarioUC
from core.use_cases.produccion import GestionarProduccionUC

# ── Phase 2: ruta canónica ────────────────────────────────────────────────────
from application.purchases.traditional_purchase_uc import TraditionalPurchaseUC
from application.purchases.commands import RegisterPurchaseCommand, PurchaseItemCommand
from application.purchases.results import PurchaseResult
from application.purchases.states import DocumentType, PRState, POState

__all__ = [
    # Legacy (deprecated) — mantener para backward compat
    "ProcesarVentaUC", "ResultadoVenta",
    "ProcesarCompraUC", "ResultadoCompra",
    "GestionarClienteUC", "ResultadoCliente",
    "GestionarInventarioUC",
    "GestionarProduccionUC",
    # Phase 2 — ruta canónica de compras
    "TraditionalPurchaseUC",
    "RegisterPurchaseCommand",
    "PurchaseItemCommand",
    "PurchaseResult",
    "DocumentType",
    "PRState",
    "POState",
]
