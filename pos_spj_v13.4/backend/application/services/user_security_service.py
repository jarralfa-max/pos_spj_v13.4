# backend/application/services/user_security_service.py
"""
UserSecurityService — flujo administrativo de desbloqueo de usuarios.

Caso de uso: un usuario quedó bloqueado por intentos fallidos de login
(usuarios.intentos_fallidos / bloqueado_hasta). Un administrador con permiso
CONFIG_SEGURIDAD.editar o USUARIOS.desbloquear puede desbloquearlo.

Reglas:
- Identidad UUID string (user_id, actor_id, operation_id) — nunca int.
- El desbloqueo SIEMPRE se audita en audit_logs (accion=USER_UNLOCKED).
- Sin permiso válido, se lanza PermissionError — no hay bypass silencioso.
- No crea ni altera schema (canónico en migrations/).
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.user_security")

PERMISSION_CODES = ("CONFIG_SEGURIDAD.editar", "USUARIOS.desbloquear")


class UserSecurityService:
    def __init__(
        self,
        db_conn,
        permission_checker: Optional[Callable[[str], bool]] = None,
    ) -> None:
        """
        Args:
            db_conn: conexión SQLite (UnitOfWork del caller).
            permission_checker: callable(codigo_permiso) -> bool para el actor.
                Si es None, unlock_user exige que el caller ya haya validado
                permisos y lo rechaza por seguridad (fail-closed).
        """
        self.db = db_conn
        self._can = permission_checker

    # ── API pública ──────────────────────────────────────────────────────────

    def get_lock_status(self, user_id: str) -> Optional[dict]:
        """Estado de bloqueo del usuario: intentos_fallidos, bloqueado_hasta."""
        user_id = str(user_id or "").strip()
        if not user_id:
            return None
        row = self.db.execute(
            "SELECT id, usuario, COALESCE(intentos_fallidos, 0), bloqueado_hasta, "
            "locked_reason FROM usuarios WHERE id=?",
            (user_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": str(row[0]),
            "usuario": str(row[1] or ""),
            "intentos_fallidos": int(row[2] or 0),
            "bloqueado_hasta": row[3],
            "locked_reason": row[4],
            "bloqueado": bool(row[3]) or int(row[2] or 0) > 0,
        }

    def unlock_user(self, user_id: str, operation_id: str, actor_id: str) -> dict:
        """
        Desbloquea al usuario: intentos_fallidos=0, bloqueado_hasta=NULL,
        locked_reason=NULL. Audita USER_UNLOCKED con actor y operation_id.

        Raises:
            PermissionError: si el actor no tiene permiso.
            ValueError: si el usuario no existe.
        """
        user_id      = str(user_id or "").strip()
        actor_id     = str(actor_id or "").strip()
        operation_id = str(operation_id or "").strip() or new_uuid()
        if not user_id:
            raise ValueError("unlock_user requiere user_id UUID válido.")

        if self._can is None or not any(self._can(code) for code in PERMISSION_CODES):
            raise PermissionError(
                "No tiene permiso para desbloquear usuarios "
                f"(requiere {' o '.join(PERMISSION_CODES)})."
            )

        estado = self.get_lock_status(user_id)
        if estado is None:
            raise ValueError(f"Usuario {user_id} no encontrado.")

        self.db.execute(
            """UPDATE usuarios
               SET intentos_fallidos = 0,
                   bloqueado_hasta   = NULL,
                   locked_reason     = NULL,
                   updated_at        = datetime('now')
               WHERE id = ?""",
            (user_id,),
        )
        self._audit_unlock(user_id, estado, actor_id, operation_id)
        try:
            self.db.commit()
        except Exception:
            pass  # el caller puede ser dueño de la transacción

        logger.info(
            "USER_UNLOCKED: usuario=%s actor=%s operation_id=%s",
            user_id, actor_id, operation_id,
        )
        return {
            "ok": True,
            "user_id": user_id,
            "operation_id": operation_id,
            "actor_id": actor_id,
        }

    # ── infra ────────────────────────────────────────────────────────────────

    def _audit_unlock(
        self, user_id: str, estado_antes: dict, actor_id: str, operation_id: str
    ) -> None:
        import json

        self.db.execute(
            """INSERT INTO audit_logs
                   (id, accion, modulo, entidad, entidad_id, usuario,
                    valor_antes, valor_despues, detalles)
               VALUES (?, 'USER_UNLOCKED', 'CONFIG_SEGURIDAD', 'usuarios', ?, ?, ?, ?, ?)""",
            (
                new_uuid(),
                user_id,
                actor_id or "Sistema",
                json.dumps(
                    {
                        "intentos_fallidos": estado_antes.get("intentos_fallidos"),
                        "bloqueado_hasta": str(estado_antes.get("bloqueado_hasta") or ""),
                        "locked_reason": str(estado_antes.get("locked_reason") or ""),
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {"intentos_fallidos": 0, "bloqueado_hasta": None, "locked_reason": None},
                    ensure_ascii=False,
                ),
                json.dumps({"operation_id": operation_id}, ensure_ascii=False),
            ),
        )
