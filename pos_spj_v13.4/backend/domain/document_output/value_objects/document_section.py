"""DocumentSection — SET-12 "Secciones": one named, ordered, toggleable
block of a rendered document (§26-27). Generalizes
`core/tickets/ticket_layout_config.py::TicketLayoutBlock`
(enabled/order/alignment) into a pure domain value object, independent of
`content_format` — the same section vocabulary applies whether a
`DocumentTemplateVersion` renders to ESC_POS, HTML, or PDF.

Deliberately not persisted on its own (no new table): a template's
section arrangement is data the template's own `content` already encodes
for MVP purposes, the same non-persistence call SET-9 made for
`WeightReading`/`StabilityPolicy` — see `MIGRATION_LOG.md`'s SET-12 entry
for the explicit reasoning.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.document_output.enums import DocumentSectionCode, SectionAlignment
from backend.domain.document_output.exceptions import DocumentInvalidValueError


@dataclass(frozen=True, slots=True)
class DocumentSection:
    code: DocumentSectionCode
    order: int
    enabled: bool = True
    alignment: SectionAlignment = SectionAlignment.LEFT

    @classmethod
    def create(
        cls, *, code: DocumentSectionCode, order: int, enabled: bool = True,
        alignment: SectionAlignment = SectionAlignment.LEFT,
    ) -> "DocumentSection":
        if isinstance(order, bool) or not isinstance(order, int) or order < 0:
            raise DocumentInvalidValueError(f"order debe ser un entero >= 0, recibido {order!r}")
        return cls(code=code, order=order, enabled=bool(enabled), alignment=alignment)
