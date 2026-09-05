"""InspectionChecklistTemplate / InspectionChecklistItem — configurable
inspection checklists (ASSET-7, §38). Never hardcode questions in the UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.assets.enums import InspectionResponseType, InspectionType
from backend.domain.assets.exceptions import AssetDomainError
from backend.shared.ids import new_uuid


@dataclass(slots=True)
class InspectionChecklistItem:
    id: str
    order: int
    question_text: str
    response_type: InspectionResponseType
    required: bool = True
    choices: tuple[str, ...] = ()

    @classmethod
    def create(cls, order: int, question_text: str, response_type: InspectionResponseType,
               *, required: bool = True, choices: tuple[str, ...] = ()) -> "InspectionChecklistItem":
        if not question_text or not question_text.strip():
            raise AssetDomainError("InspectionChecklistItem.question_text is required")
        if response_type is InspectionResponseType.CHOICE and not choices:
            raise AssetDomainError(
                "InspectionChecklistItem with CHOICE response_type requires choices")
        return cls(id=new_uuid(), order=order, question_text=question_text.strip(),
                    response_type=response_type, required=required, choices=tuple(choices))


@dataclass(slots=True)
class InspectionChecklistTemplate:
    id: str
    name: str
    inspection_type: InspectionType
    active: bool = True
    items: list[InspectionChecklistItem] = field(default_factory=list)

    @classmethod
    def create(cls, name: str, inspection_type: InspectionType) -> "InspectionChecklistTemplate":
        if not name or not name.strip():
            raise AssetDomainError("InspectionChecklistTemplate.name is required")
        return cls(id=new_uuid(), name=name.strip(), inspection_type=inspection_type)

    def add_item(self, question_text: str, response_type: InspectionResponseType, *,
                 required: bool = True, choices: tuple[str, ...] = ()) -> InspectionChecklistItem:
        item = InspectionChecklistItem.create(
            len(self.items) + 1, question_text, response_type,
            required=required, choices=choices)
        self.items.append(item)
        return item

    def deactivate(self) -> None:
        self.active = False

    def reactivate(self) -> None:
        self.active = True
