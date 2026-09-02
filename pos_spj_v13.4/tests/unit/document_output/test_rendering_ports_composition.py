"""SET-11 — "Renderers": DocumentRendererPort composition. A Protocol with
no real implementation in this bounded context (see rendering_ports.py's
docstring — real ESC/POS byte-building or PDF generation is a later,
library-dependent SET); this test proves the shape works end to end with
a fake renderer, mirroring
tests/unit/device_management/test_hardware_ports_composition.py.
"""

from __future__ import annotations

import pytest

from backend.domain.document_output.entities.document_template_version import DocumentTemplateVersion
from backend.domain.document_output.enums import RenderFormat
from backend.domain.document_output.rendering_ports import DocumentRendererPort
from backend.shared.ids import new_uuid


class _FakeRenderer:
    """Satisfies DocumentRendererPort structurally — no real ESC/POS/PDF."""

    def render(self, template_version: DocumentTemplateVersion, data: dict) -> bytes:
        rendered = template_version.content
        for key, value in data.items():
            rendered = rendered.replace("{" + key + "}", str(value))
        return rendered.encode("utf-8")


class _FailingRenderer:
    def render(self, template_version: DocumentTemplateVersion, data: dict) -> bytes:
        raise ValueError("plantilla corrupta")


def _render_use_case(renderer: DocumentRendererPort, version: DocumentTemplateVersion, data: dict) -> bytes:
    """The shape a future application-layer use case follows: this
    function never touches the DB — it only combines a template version
    with a plain data dict (§27)."""
    return renderer.render(version, data)


class TestDocumentRendererComposition:
    def test_fake_renderer_substitutes_placeholders(self):
        version = DocumentTemplateVersion.create(
            template_id=new_uuid(), content_format=RenderFormat.ESC_POS, content="Total: {total}",
        )
        output = _render_use_case(_FakeRenderer(), version, {"total": "150.00"})
        assert output == b"Total: 150.00"

    def test_renderer_failure_propagates_rather_than_returning_partial_output(self):
        version = DocumentTemplateVersion.create(
            template_id=new_uuid(), content_format=RenderFormat.ESC_POS, content="Total: {total}",
        )
        with pytest.raises(ValueError):
            _render_use_case(_FailingRenderer(), version, {"total": "150.00"})
