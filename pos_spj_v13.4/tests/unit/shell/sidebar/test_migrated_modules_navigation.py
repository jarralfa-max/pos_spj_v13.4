"""Cada módulo del shell tiene su entrada real en el menú lateral.

Este archivo fijaba NUEVE módulos, que eran los de SHELL-16. Desde entonces
se registraron nueve más (Configuración, Inteligencia de Negocios, Mermas,
Producción, Pedidos y Reparto, Fidelidad, Tarjetas de Fidelidad, Activos y
Precios) y el test se quedó atrás: pasó de proteger a estorbar.

POR QUÉ AHORA SE DESCUBREN SOLOS
---------------------------------
La lista escrita a mano no podía detectar el fallo que este módulo existe para
evitar, y que este repositorio ya cometió DOS veces: un módulo construido
entero —presentador, páginas, permisos— y sin entrada en el menú, así que nadie
podía abrirlo. Activos tenía 12 archivos de UI tras una puerta que no existía;
Precios, seis páginas y datos reales detrás. Ninguna lista fija los delata,
porque el olvido está justamente en no añadirse a la lista.

Por eso `test_every_registered_module_has_a_door` recorre el disco: si mañana
aparece `frontend/desktop/modules/<nuevo>/shell_registration.py` sin entrada
correspondiente, falla aquí y no en la queja de un usuario que no encuentra su
módulo. `_EXPECTED` se conserva además porque comprueba otra cosa: que la ruta
y el permiso de cada entrada sean los que el módulo declara, no unos tecleados
a mano (una errata ahí produce una entrada que no resuelve a nada, y
`SidebarResolver` la descarta en silencio en vez de fallar).
"""
from __future__ import annotations

import ast
from pathlib import Path

from frontend.desktop.modules.assets.shell_registration import (
    ASSETS_MODULE_ID, ASSETS_REQUIRED_PERMISSION, ASSETS_ROUTE_ID,
)
from frontend.desktop.modules.business_intelligence.shell_registration import (
    BUSINESS_INTELLIGENCE_MODULE_ID, BUSINESS_INTELLIGENCE_REQUIRED_PERMISSION,
    BUSINESS_INTELLIGENCE_ROUTE_ID,
)
from frontend.desktop.modules.cash_register.shell_registration import (
    CASH_REGISTER_MODULE_ID, CASH_REGISTER_REQUIRED_PERMISSION, CASH_REGISTER_ROUTE_ID,
)
from frontend.desktop.modules.configuracion.shell_registration import (
    CONFIGURACION_MODULE_ID, CONFIGURACION_REQUIRED_PERMISSION, CONFIGURACION_ROUTE_ID,
)
from frontend.desktop.modules.customers_crm.shell_registration import (
    CUSTOMERS_CRM_MODULE_ID, CUSTOMERS_CRM_REQUIRED_PERMISSION, CUSTOMERS_CRM_ROUTE_ID,
)
from frontend.desktop.modules.fidelidad.shell_registration import (
    FIDELIDAD_MODULE_ID, FIDELIDAD_REQUIRED_PERMISSION, FIDELIDAD_ROUTE_ID,
)
from frontend.desktop.modules.finance.shell_registration import (
    FINANCE_MODULE_ID, FINANCE_REQUIRED_PERMISSION, FINANCE_ROUTE_ID,
)
from frontend.desktop.modules.hr.shell_registration import (
    HR_MODULE_ID, HR_REQUIRED_PERMISSION, HR_ROUTE_ID,
)
from frontend.desktop.modules.inventory.shell_registration import (
    INVENTORY_MODULE_ID, INVENTORY_REQUIRED_PERMISSION, INVENTORY_ROUTE_ID,
)
from frontend.desktop.modules.losses.shell_registration import (
    LOSSES_MODULE_ID, LOSSES_REQUIRED_PERMISSION, LOSSES_ROUTE_ID,
)
from frontend.desktop.modules.meat_processing.shell_registration import (
    MEAT_PROCESSING_MODULE_ID, MEAT_PROCESSING_REQUIRED_PERMISSION,
    MEAT_PROCESSING_ROUTE_ID,
)
from frontend.desktop.modules.orders_delivery.shell_registration import (
    ORDERS_DELIVERY_MODULE_ID, ORDERS_DELIVERY_REQUIRED_PERMISSION,
    ORDERS_DELIVERY_ROUTE_ID,
)
from frontend.desktop.modules.pricing.shell_registration import (
    PRICING_MODULE_ID, PRICING_REQUIRED_PERMISSION, PRICING_ROUTE_ID,
)
from frontend.desktop.modules.products.shell_registration import (
    PRODUCTS_MODULE_ID, PRODUCTS_REQUIRED_PERMISSION, PRODUCTS_ROUTE_ID,
)
from frontend.desktop.modules.purchasing.shell_registration import (
    PURCHASING_MODULE_ID, PURCHASING_REQUIRED_PERMISSION, PURCHASING_ROUTE_ID,
)
from frontend.desktop.modules.sales_pos.shell_registration import (
    SALES_POS_MODULE_ID, SALES_POS_REQUIRED_PERMISSION, SALES_POS_ROUTE_ID,
)
from frontend.desktop.modules.transfers.shell_registration import (
    TRANSFERS_MODULE_ID, TRANSFERS_REQUIRED_PERMISSION, TRANSFERS_ROUTE_ID,
)
from frontend.desktop.shell.sidebar.migrated_modules_navigation import (
    MIGRATED_MODULES_NAVIGATION_ITEMS,
    register_migrated_modules_navigation,
)
from frontend.desktop.shell.sidebar.navigation_item_registry import NavigationItemRegistry

_EXPECTED = {
    SALES_POS_MODULE_ID: (SALES_POS_ROUTE_ID, SALES_POS_REQUIRED_PERMISSION),
    CASH_REGISTER_MODULE_ID: (CASH_REGISTER_ROUTE_ID, CASH_REGISTER_REQUIRED_PERMISSION),
    INVENTORY_MODULE_ID: (INVENTORY_ROUTE_ID, INVENTORY_REQUIRED_PERMISSION),
    TRANSFERS_MODULE_ID: (TRANSFERS_ROUTE_ID, TRANSFERS_REQUIRED_PERMISSION),
    PRODUCTS_MODULE_ID: (PRODUCTS_ROUTE_ID, PRODUCTS_REQUIRED_PERMISSION),
    CUSTOMERS_CRM_MODULE_ID: (CUSTOMERS_CRM_ROUTE_ID, CUSTOMERS_CRM_REQUIRED_PERMISSION),
    PURCHASING_MODULE_ID: (PURCHASING_ROUTE_ID, PURCHASING_REQUIRED_PERMISSION),
    FINANCE_MODULE_ID: (FINANCE_ROUTE_ID, FINANCE_REQUIRED_PERMISSION),
    HR_MODULE_ID: (HR_ROUTE_ID, HR_REQUIRED_PERMISSION),
    CONFIGURACION_MODULE_ID: (CONFIGURACION_ROUTE_ID, CONFIGURACION_REQUIRED_PERMISSION),
    BUSINESS_INTELLIGENCE_MODULE_ID: (
        BUSINESS_INTELLIGENCE_ROUTE_ID, BUSINESS_INTELLIGENCE_REQUIRED_PERMISSION),
    LOSSES_MODULE_ID: (LOSSES_ROUTE_ID, LOSSES_REQUIRED_PERMISSION),
    MEAT_PROCESSING_MODULE_ID: (MEAT_PROCESSING_ROUTE_ID, MEAT_PROCESSING_REQUIRED_PERMISSION),
    ORDERS_DELIVERY_MODULE_ID: (ORDERS_DELIVERY_ROUTE_ID, ORDERS_DELIVERY_REQUIRED_PERMISSION),
    FIDELIDAD_MODULE_ID: (FIDELIDAD_ROUTE_ID, FIDELIDAD_REQUIRED_PERMISSION),
    # Tarjetas de fidelidad: sección DENTRO de Fidelidad desde LOY-29 (§5-6).
    ASSETS_MODULE_ID: (ASSETS_ROUTE_ID, ASSETS_REQUIRED_PERMISSION),
    PRICING_MODULE_ID: (PRICING_ROUTE_ID, PRICING_REQUIRED_PERMISSION),
}

_MODULES_DIR = (
    Path(__file__).resolve().parents[4] / "frontend" / "desktop" / "modules"
)


def _module_ids_declared_on_disk() -> set[str]:
    """`<MODULO>_MODULE_ID` de cada `shell_registration.py`, leído del código.

    Estático a propósito: importar los 18 módulos arrastraría Qt y las
    conexiones de cada raíz de composición, y la pregunta —¿este módulo se
    declara para el shell?— se responde leyendo el archivo.
    """
    encontrados: set[str] = set()
    for registro in sorted(_MODULES_DIR.glob("*/shell_registration.py")):
        arbol = ast.parse(registro.read_text(encoding="utf-8"))
        for nodo in arbol.body:
            if not isinstance(nodo, ast.Assign):
                continue
            if not isinstance(nodo.value, ast.Constant) or not isinstance(nodo.value.value, str):
                continue
            for destino in nodo.targets:
                if isinstance(destino, ast.Name) and destino.id.endswith("_MODULE_ID"):
                    encontrados.add(nodo.value.value)
    return encontrados


def test_every_registered_module_has_a_door():
    """Un módulo declarado para el shell y sin entrada de menú no se puede abrir."""
    declarados = _module_ids_declared_on_disk()
    con_entrada = {item.module_id for item in MIGRATED_MODULES_NAVIGATION_ITEMS}
    assert declarados, "No se encontró ningún shell_registration.py; ruta mal resuelta"
    assert declarados - con_entrada == set(), (
        "Módulos construidos y sin puerta en el menú: "
        f"{sorted(declarados - con_entrada)}")


def test_no_menu_entry_points_at_a_module_that_does_not_exist():
    """La dirección contraria: una entrada huérfana se descarta en silencio."""
    con_entrada = {item.module_id for item in MIGRATED_MODULES_NAVIGATION_ITEMS}
    assert con_entrada - _module_ids_declared_on_disk() == set()


def test_one_item_per_module_and_no_duplicates():
    module_ids = [item.module_id for item in MIGRATED_MODULES_NAVIGATION_ITEMS]
    assert len(module_ids) == len(set(module_ids))
    assert set(module_ids) == set(_EXPECTED)


def test_every_item_matches_its_modules_real_route_and_permission():
    for item in MIGRATED_MODULES_NAVIGATION_ITEMS:
        expected_route, expected_permission = _EXPECTED[item.module_id]
        assert item.route_id == expected_route
        assert item.required_permission == expected_permission


def test_item_ids_are_unique():
    ids = [item.item_id for item in MIGRATED_MODULES_NAVIGATION_ITEMS]
    assert len(ids) == len(set(ids))


def test_orders_are_unique_so_render_sequence_is_deterministic():
    orders = [item.order for item in MIGRATED_MODULES_NAVIGATION_ITEMS]
    assert len(orders) == len(set(orders))


def test_register_all_populates_a_real_registry_without_duplicates():
    registry = NavigationItemRegistry()
    register_migrated_modules_navigation(registry)
    assert len(registry.all()) == len(_EXPECTED)
    for module_id, (route_id, _permission) in _EXPECTED.items():
        item = registry.item_for_route(route_id)
        assert item is not None
        assert item.module_id == module_id
