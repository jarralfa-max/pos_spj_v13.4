"""Matriz de permisos de un rol: qué se le puede otorgar y qué tiene.

Lo otorgable es el catálogo canónico (`CANONICAL_MODULE_PERMISSIONS`): un
permiso fuera del catálogo no se puede dar desde aquí. La pantalla recibe todo
resuelto — módulos con su nombre, acciones con su etiqueta, lo concedido y si
el rol se puede editar — y no decide nada.

Modos de un rol:
- FULL_ACCESS: roles administradores; reciben el comodín `*` por nombre
  (`ADMIN_ROLE_NAMES`). No se editan: no hay nada que dar ni quitar.
- GRANT_ONLY: `system_owner`, el dueño de la instalación. Se le puede agregar
  (los módulos nuevos nacen sin sembrar), nunca quitar: así el dueño no puede
  quedar fuera de su propia instalación.
- EDITABLE: todos los demás.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.security.permission_catalog import CANONICAL_MODULE_PERMISSIONS
from backend.application.security.permission_query_service import ADMIN_ROLE_NAMES
from backend.infrastructure.db.repositories.security.role_permission_repository import (
    SqliteRolePermissionRepository,
)
from backend.security.permissions.codes import permission_code

OWNER_ROLE_NAME = "system_owner"

MODULE_LABELS = {
    "ACTIVOS": "Activos", "CAJA": "Caja", "CALIDAD": "Calidad", "CLIENTES": "Clientes",
    "CLIENTES_CRM": "Clientes y CRM", "COMPRAS": "Compras", "CONFIGURACION": "Configuración",
    "CONFIG_HARDWARE": "Configuración (hardware, anterior)",
    "CONFIG_MODULOS": "Configuración (módulos, anterior)",
    "CONFIG_SEGURIDAD": "Configuración (seguridad, anterior)", "COTIZACIONES": "Cotizaciones",
    "CRM": "CRM", "DASHBOARD": "Tablero", "DELIVERY": "Pedidos y reparto",
    "DISPOSITIVOS": "Dispositivos", "DOCUMENTOS": "Documentos e impresión",
    "FINANZAS": "Finanzas", "FINANZAS_UNIFICADAS": "Finanzas unificadas",
    "GROWTH_ENGINE": "Fidelidad", "INTELIGENCIA_BI": "Inteligencia de negocio",
    "INVENTARIO": "Inventario", "LOGISTICA": "Logística", "MERMA": "Mermas",
    "PANTALLA_CLIENTE": "Pantalla del cliente", "POS": "Punto de venta", "PRECIOS": "Precios",
    "PRODUCCION": "Procesamiento cárnico", "PRODUCTOS": "Productos",
    "PROVEEDORES": "Proveedores", "REPORTES_BI": "Reportes", "RRHH": "Recursos humanos",
    "TARJETAS_FIDELIDAD": "Tarjetas de fidelidad", "TESORERIA": "Tesorería",
    "TRANSFERENCIAS": "Transferencias", "USUARIOS": "Usuarios",
}


def action_label(action: str) -> str:
    """`plantilla.aprobar` → «Plantilla: aprobar»; `ver` → «Ver»."""
    partes = [p.replace("_", " ") for p in action.split(".")]
    if len(partes) == 1:
        return partes[0].capitalize()
    return f"{' '.join(partes[:-1]).capitalize()}: {partes[-1]}"


@dataclass(frozen=True)
class PermissionOption:
    code: str
    label: str


@dataclass(frozen=True)
class ModulePermissions:
    key: str
    label: str
    actions: tuple[PermissionOption, ...]


@dataclass(frozen=True)
class RolePermissionMatrix:
    role_id: str
    role_name: str
    mode: str
    note: str
    granted: frozenset[str]
    modules: tuple[ModulePermissions, ...]


def catalog_modules() -> tuple[ModulePermissions, ...]:
    return tuple(sorted((
        ModulePermissions(key=module, label=MODULE_LABELS.get(module, module.title()),
                          actions=tuple(PermissionOption(permission_code(module, a), action_label(a))
                                        for a in actions))
        for module, actions in CANONICAL_MODULE_PERMISSIONS.items()), key=lambda m: m.label))


def catalog_codes() -> frozenset[str]:
    return frozenset(o.code for m in catalog_modules() for o in m.actions)


def role_mode(role_name: str) -> str:
    nombre = role_name.strip().lower()
    if nombre in ADMIN_ROLE_NAMES:
        return "FULL_ACCESS"
    if nombre == OWNER_ROLE_NAME:
        return "GRANT_ONLY"
    return "EDITABLE"


_NOTES = {
    "FULL_ACCESS": "Rol administrador: tiene acceso total por definición; no se edita.",
    "GRANT_ONLY": "Dueño de la instalación: se le pueden agregar permisos, nunca quitar.",
    "EDITABLE": "Los cambios rigen la próxima vez que cada usuario del rol inicie sesión.",
}


class RolePermissionMatrixQuery:
    def __init__(self, connection) -> None:
        self._roles = SqliteRolePermissionRepository(connection)

    def matrix(self, role_id: str) -> RolePermissionMatrix | None:
        role = self._roles.role(role_id)
        if role is None:
            return None
        mode = role_mode(role[1])
        return RolePermissionMatrix(
            role_id=role[0], role_name=role[1], mode=mode, note=_NOTES[mode],
            granted=self._roles.granted(role[0]), modules=catalog_modules())


__all__ = [
    "MODULE_LABELS", "ModulePermissions", "PermissionOption", "RolePermissionMatrix",
    "RolePermissionMatrixQuery", "action_label", "catalog_codes", "catalog_modules", "role_mode",
]
