"""Cold-chain evaluation without product-specific hardcoded temperatures."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ..enums import ColdChainStatus, ReceiptQualityStatus


def _decimal(value: Decimal | str | int) -> Decimal:
    if isinstance(value, (bool, float)):
        raise TypeError("Cold-chain values must use Decimal")
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True, slots=True)
class ProductTransferProfile:
    product_id: str
    catch_weight: bool
    lot_required: bool
    quality_required: bool
    temperature_required: bool
    minimum_temperature: Decimal | None = None
    maximum_temperature: Decimal | None = None
    temperature_warning_margin: Decimal | None = None

    def __post_init__(self) -> None:
        if self.minimum_temperature is not None:
            object.__setattr__(self, "minimum_temperature", _decimal(self.minimum_temperature))
        if self.maximum_temperature is not None:
            object.__setattr__(self, "maximum_temperature", _decimal(self.maximum_temperature))
        if self.temperature_warning_margin is not None:
            object.__setattr__(self, "temperature_warning_margin",
                               _decimal(self.temperature_warning_margin))
        if self.temperature_required and (
            self.minimum_temperature is None or self.maximum_temperature is None
        ):
            raise ValueError("Temperature-controlled product requires configured limits")
        if (self.minimum_temperature is not None and self.maximum_temperature is not None
                and self.minimum_temperature > self.maximum_temperature):
            raise ValueError("Minimum temperature cannot exceed maximum temperature")
        if self.temperature_warning_margin is not None and self.temperature_warning_margin < 0:
            raise ValueError("Temperature warning margin cannot be negative")


@dataclass(frozen=True, slots=True)
class ColdChainAssessment:
    cold_chain_status: ColdChainStatus
    quality_status: ReceiptQualityStatus
    requires_quality_inspection: bool
    reason: str | None = None


class ColdChainTransferPolicy:
    def evaluate(self, *, profile: ProductTransferProfile,
                 temperature: Decimal | str | int | None,
                 expires_on: str | None, observed_on: date) -> ColdChainAssessment:
        if expires_on is not None and date.fromisoformat(expires_on) < observed_on:
            return ColdChainAssessment(ColdChainStatus.BLOCKED, ReceiptQualityStatus.QUARANTINED,
                                       True, "EXPIRED")
        if profile.temperature_required:
            if temperature is None:
                return ColdChainAssessment(ColdChainStatus.PENDING_QUALITY,
                                           ReceiptQualityStatus.PENDING_INSPECTION,
                                           True, "TEMPERATURE_MISSING")
            value = _decimal(temperature)
            if value < profile.minimum_temperature or value > profile.maximum_temperature:
                return ColdChainAssessment(ColdChainStatus.OUT_OF_RANGE,
                                           ReceiptQualityStatus.QUARANTINED,
                                           True, "TEMPERATURE_OUT_OF_RANGE")
            if (profile.temperature_warning_margin is not None
                    and (value <= profile.minimum_temperature + profile.temperature_warning_margin
                         or value >= profile.maximum_temperature - profile.temperature_warning_margin)):
                return ColdChainAssessment(ColdChainStatus.WARNING,
                                           ReceiptQualityStatus.AVAILABLE, False,
                                           "TEMPERATURE_NEAR_LIMIT")
        if profile.quality_required:
            return ColdChainAssessment(ColdChainStatus.PENDING_QUALITY,
                                       ReceiptQualityStatus.PENDING_INSPECTION, True)
        return ColdChainAssessment(ColdChainStatus.COMPLIANT,
                                   ReceiptQualityStatus.AVAILABLE, False)
