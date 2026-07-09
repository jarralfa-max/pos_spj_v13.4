"""Diálogo de captura de cantidad/peso (teclado numérico tipo calculadora).

Especialización de NumericKeypadDialog para cantidades y pesos (decimals=3 por
defecto). La mecánica del teclado, el toggle desplegable y las reglas del skill
(inicio en 0/vacío, sin defaults arbitrarios) viven en el componente base.
"""
from __future__ import annotations

from frontend.desktop.components.numeric_keypad_dialog import NumericKeypadDialog


class QuantityInputDialog(NumericKeypadDialog):
    """Popup de captura de cantidad con teclado numérico (calculadora)."""

    def __init__(self, parent=None, *, titulo: str = "Cantidad",
                 mensaje: str = "Ingrese la cantidad:", decimals: int = 3,
                 minimo: float = 0.0, maximo: float = 999999999.0,
                 unidad: str = "", inicial: float = 0.0) -> None:
        super().__init__(
            parent, titulo=titulo, mensaje=mensaje, decimals=decimals,
            minimo=minimo, maximo=maximo, unidad=unidad, inicial=inicial,
        )

    @classmethod
    def get_quantity(
        cls,
        parent=None,
        titulo: str = "Cantidad",
        mensaje: str = "Ingrese la cantidad:",
        *,
        decimals: int = 3,
        minimo: float = 0.0,
        maximo: float = 999999999.0,
        unidad: str = "",
        inicial: float = 0.0,
    ) -> tuple[float, bool]:
        """Devuelve (valor, ok). Compatible en forma con QInputDialog.getDouble."""
        return cls.get_value(
            parent, titulo, mensaje, decimals=decimals, minimo=minimo,
            maximo=maximo, unidad=unidad, inicial=inicial, permitir_cero=False,
        )
