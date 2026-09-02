"""SET-15 — proves a sweepstakes `DocumentTemplate`/`DocumentTemplateVersion`/
`PrintJob` round-trips through SET-11's already-shipped repositories
against a real (in-memory) SQLite born-clean schema — no schema change
was needed for SET-15, `DocumentType.SWEEPSTAKES_TICKET` already existed
since SET-11.
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


class TestSweepstakesDocumentPersistence:
    def test_template_version_and_print_job_round_trip(self, conn):
        template_repo = SqliteDocumentTemplateRepository(conn)
        version_repo = SqliteDocumentTemplateVersionRepository(conn)
        job_repo = SqlitePrintJobRepository(conn)

        template = DocumentTemplate.create(
            document_type=DocumentType.SWEEPSTAKES_TICKET, name="Boleto de sorteo", module="loyalty",
        )
        template_repo.save(template)
        conn.commit()

        version = DocumentTemplateVersion.create(
            template_id=template.id, content_format=RenderFormat.ESC_POS,
            content="BOLETO {ticket_number} - {raffle_name}",
        )
        version_repo.save(version)
        conn.commit()

        fetched_template = template_repo.get(template.id)
        fetched_version = version_repo.get(version.id)
        assert fetched_template.document_type is DocumentType.SWEEPSTAKES_TICKET
        assert fetched_version.content_format is RenderFormat.ESC_POS

        job = PrintJob.create(
            document_type=DocumentType.SWEEPSTAKES_TICKET.value, source_module="loyalty",
            source_document_id=new_uuid(), template_version_id=version.id, requested_by_user_id="op-1",
        )
        job_repo.save(job)
        conn.commit()

        fetched_job = job_repo.get(job.id)
        assert fetched_job.document_type == "SWEEPSTAKES_TICKET"

    def test_reprint_persists_as_independent_job(self, conn):
        template_repo = SqliteDocumentTemplateRepository(conn)
        version_repo = SqliteDocumentTemplateVersionRepository(conn)
        job_repo = SqlitePrintJobRepository(conn)

        template = DocumentTemplate.create(
            document_type=DocumentType.SWEEPSTAKES_TICKET, name="Boleto de sorteo", module="loyalty",
        )
        template_repo.save(template)
        version = DocumentTemplateVersion.create(
            template_id=template.id, content_format=RenderFormat.ESC_POS, content="BOLETO {ticket_number}",
        )
        version_repo.save(version)
        conn.commit()

        job = PrintJob.create(
            document_type=DocumentType.SWEEPSTAKES_TICKET.value, source_module="loyalty",
            source_document_id=new_uuid(), template_version_id=version.id, requested_by_user_id="op-1",
        )
        job_repo.save(job)
        conn.commit()

        reprint = job.create_reprint(requested_by_user_id="op-2", reason="Boleto extraviado")
        job_repo.save(reprint)
        conn.commit()

        fetched = job_repo.get(reprint.id)
        assert fetched.reprint_of_job_id == job.id
        assert fetched.document_type == "SWEEPSTAKES_TICKET"
