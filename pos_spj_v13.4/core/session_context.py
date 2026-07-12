# core/session_context.py — SPJ POS v13.30
"""
SessionContext — fuente única de verdad para la sesión activa.

Centraliza: usuario, sucursal, rol, permisos.
Todos los módulos y servicios DEBEN leer de aquí en vez de mantener
sus propias copias de sucursal_id/usuario_actual.

Uso:
    session = container.session
    session.sucursal_id       # "0198..." (UUID str)
    session.sucursal_nombre   # "Centro"
    session.usuario           # "juan"
    session.nombre_completo   # "Juan Pérez"
    session.rol               # "gerente"
    session.user_id           # "0198..." (UUID str)
    session.tiene_permiso("ventas.cancelar")  # True/False
    session.es_admin          # True/False
    session.is_active         # True/False
"""
from __future__ import annotations
import logging
from typing import Set

from core.security.permission_catalog import normalize_permission

logger = logging.getLogger("spj.session")


class SessionContext:
    """Contexto de sesión inmutable-ish — se actualiza solo via set_*."""

    def __init__(self):
        self._user_id: str = ""
        self._usuario: str = ""
        self._nombre_completo: str = ""
        self._rol: str = ""
        self._sucursal_id: str = ""        # espejo de active_branch_id (UUID str)
        self._sucursal_nombre: str = ""    # display name only — NOT identity
        # D6/REGLA CERO: la sucursal es UUIDv7 (str) y su ÚNICA fuente es
        # _active_branch_id. Se eliminó el _sucursal_id entero legacy (identidad
        # dual int/str). La property `sucursal_id` es ahora un alias de esta.
        self._active_branch_id: str = ""   # canonical UUID — single source of truth
        self._permisos: Set[str] = set()
        self._is_active: bool = False
        self._sucursales_disponibles: list = []

    # ── Properties (read-only desde fuera) ────────────────────────────────────

    @property
    def user_id(self) -> str:
        return self._user_id

    @property
    def usuario(self) -> str:
        return self._usuario

    @property
    def nombre_completo(self) -> str:
        return self._nombre_completo

    @property
    def rol(self) -> str:
        return self._rol

    @property
    def sucursal_id(self) -> str:
        return self._sucursal_id

    @property
    def sucursal_nombre(self) -> str:
        return self._sucursal_nombre

    @property
    def active_branch_id(self) -> str:
        """Canonical UUID of the active branch — single source of truth."""
        return self._active_branch_id

    @property
    def permisos(self) -> Set[str]:
        return frozenset(self._permisos)

    @property
    def is_active(self) -> bool:
        return self._is_active

    @property
    def es_admin(self) -> bool:
        return self._rol in ('admin', 'superadmin', 'administrador')

    @property
    def es_gerente(self) -> bool:
        return self._rol in ('admin', 'superadmin', 'gerente', 'gerente_rh')

    @property
    def sucursales_disponibles(self) -> list:
        return list(self._sucursales_disponibles)

    # ── Mutations (solo desde AppContainer / MainWindow) ──────────────────────

    def set_user(self, user_data: dict) -> None:
        """Establece el usuario autenticado. Se llama desde MainWindow al hacer login."""
        self._user_id = str(user_data.get('id') or "").strip()
        self._usuario = user_data.get('username', '')
        self._nombre_completo = user_data.get('nombre', self._usuario)
        self._rol = str(user_data.get('rol', 'cajero') or 'cajero').strip().lower()
        self._sucursal_id = str(user_data.get('sucursal_id') or "").strip()
        self._sucursal_nombre = user_data.get('sucursal_nombre', '')
        # Sucursal = UUIDv7 str (única identidad, REGLA CERO). Preferir el UUID
        # explícito; si solo viene un id numérico legacy, usar su repr str
        # (nunca int, nunca 'Principal').
        _suc_legacy = user_data.get('sucursal_id')
        self._active_branch_id = (
            str(user_data.get('active_branch_id') or user_data.get('sucursal_uuid') or "").strip()
            or (str(_suc_legacy) if _suc_legacy else "")
        )
        self._sucursales_disponibles = user_data.get('sucursales_disponibles', [])
        self._is_active = True
        logger.info(
            "Sesión iniciada: %s (%s) en sucursal '%s' [active_branch_id=%s]",
            self._nombre_completo, self._rol,
            self._sucursal_nombre, self._active_branch_id,
        )

    def set_sucursal(self, sucursal_id: str, nombre: str = "",
                     active_branch_id: str = "") -> None:
        """Cambia la sucursal activa (para usuarios multi-branch)."""
        self._sucursal_id = str(sucursal_id or "").strip()
        if nombre:
            self._sucursal_nombre = nombre
        # active_branch_id explícito gana; en su defecto el propio sucursal_id
        # (que ya es el UUID canónico). Nunca se degrada a entero.
        branch = str(active_branch_id or sucursal_id or "").strip()
        if branch:
            self._active_branch_id = branch
        logger.info(
            "Sucursal cambiada: '%s' (active_branch_id=%s)",
            nombre, self._active_branch_id,
        )

    def set_permisos(self, permisos: Set[str]) -> None:
        """Carga permisos normalizados del usuario para la sucursal activa."""
        self._permisos = {normalize_permission(perm) for perm in (permisos or set()) if str(perm or "").strip()}
        logger.debug("Permisos cargados: %d", len(self._permisos))

    def clear(self) -> None:
        """Cierra la sesión — limpia todo. No restaura defaults ni sucursal_id=1."""
        old_user = self._usuario
        self.__init__()
        if old_user:
            logger.info("Sesión cerrada: %s", old_user)

    # ── Verificación de permisos ──────────────────────────────────────────────

    def tiene_permiso(self, codigo_permiso: str) -> bool:
        """Verifica si el usuario tiene un permiso específico.
        Admin siempre tiene todos los permisos."""
        if self.es_admin:
            return True
        normalized = normalize_permission(codigo_permiso)
        return "*" in self._permisos or normalized in self._permisos

    def requiere_permiso(self, codigo_permiso: str, accion: str = "") -> bool:
        """Verifica permiso y lanza excepción si no lo tiene.
        Retorna True si tiene permiso, lanza PermissionError si no."""
        if self.tiene_permiso(codigo_permiso):
            return True
        msg = f"No tiene permiso para: {accion or codigo_permiso}"
        raise PermissionError(msg)

    # ── Representación ────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        if not self._is_active:
            return "SessionContext(inactive)"
        return (f"SessionContext(user={self._usuario}, rol={self._rol}, "
                f"sucursal={self._sucursal_nombre}[{self._active_branch_id}], "
                f"permisos={len(self._permisos)})")

    def to_dict(self) -> dict:
        """Serializa a dict para audit logs y debugging."""
        return {
            "user_id": self._user_id,
            "usuario": self._usuario,
            "nombre": self._nombre_completo,
            "rol": self._rol,
            # sucursal_id == active_branch_id (UUIDv7 str, D6): una sola identidad.
            "sucursal_id": self._active_branch_id,
            "sucursal_nombre": self._sucursal_nombre,
            "active_branch_id": self._active_branch_id,
            "is_active": self._is_active,
            "n_permisos": len(self._permisos),
        }

    @property
    def is_branch_resolved(self) -> bool:
        """True when active_branch_id has been set (not empty)."""
        return bool(self._active_branch_id)