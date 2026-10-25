"""Quién tiene acceso total, decidido en UN solo lugar.

Auditoría global de permisos 968e0bc (PER-07). Había tres listas distintas:

- `ApplicationContext._ADMIN_ROLES` (la sesión) incluía a `system_owner`;
- `PermissionQueryService.ADMIN_ROLE_NAMES` (el autorizador en caliente y el
  control de escalamiento) NO lo incluía;
- `role_mode()` (la matriz de Configuración) lo trataba como «sólo agregar».

Resultado medido en la base real: el dueño operaba todo en su sesión, pero como
AUTORIZADOR de una excepción no tenía los permisos granulares de Inventario,
Mermas, Pedidos o Analítica — su rol se sembró con una lista congelada y los
contextos nuevos nunca le llegaron. Ahora la sesión, el autorizador y la matriz
leen esta misma lista.

Los roles se identifican por nombre porque `usuarios.rol` guarda el nombre. Para
que el nombre no sea una cadena editable que dé superpoderes, estos nombres son
RESERVADOS: ningún rol se puede renombrar hacia ni desde uno de ellos, ni crear
con ese nombre (`RoleManagementService.save_role`).
"""
from __future__ import annotations

#: Dueño de la instalación (lo crea el asistente de primer arranque).
OWNER_ROLE_NAME = "system_owner"

#: Roles administradores heredados.
ADMIN_ROLE_NAMES = frozenset({"admin", "superadmin", "administrador"})

#: Acceso total: reciben el comodín `*`. No llevan excepciones ni se editan.
FULL_ACCESS_ROLE_NAMES = ADMIN_ROLE_NAMES | {OWNER_ROLE_NAME}

#: Nombres que ningún rol puede tomar ni abandonar por renombrado.
RESERVED_ROLE_NAMES = FULL_ACCESS_ROLE_NAMES


def _clean(role_name) -> str:
    return str(role_name or "").strip().lower()


def is_full_access_role(role_name) -> bool:
    return _clean(role_name) in FULL_ACCESS_ROLE_NAMES


def is_owner_role(role_name) -> bool:
    return _clean(role_name) == OWNER_ROLE_NAME


def is_reserved_role_name(role_name) -> bool:
    return _clean(role_name) in RESERVED_ROLE_NAMES
