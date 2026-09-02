"""SET-12 — "Secciones": DocumentSection + SectionLayout. Pure domain — no DB."""

from __future__ import annotations

import pytest

from backend.domain.document_output.enums import DocumentSectionCode, SectionAlignment
from backend.domain.document_output.exceptions import DocumentInvalidValueError
from backend.domain.document_output.value_objects.document_section import DocumentSection
from backend.domain.document_output.value_objects.section_layout import SectionLayout


class TestDocumentSectionCreate:
    def test_defaults_to_enabled_and_left_aligned(self):
        section = DocumentSection.create(code=DocumentSectionCode.LOGO, order=0)
        assert section.enabled is True
        assert section.alignment is SectionAlignment.LEFT

    def test_can_be_disabled_and_aligned(self):
        section = DocumentSection.create(
            code=DocumentSectionCode.QR, order=3, enabled=False, alignment=SectionAlignment.CENTER,
        )
        assert section.enabled is False
        assert section.alignment is SectionAlignment.CENTER

    @pytest.mark.parametrize("order", [-1, 1.5, True])
    def test_rejects_invalid_order(self, order):
        with pytest.raises(DocumentInvalidValueError):
            DocumentSection.create(code=DocumentSectionCode.LOGO, order=order)


class TestSectionLayoutCreate:
    def test_requires_at_least_one_section(self):
        with pytest.raises(DocumentInvalidValueError):
            SectionLayout.create([])

    def test_rejects_duplicate_codes(self):
        with pytest.raises(DocumentInvalidValueError):
            SectionLayout.create([
                DocumentSection.create(code=DocumentSectionCode.LOGO, order=0),
                DocumentSection.create(code=DocumentSectionCode.LOGO, order=1),
            ])

    def test_accepts_distinct_codes(self):
        layout = SectionLayout.create([
            DocumentSection.create(code=DocumentSectionCode.LOGO, order=0),
            DocumentSection.create(code=DocumentSectionCode.ITEMS, order=1),
        ])
        assert len(layout.sections) == 2


class TestSectionLayoutQueries:
    def _layout(self) -> SectionLayout:
        return SectionLayout.create([
            DocumentSection.create(code=DocumentSectionCode.TOTALS, order=2),
            DocumentSection.create(code=DocumentSectionCode.LOGO, order=0),
            DocumentSection.create(code=DocumentSectionCode.ITEMS, order=1, enabled=False),
        ])

    def test_ordered_sorts_by_order_not_construction_order(self):
        layout = self._layout()
        assert [s.code for s in layout.ordered()] == [
            DocumentSectionCode.LOGO, DocumentSectionCode.ITEMS, DocumentSectionCode.TOTALS,
        ]

    def test_enabled_codes_skips_disabled_and_preserves_order(self):
        layout = self._layout()
        assert layout.enabled_codes() == (DocumentSectionCode.LOGO, DocumentSectionCode.TOTALS)

    def test_get_returns_section_or_none(self):
        layout = self._layout()
        assert layout.get(DocumentSectionCode.LOGO).order == 0
        assert layout.get(DocumentSectionCode.BARCODE) is None
