"""Rastro de auditoría transversal — tabla `audit_logs`.

Qué hizo quién, en qué módulo y cuándo. Es lo que muestra Configuración →
Auditoría y lo que exige la regla 12 de CLAUDE.md para las operaciones
sensibles.

No confundir con `ConfiguracionAuditLogRepository` (mismo paquete): ése escribe
`configuracion_audit_log`, que guarda el antes/después de UNA mutación concreta
de Configuración y se consulta por entidad. Son dos rastros distintos que
conviven a propósito — "qué pasó en el sistema" frente a "cómo cambió este
dispositivo"— y unificarlos mezclaría dos preguntas que se hacen por separado.

SOBRE LA ESCRITURA: que la administración de usuarios y roles quede auditada es
una decisión de diseño tomada aquí, no una reconstrucción de lo que hacía el
código borrado. Lo que sí es evidencia es que `SaveUserUseCase`,
`SetUserActiveUseCase` y `SaveRoleUseCase` —código canónico vivo— pasan
`operation_id` y `actor` a estos servicios: son datos de auditoría y no tenían
otro destino posible. Crear o desactivar una cuenta sin dejar rastro sería
además justo lo contrario de lo que pide la regla 12.
"""

from __future__ import annotations

import json

from backend.infrastructure.db.repositories.settings.base import SettingsRepositoryBase
from backend.shared.ids import new_uuid


def _as_json(value: dict | None) -> str | None:
    """JSON, o `NULL` si no se registró nada. `{}` sí se guarda."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)

#: Tope por defecto de filas devueltas. La tabla crece sin límite; traerla
#: entera bloquearía la interfaz en una instalación con meses de historial.
DEFAULT_LIMIT = 200

#: Módulo bajo el que se registran las operaciones de Configuración.
CONFIGURACION_MODULE = "CONFIGURACION"


class SqliteAuditLogRepository(SettingsRepositoryBase):
    def recent(self, limit: int = DEFAULT_LIMIT) -> list[tuple]:
        """`(fecha, usuario, modulo, accion, detalles)`, lo más reciente primero."""
        return self._conn.execute(
            "SELECT fecha, usuario, modulo, accion, COALESCE(detalles, '')"
            " FROM audit_logs ORDER BY fecha DESC LIMIT ?",
            (int(limit),),
        ).fetchall()

    def record(
        self, *, action: str, entity: str, entity_id: str,
        actor: str = "", operation_id: str = "", details: str = "",
        module: str = CONFIGURACION_MODULE, before: dict | None = None,
        after: dict | None = None, branch_id: str | None = None,
    ) -> None:
        """Anota una operación.

        `usuario` nunca queda vacío: la columna tiene `NOT NULL DEFAULT
        'Sistema'`, y una entrada sin autor es peor que inútil en una
        auditoría, así que se escribe explícitamente ese valor cuando no hay
        actor —una operación automática— en lugar de dejar que la ausencia
        parezca un dato perdido.

        `operation_id` viaja en `detalles` porque `audit_logs` no tiene columna
        propia para él; es lo que permite enlazar esta anotación con el resto
        de efectos de la misma operación.

        `before`/`after` se serializan a JSON. Un diccionario vacío NO es lo
        mismo que ausencia: "no había nada antes" (un alta) y "no se registró
        el antes" son cosas distintas, así que sólo el segundo queda en NULL.
        """
        detalle = " ".join(part for part in (details, f"operation_id={operation_id}"
                                             if operation_id else "") if part)
        self._conn.execute(
            "INSERT INTO audit_logs (id, accion, modulo, entidad, entidad_id, usuario,"
            " sucursal_id, valor_antes, valor_despues, detalles)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (new_uuid(), action, module, entity, entity_id,
             (actor or "").strip() or "Sistema", branch_id,
             _as_json(before), _as_json(after), detalle),
        )
