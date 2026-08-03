from dataclasses import dataclass

from backend.domain.losses.entities._validation import required_uuid
from backend.domain.losses.enums import LossClassificationCode
from backend.domain.losses.exceptions import LossInvariantError


@dataclass(frozen=True)
class LossClassification:
    id: str
    code: LossClassificationCode
    display_name: str
    active: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", required_uuid(self.id, "loss_classification_id"))
        if not isinstance(self.code, LossClassificationCode):
            raise LossInvariantError("Clasificación canónica requerida")
        if not self.display_name.strip():
            raise LossInvariantError("Nombre visible de clasificación requerido")
