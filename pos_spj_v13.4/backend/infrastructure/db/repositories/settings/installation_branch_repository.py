"""Sucursal anclada a ESTA instalación.

Una instalación del punto de venta atiende a UNA sucursal. Esa elección se
guarda en `configuraciones` bajo una única clave y es la que fija la sucursal
activa de la sesión al iniciar sesión.

Se guarda el id de la sucursal, no su nombre: un local puede renombrarse y el
ancla tiene que seguir apuntando al mismo sitio.

No confundir con `SqliteInstallationRepository` (`backend/security/
provisioning/`), que administra el ciclo de vida del aprovisionamiento —en qué
estado está la instalación—, ni con `SqliteBranchProfileRepository`, que guarda
la ficha de configuración de una sucursal. Esto responde sólo a "¿qué sucursal
es ésta?".
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.settings.base import SettingsRepositoryBase
from backend.infrastructure.sync.replication_sources import DEFAULT_SOURCES
from backend.shared.ids import validate_uuidv7

#: Clave en `configuraciones`. Se mantiene el nombre histórico a propósito: las
#: instalaciones existentes ya tienen su fila guardada bajo esta clave, y
#: renombrarla las dejaría sin sucursal anclada — arrancarían pidiendo
#: configuración inicial como si fueran nuevas.
INSTALLATION_BRANCH_KEY = "sucursal_instalacion_id"


class SqliteInstallationBranchRepository(SettingsRepositoryBase):
    def get(self) -> tuple[str, str] | None:
        """`(id, nombre)` de la sucursal anclada, o `None` si no hay ninguna.

        El JOIN contra `sucursales` es deliberado: si la clave apunta a una
        sucursal que ya no existe, esto devuelve `None` —"no hay ancla"— en vez
        de un id huérfano que el resto del arranque trataría como válido.
        """
        row = self._query_one(
            """
            SELECT s.id, s.nombre
            FROM sucursales s
            JOIN configuraciones c ON c.clave = ? AND c.valor = s.id
            LIMIT 1
            """,
            (INSTALLATION_BRANCH_KEY,),
        )
        return (str(row["id"]), str(row["nombre"])) if row else None

    def set(self, branch_id: str) -> tuple[str, str]:
        """Ancla la instalación a una sucursal existente y ACTIVA.

        Exigir que esté activa no es un capricho: anclar a una sucursal dada de
        baja dejaría la instalación sin poder abrir sesión, y el mensaje de
        error aparecería en el login, lejos de la pantalla donde se cometió el
        fallo.
        """
        branch_uuid = validate_uuidv7(branch_id)
        row = self._query_one(
            "SELECT id, nombre FROM sucursales WHERE id = ? AND COALESCE(activa, 1) = 1",
            (branch_uuid,),
        )
        if row is None:
            raise ValueError("La sucursal debe existir y estar activa.")

        self._execute(
            "INSERT INTO configuraciones (clave, valor) VALUES (?, ?)"
            " ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
            (INSTALLATION_BRANCH_KEY, str(row["id"])),
        )
        return str(row["id"]), str(row["nombre"])

    # ── guardas del re-anclaje (SDLC-ARQ-TERM-002) ──────────────────────────
    def _table_exists(self, name: str) -> bool:
        return self._query_one(
            "SELECT 1 AS x FROM sqlite_master WHERE type='table' AND name=?", (name,),
        ) is not None

    def central_enrollment_active(self) -> bool:
        """¿Está ESTE equipo vinculado al registro central?

        `device_enrollment` (migración 354) guarda la vinculación; sin la tabla o
        sin una fila ENROLLED no hay registro central y basta el permiso local.
        """
        if not self._table_exists("device_enrollment"):
            return False
        return self._query_one(
            "SELECT 1 AS x FROM device_enrollment WHERE status='ENROLLED' LIMIT 1",
        ) is not None

    def open_cash_shifts_outside(self, branch_id: str) -> int:
        """Turnos de caja sin cerrar en una sucursal distinta de `branch_id`.

        Cuenta los estados activos de la política de Caja, la misma fuente de
        `ActiveShiftResolver` (SDLC-ARQ-SHIFT-001; decisión 2026-11-14): abierto,
        suspendido, en arqueo o en cierre retiene efectivo y ventas de la
        sucursal en la que nació.
        """
        if not self._table_exists("cash_shifts"):
            return 0
        from backend.domain.cash_register.policies.workflow_policies import (
            CashShiftLifecyclePolicy,
        )
        statuses = CashShiftLifecyclePolicy.active_status_values()
        marks = ",".join("?" for _ in statuses)
        row = self._query_one(
            "SELECT COUNT(*) AS n FROM cash_shifts WHERE branch_id <> ?"
            f" AND status IN ({marks})",
            (str(branch_id), *statuses),
        )
        return int(row["n"]) if row else 0

    def pending_sync_count(self) -> int:
        """Hechos de esta estación que aún no llegan al servidor central.

        Sólo cuenta si la estación participa en replicación (tiene fila en
        `replication_stations`): sin ella no hay canal de sincronización. Cuentan
        los sobres PENDING, IN_FLIGHT, RETRY y CONFLICT —SYNCED y DEAD son
        finales— y los hechos de los outbox de contexto que aún no tienen sobre
        (el motor los preparará en el siguiente ciclo).
        """
        if not (self._table_exists("replication_stations")
                and self._table_exists("replication_envelopes")):
            return 0
        if self._query_one("SELECT 1 AS x FROM replication_stations LIMIT 1") is None:
            return 0
        row = self._query_one(
            "SELECT COUNT(*) AS n FROM replication_envelopes"
            " WHERE state IN ('PENDING','IN_FLIGHT','RETRY','CONFLICT')",
        )
        total = int(row["n"]) if row else 0
        for source in DEFAULT_SOURCES:
            if not self._table_exists(source.table):
                continue
            row = self._query_one(
                f'SELECT COUNT(*) AS n FROM "{source.table}" o'
                " WHERE NOT EXISTS (SELECT 1 FROM replication_envelopes r"
                " WHERE r.source = ? AND r.source_row_id = o.id)",
                (source.name,),
            )
            total += int(row["n"]) if row else 0
        return total
