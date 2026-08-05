"""Vendor-neutral ports for cash-register hardware.

Application and domain code only depend on these contracts. USB, serial,
ESC/POS and acquirer SDK details belong to infrastructure drivers.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Protocol


class CashHardwareError(RuntimeError):
    """A hardware command failed in a controlled, user-presentable way."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class HardwareDiagnostic:
    device_id: str
    connected: bool
    message: str
    driver: str = "unknown"


@dataclass(frozen=True, slots=True)
class PrintJob:
    document_id: str
    content: bytes
    copies: int = 1


@dataclass(frozen=True, slots=True)
class TerminalPaymentRequest:
    operation_id: str
    amount: Decimal
    currency: str
    reference: str


@dataclass(frozen=True, slots=True)
class TerminalPaymentResult:
    approved: bool
    transaction_id: str
    authorization_code: str = ""
    response_code: str = ""
    metadata: Mapping[str, str] | None = None


class CashDrawerGateway(Protocol):
    def open_drawer(self, drawer_id: str) -> None: ...


class ReceiptPrinterGateway(Protocol):
    def print_job(self, printer_id: str, job: PrintJob) -> None: ...


class PaymentTerminalGateway(Protocol):
    def charge(self, terminal_id: str,
               request: TerminalPaymentRequest) -> TerminalPaymentResult: ...


class CashHardwareGateway(CashDrawerGateway, Protocol):
    """Backward-compatible diagnostic port used by CASH-6."""

    def diagnose(self, device_id: str) -> HardwareDiagnostic: ...


class StubCashHardwareGateway:
    """Deterministic fake for composition roots and tests; never touches hardware."""

    def __init__(self, *, connected: bool = True) -> None:
        self.connected = connected
        self.opened: list[str] = []

    def diagnose(self, device_id: str) -> HardwareDiagnostic:
        return HardwareDiagnostic(
            device_id, self.connected,
            "Disponible" if self.connected else "Sin conexión",
            "stub",
        )

    def open_drawer(self, drawer_id: str) -> None:
        if not self.connected:
            raise CashHardwareError("DRAWER_UNAVAILABLE", "Cajón no disponible")
        self.opened.append(drawer_id)
