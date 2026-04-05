# core/domain/exceptions.py — SPJ POS v13.3
"""
Excepciones de dominio centralizadas.

Reemplaza las excepciones dispersas en:
  - services.py (legacy) → InventarioError, StockInsuficienteError, VentaError
  - _legacy/services.py  → mismas, versión antigua
  - core/services/inventory_engine.py → re-export

Todas las capas (use_cases, services, repositories) deben importar desde aquí.
Las excepciones legacy siguen funcionando vía shims de compatibilidad.
"""
from __future__ import annotations


# ── Base ──────────────────────────────────────────────────────────────────────

class SPJDomainError(Exception):
    """Base para todas las excepciones de dominio del sistema SPJ."""
    pass


# ── Inventario ────────────────────────────────────────────────────────────────

class InventarioError(SPJDomainError):
    """Error genérico de inventario."""
    pass


class StockInsuficienteError(InventarioError):
    """Stock insuficiente para completar la operación."""

    def __init__(
        self,
        producto_id: int = 0,
        nombre: str = "",
        disponible: float = 0.0,
        requerido: float = 0.0,
    ):
        self.producto_id = producto_id
        self.nombre = nombre
        self.disponible = disponible
        self.requerido = requerido
        super().__init__(
            f"Stock insuficiente: '{nombre}' — "
            f"disponible: {disponible:.3f}, requerido: {requerido:.3f}"
        )


class LoteExpiradoError(InventarioError):
    """Intento de operar con un lote cuya fecha de caducidad ya pasó."""
    pass


# ── Ventas ────────────────────────────────────────────────────────────────────

class VentaError(SPJDomainError):
    """Error genérico en el proceso de venta."""
    pass


class VentaCanceladaError(VentaError):
    """Intento de operar sobre una venta ya cancelada."""
    pass


class PagoInsuficienteError(VentaError):
    """Monto pagado menor al total de la venta."""
    pass


# ── Producción ────────────────────────────────────────────────────────────────

class ProduccionError(SPJDomainError):
    """Error genérico de producción."""
    pass


class LoteCerradoError(ProduccionError):
    """Intento de modificar un lote de producción ya cerrado."""
    pass


class BalancePesoError(ProduccionError):
    """Balance de peso fuera de tolerancia en cierre de lote."""
    pass


class CostoProteccionError(ProduccionError):
    """Costo total excede los límites de protección financiera."""
    pass


# ── Sync ──────────────────────────────────────────────────────────────────────

class SyncError(SPJDomainError):
    """Error genérico de sincronización."""
    pass


class ConflictoManualError(SyncError):
    """Conflicto de sync que requiere revisión humana."""

    def __init__(self, event_id: str = "", tabla: str = "", razon: str = ""):
        self.event_id = event_id
        self.tabla = tabla
        self.razon = razon
        super().__init__(
            f"Conflicto manual: tabla={tabla} event={event_id[:8]} — {razon}"
        )


# ── Auth / Seguridad ─────────────────────────────────────────────────────────

class AuthError(SPJDomainError):
    """Error de autenticación o autorización."""
    pass


class PermisoInsuficienteError(AuthError):
    """Usuario sin permisos para la operación solicitada."""
    pass
