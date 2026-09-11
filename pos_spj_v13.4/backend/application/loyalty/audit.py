"""Rastro de auditoría de Fidelidad.

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
from backend.domain.loyalty.value_objects.loyalty_audit_entry import LoyaltyAuditEntry

#: Módulo bajo el que aparece este contexto en la auditoría.
AUDIT_MODULE = "GROWTH_ENGINE"
AUDIT_ENTITY = "fidelidad"


def record_loyalty_audit_entry(connection, entry: LoyaltyAuditEntry) -> None:
    """Persiste una `LoyaltyAuditEntry` en el rastro canónico."""
    record_audit_entry(
        connection, entry, module=AUDIT_MODULE, entity=AUDIT_ENTITY,
        entity_id=getattr(entry, "entity_id", "") or "",
    )
