"""PaymentTerminalProfilePolicy — is this `DeviceProfile` a legally-shaped
payment-terminal profile? (§18/§20/§23). Transaction processing itself
(amounts, currency, authorization) is Finance/Sales' domain, not Device
Management's — this policy only checks the profile declares *some* way
to actually take a payment.
"""

from __future__ import annotations

from backend.domain.device_management.enums import PAYMENT_TERMINAL_CAPABILITIES, PAYMENT_TERMINAL_DEVICE_TYPES
from backend.domain.device_management.exceptions import InvalidPaymentTerminalProfileError


def assert_valid_payment_terminal_profile(profile) -> None:
    if profile.device_type not in PAYMENT_TERMINAL_DEVICE_TYPES:
        raise InvalidPaymentTerminalProfileError(
            f"{profile.device_type.value} no es un tipo de terminal de pago "
            f"({sorted(t.value for t in PAYMENT_TERMINAL_DEVICE_TYPES)})"
        )
    declared = {capability.code for capability in profile.capabilities}
    if not declared & PAYMENT_TERMINAL_CAPABILITIES:
        raise InvalidPaymentTerminalProfileError(
            f"{profile.name}: un perfil de terminal de pago debe declarar al menos una de "
            f"{sorted(c.value for c in PAYMENT_TERMINAL_CAPABILITIES)}"
        )
