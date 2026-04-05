# repositories/audit_repository.py — SPJ POS v13.2
"""
Repositorio de Auditoría.
Wrappea la conexión SQLite y expone insert_audit_log()
que es lo que AuditService espera.
"""
import logging

logger = logging.getLogger("spj.audit_repo")


class AuditRepository:
    """Acceso directo a la tabla audit_logs."""

    def __init__(self, db_conn):
        self.db = db_conn

    def insert_audit_log(
        self, *,
        usuario: str,
        accion: str,
        modulo: str,
        entidad: str,
        entidad_id: str,
        valor_antes: str = "{}",
        valor_despues: str = "{}",
        sucursal_id: int = 1,
        detalles: str = "",
    ) -> None:
        """Inserta un registro en audit_logs. Falla silenciosamente."""
        try:
            self.db.execute(
                """INSERT INTO audit_logs
                   (usuario, accion, modulo, entidad, entidad_id,
                    valor_antes, valor_despues, sucursal_id, detalles)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (usuario, accion, modulo, entidad, str(entidad_id),
                 valor_antes, valor_despues, sucursal_id, detalles),
            )
            try:
                self.db.commit()
            except Exception:
                pass
        except Exception as e:
            logger.debug("audit insert_audit_log: %s", e)
