
# security/rbac.py — SPJ POS v6.1
# Role-Based Access Control — fuente única de permisos.
from __future__ import annotations
import logging
import functools
from typing import Set, Optional, Callable
from core.db.connection import get_connection

logger = logging.getLogger("spj.rbac")

# ── Roles estándar ────────────────────────────────────────────────────────────
ROLES = {
    "admin":      "Administrador del sistema",
    "gerente":    "Gerente de sucursal",
    "cajero":     "Cajero de punto de venta",
    "inventario": "Encargado de inventario",
    "delivery":   "Repartidor",
    "marketing":  "Área de marketing",
    "finanzas":   "Área de finanzas",
}

# ── Permisos estándar ─────────────────────────────────────────────────────────
PERMISOS = {
    # Ventas
    "ventas.realizar":    "Procesar ventas",
    "ventas.cancelar":    "Cancelar ventas",
    "ventas.descuento":   "Aplicar descuentos",
    "ventas.ver":         "Ver historial de ventas",
    # Inventario
    "inventario.ver":     "Ver inventario",
    "inventario.ajustar": "Ajustar existencias",
    "inventario.comprar": "Registrar compras",
    "inventario.transferir": "Transferir entre sucursales",
    # Productos
    "productos.crear":    "Crear productos",
    "productos.editar":   "Editar productos",
    "productos.eliminar": "Eliminar productos",
    # Clientes
    "clientes.ver":       "Ver clientes",
    "clientes.editar":    "Editar clientes",
    # Reportes
    "reportes.ver":       "Ver reportes básicos",
    "reportes.bi":        "Ver Business Intelligence",
    "reportes.finanzas":  "Ver reportes financieros",
    # Caja
    "caja.abrir":         "Abrir caja",
    "caja.cerrar":        "Cerrar caja",
    "caja.movimientos":   "Registrar movimientos de caja",
    # Config
    "config.ver":         "Ver configuración",
    "config.editar":      "Editar configuración",
    "usuarios.gestionar": "Gestionar usuarios",
    # Finanzas
    "finanzas.ver":       "Ver módulo de finanzas",
    "finanzas.editar":    "Editar registros financieros",
    # RRHH
    "rrhh.ver":           "Ver módulo RRHH",
    "rrhh.editar":        "Editar registros RRHH",
}

# Matriz de permisos por rol
_ROLE_PERMISSIONS: dict[str, Set[str]] = {
    "admin":      set(PERMISOS.keys()),  # todo
    "gerente":    {
        "ventas.realizar","ventas.cancelar","ventas.descuento","ventas.ver",
        "inventario.ver","inventario.ajustar","inventario.comprar","inventario.transferir",
        "productos.crear","productos.editar","clientes.ver","clientes.editar",
        "reportes.ver","reportes.bi","reportes.finanzas",
        "caja.abrir","caja.cerrar","caja.movimientos",
        "config.ver","finanzas.ver","rrhh.ver",
    },
    "cajero":     {
        "ventas.realizar","ventas.ver","ventas.descuento",
        "clientes.ver","reportes.ver","caja.abrir","caja.cerrar","caja.movimientos",
    },
    "inventario": {
        "inventario.ver","inventario.ajustar","inventario.comprar","inventario.transferir",
        "productos.ver","reportes.ver",
    },
    "delivery":   {"ventas.ver","clientes.ver"},
    "marketing":  {"clientes.ver","reportes.bi","productos.ver"},
    "finanzas":   {"reportes.ver","reportes.finanzas","finanzas.ver","finanzas.editar"},
}


def inicializar_rbac(conn=None) -> None:
    """Crea tablas RBAC y siembra roles/permisos si no existen."""
    c = conn or get_connection()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS roles (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre      TEXT UNIQUE NOT NULL,
            descripcion TEXT,
            activo      INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS permisos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo      TEXT UNIQUE NOT NULL,
            modulo      TEXT NOT NULL,
            descripcion TEXT
        );
        CREATE TABLE IF NOT EXISTS roles_permisos (
            rol_id     INTEGER REFERENCES roles(id) ON DELETE CASCADE,
            permiso_id INTEGER REFERENCES permisos(id) ON DELETE CASCADE,
            PRIMARY KEY (rol_id, permiso_id)
        );
        CREATE TABLE IF NOT EXISTS usuarios_roles (
            usuario_id  INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            rol_id      INTEGER REFERENCES roles(id) ON DELETE CASCADE,
            sucursal_id INTEGER DEFAULT 1,
            PRIMARY KEY (usuario_id, rol_id, sucursal_id)
        );
    """)
    # Seed roles
    for nombre, desc in ROLES.items():
        c.execute("INSERT OR IGNORE INTO roles (nombre, descripcion) VALUES (?,?)", (nombre, desc))
    # Seed permisos
    for codigo, desc in PERMISOS.items():
        modulo = codigo.split(".")[0]
        c.execute("INSERT OR IGNORE INTO permisos (codigo, modulo, descripcion) VALUES (?,?,?)",
                  (codigo, modulo, desc))
    # Seed roles_permisos
    for rol_nombre, perms in _ROLE_PERMISSIONS.items():
        rol_row = c.execute("SELECT id FROM roles WHERE nombre=?", (rol_nombre,)).fetchone()
        if not rol_row:
            continue
        for perm_cod in perms:
            perm_row = c.execute("SELECT id FROM permisos WHERE codigo=?", (perm_cod,)).fetchone()
            if perm_row:
                c.execute("INSERT OR IGNORE INTO roles_permisos VALUES (?,?)",
                          (rol_row[0], perm_row[0]))
    c.execute("PRAGMA foreign_keys=ON")
    try:
        c.commit()
    except Exception:
        pass
    logger.info("RBAC inicializado")


def get_permisos(usuario_id: int, sucursal_id: int = 1) -> Set[str]:
    """
    Retorna el set de permisos del usuario.
    v13.1: Lee primero de rol_permisos (nueva tabla de 047).
    Fallback a tabla legacy permisos+roles_permisos.
    """
    from core.db.connection import get_connection
    conn = get_connection()

    # ── Intentar nueva tabla rol_permisos (v13) ───────────────────────────
    try:
        row_usr = conn.execute(
            "SELECT rol FROM usuarios WHERE id=?", (usuario_id,)
        ).fetchone()
        if row_usr and row_usr[0]:
            rol_nombre = row_usr[0]
            row_rol = conn.execute(
                "SELECT id FROM roles WHERE nombre=?", (rol_nombre,)
            ).fetchone()
            if row_rol:
                rows = conn.execute(
                    "SELECT modulo, accion FROM rol_permisos "
                    "WHERE rol_id=? AND permitido=1",
                    (row_rol[0],)
                ).fetchall()
                if rows:
                    perms = {f"{r[0]}.{r[1]}" for r in rows}
                    # Always add basic role permissions
                    perms.add(f"rol.{rol_nombre}")
                    logger.debug("RBAC v13: usuario=%s rol=%s perms=%d",
                                 usuario_id, rol_nombre, len(perms))
                    return perms
    except Exception as _e:
        logger.debug("RBAC v13 tabla: %s", _e)

    # ── Fallback: tabla legacy permisos+roles_permisos ────────────────────
    try:
        rows = conn.execute("""
            SELECT p.codigo FROM permisos p
            JOIN roles_permisos rp ON rp.permiso_id = p.id
            JOIN usuarios_roles ur ON ur.rol_id = rp.rol_id
            WHERE ur.usuario_id = ? AND (ur.sucursal_id = ? OR ur.sucursal_id = 0)
        """, (usuario_id, sucursal_id)).fetchall()
        if rows:
            return {r[0] for r in rows}
    except Exception as _e:
        logger.debug("RBAC legacy tabla: %s", _e)

    # ── Fallback final: permisos por rol hardcoded ────────────────────────
    try:
        row = conn.execute(
            "SELECT rol FROM usuarios WHERE id=?", (usuario_id,)
        ).fetchone()
        if row:
            return _get_default_permisos(row[0])
    except Exception:
        pass

    return set()


def _get_default_permisos(rol: str) -> Set[str]:
    """Permisos mínimos garantizados por rol cuando la BD no tiene datos."""
    defaults = {
        "admin":    {"*"},  # all
        "gerente":  {"POS.ver","POS.crear","INVENTARIO.ver","REPORTES_BI.ver",
                     "CLIENTES.ver","CLIENTES.editar","CAJA.ver","USUARIOS.ver"},
        "cajero":   {"POS.ver","POS.crear","CLIENTES.ver","CAJA.ver"},
        "almacen":  {"INVENTARIO.ver","INVENTARIO.editar","PRODUCTOS.ver"},
        "repartidor":{"DELIVERY.ver","DELIVERY.editar"},
        "solo_lectura": {"POS.ver","INVENTARIO.ver","PRODUCTOS.ver"},
    }
    return defaults.get(rol, {"POS.ver"})


def tiene_permiso(usuario_id: int, permiso: str, sucursal_id: int = 1) -> bool:
    return permiso in get_permisos(usuario_id, sucursal_id)


def asignar_rol(usuario_id: int, rol_nombre: str, sucursal_id: int = 1) -> None:
    conn = get_connection()
    rol = conn.execute("SELECT id FROM roles WHERE nombre=?", (rol_nombre,)).fetchone()
    if not rol:
        raise ValueError(f"Rol '{rol_nombre}' no existe")
    conn.execute("INSERT OR REPLACE INTO usuarios_roles VALUES (?,?,?)",
                 (usuario_id, rol[0], sucursal_id))
    conn.commit()


def requerir_permiso(permiso: str):
    """Decorador para métodos de servicio que requieren permiso."""
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(self, *args, **kwargs):
            uid = getattr(self, "usuario_id", None) or kwargs.get("usuario_id")
            if uid and not tiene_permiso(uid, permiso):
                raise PermissionError(f"Permiso requerido: {permiso}")
            return fn(self, *args, **kwargs)
        return wrapper
    return decorator
