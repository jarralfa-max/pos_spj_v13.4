"""BiSettingsService — parámetros configurables del dashboard BI.

Umbrales de alertas, metas y parámetros de forecast. Persiste vía un `store`
con contrato get(key, default)/set(key, value) — típicamente ConfigService
(RAM cache + ConfigRepository). Sin SQL ni DDL aquí (REGLA: sólo migrations toca
schema). Los valores por defecto viven aquí, no hardcodeados en la UI.
"""
from __future__ import annotations

_PREFIX = "bi."

# clave lógica → (clave de settings, valor por defecto, tipo)
_DEFAULTS = {
    "threshold_merma_pct": (f"{_PREFIX}threshold_merma_pct", 3.0, float),
    "threshold_margen_bajo_pct": (f"{_PREFIX}threshold_margen_bajo_pct", 10.0, float),
    "threshold_caida_ventas_pct": (f"{_PREFIX}threshold_caida_ventas_pct", 20.0, float),
    "threshold_cxc_aumento_pct": (f"{_PREFIX}threshold_cxc_aumento_pct", 25.0, float),
    "threshold_compras_aumento_pct": (f"{_PREFIX}threshold_compras_aumento_pct", 30.0, float),
    "forecast_window_days": (f"{_PREFIX}forecast_window_days", 30, int),
    "meta_ventas_periodo": (f"{_PREFIX}meta_ventas_periodo", 0.0, float),
}


class _MemoryStore:
    """Store en memoria (fallback para pruebas o cuando no hay ConfigService)."""

    def __init__(self):
        self._d: dict = {}

    def get(self, key, default_value=None):
        return self._d.get(key, default_value)

    def set(self, key, value):
        self._d[key] = value


class BiSettingsService:
    def __init__(self, store=None):
        self._store = store or _MemoryStore()

    def get(self, logical_key: str):
        setting_key, default, caster = _DEFAULTS[logical_key]
        raw = self._store.get(setting_key, default)
        try:
            return caster(raw)
        except (TypeError, ValueError):
            return default

    def set(self, logical_key: str, value) -> None:
        setting_key, default, caster = _DEFAULTS[logical_key]
        try:
            value = caster(value)
        except (TypeError, ValueError):
            value = default
        self._store.set(setting_key, value)

    def all(self) -> dict:
        return {k: self.get(k) for k in _DEFAULTS}

    @property
    def defaults(self) -> dict:
        return {k: v[1] for k, v in _DEFAULTS.items()}
