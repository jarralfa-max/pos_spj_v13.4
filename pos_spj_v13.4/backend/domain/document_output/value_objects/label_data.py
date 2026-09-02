"""LabelData — SET-14 "Serialización": the typed aggregate a module
assembles before calling `rendering_ports.DocumentRendererPort.render()`
for a label document_type, the label-shaped counterpart to SET-12's
`TicketData`. Generalizes
`backend/domain/inventory/value_objects/label_document.py::LabelDocument`
(INV-26) — same fields (title/lines/barcode/qr_payload/entity_ref/copies),
Decimal-safe, into the Document Output bounded context so any module can
build one, not only Inventory. That INV-26 pipeline is untouched by this
SET — see `MIGRATION_LOG.md`'s SET-14 entry for why cutting it over is
out of scope here.

If a `variable_set` is supplied, `create()` validates the caller's
`variables` dict against it (`LabelVariableSet.assert_satisfied`) before
constructing — same "catch it at construction, not on the printed
label" discipline as `TicketData`'s totals invariant.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.document_output.enums import DocumentType, LABEL_DOCUMENT_TYPES
from backend.domain.document_output.exceptions import DocumentInvalidValueError
from backend.domain.document_output.value_objects.label_variable_set import LabelVariableSet


@dataclass(frozen=True, slots=True)
class LabelData:
    label_type: DocumentType
    title: str
    body_lines: tuple[str, ...]
    barcode: str | None = None
    qr_payload: str | None = None
    entity_ref: str | None = None
    copies: int = 1
    variables: dict = field(default_factory=dict)

    @classmethod
    def create(
        cls, *, label_type: DocumentType, title: str, body_lines: tuple[str, ...] | list[str] = (),
        barcode: str | None = None, qr_payload: str | None = None, entity_ref: str | None = None,
        copies: int = 1, variables: dict | None = None, variable_set: LabelVariableSet | None = None,
    ) -> "LabelData":
        if label_type not in LABEL_DOCUMENT_TYPES:
            raise DocumentInvalidValueError(
                f"label_type debe ser uno de {sorted(t.value for t in LABEL_DOCUMENT_TYPES)}, "
                f"recibido {label_type!r}"
            )
        if not title.strip():
            raise DocumentInvalidValueError("title es obligatorio")
        if isinstance(copies, bool) or not isinstance(copies, int) or copies < 1:
            raise DocumentInvalidValueError(f"copies debe ser un entero >= 1, recibido {copies!r}")
        variables = dict(variables or {})
        if variable_set is not None:
            variable_set.assert_satisfied(variables)
        return cls(
            label_type=label_type, title=title.strip(), body_lines=tuple(body_lines), barcode=barcode,
            qr_payload=qr_payload, entity_ref=entity_ref, copies=copies, variables=variables,
        )

    def to_render_data(self) -> dict:
        """Flattens this DTO into the plain, JSON-serializable ``data``
        dict `DocumentRendererPort.render()` already expects — mirrors
        `TicketData.to_render_data()`."""
        data = {
            "label_type": self.label_type.value, "title": self.title, "body_lines": list(self.body_lines),
            "barcode": self.barcode, "qr_payload": self.qr_payload, "entity_ref": self.entity_ref,
            "copies": self.copies,
        }
        data.update({key: str(value) for key, value in self.variables.items()})
        return data
