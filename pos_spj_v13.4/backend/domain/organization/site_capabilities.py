"""Qué capacidad del sitio exige cada módulo (auditoría enterprise, Fase 2).

Las capacidades de una unidad (Fase 1) se hacen valer en la sesión: en una
planta sin POS no aparece el punto de venta, el router lo rechaza y las familias
de permisos EXCLUSIVAS del módulo se niegan, administrador incluido. Es el mismo
mecanismo que el perfil de instalación (`software_distribution.install_profile`),
pero por sitio de operación en vez de por estación.

Los módulos que no aparecen aquí (Productos, Precios, Configuración, RR. HH.,
Activos, Fidelidad) no dependen de una capacidad del sitio. Las familias de
permisos que se bloquean son las que el catálogo de instalación ya declara
exclusivas de cada módulo (`Capability.permission_modules`); los módulos del
núcleo (POS, Caja, Inventario, CRM) no declaran familias exclusivas porque otros
módulos las consultan, así que en ellos se oculta y se rechaza la ruta.
"""

from __future__ import annotations

from backend.domain.organization.org_unit import Capability
from backend.domain.software_distribution.install_profile import CAPABILITY_CATALOG

#: id del módulo del shell → capacidad que debe tener el sitio de la sesión.
MODULE_SITE_CAPABILITY: dict[str, Capability] = {
    "sales_pos": Capability.POS,
    "cash_register": Capability.CASH,
    "inventory": Capability.INVENTORY,
    "transfers": Capability.INVENTORY,
    "losses": Capability.INVENTORY,
    "purchasing": Capability.PURCHASING,
    "meat_processing": Capability.PRODUCTION,
    "logistics": Capability.LOGISTICS,
    "orders_delivery": Capability.SALES,
    "finance": Capability.FINANCE,
    "customers_crm": Capability.CRM,
    "business_intelligence": Capability.BI,
}

_FAMILIES = {c.id: c.permission_modules for c in CAPABILITY_CATALOG}


def module_allowed(module_id: str, site_capabilities: frozenset[str] | None) -> bool:
    """`site_capabilities=None`: el sitio no está gobernado (sin estructura
    organizacional o sesión sin sitio) → no se restringe nada."""
    if site_capabilities is None:
        return True
    requerida = MODULE_SITE_CAPABILITY.get(module_id)
    return requerida is None or requerida.value in site_capabilities


def blocked_permission_families(site_capabilities: frozenset[str] | None) -> frozenset[str]:
    if site_capabilities is None:
        return frozenset()
    return frozenset(
        familia for modulo, cap in MODULE_SITE_CAPABILITY.items()
        if cap.value not in site_capabilities for familia in _FAMILIES.get(modulo, ()))


__all__ = ["MODULE_SITE_CAPABILITY", "blocked_permission_families", "module_allowed"]
