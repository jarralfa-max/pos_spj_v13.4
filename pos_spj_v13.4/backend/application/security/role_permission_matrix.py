"""Matriz de permisos de un rol: qué se le puede otorgar y qué tiene.

Lo otorgable es el catálogo canónico (`CANONICAL_MODULE_PERMISSIONS`): un
permiso fuera del catálogo no se puede dar desde aquí. La pantalla recibe todo
resuelto — módulos con su nombre, acciones con su etiqueta, lo concedido y si
el rol se puede editar — y no decide nada.

Modos de un rol:
- FULL_ACCESS: administradores y `system_owner`, el dueño de la instalación;
  reciben el comodín `*` (`backend/security/permissions/principals.py`). No se
  editan: no hay nada que dar ni quitar.
- EDITABLE: todos los demás.

Hasta la auditoría de permisos 968e0bc (PER-07) el dueño era «GRANT_ONLY»: se
le podía agregar, nunca quitar. Pero la sesión ya lo trataba como administrador,
así que la matriz mostraba casillas sin efecto, y el autorizador en caliente —
que lee las filas— lo dejaba sin los permisos de cada módulo nuevo.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.security.permission_catalog import CANONICAL_MODULE_PERMISSIONS
from backend.infrastructure.db.repositories.security.role_permission_repository import (
    SqliteRolePermissionRepository,
)
from backend.security.permissions.codes import permission_code
from backend.security.permissions.principals import (
    OWNER_ROLE_NAME,
    is_full_access_role,
    is_owner_role,
)

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


#: Acentos para MOSTRAR la acción: el código (`accion_correctiva.ver`) es ASCII
#: y no cambia. Las terminaciones `-cion`/`-sion` en singular se acentúan por
#: regla; el resto, por esta lista.
_ACCENTED = {
    "analisis": "análisis", "analitica": "analítica", "auditoria": "auditoría",
    "carnica": "cárnica", "carnico": "cárnico", "categoria": "categoría",
    "codigo": "código", "compania": "compañía", "credito": "crédito", "dano": "daño",
    "deposito": "depósito", "diagnostico": "diagnóstico", "fisico": "físico",
    "garantia": "garantía", "membresia": "membresía", "metricas": "métricas",
    "minimo": "mínimo", "periodo": "período", "politicas": "políticas",
    "tesoreria": "tesorería", "transito": "tránsito",
}


def _accent(word: str) -> str:
    if word in _ACCENTED:
        return _ACCENTED[word]
    if word.endswith(("cion", "sion")):
        return word[:-3] + "ión"
    return word


def action_label(action: str) -> str:
    """`plantilla.aprobar` → «Plantilla: aprobar»; `ver` → «Ver»;
    `accion_correctiva.ver` → «Acción correctiva: ver»."""
    partes = [" ".join(_accent(w) for w in p.split("_")) for p in action.split(".")]
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
    return "FULL_ACCESS" if is_full_access_role(role_name) else "EDITABLE"


_NOTES = {
    "FULL_ACCESS": "Rol administrador: tiene acceso total por definición; no se edita.",
    "EDITABLE": "Los cambios rigen en las sesiones abiertas en cuanto se guardan.",
}
_OWNER_NOTE = ("Dueño de la instalación: acceso total por definición; no se le puede "
               "quitar nada, así nunca queda fuera de su propia instalación.")


def role_note(role_name: str) -> str:
    return _OWNER_NOTE if is_owner_role(role_name) else _NOTES[role_mode(role_name)]


class RolePermissionMatrixQuery:
    def __init__(self, connection) -> None:
        self._roles = SqliteRolePermissionRepository(connection)

    def matrix(self, role_id: str) -> RolePermissionMatrix | None:
        role = self._roles.role(role_id)
        if role is None:
            return None
        mode = role_mode(role[1])
        return RolePermissionMatrix(
            role_id=role[0], role_name=role[1], mode=mode, note=role_note(role[1]),
            granted=self._roles.granted(role[0]), modules=catalog_modules())


__all__ = [
    "MODULE_LABELS", "ModulePermissions", "PermissionOption", "RolePermissionMatrix",
    "OWNER_ROLE_NAME", "RolePermissionMatrixQuery", "action_label", "catalog_codes",
    "catalog_modules", "role_mode", "role_note",
]
