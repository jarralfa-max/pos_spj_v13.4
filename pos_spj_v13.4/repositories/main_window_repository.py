# repositories/main_window_repository.py
"""Read-only repository for the main window (shell) queries.

Holds the SQL that the PyQt main window used to run inline: branch-name lookup,
user→employee link resolution and the global search box. All reads are defensive
(the shell must never crash on a diagnostics/search read).
"""
from __future__ import annotations

import logging

logger = logging.getLogger("spj.mainwindow.repo")


class MainWindowReadRepository:
    def __init__(self, db):
        self.db = db

    def nombre_sucursal(self, branch_id: str) -> str:
        """Nombre de la sucursal por id (cadena vacía si no existe)."""
        try:
            row = self.db.execute(
                "SELECT nombre FROM sucursales WHERE id=?", (str(branch_id),)
            ).fetchone()
            return str(row[0] or "") if row else ""
        except Exception:
            return ""

    def personal_id_de_usuario(self, usuario_id: str) -> str | None:
        """Resuelve el empleado (personal.id) vinculado al usuario logueado.

        Dos rutas de vínculo: personal.usuario_id (legacy) y usuarios.personal_id
        (canónica — la escribe SQLiteEmployeeIdentityRepository).
        """
        try:
            row = self.db.execute(
                """
                SELECT p.id FROM personal p
                 WHERE p.usuario_id=? AND p.activo=1
                UNION
                SELECT p.id FROM personal p
                  JOIN usuarios u ON u.personal_id = p.id
                 WHERE u.id=? AND p.activo=1
                LIMIT 1
                """,
                (str(usuario_id), str(usuario_id)),
            ).fetchone()
            return row[0] if row else None
        except Exception:
            return None

    def buscar_productos(self, texto: str, limit: int = 8) -> list:
        try:
            return self.db.execute(
                "SELECT nombre, precio, existencia FROM productos "
                "WHERE (nombre LIKE ? OR codigo LIKE ?) AND activo=1 LIMIT ?",
                (f"%{texto}%", f"%{texto}%", int(limit)),
            ).fetchall()
        except Exception as e:
            logger.debug("buscar_productos: %s", e)
            return []

    def buscar_clientes(self, texto: str, limit: int = 5) -> list:
        try:
            return self.db.execute(
                "SELECT nombre, COALESCE(apellido,''), COALESCE(telefono,'') "
                "FROM clientes WHERE nombre LIKE ? LIMIT ?",
                (f"%{texto}%", int(limit)),
            ).fetchall()
        except Exception as e:
            logger.debug("buscar_clientes: %s", e)
            return []

    def buscar_ventas_por_folio(self, texto: str, limit: int = 4) -> list:
        try:
            return self.db.execute(
                "SELECT folio, total, fecha FROM ventas "
                "WHERE folio LIKE ? ORDER BY fecha DESC LIMIT ?",
                (f"%{texto}%", int(limit)),
            ).fetchall()
        except Exception as e:
            logger.debug("buscar_ventas_por_folio: %s", e)
            return []
