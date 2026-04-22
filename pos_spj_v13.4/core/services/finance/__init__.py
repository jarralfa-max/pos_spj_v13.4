# core/services/finance/__init__.py
"""
Finance Core — Núcleo financiero unificado SPJ POS v13.4

Single Source of Truth para:
- Contabilidad (accounting_engine)
- Tesorería (treasury_service)  
- Terceros: proveedores/clientes (third_party_service)
- Fiscal SAT (fiscal_engine)
"""

from .accounting_engine import AccountingEngine
from .fiscal_engine import FiscalEngine
from .third_party_service import UnifiedThirdPartyService
from .treasury_service import TreasuryService

__all__ = [
    "AccountingEngine",
    "FiscalEngine", 
    "UnifiedThirdPartyService",
    "TreasuryService",
]
