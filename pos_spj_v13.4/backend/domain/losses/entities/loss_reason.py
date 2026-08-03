from dataclasses import dataclass

from backend.domain.losses.entities._validation import required_uuid
from backend.domain.losses.exceptions import LossInvariantError


@dataclass(frozen=True)
class LossReason:
    id: str
    classification_id: str
    code: str
    display_name: str
    active: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", required_uuid(self.id, "loss_reason_id"))
        object.__setattr__(self, "classification_id", required_uuid(
            self.classification_id, "loss_classification_id"))
        if not self.code.strip() or not self.display_name.strip():
            raise LossInvariantError("Código y nombre del motivo son requeridos")
