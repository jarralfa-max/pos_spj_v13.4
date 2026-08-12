"""Material consumption overage validation (§17/§61). `tolerance_pct` is always an
input, never a module-level constant — the real value comes from
SystemSettingsService/ModuleSettingsService in a later phase (root CLAUDE.md #23/24).
"""

from decimal import Decimal

from backend.domain.meat_processing.exceptions import MeatProcessingInvariantError


class ConsumptionPolicy:
    @staticmethod
    def validate_overage(
        planned: Decimal,
        actual: Decimal,
        *,
        tolerance_pct: Decimal,
    ) -> None:
        if tolerance_pct < 0:
            raise MeatProcessingInvariantError("tolerance_pct no puede ser negativo")
        if planned < 0 or actual < 0:
            raise MeatProcessingInvariantError("Cantidad planeada y real no pueden ser negativas")
        if planned == 0:
            if actual > 0:
                raise MeatProcessingInvariantError(
                    "Consumo sin cantidad planeada requiere autorización explícita")
            return
        overage_pct = ((actual - planned) / planned) * Decimal("100")
        if overage_pct > tolerance_pct:
            raise MeatProcessingInvariantError(
                f"Consumo {overage_pct:.2f}% excede la tolerancia permitida de "
                f"{tolerance_pct:.2f}%")
