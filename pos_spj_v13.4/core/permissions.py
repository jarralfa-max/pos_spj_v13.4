# core/permissions.py — SPJ POS v13.30
"""
Permission enforcement helpers.

Provides:
  - requiere_permiso() — decorator for methods that need permission check
  - verificar_permiso() — function for inline checks with UI feedback
  - PermisoGuard — context manager for permission checks

Usage in modules:
    from core.permissions import verificar_permiso

    def eliminar_producto(self):
        if not verificar_permiso(self.container, "productos.eliminar", self):
            return  # Shows warning dialog automatically
        # ... proceed with deletion

    # Or as decorator on a method:
    from core.permissions import requiere_permiso
    
    @requiere_permiso("inventario.ajustar")
    def ajustar_inventario(self):
        ...  # Only runs if user has permission
"""
from __future__ import annotations
import logging
import functools
from typing import Optional

logger = logging.getLogger("spj.permissions")

# ── Mapa de permisos por módulo (para enforcement automático) ─────────────────
PERMISOS_MODULO = {
    "POS":              "ventas.realizar",
    "CAJA":             "caja.abrir",
    "INVENTARIO":       "inventario.ver",
    "PRODUCTOS":        "productos.crear",
    "CLIENTES":         "clientes.ver",
    "DELIVERY":         "ventas.realizar",
    "COMPRAS":          "inventario.comprar",
    "TRANSFERENCIAS":   "inventario.transferir",
    "MERMA":            "inventario.ajustar",
    "PRODUCCION":       "inventario.ajustar",
    "RRHH":             "rrhh.ver",
    "TESORERIA":        "finanzas.ver",
    "GROWTH_ENGINE":    "config.ver",
    "INTELIGENCIA_BI":  "reportes.bi",
    "PREDICCIONES":     "reportes.bi",
    "CONFIG_SEGURIDAD": "config.editar",
    "CONFIG_HARDWARE":  "config.editar",
    "ACTIVOS":          "finanzas.ver",
}


def verificar_permiso(container, codigo_permiso: str,
                      parent_widget=None, mostrar_alerta: bool = True) -> bool:
    """
    Verifica si el usuario actual tiene un permiso.
    Si no lo tiene y mostrar_alerta=True, muestra un QMessageBox.

    Returns: True si tiene permiso, False si no.
    """
    try:
        session = getattr(container, 'session', None)
        if not session:
            return True  # Sin SessionContext → no restricciones (compat)
        if not session.is_active:
            return True  # Sin sesión → no restricciones
        if session.es_admin:
            return True  # Admin siempre tiene acceso

        if session.tiene_permiso(codigo_permiso):
            return True

        # No tiene permiso
        if mostrar_alerta and parent_widget:
            try:
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.warning(
                    parent_widget, "🔒 Acceso Restringido",
                    f"No tienes permiso para esta acción.\n\n"
                    f"Permiso requerido: {codigo_permiso}\n"
                    f"Tu rol: {session.rol.capitalize()}\n"
                    f"Sucursal: {session.sucursal_nombre}\n\n"
                    "Contacta al administrador si necesitas este acceso.")
            except Exception:
                pass

        logger.warning(
            "Permiso denegado: %s requiere '%s' (rol=%s, sucursal=%s)",
            session.usuario, codigo_permiso, session.rol, session.sucursal_id)
        return False

    except Exception as e:
        logger.debug("verificar_permiso error: %s", e)
        return True  # En caso de error, permitir (fail-open por ahora)


def requiere_permiso(codigo_permiso: str):
    """
    Decorador para métodos de módulos que requieren un permiso.
    El método debe estar en una clase que tenga self.container.

    Usage:
        @requiere_permiso("inventario.ajustar")
        def ajustar_stock(self):
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            container = getattr(self, 'container', None)
            if not container:
                return func(self, *args, **kwargs)
            if verificar_permiso(container, codigo_permiso, self):
                return func(self, *args, **kwargs)
            # Permission denied — don't execute
            return None
        return wrapper
    return decorator


def verificar_acceso_modulo(container, codigo_modulo: str,
                            parent_widget=None) -> bool:
    """
    Verifica si el usuario puede acceder a un módulo completo.
    Usa el mapa PERMISOS_MODULO para determinar qué permiso necesita.
    """
    permiso = PERMISOS_MODULO.get(codigo_modulo)
    if not permiso:
        return True  # Módulo sin restricción definida
    return verificar_permiso(container, permiso, parent_widget)
