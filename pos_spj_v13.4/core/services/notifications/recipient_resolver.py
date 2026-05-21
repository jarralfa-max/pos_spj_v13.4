# core/services/notifications/recipient_resolver.py
"""
Resuelve QUIÉN recibe cada notificación.

Fuentes:
  1. Rol en DB (usuarios_roles o columna legacy usuarios.rol)
  2. Configuración explícita en configuraciones (responsibles por tipo)
  3. Lookup directo por empleado_id

Nunca lanza excepciones — falla silenciosa y retorna lista vacía.
"""
from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("spj.notifications.resolver")

# Matriz de roles por tipo de notificación (canónica)
_ROL_MATRIX: Dict[str, List[str]] = {
    "stock_bajo":                ["admin", "gerente", "inventario"],
    "corte_z":                   ["admin", "gerente", "cajero"],
    "venta_cancelada":           ["admin", "gerente"],
    "diferencia_caja":           ["admin", "gerente"],
    "diferencia_recepcion":      ["admin", "gerente", "inventario"],
    "caducidad_proxima":         ["admin", "gerente", "inventario"],
    "backup_fallido":            ["admin"],
    "pedido_whatsapp_nuevo":     ["admin", "gerente", "cajero"],
    "pedido_asignado_repartidor": ["delivery"],
    "forecast_sugerencia_compra": ["admin", "gerente", "compras"],
    "alerta_seguridad":          ["admin"],
    "alerta_operacion_critica":  ["admin", "gerente"],
}


class RecipientResolver:
    """Resuelve destinatarios desde DB sin lógica de canal."""

    def __init__(self, db) -> None:
        self.db = db

    def by_role(self, tipo: str, sucursal_id: int) -> List[Dict]:
        """Retorna empleados activos para el tipo, según la matriz de roles."""
        roles = _ROL_MATRIX.get(tipo, [])
        return self._query_by_roles(roles, sucursal_id)

    def by_employee_id(self, empleado_id: int) -> Optional[Dict]:
        """Retorna datos de un empleado por su ID."""
        for query in (
            """SELECT u.id, u.usuario, u.nombre,
                      COALESCE(p.telefono, '') AS telefono
               FROM usuarios u
               LEFT JOIN personal p
                 ON LOWER(p.nombre) LIKE '%' || LOWER(u.nombre) || '%'
               WHERE u.id=? AND u.activo=1 LIMIT 1""",
            """SELECT e.id, e.usuario, e.nombre,
                      COALESCE(p.telefono, '') AS telefono
               FROM empleados e
               LEFT JOIN personal p ON p.empleado_id = e.id
               WHERE e.id=? AND e.activo=1 LIMIT 1""",
        ):
            try:
                row = self.db.execute(query, (empleado_id,)).fetchone()
                if row:
                    return dict(row)
            except Exception:
                pass
        return None

    def by_username(self, username: str) -> Optional[Dict]:
        """Retorna datos de un empleado por nombre de usuario."""
        for query in (
            """SELECT u.id, u.usuario, u.nombre,
                      COALESCE(p.telefono, '') AS telefono
               FROM usuarios u
               LEFT JOIN personal p
                 ON LOWER(p.nombre) LIKE '%' || LOWER(u.nombre) || '%'
               WHERE u.usuario=? AND u.activo=1 LIMIT 1""",
            """SELECT e.id, e.usuario, e.nombre,
                      COALESCE(p.telefono, '') AS telefono
               FROM empleados e
               LEFT JOIN personal p ON p.empleado_id = e.id
               WHERE e.usuario=? AND e.activo=1 LIMIT 1""",
        ):
            try:
                row = self.db.execute(query, (username,)).fetchone()
                if row:
                    return dict(row)
            except Exception:
                pass
        return None

    def by_phone(self, empleado_id: int) -> Optional[str]:
        """Retorna sólo el teléfono de un empleado."""
        emp = self.by_employee_id(empleado_id)
        return (emp or {}).get("telefono") or None

    def explicit_responsibles(self, tipo: str, sucursal_id: int) -> List[Dict]:
        """
        Lee `configuraciones` para destinatarios explícitos de alertas críticas.
        Clave: `wa_responsibles_{tipo}` → JSON lista de {empleado_id, telefono}.
        Permite a admin configurar quién recibe alertas críticas por WA.
        """
        key = f"wa_responsibles_{tipo}"
        try:
            row = self.db.execute(
                "SELECT valor FROM configuraciones WHERE clave=?", (key,)
            ).fetchone()
            if not row or not row[0]:
                return []
            data = json.loads(row[0])
            if not isinstance(data, list):
                return []
            return data
        except Exception as exc:
            logger.debug("explicit_responsibles %s: %s", tipo, exc)
            return []

    # ── Privados ──────────────────────────────────────────────────────────────

    def _query_by_roles(self, roles: List[str], sucursal_id: int) -> List[Dict]:
        if not roles:
            return []
        ph = ",".join("?" * len(roles))
        queries = [
            # RBAC completo
            f"""SELECT DISTINCT u.id, u.usuario, u.nombre,
                       COALESCE(p.telefono, '') AS telefono
                FROM usuarios u
                JOIN usuarios_roles ur ON ur.usuario_id = u.id
                JOIN roles r ON r.id = ur.rol_id
                LEFT JOIN personal p
                  ON LOWER(p.nombre) LIKE '%' || LOWER(u.nombre) || '%'
                WHERE r.nombre IN ({ph})
                  AND (ur.sucursal_id=? OR ur.sucursal_id=0)
                  AND u.activo=1""",
            # Legacy columna usuarios.rol
            f"""SELECT u.id, u.usuario, u.nombre,
                       COALESCE(p.telefono, '') AS telefono
                FROM usuarios u
                LEFT JOIN personal p
                  ON LOWER(p.nombre) LIKE '%' || LOWER(u.nombre) || '%'
                WHERE LOWER(u.rol) IN ({ph})
                  AND (u.sucursal_id=? OR u.sucursal_id IS NULL)
                  AND u.activo=1""",
            # Legacy tabla empleados
            f"""SELECT e.id, e.usuario, e.nombre,
                       COALESCE(p.telefono, '') AS telefono
                FROM empleados e
                LEFT JOIN personal p ON p.empleado_id = e.id
                WHERE LOWER(e.rol) IN ({ph})
                  AND (e.sucursal_id=? OR e.sucursal_id IS NULL)
                  AND e.activo=1""",
        ]
        lower_roles = [r.lower() for r in roles]
        for q in queries:
            try:
                rows = self.db.execute(q, (*lower_roles, sucursal_id)).fetchall()
                if rows:
                    return [dict(r) for r in rows]
            except Exception:
                pass
        return []
