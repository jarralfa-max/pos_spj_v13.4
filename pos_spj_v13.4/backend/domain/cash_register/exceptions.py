"""Cash Register security and policy errors."""


class CashRegisterError(Exception):
    """Base error for the Cash Register bounded context."""


class CashConfigurationError(CashRegisterError):
    pass


class CashPermissionDeniedError(CashRegisterError):
    pass


class CashAuthorizationRequiredError(CashRegisterError):
    pass


class CashLimitExceededError(CashRegisterError):
    pass


class CashSegregationOfDutiesError(CashRegisterError):
    pass


class CashInvalidStateError(CashRegisterError):
    pass


class CashShiftNotOpenError(CashInvalidStateError):
    """El cajero no tiene un turno con el que se pueda cobrar o reembolsar.

    `shift_id`/`status` identifican su turno activo cuando existe (suspendido
    o en cierre) para que Caja y POS hablen del MISMO turno; ambos son None si
    no tiene ninguno (SDLC-ARQ-SHIFT-001)."""

    def __init__(self, message: str, *, shift_id: str | None = None,
                 status: str | None = None) -> None:
        super().__init__(message)
        self.shift_id = shift_id
        self.status = status


class CashShiftSuspendedError(CashShiftNotOpenError):
    """El turno activo está suspendido: hay que reanudarlo en Caja."""


class CashShiftClosingError(CashShiftNotOpenError):
    """El turno activo está en cierre: hay que terminarlo y abrir otro."""


class CashShiftConflictError(CashInvalidStateError):
    """El turno cambió entre leerlo y escribirlo: nada se escribió
    (SDLC-ARQ-SHIFT-004). Quien lo recibe vuelve a consultar el turno."""


class CashDuplicateOperationError(CashRegisterError):
    pass

