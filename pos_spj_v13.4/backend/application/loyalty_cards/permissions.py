"""Granular Loyalty Cards permission codes (master prompt §59 'Tarjetas').

Mirrors ``backend/application/loyalty/permissions.py``'s own reasoning, but
for the specialized Loyalty Cards sub-bounded context (physical/digital
cards, templates, designer, sheet imposition, batches, printing, QR)
— master prompt §30: "El subdominio Tarjetas debe ser especializado."

The catalog key stays ``TARJETAS_FIDELIDAD`` (not folded into
``GROWTH_ENGINE``) — it already exists in `CANONICAL_MODULE_PERMISSIONS`
and is tied to its own real sidebar entry ("💳 Tarjetas Fidelidad"); this
phase EXTENDS it with granular actions. The original flat ``ver`` action is
kept for backward compatibility.
"""

from __future__ import annotations


class LoyaltyCardsPermissions:
    # ── acceso (§59) ─────────────────────────────────────────────────────
    VIEW = "TARJETAS_FIDELIDAD.ver"
    ACCESS = "TARJETAS_FIDELIDAD.acceso"

    # ── tarjetas (§59) ───────────────────────────────────────────────────
    CARD_VIEW = "TARJETAS_FIDELIDAD.tarjeta.ver"
    CARD_CREATE = "TARJETAS_FIDELIDAD.tarjeta.crear"
    CARD_ASSIGN = "TARJETAS_FIDELIDAD.tarjeta.asignar"
    CARD_ACTIVATE = "TARJETAS_FIDELIDAD.tarjeta.activar"
    CARD_BLOCK = "TARJETAS_FIDELIDAD.tarjeta.bloquear"
    CARD_REPLACE = "TARJETAS_FIDELIDAD.tarjeta.reponer"
    CARD_CANCEL = "TARJETAS_FIDELIDAD.tarjeta.cancelar"

    # ── plantillas (§59) ─────────────────────────────────────────────────
    TEMPLATE_VIEW = "TARJETAS_FIDELIDAD.plantilla.ver"
    TEMPLATE_CREATE = "TARJETAS_FIDELIDAD.plantilla.crear"
    TEMPLATE_EDIT = "TARJETAS_FIDELIDAD.plantilla.editar"
    TEMPLATE_IMPORT = "TARJETAS_FIDELIDAD.plantilla.importar"
    TEMPLATE_APPROVE = "TARJETAS_FIDELIDAD.plantilla.aprobar"
    TEMPLATE_ACTIVATE = "TARJETAS_FIDELIDAD.plantilla.activar"
    TEMPLATE_ARCHIVE = "TARJETAS_FIDELIDAD.plantilla.archivar"

    # ── diseñador / formatos / pliegos (§34, §38, §39, §59) ─────────────
    DESIGNER_ACCESS = "TARJETAS_FIDELIDAD.disenador.acceso"
    FORMAT_MANAGE = "TARJETAS_FIDELIDAD.formato.gestionar"
    SHEET_MANAGE = "TARJETAS_FIDELIDAD.pliego.gestionar"

    # ── lotes / impresión (§43, §50, §51, §59) ──────────────────────────
    BATCH_CREATE = "TARJETAS_FIDELIDAD.lote.crear"
    BATCH_APPROVE = "TARJETAS_FIDELIDAD.lote.aprobar"
    BATCH_PRINT = "TARJETAS_FIDELIDAD.lote.imprimir"
    REPRINT = "TARJETAS_FIDELIDAD.reimprimir"

    # ── QR (§32, §59) ────────────────────────────────────────────────────
    QR_ROTATE = "TARJETAS_FIDELIDAD.qr.rotar"

    # ── auditoría / configuración (§59) ─────────────────────────────────
    AUDIT_VIEW = "TARJETAS_FIDELIDAD.auditoria.ver"
    CONFIG_VIEW = "TARJETAS_FIDELIDAD.configuracion.ver"
    CONFIG_EDIT = "TARJETAS_FIDELIDAD.configuracion.editar"


ALL_LOYALTY_CARDS_PERMISSIONS = frozenset(
    v for k, v in vars(LoyaltyCardsPermissions).items()
    if not k.startswith("_") and isinstance(v, str)
)
