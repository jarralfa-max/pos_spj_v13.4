# core/use_cases/__init__.py — SPJ POS v13.30
"""
Capa de casos de uso — orquestación entre servicios.

Cada caso de uso:
  1. Recibe datos de entrada validados
  2. Coordina múltiples servicios sin lógica de negocio propia
  3. Publica eventos al EventBus al completar
  4. Devuelve un resultado tipado

Importar desde aquí:
    from core.use_cases import ProcesarVentaUC, ProcesarPedidoWAUC, GestionarInventarioUC
    from core.use_cases import GestionarProduccionUC  # v13.30
"""
from core.use_cases.venta import ProcesarVentaUC, ResultadoVenta
from core.use_cases.pedido_wa import ProcesarPedidoWAUC, ResultadoPedido
from core.use_cases.inventario import GestionarInventarioUC, ResultadoInventario
from core.use_cases.produccion import GestionarProduccionUC, ResultadoProduccion

__all__ = [
    "ProcesarVentaUC", "ResultadoVenta",
    "ProcesarPedidoWAUC", "ResultadoPedido",
    "GestionarInventarioUC", "ResultadoInventario",
    "GestionarProduccionUC", "ResultadoProduccion",
]
