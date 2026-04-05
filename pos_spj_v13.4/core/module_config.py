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

logger = logging.getLogger("spj.config")

# Toggles disponibles con valores por defecto
DEFAULT_TOGGLES = {
    "printing_enabled":              True,
    "loyalty_enabled":               True,
    "finance_enabled":               True,
    "treasury_central_enabled":      False,   # CAPEX — Fase 3
    "alerts_enabled":                True,
    "decisions_enabled":             False,   # Fase 5
    "forecasting_enabled":           True,
    "simulation_enabled":            False,   # Fase 7
    "ai_enabled":                    False,   # Fase 8
    "franchise_mode_enabled":        False,   # Fase 10
    "whatsapp_integration_enabled":  False,
    "rrhh_enabled":                  True,    # FASE RRHH — HRRuleEngine
}


class ModuleConfig:
    """Configuración de módulos con toggles persistentes."""

    def __init__(self, db_conn=None):
        self.db = db_conn
        self._toggles: Dict[str, bool] = dict(DEFAULT_TOGGLES)
        self._ensure_table()
        self._load()

    def _ensure_table(self):
        if not self.db:
            return
        try:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS module_toggles (
                    clave TEXT PRIMARY KEY,
                    activo INTEGER DEFAULT 1,
                    descripcion TEXT DEFAULT ''
                )
            """)
            # Insertar defaults si no existen
            for k, v in DEFAULT_TOGGLES.items():
                self.db.execute(
                    "INSERT OR IGNORE INTO module_toggles(clave, activo) VALUES(?,?)",
                    (k, 1 if v else 0))
            try:
                self.db.commit()
            except Exception:
                pass
        except Exception as e:
            logger.debug("_ensure_table: %s", e)

    def _load(self):
        if not self.db:
            return
        try:
            rows = self.db.execute(
                "SELECT clave, activo FROM module_toggles"
            ).fetchall()
            for r in rows:
                self._toggles[r[0]] = bool(r[1])
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
        if self.db:
            try:
                self.db.execute(
                    "INSERT INTO module_toggles(clave, activo) VALUES(?,?) "
                    "ON CONFLICT(clave) DO UPDATE SET activo=excluded.activo",
                    (key, 1 if enabled else 0))
                try:
                    self.db.commit()
                except Exception:
                    pass
            except Exception as e:
                logger.warning("set_enabled %s: %s", key, e)
        logger.info("Toggle %s = %s", key, enabled)

    def get_all(self) -> Dict[str, bool]:
        return dict(self._toggles)
