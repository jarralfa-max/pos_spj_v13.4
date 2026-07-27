# core/services/finance/__init__.py
"""Plomería financiera operativa remanente (transición FASE 20).

La contabilidad canónica vive en el bounded context de Finanzas
(``backend/domain/finance`` + posting engine). Este paquete conserva
únicamente servicios operativos aún acoplados a Caja/Compras/Producción
(tesorería operativa, CxC/CxP operativas, costo de producción); su migración
final ocurre con el refactor de esos módulos. Prohibido agregar lógica nueva.
"""

from .treasury_service import TreasuryService
from .production_cost_service import ProductionCostService, ProductionCostSummary, OutputCostLine

__all__ = [
    "TreasuryService",
    "ProductionCostService",
    "ProductionCostSummary",
    "OutputCostLine",
]
