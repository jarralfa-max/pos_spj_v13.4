"""Granular Fidelidad/Loyalty permission codes (master prompt §59).

Loyalty is never gated by a single ``GROWTH_ENGINE.ver`` code. Every
sensitive action — approving a program, crediting/redeeming/adjusting
points, activating a campaign, issuing/overriding a coupon, reloading a
voucher, drawing a sweepstakes winner — has its own granular code, and the
backend re-validates each one on every future use case (§59: "No autorizar
por nombre de rol").

Codes use the app-wide canonical `MODULO.accion` format (see
`core/security/permission_catalog.py`), case-insensitive at check time.

The catalog key stays ``GROWTH_ENGINE`` (not a new ``FIDELIDAD`` key) — it
already exists in `CANONICAL_MODULE_PERMISSIONS` and is tied to the real
sidebar entry ("⭐ Fidelización"); this phase EXTENDS it with granular
actions instead of minting a parallel key (one canonical route per
functional area, master prompt §3/§64 — same convention SALES-2 applied to
`POS`, see [[feedback_permissions_compras_standard]]). The original flat
``ver`` action is kept for backward compatibility.

Loyalty Cards (physical/digital cards, templates, designer, batches,
printing, QR) is a separate bounded context with its OWN catalog key
(``TARJETAS_FIDELIDAD``) and its own permissions module —
``backend/application/loyalty_cards/permissions.py`` — master prompt §30:
"El subdominio Tarjetas debe ser especializado."
"""

from __future__ import annotations


class LoyaltyPermissions:
    # ── acceso (§59) — compat con el catálogo original ─────────────────────
    VIEW = "GROWTH_ENGINE.ver"
    ACCESS = "GROWTH_ENGINE.acceso"
    DASHBOARD_VIEW = "GROWTH_ENGINE.dashboard.ver"
    AUDIT_VIEW = "GROWTH_ENGINE.auditoria.ver"

    # ── programas (§59) ──────────────────────────────────────────────────
    PROGRAM_VIEW = "GROWTH_ENGINE.programa.ver"
    PROGRAM_CREATE = "GROWTH_ENGINE.programa.crear"
    PROGRAM_EDIT = "GROWTH_ENGINE.programa.editar"
    PROGRAM_APPROVE = "GROWTH_ENGINE.programa.aprobar"
    PROGRAM_ACTIVATE = "GROWTH_ENGINE.programa.activar"
    PROGRAM_SUSPEND = "GROWTH_ENGINE.programa.suspender"

    # ── membresías (§59) ─────────────────────────────────────────────────
    MEMBERSHIP_VIEW = "GROWTH_ENGINE.membresia.ver"
    MEMBERSHIP_ENROLL = "GROWTH_ENGINE.membresia.inscribir"
    MEMBERSHIP_SUSPEND = "GROWTH_ENGINE.membresia.suspender"
    MEMBERSHIP_CLOSE = "GROWTH_ENGINE.membresia.cerrar"

    # ── puntos (§59) ─────────────────────────────────────────────────────
    POINTS_VIEW = "GROWTH_ENGINE.puntos.ver"
    POINTS_CREDIT = "GROWTH_ENGINE.puntos.acreditar"
    POINTS_REDEEM = "GROWTH_ENGINE.puntos.canjear"
    POINTS_ADJUST = "GROWTH_ENGINE.puntos.ajustar"
    POINTS_REVERSE = "GROWTH_ENGINE.puntos.reversar"
    POINTS_AUDIT = "GROWTH_ENGINE.puntos.auditar"

    # ── niveles / recompensas / retos (§7, §9, §15, §16) ────────────────
    TIER_VIEW = "GROWTH_ENGINE.nivel.ver"
    TIER_MANAGE = "GROWTH_ENGINE.nivel.gestionar"
    REWARD_VIEW = "GROWTH_ENGINE.recompensa.ver"
    REWARD_MANAGE = "GROWTH_ENGINE.recompensa.gestionar"
    REWARD_REDEEM = "GROWTH_ENGINE.recompensa.canjear"
    CHALLENGE_VIEW = "GROWTH_ENGINE.reto.ver"
    CHALLENGE_MANAGE = "GROWTH_ENGINE.reto.gestionar"

    # ── referidos / cumpleaños / retención (§17, §18, §20) ──────────────
    REFERRAL_VIEW = "GROWTH_ENGINE.referido.ver"
    REFERRAL_MANAGE = "GROWTH_ENGINE.referido.gestionar"
    REFERRAL_APPROVE = "GROWTH_ENGINE.referido.aprobar"
    BIRTHDAY_VIEW = "GROWTH_ENGINE.cumpleanos.ver"
    BIRTHDAY_MANAGE = "GROWTH_ENGINE.cumpleanos.gestionar"
    RETENTION_VIEW = "GROWTH_ENGINE.retencion.ver"
    RETENTION_MANAGE = "GROWTH_ENGINE.retencion.gestionar"

    # ── campañas (§59) ───────────────────────────────────────────────────
    CAMPAIGN_VIEW = "GROWTH_ENGINE.campana.ver"
    CAMPAIGN_CREATE = "GROWTH_ENGINE.campana.crear"
    CAMPAIGN_APPROVE = "GROWTH_ENGINE.campana.aprobar"
    CAMPAIGN_ACTIVATE = "GROWTH_ENGINE.campana.activar"

    # ── cupones (§59) ────────────────────────────────────────────────────
    COUPON_VIEW = "GROWTH_ENGINE.cupon.ver"
    COUPON_ISSUE = "GROWTH_ENGINE.cupon.emitir"
    COUPON_REDEEM = "GROWTH_ENGINE.cupon.canjear"
    COUPON_CANCEL = "GROWTH_ENGINE.cupon.cancelar"
    COUPON_OVERRIDE = "GROWTH_ENGINE.cupon.override"

    # ── vales (§59) ──────────────────────────────────────────────────────
    VOUCHER_VIEW = "GROWTH_ENGINE.vale.ver"
    VOUCHER_ISSUE = "GROWTH_ENGINE.vale.emitir"
    VOUCHER_REDEEM = "GROWTH_ENGINE.vale.canjear"
    VOUCHER_RELOAD = "GROWTH_ENGINE.vale.recargar"
    VOUCHER_CANCEL = "GROWTH_ENGINE.vale.cancelar"
    VOUCHER_ADJUST = "GROWTH_ENGINE.vale.ajustar"

    # ── sorteos (§59) ────────────────────────────────────────────────────
    SWEEPSTAKES_VIEW = "GROWTH_ENGINE.sorteo.ver"
    SWEEPSTAKES_MANAGE = "GROWTH_ENGINE.sorteo.gestionar"
    SWEEPSTAKES_DRAW = "GROWTH_ENGINE.sorteo.sortear"
    SWEEPSTAKES_TICKET_PRINT = "GROWTH_ENGINE.sorteo.boleto_imprimir"
    SWEEPSTAKES_TICKET_REPRINT = "GROWTH_ENGINE.sorteo.boleto_reimprimir"

    # ── antifraude (§29, §59) ────────────────────────────────────────────
    FRAUD_VIEW = "GROWTH_ENGINE.antifraude.ver"
    FRAUD_MANAGE = "GROWTH_ENGINE.antifraude.gestionar"

    # ── configuración (§58) ──────────────────────────────────────────────
    CONFIG_VIEW = "GROWTH_ENGINE.configuracion.ver"
    CONFIG_EDIT = "GROWTH_ENGINE.configuracion.editar"


ALL_LOYALTY_PERMISSIONS = frozenset(
    v for k, v in vars(LoyaltyPermissions).items()
    if not k.startswith("_") and isinstance(v, str)
)
