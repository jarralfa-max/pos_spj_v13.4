# sync/domain_validators/production_validator.py — SPJ POS v13.3
"""
Validador de dominio para producción cárnica en sincronización.

Reglas específicas del negocio:
  1. Un lote CERRADO nunca se reabre por sync remoto
  2. Balance de peso con merma > 50% → dato corrupto
  3. Cost allocation no puede exceder 200% del costo de materia prima
  4. Subproducto con peso = 0 después de cierre → sospechoso
"""
from __future__ import annotations

import logging
from typing import Optional

from sync.domain_validators.base import DomainValidator

logger = logging.getLogger("spj.sync.validators.production")

PRODUCTION_TABLES = frozenset({
    "production_batches", "production_outputs",
    "production_cost_ledger", "production_yield_analysis",
})


class ProductionValidator(DomainValidator):
    """Valida reglas de negocio de producción cárnica post-resolución."""

    def __init__(
        self,
        max_merma_pct: float = 50.0,
        max_cost_ratio: float = 2.0,
    ):
        self.max_merma_pct = max_merma_pct
        self.max_cost_ratio = max_cost_ratio

    def validate(
        self,
        tabla: str,
        resolved: dict,
        local: dict,
        remote: dict,
    ) -> Optional[str]:
        if tabla not in PRODUCTION_TABLES:
            return None

        if tabla == "production_batches":
            return self._validate_batch(resolved, local, remote)

        if tabla == "production_outputs":
            return self._validate_output(resolved, local, remote)

        if tabla == "production_cost_ledger":
            return self._validate_cost(resolved, local, remote)

        return None

    def _validate_batch(
        self, resolved: dict, local: dict, remote: dict
    ) -> Optional[str]:
        local_status = local.get("estado", local.get("status", ""))
        remote_status = remote.get("estado", remote.get("status", ""))

        # ── Regla 1: Lote cerrado no se reabre ───────────────────────────
        if local_status == "cerrado" and remote_status in ("abierto", "open"):
            return (
                f"Lote {local.get('folio', '?')} cerrado localmente — "
                "sync remoto intentó reabrirlo"
            )

        # ── Regla 2: Balance de peso sospechoso ──────────────────────────
        source_kg = float(resolved.get("source_weight",
                          resolved.get("peso_origen", 0)))
        output_kg = float(resolved.get("total_output_weight",
                          resolved.get("peso_total_salida", 0)))

        if source_kg > 0 and output_kg > 0:
            merma_pct = abs(source_kg - output_kg) / source_kg * 100
            if merma_pct > self.max_merma_pct:
                return (
                    f"Balance de peso sospechoso en lote {resolved.get('folio', '?')}: "
                    f"origen={source_kg:.3f}kg, salida={output_kg:.3f}kg, "
                    f"merma={merma_pct:.1f}% (max={self.max_merma_pct}%)"
                )

        return None

    def _validate_output(
        self, resolved: dict, local: dict, remote: dict
    ) -> Optional[str]:
        # Subproducto con peso 0 después de cierre
        weight = float(resolved.get("weight", resolved.get("peso", 0)))
        batch_status = resolved.get("batch_status", "")

        if weight <= 0 and batch_status == "cerrado":
            return (
                f"Subproducto {resolved.get('product_id', '?')} con peso=0 "
                f"en lote cerrado — posible corrupción"
            )

        return None

    def _validate_cost(
        self, resolved: dict, local: dict, remote: dict
    ) -> Optional[str]:
        # Cost allocation no puede exceder N veces el costo de MP
        allocated = float(resolved.get("costo_asignado",
                          resolved.get("allocated_cost", 0)))
        source_cost = float(resolved.get("costo_materia_prima",
                            resolved.get("source_cost", 0)))

        if source_cost > 0 and allocated > source_cost * self.max_cost_ratio:
            return (
                f"Cost allocation sospechoso: asignado=${allocated:.2f} "
                f"vs materia_prima=${source_cost:.2f} "
                f"(ratio={allocated/source_cost:.1f}x, max={self.max_cost_ratio}x)"
            )

        return None
