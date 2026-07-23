"""CuttingSchemeService — validate a cutting-scheme version (§24).

Rules:
- at least one output;
- outputs must not repeat the same product;
- the scheme's input product may not appear as one of its own outputs (a scheme
  may not contain itself — §24).
Pure domain service — no persistence.
"""

from __future__ import annotations

from backend.domain.products.entities.cutting_scheme import CuttingScheme
from backend.domain.products.entities.cutting_scheme_version import (
    CuttingSchemeVersion,
)
from backend.domain.products.exceptions import (
    CuttingSchemeCycleDetectedError,
    CuttingSchemeInvalidError,
)


class CuttingSchemeService:
    def validate(self, scheme: CuttingScheme, version: CuttingSchemeVersion) -> None:
        if not version.outputs:
            raise CuttingSchemeInvalidError("El esquema requiere al menos un output (§24)")

        product_ids = version.output_product_ids()
        if len(product_ids) != len(set(product_ids)):
            raise CuttingSchemeInvalidError("Los outputs no pueden repetir producto")

        if scheme.input_product_id in product_ids:
            raise CuttingSchemeCycleDetectedError(
                "El esquema de despiece no puede contenerse a sí mismo (§24)")
