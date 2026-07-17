# modulos/compras_pro.py — SPJ POS v13.4
"""Wrapper temporal (PUR-13): Compras usa el módulo enterprise canónico.

El monolito de 7,362 líneas fue reemplazado. Toda su funcionalidad vive ahora en
el bounded context de Compras (`frontend/desktop/modules/purchasing/` +
`backend/…/procurement/` + handlers de Inventario): panel, compra directa,
solicitudes, órdenes, recepción QR (generar/asignar/recibir/histórico), facturas
(conciliación 3 vías), historial, analítica, lotes (FIFO) y recetas. Este wrapper
no contiene SQL, layouts, estilos, validaciones, lógica de negocio, acceso a
repositorios, afectaciones de inventario ni pagos.

`ModuloComprasPro` se conserva como nombre para no romper `main_window`,
`menu_lateral` y el `module_loader`, que abren el módulo canónico a través de él.
Debe eliminarse cuando esos consumidores usen `ModuloComprasEnterprise`
directamente.
"""

from __future__ import annotations

from modulos.compras_enterprise import ModuloComprasEnterprise


class ModuloComprasPro:
    """Alias de compatibilidad → módulo enterprise de Compras (Design System)."""

    def __new__(cls, container, *args, **kwargs):
        # El loader llama con (conexion, usuario[, parent]); main_window con
        # (container). Sólo el contenedor importa; el resto se ignora.
        return ModuloComprasEnterprise(container)
