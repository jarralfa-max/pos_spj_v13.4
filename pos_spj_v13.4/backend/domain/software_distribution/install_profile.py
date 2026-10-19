"""Install profiles — which capabilities a station has ENABLED.

Phase 1 ships ONE complete bundle to every station. A profile does not
remove files; it decides which capabilities are enabled on the station.
Three layers stay separate and are all evaluated:

1. Install profile (this module) — per station, chosen in the installer.
   A capability that is not installed is hidden from the menu, refused by
   the router and its permission families are denied even to an admin.
2. Feature flags `modulo.<id>` — per branch, in Configuración → Feature
   Flags (`backend/application/feature_flags/module_flags.py`).
3. Permissions — per user/role.

Capability ids are the shell module ids
(`frontend/desktop/modules/<id>/shell_registration.py`);
`tests/architecture/test_install_profile_catalog.py` keeps them in sync.

`permission_modules` lists the permission families (`MODULO` of
`MODULO.accion`) a capability owns EXCLUSIVELY, plus legacy flat-code
prefixes for the three contexts still on flat codes. Only families that no
core module checks are listed — verified by grep on 2026-10-14; the one real
crossing is the POS checking `GROWTH_ENGINE.puntos.canjear`, so a station
without Fidelidad cannot redeem points at the till (accrual keeps running in
the backend). That is why "POS esencial" includes Fidelidad by default.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class InstallProfile(str, Enum):
    POS_ESSENTIAL = "pos_essential"
    ERP_FULL = "erp_full"
    CUSTOM = "custom"

    @property
    def label(self) -> str:
        return {
            "pos_essential": "POS esencial",
            "erp_full": "ERP completo",
            "custom": "Personalizado",
        }[self.value]


class UnknownCapabilityError(ValueError):
    pass


@dataclass(frozen=True)
class Capability:
    id: str
    label: str
    core: bool = False
    requires: tuple[str, ...] = ()
    permission_modules: tuple[str, ...] = ()
    flat_permission_prefixes: tuple[str, ...] = ()


CAPABILITY_CATALOG: tuple[Capability, ...] = (
    # ── Núcleo indecomponible: POS/Caja, catálogo, identidad, configuración ──
    Capability("sales_pos", "Punto de venta", core=True),
    Capability("cash_register", "Caja", core=True),
    Capability("products", "Productos", core=True),
    Capability("inventory", "Inventario", core=True),
    Capability("pricing", "Precios", core=True),
    Capability("customers_crm", "Clientes y CRM", core=True),
    Capability("configuracion", "Configuración", core=True),
    # ── Opcionales ──────────────────────────────────────────────────────────
    Capability("fidelidad", "Fidelidad y tarjetas",
               permission_modules=("GROWTH_ENGINE", "TARJETAS_FIDELIDAD")),
    Capability("orders_delivery", "Pedidos y entregas",
               permission_modules=("DELIVERY",)),
    # Integración Logística 32cfbf (decisión del usuario): Logística es su propia
    # capacidad. No exige Compras — «Compra en origen» lo pide sólo en su ruta.
    # Las instalaciones de un catálogo anterior que tenían «Pedidos y entregas»
    # la reciben al leer su configuración (ver `migrate_legacy_capabilities`).
    Capability("logistics", "Logística (contenedores y embarques)",
               permission_modules=("LOGISTICA",)),
    Capability("purchasing", "Compras y proveedores",
               permission_modules=("COMPRAS", "PROVEEDORES"),
               flat_permission_prefixes=("SUPPLIERS_",)),
    Capability("transfers", "Transferencias",
               permission_modules=("TRANSFERENCIAS",),
               flat_permission_prefixes=("TRANSFERS_",)),
    Capability("losses", "Mermas",
               permission_modules=("MERMA",),
               flat_permission_prefixes=("LOSSES_",)),
    Capability("meat_processing", "Procesamiento cárnico",
               permission_modules=("PRODUCCION", "CALIDAD")),
    Capability("finance", "Finanzas y contabilidad",
               permission_modules=("FINANZAS", "FINANZAS_UNIFICADAS", "TESORERIA")),
    Capability("hr", "Recursos humanos y nómina", requires=("finance",),
               permission_modules=("RRHH",)),
    Capability("business_intelligence", "Inteligencia de negocio",
               permission_modules=("INTELIGENCIA_BI", "REPORTES_BI")),
    Capability("assets", "Activos", requires=("finance",),
               permission_modules=("ACTIVOS",)),
)

_BY_ID = {capability.id: capability for capability in CAPABILITY_CATALOG}
CORE_CAPABILITIES = frozenset(c.id for c in CAPABILITY_CATALOG if c.core)
ALL_CAPABILITIES = frozenset(_BY_ID)

PROFILE_DEFAULTS: dict[InstallProfile, frozenset[str]] = {
    InstallProfile.POS_ESSENTIAL: CORE_CAPABILITIES | {"fidelidad"},
    InstallProfile.ERP_FULL: ALL_CAPABILITIES,
}


#: Versión del catálogo que escribe el instalador en `install_config.json`.
#: 1 = antes de separar Logística; 2 = con la capacidad `logistics`.
CAPABILITY_CATALOG_VERSION = 2


def migrate_legacy_capabilities(selected: Iterable[str], catalog_version: int) -> set[str]:
    """Una selección personalizada hecha con un catálogo anterior conserva los
    accesos que ya tenía: «Pedidos y entregas» incluía Logística (LOGISTICA)."""
    migrated = set(selected)
    if catalog_version < 2 and "orders_delivery" in migrated:
        migrated.add("logistics")
    return migrated


def capability(capability_id: str) -> Capability:
    try:
        return _BY_ID[capability_id]
    except KeyError as exc:
        raise UnknownCapabilityError(f"Capacidad desconocida: {capability_id!r}") from exc


@dataclass(frozen=True)
class EnabledCapabilities:
    """The resolved, dependency-closed set for one station."""

    profile: InstallProfile
    enabled: frozenset[str]

    @classmethod
    def resolve(
        cls, profile: InstallProfile, selected: Iterable[str] = (),
        catalog_version: int = CAPABILITY_CATALOG_VERSION,
    ) -> "EnabledCapabilities":
        if profile is InstallProfile.CUSTOM:
            requested = migrate_legacy_capabilities(selected, catalog_version)
            unknown = requested - ALL_CAPABILITIES
            if unknown:
                raise UnknownCapabilityError(
                    "Capacidades desconocidas: " + ", ".join(sorted(unknown)))
        else:
            requested = set(PROFILE_DEFAULTS[profile])
        return cls(profile=profile, enabled=_close_over_requirements(requested | CORE_CAPABILITIES))

    @classmethod
    def everything(cls) -> "EnabledCapabilities":
        return cls(profile=InstallProfile.ERP_FULL, enabled=ALL_CAPABILITIES)

    @property
    def disabled(self) -> frozenset[str]:
        return ALL_CAPABILITIES - self.enabled

    def is_enabled(self, capability_id: str) -> bool:
        # A module id outside the catalog is not governed by install profiles.
        return capability_id not in _BY_ID or capability_id in self.enabled

    @property
    def blocked_permission_modules(self) -> frozenset[str]:
        return frozenset(
            module for cid in self.disabled for module in _BY_ID[cid].permission_modules)

    @property
    def blocked_flat_prefixes(self) -> tuple[str, ...]:
        return tuple(sorted(
            prefix for cid in self.disabled for prefix in _BY_ID[cid].flat_permission_prefixes))

    def permission_blocked(self, normalized_code: str) -> bool:
        """`normalized_code` is the UPPER-CASE comparison form."""
        code = normalized_code.strip().upper()
        if "." in code:
            return code.split(".", 1)[0] in self.blocked_permission_modules
        return any(code.startswith(prefix) for prefix in self.blocked_flat_prefixes)


def _close_over_requirements(requested: set[str]) -> frozenset[str]:
    """Add every transitive requirement. Requirements are always enabled,
    never silently dropped: a capability whose dependency is missing would
    open and fail at its first cross-module call."""
    closed = set(requested)
    pending = list(requested)
    while pending:
        current = _BY_ID[pending.pop()]
        for dependency in current.requires:
            if dependency not in closed:
                closed.add(dependency)
                pending.append(dependency)
    return frozenset(closed)
