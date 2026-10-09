"""Módulos por sucursal: un feature flag por módulo (`modulo.<id>`).

Apagar un módulo en una sucursal es una regla de ámbito SUCURSAL sobre su flag,
en Configuración → Feature Flags (la misma sección de siempre: no hay una
pantalla aparte). La migración 305 siembra un flag ENCENDIDO por módulo, así
que por omisión todo sigue visible.

Un módulo se oculta sólo si su flag EXISTE y quedó APAGADO para la sucursal:
un flag ausente no apaga nada. Configuración nunca se apaga — sería quedarse
sin la pantalla desde la que se vuelve a encender.
"""

from __future__ import annotations

MODULE_FLAG_PREFIX = "modulo."
NON_DISABLEABLE_MODULES = frozenset({"configuracion"})


def module_flag_code(module_id: str) -> str:
    return f"{MODULE_FLAG_PREFIX}{module_id}"


def module_disabled(feature_context, module_id: str) -> bool:
    if module_id in NON_DISABLEABLE_MODULES:
        return False
    return feature_context.is_disabled(module_flag_code(module_id))
