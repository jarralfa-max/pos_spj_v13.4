"""SalesPaymentTerminalClient — Sales' integration point onto the real Cash
Register bounded context for card-terminal charges (POS-12/§49-51).

SALES-0/SALES-11 both classified the payment terminal as "100% new work" —
research for this phase found that framing outdated: a real, well-formed
Protocol/use-case triad now exists (`backend/application/cash_register/
hardware.py::PaymentTerminalGateway` + `hardware_use_cases.py::
ChargePaymentTerminalUseCase`), built in a concurrent refactor of the Caja
bounded context. It is audited (`CashEvents.TERMINAL_PAYMENT_EXECUTED` /
`HARDWARE_OPERATION_FAILED`) and permission-gated
(`CashPermissions.TERMINAL_OPERATE`) exactly like drawer-open and print.
What is still genuinely missing — confirmed by research, not assumed — is a
real acquirer SDK behind `PaymentTerminalGateway`; no vendor driver exists
anywhere in this repository. This client does not fabricate one. It wraps
the real, already-audited use case so Sales can request a terminal charge
through the correct bounded-context boundary the moment a real
`PaymentTerminalGateway` implementation is wired in; until then, callers
inject `StubCashHardwareGateway`-style test doubles, exactly like Caja's own
test suite already does.

`ChargePaymentTerminalUseCase`'s own docstring: "Hardware boundary only;
Sales remains owner of payment business state" — this client is exactly
that boundary call, never store this result in Sale itself here; a future
phase (§30-36, checkout/pago) is responsible for taking the returned
`TerminalPaymentResult` and driving Sale's own payment-status transitions.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.hardware import PaymentTerminalGateway, TerminalPaymentResult
from backend.application.cash_register.hardware_use_cases import ChargePaymentTerminalUseCase


class SalesPaymentTerminalClient:
    def __init__(self, authorization: CashAuthorizationPolicy, gateway: PaymentTerminalGateway) -> None:
        self._use_case = ChargePaymentTerminalUseCase(authorization, gateway)

    def charge(
        self, connection, *, terminal_id: str, amount: Decimal, currency: str,
        reference: str, branch_id: str, actor_user_id: str, operation_id: str,
    ) -> TerminalPaymentResult:
        return self._use_case.execute(
            connection, terminal_id=terminal_id, amount=amount, currency=currency,
            reference=reference, branch_id=branch_id, actor_user_id=actor_user_id,
            operation_id=operation_id)
