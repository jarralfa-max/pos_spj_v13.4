"""Todo permiso que el menú lateral exige tiene que ser otorgable.

Antes esto se comprobaba leyendo `interfaz/menu_lateral.py` con una expresión
regular para sacar los nombres de módulo de sus `_crear_boton(...)`. Ese archivo
ya no existe. El guardrail no se borra por eso —sigue protegiendo algo real—
sino que se apunta a la fuente viva: el registro de navegación canónico que
alimenta `GlobalSidebar`.

QUÉ PROTEGE, EN CONCRETO
------------------------
Una entrada del menú que exige `FINANZAS.ver` cuando el catálogo no conoce
`FINANZAS` no provoca ningún error: la entrada simplemente no aparece nunca
para nadie, salvo para el administrador —que lleva el comodín global y por eso
no lo nota— y no hay forma de otorgarla desde Configuración → Seguridad →
Permisos, porque la matriz se construye desde el catálogo. El módulo queda
inaccesible en silencio y sin ninguna pista de por qué.
"""
from __future__ import annotations

from backend.application.security.permission_catalog import CANONICAL_MODULE_PERMISSIONS
from backend.security.permissions.codes import split_permission
from frontend.desktop.shell.sidebar.migrated_modules_navigation import (
    register_migrated_modules_navigation,
)
from frontend.desktop.shell.sidebar.navigation_item_registry import NavigationItemRegistry


def _required_permissions() -> tuple[tuple[str, str], ...]:
    """`(item_id, codigo)` de cada entrada del menú que exige un permiso."""
    registry = NavigationItemRegistry()
    register_migrated_modules_navigation(registry)
    return tuple(
        (item.item_id, item.required_permission)
        for item in registry.all()
        if item.required_permission
    )


def test_the_sidebar_registers_navigation_items() -> None:
    """Si esto fallara, los demás tests pasarían sin comprobar nada."""
    assert _required_permissions()


def test_every_sidebar_permission_belongs_to_a_catalog_module() -> None:
    desconocidos = [
        (item_id, code) for item_id, code in _required_permissions()
        if split_permission(code)[0] not in CANONICAL_MODULE_PERMISSIONS
    ]
    assert not desconocidos, (
        "Entradas del menú cuyo módulo no existe en el catálogo (serían "
        f"invisibles e inotorgables): {desconocidos}")


def test_every_sidebar_permission_is_a_registered_action() -> None:
    faltantes = []
    for item_id, code in _required_permissions():
        module_key, action = split_permission(code)
        if module_key not in CANONICAL_MODULE_PERMISSIONS:
            continue  # ya lo reporta el test anterior
        if action not in CANONICAL_MODULE_PERMISSIONS[module_key]:
            faltantes.append((item_id, code))
    assert not faltantes, (
        "Entradas del menú cuya acción no está registrada en su módulo: "
        f"{faltantes}")


def test_sidebar_permissions_use_the_dotted_module_action_format() -> None:
    """Un código plano (`LOSSES_VIEW`) no tiene módulo, así que nunca puede
    cotejarse contra el catálogo ni otorgarse desde la matriz de permisos."""
    planos = [
        (item_id, code) for item_id, code in _required_permissions()
        if not split_permission(code)[0]
    ]
    assert not planos, (
        "Entradas del menú con código plano, sin módulo — no son otorgables "
        f"desde la matriz de permisos: {planos}")
