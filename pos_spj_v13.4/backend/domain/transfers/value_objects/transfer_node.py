from dataclasses import dataclass
from ..enums import TransferNodeType


@dataclass(frozen=True, slots=True)
class TransferNode:
    """A logistics endpoint; IDs are UUIDv7 strings supplied by their owners."""
    node_type: TransferNodeType
    branch_id: str | None = None
    warehouse_id: str | None = None
    location_id: str | None = None

    def identity(self) -> tuple[TransferNodeType, str | None, str | None, str | None]:
        return self.node_type, self.branch_id, self.warehouse_id, self.location_id
