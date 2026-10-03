"""Etiquetas en español de los valores de los enums de Fidelidad.

La pantalla nunca muestra `PENDING_APPROVAL` ni `WIN_BACK`: muestra lo que dice
este mapa. Un valor sin etiqueta cae al genérico y, si tampoco está, se muestra
tal cual — visible, no escondido — para que la omisión se note y se corrija.
"""

from __future__ import annotations

from enum import Enum

_GENERIC: dict[str, str] = {
    "DRAFT": "Borrador", "PENDING_APPROVAL": "Por aprobar", "APPROVED": "Aprobado",
    "ACTIVE": "Activo", "SUSPENDED": "Suspendido", "CLOSED": "Cerrado",
    "ARCHIVED": "Archivado", "BLOCKED": "Bloqueado", "CANCELLED": "Cancelado",
    "EXPIRED": "Vencido", "COMPLETED": "Completado", "PAUSED": "En pausa",
    "SCHEDULED": "Programado", "PENDING": "Pendiente", "REVERSED": "Reversado",
    "RESERVED": "Reservado", "ISSUED": "Emitido", "REDEEMED": "Canjeado",
    "CONFIRMED": "Confirmado", "FAILED": "Fallido", "PRINTED": "Impreso",
    "PHYSICAL": "Física", "DIGITAL": "Digital", "BOTH": "Física y digital",
    "NONE": "Ninguno", "POINTS": "Puntos", "COUPON": "Cupón", "VOUCHER": "Vale",
    "REWARD": "Recompensa", "REFERRAL": "Referido", "BIRTHDAY": "Cumpleaños",
    "FIXED_AMOUNT": "Monto fijo", "PERCENTAGE": "Porcentaje",
    "FREE_DELIVERY": "Envío gratis", "WIN_BACK": "Recuperación", "AVAILABLE": "Disponible",
    "CONSUMED": "Consumido", "REJECTED": "Rechazado", "VOID": "Anulado",
}

_POR_ENUM: dict[str, dict[str, str]] = {
    "TransactionType": {
        "EARN": "Acumulación", "BONUS": "Bono", "REDEEM": "Canje", "RESERVE": "Reserva",
        "RELEASE": "Liberación", "EXPIRE": "Caducidad", "ADJUSTMENT": "Ajuste",
        "REVERSAL": "Reverso", "TRANSFER_IN": "Traspaso recibido",
        "TRANSFER_OUT": "Traspaso enviado"},
    "MembershipStatus": {"ACTIVE": "Activa", "SUSPENDED": "Suspendida",
                         "BLOCKED": "Bloqueada", "CLOSED": "Cerrada"},
    "AccountStatus": {"ACTIVE": "Activa", "SUSPENDED": "Suspendida", "CLOSED": "Cerrada"},
    "CampaignType": {
        "ACQUISITION": "Adquisición", "RETENTION": "Retención", "WIN_BACK": "Recuperación",
        "BIRTHDAY": "Cumpleaños", "REFERRAL": "Referidos", "SEASONAL": "De temporada",
        "PRODUCT_PUSH": "Impulso de producto", "BRANCH_SPECIFIC": "Por sucursal",
        "LOYALTY_TIER": "Por nivel", "CLEARANCE": "Liquidación"},
    "CampaignStatus": {"ACTIVE": "Activa", "APPROVED": "Aprobada", "SCHEDULED": "Programada",
                       "COMPLETED": "Concluida", "CANCELLED": "Cancelada", "PAUSED": "En pausa"},
    "ChallengeCriteriaType": {
        "PURCHASE_COUNT": "Número de compras", "SPEND_AMOUNT": "Monto gastado",
        "PRODUCT_CATEGORY": "Categoría de producto", "PRODUCT_PURCHASE": "Compra de producto",
        "BRANCH_VISIT": "Visita a sucursal", "REFERRAL": "Referidos",
        "BIRTHDAY": "Cumpleaños", "CONSECUTIVE_WEEKS": "Semanas consecutivas",
        "MULTI_CATEGORY": "Varias categorías", "CUSTOM_RULE": "Regla personalizada"},
    "ChallengeMode": {"CHALLENGE": "Reto", "MISSION": "Misión", "MILESTONE": "Logro"},
    "ChallengeStatus": {"ACTIVE": "Activo", "COMPLETED": "Concluido"},
    "FraudCaseStatus": {"OPEN": "Abierto", "UNDER_REVIEW": "En revisión",
                        "CONFIRMED": "Confirmado", "DISMISSED": "Descartado"},
    "FraudCaseSubjectType": {
        "REFERRAL": "Referido", "TRANSACTION": "Movimiento de puntos",
        "MEMBERSHIP": "Membresía", "COUPON": "Cupón", "VOUCHER": "Vale",
        "SWEEPSTAKES_ENTRY": "Participación de sorteo"},
    "ReferralStatus": {"REGISTERED": "Registrado", "QUALIFIED": "Calificado",
                       "REWARDED": "Recompensado", "REJECTED": "Rechazado",
                       "EXPIRED": "Vencido", "FRAUD_SUSPECTED": "Sospecha de fraude"},
    "RewardRedemptionStatus": {"RESERVED": "Reservado", "CONFIRMED": "Confirmado",
                               "CANCELLED": "Cancelado"},
    "RewardType": {"PRODUCT": "Producto", "DISCOUNT": "Descuento",
                   "FIXED_AMOUNT": "Monto fijo", "PERCENTAGE": "Porcentaje",
                   "FREE_DELIVERY": "Envío gratis", "COUPON": "Cupón", "VOUCHER": "Vale",
                   "EXPERIENCE": "Experiencia", "OTHER": "Otro"},
    "TierEvaluationMethod": {"ROLLING_PERIOD": "Periodo móvil",
                             "CALENDAR_YEAR": "Año calendario", "LIFETIME": "Histórico",
                             "FIXED_PERIOD": "Periodo fijo"},
    "TransactionStatus": {"AVAILABLE": "Disponible", "CONSUMED": "Consumido"},
    "ProgramStatus": {},
    "BirthdayBenefitType": {},
    "CommercialBenefitType": {
        "FIXED_AMOUNT": "Monto fijo", "PERCENTAGE": "Porcentaje",
        "FREE_PRODUCT": "Producto gratis", "BUY_X_GET_Y": "Compra X lleva Y",
        "FREE_DELIVERY": "Envío gratis", "PRICE_OVERRIDE": "Precio especial"},
    "CouponType": {
        "PUBLIC_CODE": "Código público", "UNIQUE_CODE": "Código único",
        "AUTOMATIC": "Automático", "PERSONALIZED": "Personalizado",
        "BIRTHDAY": "Cumpleaños", "REFERRAL": "Referido", "WIN_BACK": "Recuperación",
        "LOYALTY_REWARD": "Recompensa de lealtad", "SUPPLIER_FUNDED": "Fondeado por proveedor",
        "EMPLOYEE_GRANTED": "Otorgado por empleado"},
    "CouponInstanceStatus": {"ISSUED": "Emitido", "ACTIVE": "Vigente"},
    "VoucherType": {
        "REFUND_VOUCHER": "Vale por devolución", "STORE_CREDIT": "Saldo a favor",
        "PROMOTIONAL_VOUCHER": "Vale promocional", "COMPENSATION_VOUCHER": "Vale de compensación",
        "PREPAID_VOUCHER": "Vale prepagado", "SUPPLIER_FUNDED_VOUCHER": "Fondeado por proveedor",
        "EMPLOYEE_AUTHORIZED_VOUCHER": "Autorizado por empleado"},
    "VoucherInstanceStatus": {"ISSUED": "Emitido", "ACTIVE": "Vigente",
                              "PARTIALLY_REDEEMED": "Canjeado parcialmente"},
    "SweepstakesCampaignStatus": {"DRAWN": "Sorteado", "ACTIVE": "Activa",
                                  "APPROVED": "Aprobada", "CLOSED": "Cerrada",
                                  "CANCELLED": "Cancelada", "PAUSED": "En pausa"},
    "SweepstakesDrawStatus": {"SCHEDULED": "Programado", "COMPLETED": "Realizado"},
    "SweepstakesEntryMethod": {
        "PURCHASE_AMOUNT": "Por monto de compra", "PRODUCT_PURCHASE": "Por producto",
        "MANUAL_GRANT": "Otorgamiento manual", "REFERRAL": "Por referido",
        "LOYALTY_POINTS_EXCHANGE": "Canje de puntos"},
    "SweepstakesPrizeStatus": {"PENDING": "Pendiente", "ASSIGNED": "Asignado",
                               "DELIVERED": "Entregado"},
    "SweepstakesTicketStatus": {"ISSUED": "Emitido", "PRINTED": "Impreso", "VOID": "Anulado"},
    "SweepstakesWinnerStatus": {
        "PENDING_VALIDATION": "Por validar", "VALIDATED": "Validado",
        "DISQUALIFIED": "Descalificado", "PRIZE_DELIVERED": "Premio entregado",
        "EXPIRED": "Vencido"},
    "LoyaltyCardStatus": {"ISSUED": "Emitida", "ACTIVE": "Activa", "BLOCKED": "Bloqueada",
                          "REPLACED": "Repuesta", "CANCELLED": "Cancelada", "EXPIRED": "Vencida"},
    "LoyaltyCardBatchStatus": {"PRINTING": "Imprimiendo", "COMPLETED": "Terminado"},
    "LoyaltyCardBatchItemStatus": {},
    "LoyaltyCardPrintJobStatus": {"RENDERING": "Generando", "READY": "Listo"},
    "LoyaltyCardTemplateStatus": {"ACTIVE": "Activa", "ARCHIVED": "Archivada",
                                  "APPROVED": "Aprobada"},
    "LoyaltyCardTemplateVersionStatus": {"ACTIVE": "Activa", "ARCHIVED": "Archivada",
                                         "APPROVED": "Aprobada"},
    "LoyaltyCardType": {"PHYSICAL": "Física", "DIGITAL": "Digital"},
    "SheetOrientation": {"PORTRAIT": "Vertical", "LANDSCAPE": "Horizontal"},
}


def label_for(enum_cls: type[Enum] | None, value) -> str:
    if value is None or value == "":
        return "—"
    raw = value.value if isinstance(value, Enum) else str(value)
    if enum_cls is not None:
        propio = _POR_ENUM.get(enum_cls.__name__, {})
        if raw in propio:
            return propio[raw]
    return _GENERIC.get(raw, raw)


def options_for(enum_cls: type[Enum], only: tuple[str, ...] = ()) -> list[tuple[str, str]]:
    return [(m.value, label_for(enum_cls, m.value)) for m in enum_cls
            if not only or m.value in only]


__all__ = ["label_for", "options_for"]
