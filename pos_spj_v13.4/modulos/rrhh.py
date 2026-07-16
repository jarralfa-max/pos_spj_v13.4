"""Wrapper legacy: módulo RRHH (Recursos Humanos).

La implementación vive en ``frontend/desktop/modules/hr`` (bounded context de
Recursos Humanos: dominio, aplicación, infraestructura y UI limpia). Este
archivo solo preserva los imports legacy de navegación; no contiene SQL, lógica
de negocio, estilos ni cálculo de nómina/horas/KPIs.
"""
from __future__ import annotations

from frontend.desktop.modules.hr.hr_routes import create_hr_view


class ModuloRRHH:
    """Factory-compatible: ``ModuloRRHH(container)`` devuelve la vista nueva."""

    def __new__(cls, container, *args, **kwargs):
        parent = kwargs.get("parent")
        if parent is None and args:
            parent = args[-1]
        return create_hr_view(container, parent)
