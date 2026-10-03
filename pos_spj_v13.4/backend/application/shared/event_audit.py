"""Auditoría de cada hecho de negocio, en la misma transacción que lo produce.

Fidelidad, Instrumentos comerciales, Sorteos y Tarjetas publican un evento al
outbox por cada cambio de estado (`_emit` de su caso de uso base). Hasta LOY-29
ninguno dejaba rastro en `audit_logs`: los escritores de auditoría existían
pero nadie los llamaba (§61). Ahora `_emit` anota también la auditoría, con la
misma conexión de la unidad de trabajo — si la operación se revierte, su
auditoría también.

Qué se guarda: quién (`actor_user_id`), qué (el nombre del evento), sobre qué
(`entity_id`), dónde (`branch_id`), la operación y el detalle del evento como
"después". Nunca un token de QR ni nada que permita reconstruirlo.

Sin la tabla `audit_logs` (bases de prueba mínimas) no se escribe nada y se
avisa una vez en el log; la base real siempre la tiene (m000) y una prueba de
arquitectura lo fija.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, Mapping

from backend.application.shared.audit_trail import record_audit_entry

logger = logging.getLogger("spj.audit.events")

#: Claves que jamás viajan a la auditoría.
_SENSITIVE_KEYS = frozenset({"token", "qr_token", "raw_token", "card_token", "password"})

_avisado = False


def _has_audit_table(connection) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='audit_logs'").fetchone() is not None


def record_event_audit(
    connection, *, module: str, entity: str, event_name: str, entity_id: str,
    operation_id: str, branch_id: str | None, actor_user_id: str | None,
    details: Mapping[str, Any] | None = None,
) -> None:
    global _avisado
    if not _has_audit_table(connection):
        if not _avisado:
            logger.warning("audit_logs no existe en esta base: la auditoría de eventos se omite")
            _avisado = True
        return
    despues = {k: v for k, v in dict(details or {}).items() if k not in _SENSITIVE_KEYS}
    entrada = SimpleNamespace(
        action=event_name, user_id=actor_user_id or "", operation_id=operation_id,
        branch_id=branch_id or None, before={}, after=despues,
        reason=despues.get("reason") or despues.get("reason_code"),
        authorized_by=despues.get("authorized_by") or despues.get("authorizer_user_id"),
        device_id=None, occurred_at=None, workstation_id=None)
    record_audit_entry(connection, entrada, module=module, entity=entity,
                       entity_id=entity_id or "")


__all__ = ["record_event_audit"]
