# core/module_config.py — SPJ POS v13.30 — Toggles globales
"""
Sistema de toggles para activar/desactivar módulos sin romper el sistema.
Lee configuración de la BD y expone API simple.

USO:
    cfg = container.module_config
    if cfg.is_enabled('printing'):
        printer.print_ticket(data)
    if cfg.is_enabled('loyalty'):
        loyalty.process(venta)
"""
from __future__ import annotations
import logging
from typing import Dict, Optional

from repositories.config_repository import ConfigRepository

logger = logging.getLogger("spj.config")

# Toggles disponibles con valores por defecto
DEFAULT_TOGGLES = {
    "printing_enabled":              True,
    "loyalty_enabled":               True,
    "finance_enabled":               True,
    "treasury_central_enabled":      True,    # CAPEX — Fase 3 (visible por defecto)
    "alerts_enabled":                True,
    "decisions_enabled":             True,    # Fase 5 (visible por defecto)
    "forecasting_enabled":           True,
    "simulation_enabled":            False,   # Fase 7
    "ai_enabled":                    False,   # Fase 8
    "franchise_mode_enabled":        False,   # Fase 10
    "whatsapp_integration_enabled":  True,    # visible por defecto (Fase 0 whitelist)
    "whatsapp_advanced_enabled":     False,   # FASE WA — Orchestrator + OC auto
    "reminder_engine_enabled":       False,   # FASE WA — ReminderEngine
    "rrhh_enabled":                  True,    # FASE RRHH — HRRuleEngine
}


class ModuleConfig:
    """Configuración de módulos con toggles persistentes."""

    def __init__(self, db_conn=None):
        self.db = db_conn
        self.repository = ConfigRepository(db_conn) if db_conn else None
        self._toggles: Dict[str, bool] = dict(DEFAULT_TOGGLES)
        self._ensure_table()
        self._load()

    def _ensure_table(self):
        """Validate migration-owned module_toggles availability.

        Schema creation and default seeding now live in migrations, not services.
        """
        if not self.db:
            return
        try:
            if self.repository is not None:
                self.repository.get_module_toggles()
        except Exception as e:
            logger.debug("module_toggles unavailable; run migrations: %s", e)

    def _load(self):
        if not self.db:
            return
        try:
            if self.repository is not None:
                self._toggles.update(self.repository.get_module_toggles())
        except Exception:
            pass

    def is_enabled(self, module_key: str) -> bool:
        """Verifica si un módulo está habilitado."""
        # Acepta con y sin _enabled suffix
        key = module_key if module_key.endswith('_enabled') else f"{module_key}_enabled"
        return self._toggles.get(key, True)

    def set_enabled(self, module_key: str, enabled: bool):
        """Cambia el estado de un toggle y lo persiste."""
        key = module_key if module_key.endswith('_enabled') else f"{module_key}_enabled"
        self._toggles[key] = enabled
        if self.repository is not None:
            try:
                self.repository.set_module_toggle(key, enabled)
            except Exception as e:
                logger.warning("set_enabled %s: %s", key, e)
        logger.info("Toggle %s = %s", key, enabled)

    def get_all(self) -> Dict[str, bool]:
        return dict(self._toggles)
