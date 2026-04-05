# core/session_context.py — SPJ POS v13.30
"""
SessionContext — fuente única de verdad para la sesión activa.

Centraliza: usuario, sucursal, rol, permisos.
Todos los módulos y servicios DEBEN leer de aquí en vez de mantener
sus propias copias de sucursal_id/usuario_actual.

Uso:
    session = container.session
    session.sucursal_id       # 2
    session.sucursal_nombre   # "Centro"
    session.usuario           # "juan"
    session.nombre_completo   # "Juan Pérez"
    session.rol               # "gerente"
    session.user_id           # 5
    session.tiene_permiso("ventas.cancelar")  # True/False
    session.es_admin          # True/False
    session.is_active         # True/False
"""
from __future__ import annotations
import logging
from typing import Set, Optional

logger = logging.getLogger("spj.session")


class SessionContext:
    """Contexto de sesión inmutable-ish — se actualiza solo via set_*."""

    def __init__(self):
        self._user_id: int = 0
        self._usuario: str = ""
        self._nombre_completo: str = ""
        self._rol: str = ""
        self._sucursal_id: int = 1
        self._sucursal_nombre: str = "Principal"
        self._permisos: Set[str] = set()
        self._is_active: bool = False
        self._sucursales_disponibles: list = []

    # ── Properties (read-only desde fuera) ────────────────────────────────────

    @property
    def user_id(self) -> int:
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
    def sucursal_id(self) -> int:
        return self._sucursal_id

    @property
    def sucursal_nombre(self) -> str:
        return self._sucursal_nombre

    @property
    def permisos(self) -> Set[str]:
        return frozenset(self._permisos)

    @property
    def is_active(self) -> bool:
        return self._is_active

    @property
    def es_admin(self) -> bool:
        return self._rol in ('admin', 'superadmin')

    @property
    def es_gerente(self) -> bool:
        return self._rol in ('admin', 'superadmin', 'gerente', 'gerente_rh')

    @property
    def sucursales_disponibles(self) -> list:
        return list(self._sucursales_disponibles)

    # ── Mutations (solo desde AppContainer / MainWindow) ──────────────────────

    def set_user(self, user_data: dict) -> None:
        """Establece el usuario autenticado. Se llama desde MainWindow al hacer login."""
        self._user_id = user_data.get('id', 0)
        self._usuario = user_data.get('username', '')
        self._nombre_completo = user_data.get('nombre', self._usuario)
        self._rol = user_data.get('rol', 'cajero')
        self._sucursal_id = user_data.get('sucursal_id', 1)
        self._sucursal_nombre = user_data.get('sucursal_nombre', 'Principal')
        self._sucursales_disponibles = user_data.get('sucursales_disponibles', [])
        self._is_active = True
        logger.info(
            "Sesión iniciada: %s (%s) en sucursal %s [%s]",
            self._nombre_completo, self._rol,
            self._sucursal_nombre, self._sucursal_id)

    def set_sucursal(self, sucursal_id: int, nombre: str = "") -> None:
        """Cambia la sucursal activa (para usuarios multi-branch)."""
        self._sucursal_id = sucursal_id
        if nombre:
            self._sucursal_nombre = nombre
        logger.info("Sucursal cambiada: %s (%s)", nombre, sucursal_id)

    def set_permisos(self, permisos: Set[str]) -> None:
        """Carga los permisos RBAC del usuario para la sucursal activa."""
        self._permisos = set(permisos)
        logger.debug("Permisos cargados: %d", len(self._permisos))

    def clear(self) -> None:
        """Cierra la sesión — limpia todo."""
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
        return codigo_permiso in self._permisos

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
                f"sucursal={self._sucursal_nombre}[{self._sucursal_id}], "
                f"permisos={len(self._permisos)})")

    def to_dict(self) -> dict:
        """Serializa a dict para audit logs y debugging."""
        return {
            "user_id": self._user_id,
            "usuario": self._usuario,
            "nombre": self._nombre_completo,
            "rol": self._rol,
            "sucursal_id": self._sucursal_id,
            "sucursal_nombre": self._sucursal_nombre,
            "is_active": self._is_active,
            "n_permisos": len(self._permisos),
        }
