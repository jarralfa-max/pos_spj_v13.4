"""SET-14 — proves a label `DocumentTemplate`/`DocumentTemplateVersion`/
`PrintJob` round-trips through SET-11's already-shipped repositories
(`SqliteDocumentTemplateRepository`, `SqliteDocumentTemplateVersionRepository`,
`SqlitePrintJobRepository`) against a real (in-memory) SQLite born-clean
schema — no schema change was needed for SET-14: `document_type` columns
have no fixed-value CHECK constraint, so the new label `DocumentType`
values (enums.py) just work.
"""

from __future__ import annotations

import pytest

from backend.domain.document_output.entities.document_template import DocumentTemplate
from backend.domain.document_output.entities.document_template_version import DocumentTemplateVersion
from backend.domain.document_output.entities.print_job import PrintJob
from backend.domain.document_output.enums import DocumentType, RenderFormat
from backend.infrastructure.db.repositories.document_output.document_template_repository import (
    SqliteDocumentTemplateRepository,
)
from backend.infrastructure.db.repositories.document_output.document_template_version_repository import (
    SqliteDocumentTemplateVersionRepository,
)
from backend.infrastructure.db.repositories.document_output.print_job_repository import (
    SqlitePrintJobRepository,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


class TestLabelDocumentPersistence:
    def test_label_template_version_and_print_job_round_trip(self, conn):
        template_repo = SqliteDocumentTemplateRepository(conn)
        version_repo = SqliteDocumentTemplateVersionRepository(conn)
        job_repo = SqlitePrintJobRepository(conn)

        template = DocumentTemplate.create(
            document_type=DocumentType.WEIGHT_LABEL, name="Etiqueta de peso variable", module="inventory",
        )
        template_repo.save(template)
        conn.commit()

        version = DocumentTemplateVersion.create(
            template_id=template.id, content_format=RenderFormat.ZPL,
            content="^XA^FO50,50^FD{product_name}^FS^XZ",
        )
        version_repo.save(version)
        conn.commit()

        fetched_template = template_repo.get(template.id)
        fetched_version = version_repo.get(version.id)
        assert fetched_template.document_type is DocumentType.WEIGHT_LABEL
        assert fetched_version.content_format is RenderFormat.ZPL

        job = PrintJob.create(
            document_type=DocumentType.WEIGHT_LABEL.value, source_module="inventory",
            source_document_id=new_uuid(), template_version_id=version.id, requested_by_user_id="op-1",
        )
        job_repo.save(job)
        conn.commit()

        fetched_job = job_repo.get(job.id)
        assert fetched_job.document_type == "WEIGHT_LABEL"

    def test_list_by_document_type_finds_label_templates(self, conn):
        template_repo = SqliteDocumentTemplateRepository(conn)
        lot_template = DocumentTemplate.create(
            document_type=DocumentType.LOT_LABEL, name="Etiqueta de lote", module="inventory",
        )
        weight_template = DocumentTemplate.create(
            document_type=DocumentType.WEIGHT_LABEL, name="Etiqueta de peso", module="inventory",
        )
        template_repo.save(lot_template)
        template_repo.save(weight_template)
        conn.commit()

        lot_results = template_repo.list_by_document_type(DocumentType.LOT_LABEL)
        assert [t.id for t in lot_results] == [lot_template.id]
