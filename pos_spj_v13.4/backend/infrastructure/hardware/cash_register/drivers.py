"""Thin hardware drivers built around injected vendor transports."""
from __future__ import annotations

from typing import Protocol

from backend.application.cash_register.hardware import (
    CashHardwareError, PrintJob, TerminalPaymentRequest, TerminalPaymentResult,
)


class ByteTransport(Protocol):
    def write(self, device_id: str, payload: bytes) -> None: ...


class PrinterTransport(Protocol):
    def print_bytes(self, printer_id: str, payload: bytes, copies: int) -> None: ...


class AcquirerClient(Protocol):
    def charge(self, terminal_id: str, *, amount: str, currency: str,
               reference: str, idempotency_key: str) -> dict: ...


class EscPosDrawerDriver:
    def __init__(self, transport: ByteTransport,
                 pulse: bytes = b"\x1b\x70\x00\x19\xfa") -> None:
        if not pulse:
            raise ValueError("ESC/POS pulse cannot be empty")
        self._transport, self._pulse = transport, pulse

    def open_drawer(self, drawer_id: str) -> None:
        try:
            self._transport.write(drawer_id, self._pulse)
        except Exception as exc:
            raise CashHardwareError("DRAWER_IO_ERROR", "No fue posible abrir el cajón") from exc


class ReceiptPrinterDriver:
    def __init__(self, transport: PrinterTransport) -> None:
        self._transport = transport

    def print_job(self, printer_id: str, job: PrintJob) -> None:
        try:
            self._transport.print_bytes(printer_id, job.content, job.copies)
        except Exception as exc:
            raise CashHardwareError("PRINTER_IO_ERROR", "No fue posible imprimir") from exc


class PaymentTerminalDriver:
    def __init__(self, client: AcquirerClient) -> None:
        self._client = client

    def charge(self, terminal_id: str,
               request: TerminalPaymentRequest) -> TerminalPaymentResult:
        try:
            raw = self._client.charge(
                terminal_id, amount=str(request.amount), currency=request.currency,
                reference=request.reference, idempotency_key=request.operation_id,
            )
        except Exception as exc:
            raise CashHardwareError("TERMINAL_IO_ERROR", "La terminal no respondió") from exc
        transaction_id = str(raw.get("transaction_id", "")).strip()
        if not transaction_id:
            raise CashHardwareError("TERMINAL_INVALID_RESPONSE", "Respuesta inválida de terminal")
        return TerminalPaymentResult(
            approved=bool(raw.get("approved")), transaction_id=transaction_id,
            authorization_code=str(raw.get("authorization_code", "")),
            response_code=str(raw.get("response_code", "")),
        )
