"""Permisos de Cotizaciones (CRM-43): vocabulario ``COTIZACIONES.<accion>``.

El módulo ``COTIZACIONES`` ya existía en ``rol_permisos`` con las cinco acciones
gruesas del sembrado base; la migración 319 siembra la matriz granular que eligió
el usuario (como el CRM: dueño/admin todo; gerente su sucursal, aprueba y
convierte; cajero las suyas, sin aprobar; solo lectura consulta).
"""

from __future__ import annotations


class QuotePermissions:
    VIEW = "COTIZACIONES.ver"
    VIEW_OWN = "COTIZACIONES.ver.propia"
    VIEW_BRANCH = "COTIZACIONES.ver.sucursal"
    VIEW_COMPANY = "COTIZACIONES.ver.compania"
    CREATE = "COTIZACIONES.crear"
    EDIT = "COTIZACIONES.editar"
    APPROVE = "COTIZACIONES.aprobar"
    SEND = "COTIZACIONES.enviar"
    RESPOND = "COTIZACIONES.registrar_respuesta"
    CANCEL = "COTIZACIONES.cancelar"
    CONVERT = "COTIZACIONES.convertir"
    EXPORT = "COTIZACIONES.exportar"


ALL_QUOTE_PERMISSIONS = frozenset(
    v for k, v in vars(QuotePermissions).items() if not k.startswith("_") and isinstance(v, str))

#: Alcance de lectura, del más estrecho al más amplio (mismo formato que el CRM).
QUOTE_VIEW_SCOPE_PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("OWN", QuotePermissions.VIEW_OWN),
    ("BRANCH", QuotePermissions.VIEW_BRANCH),
    ("COMPANY", QuotePermissions.VIEW_COMPANY),
)
