"""Escritura del rastro de auditoría, compartida por los contextos acotados.

Reemplaza `core.services.auto_audit.audit_write`, borrado. Los cuatro contextos
que auditan (Ventas, Fidelidad, Tarjetas, Reparto) repetían el MISMO bloque de
veinticinco líneas para armar `detalles` y llamar al sumidero; ahora lo
comparten y cada uno sólo aporta lo suyo: bajo qué módulo y qué entidad.

EL CAMBIO QUE IMPORTA: CONEXIÓN, NO CONTENEDOR
-----------------------------------------------
`audit_write()` recibía un `container` de la aplicación. Los casos de uso no lo
tienen —trabajan con una `connection`— y por eso NINGUNO de los cuatro
escritores llegó a usarse nunca. Está dicho en dos sitios como una limitación
abierta, entre ellos el propio `backend/application/sales/use_cases/_base.py`:
"eso requeriría pasar un `container` por cada caso de uso además de la
`connection`".

Este sumidero toma la conexión, que es lo que los casos de uso ya tienen. Con
eso la auditoría deja de ser inalcanzable por una cuestión de fontanería.

AÚN NO ESTÁ CONECTADA. Los cuatro escritores siguen sin llamarse desde ningún
caso de uso: conectarlos hace aparecer filas nuevas en `audit_logs` y eso es un
cambio de comportamiento visible, no un efecto colateral de una migración de
código. Queda como el paso siguiente, explícito.

UNA SOLA TABLA. Se escribe en `audit_logs`, el rastro transversal, en vez de
levantar un `<contexto>_audit_log` por contexto: una auditoría repartida en
cinco tablas no se puede leer en orden cronológico, que es justo para lo que
sirve una auditoría.
"""

from __future__ import annotations

import json
from typing import Any

from backend.infrastructure.db.repositories.settings.audit_log_repository import (
    SqliteAuditLogRepository,
)

#: Campos que acompañan a la anotación pero no tienen columna propia en
#: `audit_logs`. Viajan serializados en `detalles`.
_EXTRA_FIELDS = (
    "operation_id", "authorized_by", "reason", "workstation_id", "device_id",
    "occurred_at",
)


def record_audit_entry(
    connection, entry: Any, *, module: str, entity: str, entity_id: str,
) -> None:
    """Anota una entrada de auditoría de un contexto acotado.

    `entry` es el objeto de valor propio de cada contexto (`SalesAuditEntry`,
    `LoyaltyAuditEntry`, …). No comparten un tipo base a propósito —cada
    contexto define el suyo—, así que aquí se leen por atributo y los que no
    existan se omiten, en vez de exigir una jerarquía común que obligaría a los
    cuatro dominios a depender entre sí.
    """
    extra = {
        campo: getattr(entry, campo, None) for campo in _EXTRA_FIELDS
    }
    detalles = json.dumps(
        {clave: valor for clave, valor in extra.items() if valor is not None},
        ensure_ascii=False, default=str)

    SqliteAuditLogRepository(connection).record(
        action=getattr(entry, "action", ""),
        entity=entity,
        entity_id=entity_id or "",
        actor=getattr(entry, "user_id", "") or "",
        operation_id="",  # ya va dentro de `detalles`; no se duplica
        details=detalles,
        module=module,
        before=dict(getattr(entry, "before", {}) or {}),
        after=dict(getattr(entry, "after", {}) or {}),
        branch_id=getattr(entry, "branch_id", None),
    )
