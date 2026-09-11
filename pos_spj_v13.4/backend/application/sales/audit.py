"""Rastro de auditoría de Ventas / punto de venta.

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
from backend.domain.sales.value_objects.sales_audit_entry import SalesAuditEntry

#: Módulo bajo el que aparece este contexto en la auditoría.
AUDIT_MODULE = "POS"
AUDIT_ENTITY = "venta"


def record_sales_audit_entry(connection, entry: SalesAuditEntry) -> None:
    """Persiste una `SalesAuditEntry` en el rastro canónico."""
    record_audit_entry(
        connection, entry, module=AUDIT_MODULE, entity=AUDIT_ENTITY,
        entity_id=getattr(entry, "sale_id", "") or "",
    )
