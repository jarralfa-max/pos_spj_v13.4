"""342 — diseño del ticket, logos y foto del ticket (comparativa de tickets
main ↔ ERP 968e0bc, 2026-10-16).

Medido en la base real: el impresor de Ventas ignoraba la plantilla (una versión
de `SALE_TICKET` con el texto libre «Productos, unidad, cantidad, costo» esperaba
aprobación sin ningún efecto posible), el logo era un UUID que nadie podía
cargar y `print_jobs` tenía 0 filas — sin versión activa no se registraba
ninguna impresión.

1. `branding_assets` + `branch_branding`: la biblioteca de logos (empresa y,
   opcionalmente, cada sucursal — decisión del usuario).
2. `sale_receipt_snapshots`: la foto de cada ticket para reimprimirlo idéntico
   (decisión del usuario).
3. Para `SALE_TICKET` y `SWEEPSTAKES_TICKET` sin versión ACTIVA: una versión
   ACTIVA con el DISEÑO POR OMISIÓN (el ticket de siempre), en la plantilla que
   ya exista de ese tipo o en una nueva. Es el punto de partida del diseñador y
   la versión que se registra en cada impresión. No toca versiones existentes
   (la de texto libre queda donde está; ya no podrá aprobarse ni activarse).

Idempotente.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.342")

_TEMPLATES = {
    "SALE_TICKET": ("Ticket de venta", "sales", "Diseño del ticket del punto de venta"),
    "SWEEPSTAKES_TICKET": ("Boleto de sorteo", "sweepstakes", "Diseño del boleto de sorteo"),
}


def _table(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (name,)).fetchone() is not None


def run(conn) -> None:
    from backend.infrastructure.db.schema.branding_schema import create_branding_schema

    create_branding_schema(conn)
    if _table(conn, "sales"):
        from backend.infrastructure.db.schema.sales_schema import create_sales_schema
        create_sales_schema(conn)
    seeded = 0
    if _table(conn, "document_templates") and _table(conn, "document_template_versions"):
        seeded = _seed_default_designs(conn)
    conn.commit()
    logger.info("342: logos, foto del ticket y %s diseño(s) por omisión activos.", seeded)


def _seed_default_designs(conn) -> int:
    from backend.domain.document_output.entities.document_template import DocumentTemplate
    from backend.domain.document_output.entities.document_template_version import (
        DocumentTemplateVersion,
    )
    from backend.domain.document_output.enums import DocumentType, RenderFormat
    from backend.domain.document_output.ticket_layout import (
        default_layout,
        layout_for_document_type,
    )
    from backend.infrastructure.db.repositories.document_output.document_template_repository import (
        SqliteDocumentTemplateRepository,
    )
    from backend.infrastructure.db.repositories.document_output.document_template_version_repository import (
        SqliteDocumentTemplateVersionRepository,
    )

    templates = SqliteDocumentTemplateRepository(conn)
    versions = SqliteDocumentTemplateVersionRepository(conn)
    seeded = 0
    for doc_type, (name, module, description) in _TEMPLATES.items():
        existing = templates.list_by_document_type(DocumentType(doc_type))
        if any(versions.get_active_for_template(t.id) for t in existing):
            continue
        template = next((t for t in existing if t.active), None)
        if template is None:
            template = DocumentTemplate.create(document_type=DocumentType(doc_type), name=name,
                                               module=module, description=description)
            templates.save(template)
            number = 1
        else:
            number = max((v.version for v in versions.list_for_template(template.id)),
                         default=0) + 1
        version = DocumentTemplateVersion.create(
            template_id=template.id, content_format=RenderFormat.ESC_POS,
            content=default_layout(layout_for_document_type(doc_type)).to_json())
        version.version = number
        version.reason = "Diseño por omisión (migración 342)"
        version.submit_for_approval()
        version.approve("sistema")
        version.activate("sistema")
        versions.save(version)
        seeded += 1
    return seeded
