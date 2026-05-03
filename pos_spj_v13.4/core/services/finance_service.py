
# core/services/finance_service.py
# ── SHIM de Compatibilidad v12 ────────────────────────────────────────────────
# Re-exporta FinanceService del módulo Enterprise (920 líneas, ERP completo).
# Este shim garantiza que app_container.py y código legacy no rompan.
from core.services.enterprise.finance_service import FinanceService  # noqa: F401

__all__ = ['FinanceService']
