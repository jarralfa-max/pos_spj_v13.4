# application/use_cases/__init__.py — shim to core/use_cases for clean architecture
from core.use_cases.venta import ProcesarVentaUC, ResultadoVenta
from core.use_cases.cliente import GestionarClienteUC, ResultadoCliente
from core.use_cases.inventario import GestionarInventarioUC
from core.use_cases.produccion import GestionarProduccionUC

__all__ = [
    "ProcesarVentaUC", "ResultadoVenta",
    "GestionarClienteUC", "ResultadoCliente",
    "GestionarInventarioUC",
    "GestionarProduccionUC",
]
