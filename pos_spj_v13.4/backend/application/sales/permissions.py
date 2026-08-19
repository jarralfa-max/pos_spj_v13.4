"""Granular Sales/POS permission codes (master prompt §61).

Sales/POS is never gated by a single ``POS`` permission. Every sensitive
action — completing a sale, applying a protected discount, overriding a
price, opening the cash drawer manually, cancelling, returning, reversing,
reprinting, requesting an invoice — has its own code, and the backend
re-validates each one on every use case (hiding a button is not security —
see the role-name check this phase replaces in
``modulos/ventas.py::set_usuario_actual``).

Codes use the app-wide canonical `MODULO.accion` format (see
`core/security/permission_catalog.py`) so they are stored, granted and
checked exactly like every other module's permissions — `rol_permisos` rows,
the Configuración permission matrix and every other module's
`AuthorizationPolicy` all share this one vocabulary. Comparisons are
case-insensitive (values are normalized to uppercase at check time).

The catalog key stays ``POS`` (not a new ``VENTAS`` key) — it already exists
in `CANONICAL_MODULE_PERMISSIONS` and is tied to the real sidebar entry; this
phase EXTENDS it with granular actions instead of minting a parallel key
(one canonical route per functional area, master prompt §3/§64). The 4
original flat actions (``ver``/``crear``/``cancelar``/``descuento``) are kept
as-is for backward compatibility with anything still checking them.
"""

from __future__ import annotations


class SalesPermissions:
    # ── acceso (§61) — compat con el catálogo original ─────────────────────
    VIEW = "POS.ver"
    ACCESS = "POS.acceso"
    OPEN = "POS.abrir"

    # ── venta (§61) ──────────────────────────────────────────────────────
    SALE_CREATE = "POS.crear"
    LINE_ADD = "POS.venta.linea_agregar"
    LINE_UPDATE = "POS.venta.linea_actualizar"
    LINE_REMOVE = "POS.venta.linea_eliminar"
    SALE_COMPLETE = "POS.venta.completar"
    SALE_CANCEL = "POS.cancelar"
    SALE_SUSPEND = "POS.venta.suspender"
    SALE_RESUME = "POS.venta.reanudar"

    # ── descuentos (§61/§25) ────────────────────────────────────────────
    DISCOUNT_APPLY = "POS.descuento"
    DISCOUNT_CUSTOM = "POS.descuento.personalizado"
    DISCOUNT_OVERRIDE = "POS.descuento.sobrescribir"
    PRICE_OVERRIDE = "POS.precio.sobrescribir"

    # ── pagos (§61/§30-36) ───────────────────────────────────────────────
    PAYMENT_CASH = "POS.pago.efectivo"
    PAYMENT_CARD = "POS.pago.tarjeta"
    PAYMENT_TRANSFER = "POS.pago.transferencia"
    PAYMENT_MIXED = "POS.pago.mixto"
    PAYMENT_CREDIT = "POS.pago.credito"
    PAYMENT_MERCADO_PAGO = "POS.pago.mercado_pago"

    # ── postventa (§61/§42-48) ───────────────────────────────────────────
    RETURN = "POS.devolucion"
    REVERSE = "POS.reverso"
    RECEIPT_REPRINT = "POS.ticket.reimprimir"
    INVOICE_REQUEST = "POS.factura.solicitar"

    # ── hardware (§61/§49-51) ────────────────────────────────────────────
    DRAWER_OPEN_MANUAL = "POS.cajon.abrir_manual"
    SCALE_USE = "POS.bascula.usar"
    DEVICE_DIAGNOSTICS_VIEW = "POS.dispositivo.diagnostico_ver"


ALL_SALES_PERMISSIONS = frozenset(
    v for k, v in vars(SalesPermissions).items()
    if not k.startswith("_") and isinstance(v, str)
)
