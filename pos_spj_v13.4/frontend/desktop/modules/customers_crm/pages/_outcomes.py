"""Resultados de pantalla para flujos de varios pasos (CRM-43)."""

from __future__ import annotations


class Fail:
    """Rechazo con mensaje propio: el formulario sigue abierto."""

    success = False

    def __init__(self, message: str) -> None:
        self.message = message


class DoneWithWarning:
    """La operación principal SÍ se hizo (reintentarla duplicaría) pero un paso
    posterior falló: el formulario se cierra y se avisa."""

    success = True

    def __init__(self, message: str) -> None:
        self.message = message
