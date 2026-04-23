"""Compat wrapper: módulo FINANZAS único (UI delgada).

La implementación real vive en `modulos.finanzas_unificadas.ModuloFinanzasUnificadas`
y toda la lógica de negocio en `core/services/finance/*` +
`core/services/analytics/analytics_engine.py`.
"""
from __future__ import annotations

from modulos.finanzas_unificadas import ModuloFinanzasUnificadas


class ModuloFinanzas(ModuloFinanzasUnificadas):
    """Alias estable para mantener imports legacy sin duplicar lógica."""

    pass
