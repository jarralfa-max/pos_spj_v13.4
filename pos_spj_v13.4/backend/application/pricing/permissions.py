"""Granular pricing / costing permission codes (PRC-1).

Pricing is never gated by a single ``PRECIOS`` permission. Viewing cost, changing a
sale price, approving/activating a price list, or overriding the minimum-price
protection each has its own code, re-validated by every use case (hiding a button
is not security). Segregation of duties (create ≠ approve) sits on top.
"""

from __future__ import annotations


class PricingPermissions:
    """Vocabulario punteado `PRECIOS.<accion>` (migrado desde `PRICING_*`).

    Los códigos PLANOS anteriores no eran otorgables desde Configuración →
    Seguridad → Permisos: esa matriz se construye desde `permission_catalog.py`,
    que sólo publica módulos con forma `MODULO.accion`. El efecto real era que
    TODO el módulo quedaba reservado al administrador, que pasa por bypass.

    La migración no deja nada inerte —a diferencia de la de Inventario
    (migración 179)— porque `PRECIOS` nunca estuvo sembrado en `rol_permisos`:
    no había concesiones gruesas que retirar. Es estrictamente aditivo.

    Las acciones compuestas (`lista.aprobar`) son válidas: `split_permission`
    corta sólo en el PRIMER punto, igual que `CONFIGURACION.valor.aprobar`.
    """

    # ── consulta ──────────────────────────────────────────────────────────
    ACCESS = "PRECIOS.acceder"
    VIEW = "PRECIOS.ver"
    VIEW_COST = "PRECIOS.costo.ver"
    VIEW_MARGIN = "PRECIOS.margen.ver"
    VIEW_AUDIT = "PRECIOS.auditoria.ver"
    EXPORT = "PRECIOS.exportar"

    # ── precios de venta ──────────────────────────────────────────────────
    PRICE_CREATE = "PRECIOS.precio.crear"
    PRICE_EDIT = "PRECIOS.precio.editar"
    PRICE_MIN_OVERRIDE = "PRECIOS.precio.minimo.excepcion"  # vender bajo el mínimo
    VOLUME_PRICE_MANAGE = "PRECIOS.volumen.gestionar"
    BRANCH_PRICE_MANAGE = "PRECIOS.sucursal.gestionar"

    # ── listas de precio ──────────────────────────────────────────────────
    LIST_VIEW = "PRECIOS.lista.ver"
    LIST_CREATE = "PRECIOS.lista.crear"
    LIST_EDIT = "PRECIOS.lista.editar"
    LIST_SUBMIT = "PRECIOS.lista.enviar"
    LIST_APPROVE = "PRECIOS.lista.aprobar"
    LIST_ACTIVATE = "PRECIOS.lista.activar"
    LIST_DEACTIVATE = "PRECIOS.lista.desactivar"
    CUSTOMER_LIST_ASSIGN = "PRECIOS.lista.cliente.asignar"

    # ── costos ────────────────────────────────────────────────────────────
    COST_MANAGE = "PRECIOS.costo.gestionar"
    COST_STANDARD_SET = "PRECIOS.costo.estandar.fijar"

    # ── configuración ─────────────────────────────────────────────────────
    SETTINGS_VIEW = "PRECIOS.configuracion.ver"
    SETTINGS_MANAGE = "PRECIOS.configuracion.gestionar"


ALL_PRICING_PERMISSIONS = frozenset(
    v for k, v in vars(PricingPermissions).items()
    if not k.startswith("_") and isinstance(v, str)
)


# Pares crea → aprueba/activa vigilados por la segregación de funciones.
SEGREGATED_APPROVALS = {
    PricingPermissions.LIST_APPROVE: PricingPermissions.LIST_CREATE,
    PricingPermissions.LIST_ACTIVATE: PricingPermissions.LIST_CREATE,
}
