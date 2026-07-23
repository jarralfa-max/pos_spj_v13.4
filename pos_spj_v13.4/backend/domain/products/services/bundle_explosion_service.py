"""BundleExplosionService — validate and explode a bundle (§28).

Validation: at least one component; components must not repeat; the bundle's own
product may not be a component (direct cycle); no transitive cycle via a resolver
(a bundle of a bundle of itself). Explosion: expand a virtual bundle into the
component quantities to consume at sale time (optional components excluded unless
selected). Pure; Decimal-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from backend.domain.products.entities.bundle_version import BundleVersion
from backend.domain.products.entities.product_bundle import ProductBundle
from backend.domain.products.exceptions import (
    BundleCycleDetectedError,
    InvalidBundleError,
)

ComponentResolver = Callable[[str], list[str]]


def _no_op(_pid: str) -> list[str]:
    return []


@dataclass(frozen=True)
class ExplodedBundleComponent:
    component_product_id: str
    quantity: Decimal
    unit_id: str


class BundleExplosionService:
    def validate(
        self,
        bundle: ProductBundle,
        version: BundleVersion,
        *,
        resolver: ComponentResolver | None = None,
    ) -> None:
        if not version.components:
            raise InvalidBundleError("El combo requiere al menos un componente (§28)")

        ids = version.component_product_ids()
        if len(ids) != len(set(ids)):
            raise InvalidBundleError("Los componentes del combo no pueden repetirse")

        if bundle.product_id in ids:
            raise BundleCycleDetectedError(
                "Un combo no puede contener su propio producto")

        resolve = resolver or _no_op
        stack = list(ids)
        seen: set[str] = set()
        while stack:
            pid = stack.pop()
            if pid == bundle.product_id:
                raise BundleCycleDetectedError(
                    f"Ciclo de combo: {bundle.product_id} se contiene a sí mismo")
            if pid in seen:
                continue
            seen.add(pid)
            stack.extend(resolve(pid))

    def explode(
        self,
        version: BundleVersion,
        target_quantity: Decimal | int | str = Decimal("1"),
        *,
        include_optional: bool = False,
    ) -> list[ExplodedBundleComponent]:
        if isinstance(target_quantity, bool) or isinstance(target_quantity, float):
            raise InvalidBundleError("La cantidad objetivo no puede ser float")
        factor = Decimal(str(target_quantity))
        if factor <= 0:
            raise InvalidBundleError("La cantidad objetivo debe ser positiva")
        result: list[ExplodedBundleComponent] = []
        for c in version.components:
            if c.optional and not include_optional:
                continue
            result.append(ExplodedBundleComponent(
                component_product_id=c.component_product_id,
                quantity=(c.quantity * factor), unit_id=c.unit_id))
        return result
