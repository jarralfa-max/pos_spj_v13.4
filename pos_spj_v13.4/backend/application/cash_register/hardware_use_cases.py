"""Audited orchestration for physical cash-register hardware."""
from __future__ import annotations

from decimal import Decimal

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.hardware import (
    CashDrawerGateway, CashHardwareError, PaymentTerminalGateway, PrintJob,
    ReceiptPrinterGateway, TerminalPaymentRequest,
)
from backend.application.cash_register.permissions import CashPermissions
from backend.application.cash_register.shift_use_cases import _record
from backend.domain.cash_register.events import CashEvents
from backend.infrastructure.db.repositories.cash_register.unit_of_work import CashRegisterUnitOfWork
from backend.shared.ids import validate_uuidv7


def _failure(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, CashHardwareError):
        return exc.code, str(exc)
    return "DRIVER_FAILURE", "El dispositivo no respondió correctamente"


def _record_failure(connection, *, operation_id: str, entity_id: str,
                    branch_id: str, actor_user_id: str, command: str,
                    code: str, message: str) -> None:
    with CashRegisterUnitOfWork(connection) as uow:
        _record(
            uow, CashEvents.HARDWARE_OPERATION_FAILED,
            operation_id=operation_id, entity_id=entity_id,
            branch_id=branch_id, actor_user_id=actor_user_id,
            reason=message, command=command, error_code=code,
            alert_required=True, alert_severity="CRITICAL",
        )


class OpenCashDrawerUseCase:
    def __init__(self, authorization: CashAuthorizationPolicy,
                 gateway: CashDrawerGateway) -> None:
        self._authorization, self._gateway = authorization, gateway

    def execute(self, connection, *, drawer_id: str, branch_id: str,
                actor_user_id: str, operation_id: str,
                sale_id: str | None = None, reason: str = "") -> None:
        validate_uuidv7(drawer_id)
        validate_uuidv7(branch_id)
        validate_uuidv7(actor_user_id)
        validate_uuidv7(operation_id)
        if sale_id is not None:
            validate_uuidv7(sale_id)
        self._authorization.require(user_id=actor_user_id,
                                    permission_code=CashPermissions.DRAWER_OPEN,
                                    branch_id=branch_id)
        if sale_id is None:
            if not reason.strip():
                raise ValueError("La apertura sin venta requiere motivo")
            self._authorization.require(
                user_id=actor_user_id,
                permission_code=CashPermissions.DRAWER_OPEN_WITHOUT_SALE,
                branch_id=branch_id,
            )
        with CashRegisterUnitOfWork(connection) as uow:
            drawer = uow.devices.get("drawer", drawer_id)
            if not drawer or drawer["branch_id"] != branch_id:
                raise LookupError("Cajón fuera de alcance")
            if drawer["status"] != "ACTIVE":
                raise RuntimeError("El cajón no está activo")
        try:
            self._gateway.open_drawer(drawer_id)
        except Exception as exc:
            code, message = _failure(exc)
            _record_failure(connection, operation_id=operation_id, entity_id=drawer_id,
                            branch_id=branch_id, actor_user_id=actor_user_id,
                            command="OPEN_DRAWER", code=code, message=message)
            raise CashHardwareError(code, message) from exc
        with CashRegisterUnitOfWork(connection) as uow:
            _record(uow, CashEvents.DRAWER_OPENED, operation_id=operation_id,
                    entity_id=drawer_id, branch_id=branch_id,
                    actor_user_id=actor_user_id, reason=reason,
                    sale_id=sale_id, without_sale=sale_id is None)


class PrintCashDocumentUseCase:
    def __init__(self, authorization: CashAuthorizationPolicy,
                 gateway: ReceiptPrinterGateway) -> None:
        self._authorization, self._gateway = authorization, gateway

    def execute(self, connection, *, printer_id: str, document_id: str,
                content: bytes, branch_id: str, actor_user_id: str,
                operation_id: str, copies: int = 1) -> None:
        self._authorization.require(user_id=actor_user_id,
                                    permission_code=CashPermissions.PRINT,
                                    branch_id=branch_id)
        if not content or not 1 <= copies <= 3:
            raise ValueError("Documento vacío o número de copias inválido")
        for value in (printer_id, document_id, operation_id):
            validate_uuidv7(value)
        try:
            self._gateway.print_job(printer_id, PrintJob(document_id, content, copies))
        except Exception as exc:
            code, message = _failure(exc)
            _record_failure(connection, operation_id=operation_id, entity_id=printer_id,
                            branch_id=branch_id, actor_user_id=actor_user_id,
                            command="PRINT", code=code, message=message)
            raise CashHardwareError(code, message) from exc
        with CashRegisterUnitOfWork(connection) as uow:
            _record(uow, CashEvents.CASH_DOCUMENT_PRINTED,
                    operation_id=operation_id, entity_id=printer_id,
                    branch_id=branch_id, actor_user_id=actor_user_id,
                    document_id=document_id, copies=copies)


class ChargePaymentTerminalUseCase:
    """Hardware boundary only; Sales remains owner of payment business state."""

    def __init__(self, authorization: CashAuthorizationPolicy,
                 gateway: PaymentTerminalGateway) -> None:
        self._authorization, self._gateway = authorization, gateway

    def execute(self, connection, *, terminal_id: str, amount: Decimal,
                currency: str, reference: str, branch_id: str,
                actor_user_id: str, operation_id: str):
        validate_uuidv7(terminal_id)
        validate_uuidv7(branch_id)
        validate_uuidv7(actor_user_id)
        validate_uuidv7(operation_id)
        self._authorization.require(user_id=actor_user_id,
                                    permission_code=CashPermissions.TERMINAL_OPERATE,
                                    branch_id=branch_id)
        if amount <= 0 or not currency.strip() or not reference.strip():
            raise ValueError("Solicitud de cobro inválida")
        with CashRegisterUnitOfWork(connection) as uow:
            terminal = uow.devices.get("terminal", terminal_id)
            if not terminal or terminal["branch_id"] != branch_id:
                raise LookupError("Terminal fuera de alcance")
            if terminal["status"] != "ACTIVE":
                raise RuntimeError("La terminal no está activa")
        request = TerminalPaymentRequest(operation_id, amount, currency.upper(), reference)
        try:
            result = self._gateway.charge(terminal_id, request)
        except Exception as exc:
            code, message = _failure(exc)
            _record_failure(connection, operation_id=operation_id, entity_id=terminal_id,
                            branch_id=branch_id, actor_user_id=actor_user_id,
                            command="TERMINAL_CHARGE", code=code, message=message)
            raise CashHardwareError(code, message) from exc
        with CashRegisterUnitOfWork(connection) as uow:
            _record(uow, CashEvents.TERMINAL_PAYMENT_EXECUTED,
                    operation_id=operation_id, entity_id=terminal_id,
                    branch_id=branch_id, actor_user_id=actor_user_id,
                    approved=result.approved, transaction_id=result.transaction_id,
                    response_code=result.response_code, reference=reference)
        return result
