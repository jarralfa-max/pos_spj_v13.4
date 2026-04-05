# core/services/auto_audit.py — SPJ POS v13.2
"""
Auditoría automática — helper centralizado.

USO desde cualquier módulo:
    from core.services.auto_audit import audit_write

    audit_write(container, modulo="MERMA", accion="REGISTRAR",
                entidad="merma", entidad_id=merma_id,
                usuario=self.usuario, detalles=f"Producto {nombre}, {cantidad}kg")
"""
from __future__ import annotations
import logging

logger = logging.getLogger("spj.auto_audit")


def audit_write(
    container,
    modulo: str,
    accion: str,
    entidad: str,
    entidad_id: str = "",
    usuario: str = "Sistema",
    detalles: str = "",
    before: dict = None,
    after: dict = None,
    sucursal_id: int = 1,
) -> None:
    """
    Registra una acción de escritura en el log de auditoría.
    Falla silenciosamente — nunca interrumpe el flujo principal.
    """
    try:
        svc = getattr(container, 'audit_service', None)
        if svc:
            svc.log_change(
                usuario      = usuario or "Sistema",
                accion       = accion,
                modulo       = modulo,
                entidad      = entidad,
                entidad_id   = str(entidad_id),
                before_state = before or {},
                after_state  = after or {},
                sucursal_id  = sucursal_id,
                detalles     = detalles,
            )
        else:
            # Direct DB fallback
            db = getattr(container, 'db', None)
            if db:
                db.execute(
                    """INSERT INTO audit_logs
                       (usuario, accion, modulo, entidad, entidad_id,
                        valor_antes, valor_despues, sucursal_id, detalles)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (usuario or "Sistema", accion, modulo, entidad,
                     str(entidad_id), str(before or {}), str(after or {}),
                     sucursal_id, detalles)
                )
                try: db.commit()
                except Exception: pass
    except Exception as e:
        logger.debug("auto_audit: %s", e)
