
# core/scheduler.py
# ── SHIM de Compatibilidad v12 ────────────────────────────────────────────────
# Re-exporta SchedulerService (canónico, 348 líneas).
# Este archivo se conserva para no romper imports legacy.
from core.services.scheduler_service import SchedulerService as Scheduler  # noqa: F401

__all__ = ['Scheduler']
