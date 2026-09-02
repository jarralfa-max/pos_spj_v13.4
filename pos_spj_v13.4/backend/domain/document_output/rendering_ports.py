"""DocumentRendererPort — SET-11 "Renderers". Distinct from
`repository_ports.py` (persistence), same idea as
`backend/domain/device_management/hardware_ports.py`: this is the
contract a *real* renderer (`backend/infrastructure/printing/escpos_renderer.py`,
`html_renderer.py`, `pdf_renderer.py`, ... — a later SET) would
implement. No ESC/POS byte-building or PDF-library code is written here
— generating real ESC/POS bytes or a real PDF is a format-specific,
vendor/library-dependent job that needs a real target to validate
against, the same reasoning that kept `hardware_ports.py` a pure
contract in SET-10.

§27: "La plantilla no consulta tablas. Document Output no calcula reglas
de negocio." — `render()` takes the *template* and a plain `data` dict
(the canonical DTO the owning module already assembled), nothing else.
It never reaches into a database.
"""

from __future__ import annotations

from typing import Protocol

from backend.domain.document_output.entities.document_template_version import DocumentTemplateVersion


class DocumentRendererPort(Protocol):
    def render(self, template_version: DocumentTemplateVersion, data: dict) -> bytes:
        """Render `template_version.content` against `data`, producing
        output in `template_version.content_format`. Must raise rather
        than return partial/garbled output on a rendering failure — the
        caller (a future use case) is responsible for turning that into
        `PrintJob.fail(reason)`."""
        ...
