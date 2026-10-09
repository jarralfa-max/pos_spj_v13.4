"""Cajón de dinero real: pulso ESC/POS por la impresora del ticket (CASH-26 bloque 2).

Medido 2026-10-07: la shell componía Caja con `StubCashHardwareGateway`, así que
«Abrir cajón» registraba el evento y el cajón nunca se abría. Configuración no
registra cajones («se administran en Caja») y `cash_drawers` no guarda ninguna
conexión, porque el cajón de un mostrador va conectado al puerto RJ11 de la
impresora térmica y se abre con el pulso `ESC p`. Por eso el cajón se abre por
la impresora que Document Output asigna al ticket de venta de su sucursal (la
misma por la que sale el ticket).
"""

from __future__ import annotations

from backend.application.cash_register.hardware import CashHardwareError, HardwareDiagnostic
from backend.infrastructure.db.repositories.cash_register.unit_of_work import CashRegisterUnitOfWork
from backend.infrastructure.printing.routed_printer import (
    PrintTargetUnavailable,
    resolve_routed_device,
    send,
)

#: ESC p m t1 t2 — pin 2, 50 ms encendido, 500 ms apagado (estándar Epson/Xprinter).
DRAWER_KICK = b"\x1bp\x00\x19\xfa"

NO_DRAWER_PRINTER_MESSAGE = (
    "El cajón se abre por la impresora de tickets y esta sucursal no tiene una asignada. "
    "Asígnala en Configuración → Dispositivos (ruta de impresión «Ticket de venta»).")


class PrinterKickCashDrawerGateway:
    """`CashHardwareGateway`: abre el cajón con el pulso de la impresora del ticket."""

    def __init__(self, connection, *, workstation_id: str | None = None) -> None:
        self._conn = connection
        self._workstation_id = workstation_id or None

    def open_drawer(self, drawer_id: str) -> None:
        try:
            device, profile = self._printer_for(drawer_id)
            send(device, profile, DRAWER_KICK, what="la señal del cajón")
        except PrintTargetUnavailable as exc:
            raise CashHardwareError("DRAWER_UNAVAILABLE", str(exc)) from exc

    def diagnose(self, device_id: str) -> HardwareDiagnostic:
        """Sin abrir el cajón no hay forma de comprobarlo físicamente: informa por
        qué impresora se abriría o por qué no puede abrirse."""
        if self._drawer(device_id) is None:
            return HardwareDiagnostic(device_id, False,
                                      "Este dispositivo no tiene controlador de hardware", "none")
        try:
            device, _profile = self._printer_for(device_id)
        except PrintTargetUnavailable as exc:
            return HardwareDiagnostic(device_id, False, str(exc), "escpos-kick")
        return HardwareDiagnostic(device_id, True,
                                  f"Se abre por la impresora {device.code}", "escpos-kick")

    def _drawer(self, drawer_id: str):
        return CashRegisterUnitOfWork(self._conn).devices.get("drawer", drawer_id)

    def _printer_for(self, drawer_id: str):
        from backend.domain.device_management.enums import PrintRouteModule
        from backend.domain.document_output.enums import DocumentType

        drawer = self._drawer(drawer_id)
        if drawer is None:
            raise PrintTargetUnavailable("El cajón no existe en Caja.")
        return resolve_routed_device(
            self._conn, DocumentType.SALE_TICKET.value, branch_id=drawer["branch_id"],
            workstation_id=self._workstation_id, module=PrintRouteModule.SALES.value,
            no_printer_message=NO_DRAWER_PRINTER_MESSAGE)
