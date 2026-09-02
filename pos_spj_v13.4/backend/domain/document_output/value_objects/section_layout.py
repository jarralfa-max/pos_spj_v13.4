"""SectionLayout — SET-12: a validated, ordered collection of
`DocumentSection`. No two sections may claim the same `code` (a section
either exists once in a layout or not at all — legacy
`TicketLayoutConfig.blocks` is a dict keyed by block name for exactly
this reason).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.document_output.enums import DocumentSectionCode
from backend.domain.document_output.exceptions import DocumentInvalidValueError
from backend.domain.document_output.value_objects.document_section import DocumentSection


@dataclass(frozen=True, slots=True)
class SectionLayout:
    sections: tuple[DocumentSection, ...]

    @classmethod
    def create(cls, sections: tuple[DocumentSection, ...] | list[DocumentSection]) -> "SectionLayout":
        sections = tuple(sections)
        if not sections:
            raise DocumentInvalidValueError("SectionLayout requiere al menos una sección")
        codes = [section.code for section in sections]
        if len(codes) != len(set(codes)):
            raise DocumentInvalidValueError(f"Códigos de sección duplicados en el layout: {codes}")
        return cls(sections=sections)

    def ordered(self) -> tuple[DocumentSection, ...]:
        return tuple(sorted(self.sections, key=lambda section: section.order))

    def enabled_codes(self) -> tuple[DocumentSectionCode, ...]:
        return tuple(section.code for section in self.ordered() if section.enabled)

    def get(self, code: DocumentSectionCode) -> DocumentSection | None:
        for section in self.sections:
            if section.code is code:
                return section
        return None
