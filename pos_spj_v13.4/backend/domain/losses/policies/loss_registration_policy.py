from backend.domain.losses.enums import LossClassificationCode, LossOrigin
from backend.domain.losses.exceptions import LossInvariantError


class LossRegistrationPolicy:
    _NO_PHYSICAL_POSTING = frozenset({
        LossClassificationCode.THEORETICAL_LOSS,
        LossClassificationCode.YIELD_VARIANCE,
    })
    _PRODUCTION_CLASSIFICATIONS = frozenset({
        LossClassificationCode.PROCESS_LOSS,
        LossClassificationCode.CUTTING_LOSS,
        LossClassificationCode.YIELD_VARIANCE,
        LossClassificationCode.PRODUCTION_SAMPLE,
    })

    def requires_inventory_posting(self, classification: LossClassificationCode) -> bool:
        return classification not in self._NO_PHYSICAL_POSTING

    def validate_origin(
        self,
        *,
        classification: LossClassificationCode,
        origin: LossOrigin,
        source_document_id: str | None,
    ) -> None:
        if classification in self._PRODUCTION_CLASSIFICATIONS:
            if origin not in {LossOrigin.PRODUCTION, LossOrigin.CUTTING, LossOrigin.SLAUGHTER_FUTURE}:
                raise LossInvariantError("La pérdida de proceso requiere origen de producción")
            if not source_document_id:
                raise LossInvariantError("La pérdida de producción requiere documento origen")
        if classification is LossClassificationCode.TRANSFER_DIFFERENCE \
                and origin is not LossOrigin.TRANSFER:
            raise LossInvariantError("La diferencia de transferencia requiere origen TRANSFER")
        if classification in {LossClassificationCode.QUALITY_REJECTION,
                              LossClassificationCode.CONDEMNATION} \
                and origin is not LossOrigin.QUALITY:
            raise LossInvariantError("Rechazo y decomiso requieren origen QUALITY")
