"""Rastro de auditoría de Tarjetas de fidelidad.

Envoltorio fino sobre `backend/application/shared/audit_trail.py`, que escribe
en `audit_logs` — el rastro transversal, no una tabla por contexto.

Antes cada contexto repetía aquí el mismo bloque de veinticinco líneas y
llamaba a `core.services.auto_audit.audit_write`, que pedía un `container`. Los
casos de uso no lo tienen, y por eso este escritor nunca llegó a usarse. Ahora
recibe la `connection` que sí tienen.

SIGUE SIN LLAMARSE desde ningún caso de uso: conectarlo hace aparecer filas
nuevas en la auditoría, que es un cambio de comportamiento y merece su propio
paso.
"""

from __future__ import annotations

from backend.application.shared.audit_trail import record_audit_entry
from backend.domain.loyalty_cards.value_objects.card_audit_entry import CardAuditEntry

#: Módulo bajo el que aparece este contexto en la auditoría.
AUDIT_MODULE = "TARJETAS_FIDELIDAD"
AUDIT_ENTITY = "tarjeta_fidelidad"


def record_card_audit_entry(connection, entry: CardAuditEntry) -> None:
    """Persiste una `CardAuditEntry` en el rastro canónico."""
    record_audit_entry(
        connection, entry, module=AUDIT_MODULE, entity=AUDIT_ENTITY,
        entity_id=getattr(entry, "card_id", "") or "",
    )
