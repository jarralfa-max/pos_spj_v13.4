"""YieldValidationService — validate a yield profile version (§23).

Rules:
- at least one output, exactly modelling MAIN/CO/BY_PRODUCT/WASTE/LOSS;
- outputs must not repeat the same product;
- expected yields must sum to 100 % within the version's configured tolerance —
  never hardcoded to an exact 100 %; a technical process legitimately uses a band.
Pure domain service — no persistence.
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.products.entities.yield_profile_version import YieldProfileVersion
from backend.domain.products.exceptions import (
    YieldProfileInvalidError,
    YieldToleranceExceededError,
)

_HUNDRED = Decimal("100")


class YieldValidationService:
    def validate(self, version: YieldProfileVersion) -> None:
        if not version.outputs:
            raise YieldProfileInvalidError("El perfil requiere al menos un output (§23)")

        product_ids = [o.product_id for o in version.outputs]
        if len(product_ids) != len(set(product_ids)):
            raise YieldProfileInvalidError("Los outputs no pueden repetir producto")

        total = version.total_expected_yield()
        deviation = abs(total - _HUNDRED)
        if deviation > version.tolerance_pct:
            raise YieldToleranceExceededError(
                f"La suma de rendimientos ({total} %) se desvía {deviation} % de 100 %, "
                f"fuera de la tolerancia configurada ({version.tolerance_pct} %)")

    def is_within_tolerance(self, version: YieldProfileVersion) -> bool:
        try:
            self.validate(version)
            return True
        except (YieldProfileInvalidError, YieldToleranceExceededError):
            return False
