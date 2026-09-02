"""DisplayLayout — SET-17 "Layouts": which `DisplaySection`s render, in
what order, for one `CustomerDisplayMode`. At most one ACTIVE layout may
exist per mode — enforced by a partial unique index
(`ux_display_layouts_mode_active`), mirroring
`document_template_versions`' "one ACTIVE version per template" rule
(SET-11) at a coarser grain (no version history here — SET-17 doesn't
call for one, unlike Document Output's templates).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.customer_display.enums import CustomerDisplayMode, CustomerDisplaySectionCode
from backend.domain.customer_display.exceptions import CustomerDisplayInvalidValueError
from backend.domain.customer_display.value_objects.display_section import DisplaySection
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class DisplayLayout:
    id: str
    mode: CustomerDisplayMode
    sections: tuple[DisplaySection, ...]
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, *, mode: CustomerDisplayMode, sections: tuple[DisplaySection, ...] | list[DisplaySection],
    ) -> "DisplayLayout":
        sections = tuple(sections)
        if not sections:
            raise CustomerDisplayInvalidValueError("DisplayLayout requiere al menos una sección")
        codes = [section.code for section in sections]
        if len(codes) != len(set(codes)):
            raise CustomerDisplayInvalidValueError(f"Códigos de sección duplicados en el layout: {codes}")
        return cls(id=new_uuid(), mode=mode, sections=sections)

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def activate(self) -> None:
        self.active = True
        self._touch()

    def deactivate(self) -> None:
        self.active = False
        self._touch()

    def ordered_sections(self) -> tuple[DisplaySection, ...]:
        return tuple(sorted(self.sections, key=lambda section: section.order))

    def enabled_codes(self) -> tuple[CustomerDisplaySectionCode, ...]:
        return tuple(section.code for section in self.ordered_sections() if section.enabled)
