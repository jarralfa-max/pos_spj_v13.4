from __future__ import annotations

from typing import Any


class SaleCheckoutWorkerFactory:
    """Bloqueada: la venta transaccional no puede clonarse superficialmente a QThread."""

    def __init__(self, container):
        self._container = container

    def build(self, uc_venta: Any, items, datos_pago, sucursal_id, usuario):
        raise RuntimeError(
            "SaleCheckoutWorkerFactory deshabilitado: ejecutar ProcesarVentaUC.ejecutar() "
            "en el hilo principal hasta tener WorkerAppContainer real."
        )
