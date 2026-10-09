"""Etiquetas en español y variantes de insignia para los enums de Clientes y CRM.

CRM-43 (re-auditoría sobre la base real, 2026-10-08): el directorio mostraba
``PUBLIC_CUSTOMER`` y el expediente ``NOT_CONFIGURED`` tal cual salían del
dominio. Toda página del módulo traduce aquí — un solo diccionario por
vocabulario, nunca un ``_STATUS_LABELS`` por página.

``label(kind, value)`` acepta el enum o su ``.value``; un valor desconocido se
muestra tal cual (mejor un código legible que una celda vacía).
``variant(kind, value)`` devuelve la variante semántica de ``StatusBadge``
(``neutral/info/success/warning/danger/accent``): el color NUNCA es el único
indicador — la insignia siempre lleva el texto.
"""

from __future__ import annotations

from enum import Enum

_LABELS: dict[str, dict[str, str]] = {
    "customer_type": {
        "INDIVIDUAL": "Persona física", "BUSINESS": "Empresa",
        "PUBLIC_CUSTOMER": "Público en general", "EMPLOYEE": "Empleado",
        "INTERNAL": "Interno", "OTHER": "Otro",
    },
    "customer_status": {
        "DRAFT": "Borrador", "PROSPECT": "Prospecto", "ACTIVE": "Activo",
        "INACTIVE": "Inactivo", "SUSPENDED": "Suspendido", "BLOCKED": "Bloqueado",
        "CLOSED": "Cerrado", "MERGED": "Fusionado", "ANONYMIZED": "Anonimizado",
    },
    "lifecycle": {
        "PROSPECT": "Prospecto", "LEAD": "Lead", "QUALIFIED": "Calificado",
        "CUSTOMER": "Cliente", "REPEAT_CUSTOMER": "Cliente recurrente",
        "AT_RISK": "En riesgo", "INACTIVE": "Inactivo", "LOST": "Perdido",
    },
    "decision_role": {
        "DECISION_MAKER": "Decide la compra", "INFLUENCER": "Influye",
        "BUYER": "Comprador", "USER": "Usuario", "FINANCE_CONTACT": "Finanzas / pagos",
        "DELIVERY_CONTACT": "Recibe entregas", "OTHER": "Otro",
    },
    "address_type": {
        "FISCAL": "Fiscal", "BILLING": "Facturación", "DELIVERY": "Entrega",
        "COMMERCIAL": "Comercial", "PERSONAL": "Personal",
    },
    "validation": {"MANUAL": "Captura manual", "VALIDATED": "Validada", "FAILED": "No válida"},
    "duplicate_status": {
        "DETECTED": "Detectado", "UNDER_REVIEW": "En revisión",
        "CONFIRMED_DUPLICATE": "Duplicado confirmado", "DISMISSED": "Descartado",
        "MERGED": "Fusionado",
    },
    "merge_status": {"PROPOSED": "Propuesta", "EXECUTED": "Ejecutada", "REJECTED": "Rechazada"},
    "quality_status": {
        "OPEN": "Abierta", "ACKNOWLEDGED": "Reconocida", "CORRECTED": "Corregida",
        "DISMISSED": "Descartada",
    },
    "quality_rule": {
        "INCOMPLETE_NAME": "Nombre incompleto", "INVALID_PHONE": "Teléfono inválido",
        "INVALID_EMAIL": "Correo inválido", "INVALID_TAX_ID": "RFC inválido",
        "INCOMPLETE_ADDRESS": "Dirección incompleta",
    },
    "import_status": {
        "PENDING_APPROVAL": "Por aprobar", "PROCESSING": "Procesando",
        "COMPLETED": "Completada", "PARTIAL": "Parcial", "FAILED": "Fallida",
        "REJECTED": "Rechazada",
    },
    "sync_status": {
        "OPEN": "Abierto", "RESOLVED_LOCAL": "Se conservó lo local",
        "RESOLVED_REMOTE": "Se aplicó lo remoto", "RESOLVED_MERGED": "Combinado",
    },
    "lead_status": {
        "NEW": "Nuevo", "ASSIGNED": "Asignado", "CONTACTED": "Contactado",
        "NURTURING": "En seguimiento", "QUALIFIED": "Calificado",
        "UNQUALIFIED": "No calificado", "CONVERTED": "Convertido", "LOST": "Perdido",
        "ARCHIVED": "Archivado",
    },
    "lead_source": {
        "WALK_IN": "Visita a tienda", "POS": "Punto de venta", "WHATSAPP": "WhatsApp",
        "PHONE": "Teléfono", "REFERRAL": "Recomendación", "SOCIAL_MEDIA": "Redes sociales",
        "WEBSITE": "Sitio web", "CAMPAIGN": "Campaña", "IMPORT": "Importación",
        "SALES_REP": "Vendedor", "OTHER": "Otro",
    },
    "priority": {
        "LOW": "Baja", "NORMAL": "Normal", "HIGH": "Alta", "URGENT": "Urgente",
        "CRITICAL": "Crítica",
    },
    "qualification_model": {
        "MANUAL": "Decisión manual", "SCORE_BASED": "Por puntaje",
        "BANT_LIKE": "Criterios (necesidad, presupuesto, autoridad, tiempo)",
        "CUSTOM_RULE": "Regla propia",
    },
    "qualification_decision": {"QUALIFIED": "Calificado", "UNQUALIFIED": "No calificado"},
    "opportunity_status": {
        "OPEN": "Abierta", "WON": "Ganada", "LOST": "Perdida", "CANCELLED": "Cancelada",
        "ON_HOLD": "En pausa",
    },
    "related_entity": {
        "LEAD": "Prospecto", "OPPORTUNITY": "Oportunidad", "CUSTOMER": "Cliente",
        "CASE": "Caso",
    },
    "activity_type": {
        "CALL": "Llamada", "MEETING": "Reunión", "VISIT": "Visita", "EMAIL": "Correo",
        "WHATSAPP": "WhatsApp", "FOLLOW_UP": "Seguimiento", "QUOTE_REVIEW": "Revisión de cotización",
        "PAYMENT_FOLLOW_UP": "Seguimiento de pago", "OTHER": "Otra",
        "TASK": "Tarea", "NOTE": "Nota",
    },
    "work_status": {
        "PLANNED": "Programada", "IN_PROGRESS": "En curso", "COMPLETED": "Completada",
        "CANCELLED": "Cancelada", "OVERDUE": "Vencida",
    },
    "reminder_channel": {
        "IN_APP": "En el sistema", "EMAIL": "Correo", "WHATSAPP_INTERNAL": "WhatsApp interno",
        "PUSH_FUTURE": "Notificación móvil (próximamente)",
    },
    "ownership_type": {
        "PRIMARY": "Responsable principal", "SECONDARY": "Responsable secundario",
        "ACCOUNT_MANAGER": "Ejecutivo de cuenta", "CREDIT_MANAGER": "Responsable de crédito",
        "SERVICE_OWNER": "Responsable de atención",
    },
    "automation_trigger": {
        "LEAD_CREATED": "Se crea un prospecto", "LEAD_IDLE": "Prospecto sin movimiento",
        "OPPORTUNITY_STAGE_CHANGED": "Oportunidad cambia de etapa",
        "OPPORTUNITY_IDLE": "Oportunidad sin movimiento",
        "OPPORTUNITY_OVERDUE": "Oportunidad vencida", "CUSTOMER_INACTIVE": "Cliente inactivo",
        "CASE_CREATED": "Se crea un caso", "SLA_AT_RISK": "SLA en riesgo",
        "SLA_BREACHED": "SLA vencido", "CREDIT_REVIEW_DUE": "Revisión de crédito pendiente",
    },
    "automation_action": {
        "CREATE_TASK": "Crear tarea", "ASSIGN_OWNER": "Asignar responsable",
        "SEND_NOTIFICATION": "Enviar aviso", "CHANGE_PRIORITY": "Cambiar prioridad",
        "ESCALATE_CASE": "Escalar caso", "ADD_TAG": "Agregar etiqueta",
        "ADD_TO_SEGMENT": "Agregar a segmento",
    },
    "automation_execution": {"SUCCEEDED": "Ejecutada", "FAILED": "Falló", "SKIPPED": "Omitida"},
    "segment_source": {
        "MANUAL": "Manual", "RULE_BASED": "Por regla", "IMPORTED": "Importado",
        "ANALYTICS_GENERATED": "Sugerido por análisis",
    },
    "case_type": {
        "QUESTION": "Pregunta", "REQUEST": "Solicitud", "COMPLAINT": "Queja",
        "INCIDENT": "Incidencia", "RETURN_REQUEST": "Solicitud de devolución",
        "DELIVERY_ISSUE": "Problema de entrega", "PAYMENT_ISSUE": "Problema de pago",
        "PRODUCT_QUALITY": "Calidad del producto", "CREDIT_ISSUE": "Crédito", "OTHER": "Otro",
    },
    "case_status": {
        "NEW": "Nuevo", "ASSIGNED": "Asignado", "IN_PROGRESS": "En atención",
        "WAITING_CUSTOMER": "Esperando al cliente", "WAITING_INTERNAL": "Esperando área interna",
        "ESCALATED": "Escalado", "RESOLVED": "Resuelto", "CLOSED": "Cerrado",
        "CANCELLED": "Cancelado",
    },
    "case_channel": {
        "PHONE": "Teléfono", "EMAIL": "Correo", "WHATSAPP": "WhatsApp",
        "WALK_IN": "En tienda", "WEB": "Web", "OTHER": "Otro",
    },
    "escalation_reason": {
        "SLA_BREACHED": "SLA vencido", "PRIORITY_CUSTOMER": "Cliente prioritario",
        "CRITICAL_CASE": "Caso crítico", "MULTIPLE_REOPENS": "Reaperturas repetidas",
        "FINANCIAL_IMPACT": "Impacto financiero", "REPUTATIONAL_RISK": "Riesgo reputacional",
        "OTHER": "Otro",
    },
    "sla_status": {
        "ON_TIME": "En tiempo", "AT_RISK": "En riesgo", "BREACHED": "Vencido",
        "PAUSED": "En pausa", "COMPLETED": "Cumplido",
    },
    "credit_status": {
        "NOT_CONFIGURED": "Sin crédito", "PENDING_APPROVAL": "Por aprobar",
        "UNDER_REVIEW": "En revisión", "AUTHORIZED": "Autorizado", "SUSPENDED": "Suspendido",
        "BLOCKED": "Bloqueado", "CLOSED": "Cerrado",
    },
    "risk_level": {"LOW": "Bajo", "MEDIUM": "Medio", "HIGH": "Alto", "VERY_HIGH": "Muy alto"},
    "receivable_status": {
        "SIN_MOVIMIENTOS": "Sin saldo", "AL_CORRIENTE": "Al corriente",
        "CURRENT": "Al corriente", "OVERDUE": "Con vencido", "VENCIDO": "Con vencido",
        "NO_DATA": "Sin datos",
    },
    "consent_type": {
        "PRIVACY_NOTICE": "Aviso de privacidad", "WHATSAPP": "WhatsApp", "EMAIL": "Correo",
        "SMS": "SMS", "MARKETING": "Promociones y marketing", "PROFILING": "Perfilamiento",
        "TERMS": "Términos y condiciones", "DATA_SHARING": "Compartir datos",
    },
    "consent_status": {
        "PENDING": "Pendiente", "GRANTED": "Otorgado", "WITHDRAWN": "Retirado",
        "EXPIRED": "Vencido", "NOT_REQUIRED": "No requerido",
    },
    "consent_channel": {
        "WEB": "Web", "WHATSAPP": "WhatsApp", "IN_PERSON": "En persona", "PHONE": "Teléfono",
        "EMAIL": "Correo", "IMPORTED": "Importado", "OTHER": "Otro",
    },
    "preferred_channel": {
        "WHATSAPP": "WhatsApp", "EMAIL": "Correo", "SMS": "SMS", "PHONE": "Teléfono",
        "NONE": "Ninguno",
    },
    "privacy_type": {
        "ACCESS": "Acceso", "RECTIFICATION": "Rectificación", "CANCELLATION": "Cancelación",
        "OPPOSITION": "Oposición", "EXPORT": "Exportación de datos",
        "ANONYMIZATION": "Anonimización", "CONSENT_WITHDRAWAL": "Retiro de consentimiento",
    },
    "privacy_status": {
        "RECEIVED": "Recibida", "VALIDATING": "En validación", "IN_PROGRESS": "En proceso",
        "COMPLETED": "Atendida", "REJECTED": "Rechazada", "CANCELLED": "Cancelada",
    },
    "data_category": {
        "INACTIVE_CUSTOMER": "Clientes inactivos", "CONTACT": "Datos de contacto",
        "CONSENT_EVIDENCE": "Evidencia de consentimiento", "CRM_ACTIVITY": "Actividad CRM",
        "SERVICE_CASE": "Casos de atención",
    },
}

_VARIANTS: dict[str, dict[str, str]] = {
    "customer_status": {
        "ACTIVE": "success", "PROSPECT": "info", "DRAFT": "neutral", "INACTIVE": "neutral",
        "SUSPENDED": "warning", "BLOCKED": "danger", "CLOSED": "neutral",
    },
    "lead_status": {
        "NEW": "info", "ASSIGNED": "info", "CONTACTED": "accent", "NURTURING": "accent",
        "QUALIFIED": "success", "UNQUALIFIED": "neutral", "CONVERTED": "success",
        "LOST": "danger",
    },
    "opportunity_status": {"OPEN": "info", "WON": "success", "LOST": "danger",
                           "ON_HOLD": "warning"},
    "work_status": {"PLANNED": "info", "IN_PROGRESS": "accent", "COMPLETED": "success",
                    "OVERDUE": "danger"},
    "case_status": {
        "NEW": "info", "ASSIGNED": "info", "IN_PROGRESS": "accent",
        "WAITING_CUSTOMER": "warning", "WAITING_INTERNAL": "warning", "ESCALATED": "danger",
        "RESOLVED": "success", "CLOSED": "neutral",
    },
    "priority": {"LOW": "neutral", "NORMAL": "info", "HIGH": "warning", "URGENT": "danger",
                 "CRITICAL": "danger"},
    "sla_status": {"ON_TIME": "success", "AT_RISK": "warning", "BREACHED": "danger",
                   "PAUSED": "neutral", "COMPLETED": "success"},
    "credit_status": {"AUTHORIZED": "success", "PENDING_APPROVAL": "info",
                      "UNDER_REVIEW": "accent", "SUSPENDED": "warning", "BLOCKED": "danger"},
    "risk_level": {"LOW": "success", "MEDIUM": "info", "HIGH": "warning", "VERY_HIGH": "danger"},
    "consent_status": {"GRANTED": "success", "PENDING": "info", "WITHDRAWN": "danger",
                       "EXPIRED": "warning"},
    "privacy_status": {"RECEIVED": "info", "VALIDATING": "accent", "IN_PROGRESS": "accent",
                       "COMPLETED": "success", "REJECTED": "danger"},
    "duplicate_status": {"DETECTED": "warning", "UNDER_REVIEW": "accent",
                         "CONFIRMED_DUPLICATE": "danger", "MERGED": "success"},
    "quality_status": {"OPEN": "warning", "ACKNOWLEDGED": "accent", "CORRECTED": "success"},
    "import_status": {"PENDING_APPROVAL": "info", "COMPLETED": "success", "PARTIAL": "warning",
                      "FAILED": "danger", "REJECTED": "danger"},
    "merge_status": {"PROPOSED": "info", "EXECUTED": "success", "REJECTED": "danger"},
}


def _raw(value) -> str:
    if value is None:
        return ""
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def label(kind: str, value) -> str:
    raw = _raw(value)
    if not raw:
        return "—"
    return _LABELS.get(kind, {}).get(raw, raw)


def variant(kind: str, value) -> str:
    return _VARIANTS.get(kind, {}).get(_raw(value), "neutral")


def options(kind: str, *, exclude: tuple[str, ...] = ()) -> list[tuple[str, str]]:
    """``(valor, etiqueta)`` para un selector, en el orden declarado."""
    return [(code, text) for code, text in _LABELS.get(kind, {}).items()
            if code not in exclude]


def yes_no(value) -> str:
    if value is None:
        return "—"
    return "Sí" if bool(value) else "No"


# -- eventos (historial / auditoría) ---------------------------------------------
_EVENT_NOUNS = {
    "": "Cliente", "LEAD": "Prospecto", "OPPORTUNITY": "Oportunidad", "ACTIVITY": "Actividad",
    "TASK": "Tarea", "NOTE": "Nota", "CASE": "Caso", "CONTACT": "Contacto",
    "ADDRESS": "Dirección", "CREDIT": "Crédito", "CONSENT": "Consentimiento",
    "SEGMENT": "Segmento", "TAG": "Etiqueta", "TERRITORY": "Territorio", "PORTFOLIO": "Cartera",
    "OWNER": "Responsable", "CUSTOMER_OWNER": "Responsable", "CUSTOMER_TERRITORY": "Territorio",
    "PRIVACY_REQUEST": "Solicitud de privacidad", "DUPLICATE": "Duplicado", "MERGE": "Fusión",
    "IMPORT_BATCH": "Importación", "DATA_QUALITY_ISSUE": "Calidad de datos",
    "TAX_PROFILE": "Datos fiscales", "SYNC_CONFLICT": "Conflicto de sincronización",
    "COMMUNICATION_PREFERENCE": "Preferencias de comunicación", "REMINDER": "Recordatorio",
    "LIFECYCLE_STAGE": "Etapa del cliente", "SLA": "SLA", "PIPELINE_STAGE": "Etapa del pipeline",
}
_EVENT_VERBS = (
    ("FIRST_RESPONSE_RECORDED", "primera respuesta"), ("MARKED_NOT_REQUIRED", "no requerido"),
    ("WAITING_CUSTOMER", "espera al cliente"), ("WAITING_INTERNAL", "espera interna"),
    ("LIMIT_OVERRIDDEN", "límite extraordinario"), ("LIMIT_UPDATED", "cambio de límite"),
    ("STAGE_CHANGED", "cambio de etapa"), ("MEMBER_ADDED", "alta de miembro"),
    ("MEMBER_REMOVED", "baja de miembro"), ("PUT_ON_HOLD", "pausa"), ("UNDER_REVIEW", "revisión"),
    ("IN_PROGRESS", "en proceso"), ("CONFIGURED", "configuración"),
    ("CREATED", "alta"), ("UPDATED", "edición"), ("REASSIGNED", "reasignación"),
    ("ASSIGNED", "asignación"), ("CANCELLED", "cancelación"), ("COMPLETED", "terminado"),
    ("CLOSED", "cierre"), ("REOPENED", "reapertura"), ("RESOLVED", "resolución"),
    ("ESCALATED", "escalamiento"), ("STARTED", "inicio"), ("RESUMED", "reanudación"),
    ("WON", "ganada"), ("LOST", "perdido"), ("CONVERTED", "conversión"),
    ("DISQUALIFIED", "descalificación"), ("QUALIFIED", "calificación"),
    ("CONTACTED", "contacto"), ("NURTURING", "seguimiento"), ("ARCHIVED", "archivo"),
    ("DEACTIVATED", "baja"), ("ACTIVATED", "activación"), ("SUSPENDED", "suspensión"),
    ("BLOCKED", "bloqueo"), ("ADDED", "alta"), ("REMOVED", "baja"), ("DELETED", "borrado"),
    ("APPROVED", "aprobación"), ("REJECTED", "rechazo"), ("REQUESTED", "solicitud"),
    ("REVIEWED", "revisión"), ("CAPTURED", "captura"), ("CONFIRMED", "confirmación"),
    ("WITHDRAWN", "retiro"), ("DETECTED", "detección"), ("PROPOSED", "propuesta"),
    ("EXECUTED", "ejecución"), ("SUBMITTED", "envío"), ("RESCHEDULED", "reprogramación"),
    ("ANONYMIZED", "anonimización"), ("CHANGED", "cambio"), ("RECEIVED", "recepción"),
    ("VALIDATING", "validación"), ("ACKNOWLEDGED", "reconocida"), ("CORRECTED", "corrección"),
    ("DISMISSED", "descarte"), ("OVERRIDDEN", "ajuste manual"),
)
_EVENT_OVERRIDES = {
    "VENTA_COMPLETADA": "Venta completada", "VENTA_CANCELADA": "Venta cancelada",
    "SALE_COMPLETED": "Venta completada", "SALE_CANCELLED": "Venta cancelada",
    "SALE_RETURNED": "Devolución", "CUSTOMER_SALE_RECORDED": "Venta registrada",
}
_MODULES = {"customers": "Clientes", "crm": "CRM", "customer_service": "Atención",
            "customer_credit": "Crédito", "customer_privacy": "Privacidad", "sales": "Ventas",
            "ventas": "Ventas", "whatsapp": "WhatsApp", "loyalty": "Fidelidad"}


def event_label(code) -> str:
    """``CRM_OPPORTUNITY_WON`` → «Oportunidad: ganada». Desconocido → legible."""
    raw = _raw(code).strip().upper()
    if not raw:
        return "—"
    if raw in _EVENT_OVERRIDES:
        return _EVENT_OVERRIDES[raw]
    body = raw
    for prefix in ("CRM_", "CUSTOMER_"):
        if body.startswith(prefix):
            body = body[len(prefix):]
            break
    for suffix, verb in _EVENT_VERBS:
        if body == suffix or body.endswith("_" + suffix):
            noun_key = body[: -len(suffix)].rstrip("_")
            noun = _EVENT_NOUNS.get(noun_key)
            if noun is None and noun_key.startswith("CUSTOMER_"):
                noun = _EVENT_NOUNS.get(noun_key[len("CUSTOMER_"):])
            if noun is not None:
                return f"{noun}: {verb}"
    return raw.replace("_", " ").capitalize()


def module_label(code) -> str:
    raw = _raw(code)
    return _MODULES.get(raw, raw or "—")
