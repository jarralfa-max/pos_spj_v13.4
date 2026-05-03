"""Compat wrapper: Proveedores ahora es submódulo de FINANZAS.

Este archivo conserva compatibilidad de import, pero NO contiene
lógica de negocio ni UI duplicada. Redirige al módulo unificado.
"""
from __future__ import annotations

from modulos.finanzas_unificadas import ModuloFinanzasUnificadas


class ModuloProveedores(ModuloFinanzasUnificadas):
    """Vista de compatibilidad que abre directamente la pestaña Proveedores."""

    def __init__(self, container, parent=None):
        super().__init__(container, parent)
        self.set_active_submodule("proveedores")
