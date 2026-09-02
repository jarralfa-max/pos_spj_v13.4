"""Wrapper de navegación: nuevo módulo Configuración.

La implementación vive en ``frontend/desktop/modules/configuracion``
(bounded context de Configuración: gobierna Settings/Device Management/
Document Output/Customer Display/Integrations/Feature Flags/Appearance/
Notifications/Offline — SET-0..23). Este archivo solo preserva el import
legacy de navegación (mismo patrón que ``modulos/rrhh.py``/
``modulos/finanzas.py``); no contiene SQL, lógica de negocio ni estilos.

Registrado junto a — no en reemplazo de — ``modulos/configuracion.py``/
``config_hardware.py``/``config_modules.py``: esos 3 archivos siguen
cubriendo funcionalidad real que este módulo nuevo todavía no iguala
(SMTP con envío de prueba, cierre mensual, configuración de hardware,
alternado de módulos por sucursal) — ver
``docs/refactor/SET-25_legacy_removal_report.md``.
"""
from __future__ import annotations

from frontend.desktop.modules.configuracion.configuracion_routes import create_configuracion_view


class ModuloConfiguracionWorkspace:
    """Factory-compatible: ``ModuloConfiguracionWorkspace(container)``
    devuelve la vista nueva."""

    def __new__(cls, container, *args, **kwargs):
        parent = kwargs.get("parent")
        if parent is None and args:
            parent = args[-1]
        return create_configuracion_view(container, parent)
