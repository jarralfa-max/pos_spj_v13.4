
# utils/logging_setup.py
# ── SHIM de Compatibilidad v12 ────────────────────────────────────────────────
# El setup canónico está en core/logging_setup.py (v10, 4 handlers, JSON).
from core.logging_setup import setup_logging  # noqa: F401

__all__ = ['setup_logging']
