"""SET-11 — Document Output infrastructure repositories against a real
(in-memory) SQLite born-clean schema (migration 214).
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.domain.device_management.entities.device import Device
from backend.domain.device_management.entities.device_profile import DeviceProfile
from backend.domain.device_management.entities.print_route import PrintRoute
from backend.domain.device_management.enums import ConnectionType, DeviceType
from backend.domain.device_management.value_objects.connection_profile import ConnectionProfile
from backend.domain.document_output.entities.document_template import DocumentTemplate
from backend.domain.document_output.entities.document_template_version import DocumentTemplateVersion
from backend.domain.document_output.entities.print_job import PrintJob
from backend.domain.document_output.enums import DocumentType, PrintJobStatus, RenderFormat
from backend.domain.document_output.policies.template_activation_policy import activate_version
from backend.infrastructure.db.repositories.device_management.device_profile_repository import (
    SqliteDeviceProfileRepository,
)
from backend.infrastructure.db.repositories.device_management.device_repository import (
    SqliteDeviceRepository,
)
from backend.infrastructure.db.repositories.device_management.print_route_repository import (
    SqlitePrintRouteRepository,
)
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


@pytest.fixture
def template_repo(conn):
    return SqliteDocumentTemplateRepository(conn)


@pytest.fixture
def version_repo(conn):
    return SqliteDocumentTemplateVersionRepository(conn)


@pytest.fixture
def job_repo(conn):
    return SqlitePrintJobRepository(conn)


def _existing_branch_id(conn) -> str:
    branch_id = new_uuid()
    conn.execute("INSERT INTO sucursales (id, nombre) VALUES (?, ?)", (branch_id, "Sucursal de prueba"))
    return branch_id


def _existing_device(conn) -> Device:
    branch_id = _existing_branch_id(conn)
    profile = DeviceProfile.create(
        name="Impresora térmica", device_type=DeviceType.THERMAL_PRINTER,
        connection_profile=ConnectionProfile.create(ConnectionType.USB),
    )
    SqliteDeviceProfileRepository(conn).save(profile)
    device = Device.create(branch_id=branch_id, profile_id=profile.id, code="PRN-01", name="Impresora 1")
    SqliteDeviceRepository(conn).save(device)
    conn.commit()
    return device


class TestDocumentTemplateRepository:
    def test_save_get_roundtrip(self, conn, template_repo):
        template = DocumentTemplate.create(
            document_type=DocumentType.SALE_TICKET, name="Ticket de venta", module="sales",
        )
        template_repo.save(template)
        conn.commit()

        fetched = template_repo.get(template.id)
        assert fetched.id == template.id
        assert fetched.document_type == DocumentType.SALE_TICKET
        assert fetched.name == "Ticket de venta"
        assert fetched.module == "sales"
        assert fetched.active is True

    def test_upsert_updates_in_place(self, conn, template_repo):
        template = DocumentTemplate.create(
            document_type=DocumentType.SALE_TICKET, name="Ticket", module="sales",
        )
        template_repo.save(template)
        conn.commit()

        template.deactivate()
        template_repo.save(template)
        conn.commit()

        assert template_repo.get(template.id).active is False

    def test_list_by_document_type_and_list_active(self, conn, template_repo):
        ticket = DocumentTemplate.create(
            document_type=DocumentType.SALE_TICKET, name="Ticket", module="sales",
        )
        quote = DocumentTemplate.create(document_type=DocumentType.QUOTE, name="Cotización", module="sales")
        inactive_ticket = DocumentTemplate.create(
            document_type=DocumentType.SALE_TICKET, name="Ticket viejo", module="sales",
        )
        inactive_ticket.deactivate()
        for t in (ticket, quote, inactive_ticket):
            template_repo.save(t)
        conn.commit()

        by_type = template_repo.list_by_document_type(DocumentType.SALE_TICKET)
        assert {t.id for t in by_type} == {ticket.id, inactive_ticket.id}

        active = template_repo.list_active()
        assert ticket.id in {t.id for t in active}
        assert inactive_ticket.id not in {t.id for t in active}


class TestDocumentTemplateVersionRepository:
    def test_save_get_roundtrip(self, conn, template_repo, version_repo):
        template = DocumentTemplate.create(
            document_type=DocumentType.SALE_TICKET, name="Ticket", module="sales",
        )
        template_repo.save(template)
        conn.commit()

        version = DocumentTemplateVersion.create(
            template_id=template.id, content_format=RenderFormat.ESC_POS, content="<ticket/>",
            created_by_user_id="admin-1",
        )
        version_repo.save(version)
        conn.commit()

        fetched = version_repo.get(version.id)
        assert fetched.template_id == template.id
        assert fetched.version == 1
        assert fetched.content_format is RenderFormat.ESC_POS
        assert fetched.content == "<ticket/>"

    def test_list_for_template_ordered_by_version(self, conn, template_repo, version_repo):
        template = DocumentTemplate.create(
            document_type=DocumentType.SALE_TICKET, name="Ticket", module="sales",
        )
        template_repo.save(template)
        conn.commit()

        v1 = DocumentTemplateVersion.create(
            template_id=template.id, content_format=RenderFormat.ESC_POS, content="v1",
        )
        version_repo.save(v1)
        conn.commit()
        v2 = v1.create_next_version(content="v2")
        version_repo.save(v2)
        conn.commit()

        versions = version_repo.list_for_template(template.id)
        assert [v.version for v in versions] == [1, 2]

    def test_get_active_for_template_and_supersession_via_policy(self, conn, template_repo, version_repo):
        template = DocumentTemplate.create(
            document_type=DocumentType.SALE_TICKET, name="Ticket", module="sales",
        )
        template_repo.save(template)
        conn.commit()

        v1 = DocumentTemplateVersion.create(
            template_id=template.id, content_format=RenderFormat.ESC_POS, content="v1",
        )
        v1.submit_for_approval()
        v1.approve(approved_by_user_id="admin-1")
        activate_version(v1, activated_by_user_id="admin-1")
        version_repo.save(v1)
        conn.commit()

        assert version_repo.get_active_for_template(template.id).id == v1.id

        v2 = v1.create_next_version(content="v2")
        v2.submit_for_approval()
        v2.approve(approved_by_user_id="admin-1")
        activate_version(v2, activated_by_user_id="admin-1", currently_active_version=v1)
        version_repo.save(v1)
        version_repo.save(v2)
        conn.commit()

        active = version_repo.get_active_for_template(template.id)
        assert active.id == v2.id

    def test_unique_index_blocks_two_active_versions_for_same_template(self, conn, template_repo, version_repo):
        template = DocumentTemplate.create(
            document_type=DocumentType.SALE_TICKET, name="Ticket", module="sales",
        )
        template_repo.save(template)
        conn.commit()

        def _active_version(content: str) -> DocumentTemplateVersion:
            version = DocumentTemplateVersion.create(
                template_id=template.id, content_format=RenderFormat.ESC_POS, content=content,
            )
            version.submit_for_approval()
            version.approve(approved_by_user_id="admin-1")
            version.activate(activated_by_user_id="admin-1")
            return version

        version_repo.save(_active_version("v1"))
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            version_repo.save(_active_version("v2-not-superseding-v1"))
            conn.commit()
        conn.rollback()


class TestPrintJobRepository:
    def _active_version(self, conn, template_repo, version_repo) -> DocumentTemplateVersion:
        template = DocumentTemplate.create(
            document_type=DocumentType.SALE_TICKET, name="Ticket", module="sales",
        )
        template_repo.save(template)
        conn.commit()
        version = DocumentTemplateVersion.create(
            template_id=template.id, content_format=RenderFormat.ESC_POS, content="<ticket/>",
        )
        version.submit_for_approval()
        version.approve(approved_by_user_id="admin-1")
        version.activate(activated_by_user_id="admin-1")
        version_repo.save(version)
        conn.commit()
        return version

    def test_save_get_roundtrip(self, conn, template_repo, version_repo, job_repo):
        version = self._active_version(conn, template_repo, version_repo)
        job = PrintJob.create(
            document_type="sale_ticket", source_module="sales", source_document_id=new_uuid(),
            template_version_id=version.id, requested_by_user_id="cashier-1",
        )
        job_repo.save(job)
        conn.commit()

        fetched = job_repo.get(job.id)
        assert fetched.id == job.id
        assert fetched.status is PrintJobStatus.PENDING
        assert fetched.template_version_id == version.id

    def test_save_persists_lifecycle_transitions(self, conn, template_repo, version_repo, job_repo):
        version = self._active_version(conn, template_repo, version_repo)
        device = _existing_device(conn)
        route = PrintRoute.create(document_type="SALE_TICKET", primary_device_id=device.id)
        SqlitePrintRouteRepository(conn).save(route)
        conn.commit()

        job = PrintJob.create(
            document_type="sale_ticket", source_module="sales", source_document_id=new_uuid(),
            template_version_id=version.id, requested_by_user_id="cashier-1",
        )
        job_repo.save(job)
        conn.commit()

        job.start_rendering()
        job.mark_ready()
        job.assign_route(print_route_id=route.id, printer_device_id=device.id)
        job.start_printing()
        job.mark_printed()
        job_repo.save(job)
        conn.commit()

        fetched = job_repo.get(job.id)
        assert fetched.status is PrintJobStatus.PRINTED
        assert fetched.printer_device_id == device.id
        assert fetched.printed_at is not None

    def test_list_by_status(self, conn, template_repo, version_repo, job_repo):
        version = self._active_version(conn, template_repo, version_repo)

        pending = PrintJob.create(
            document_type="sale_ticket", source_module="sales", source_document_id=new_uuid(),
            template_version_id=version.id, requested_by_user_id="cashier-1",
        )
        rendering = PrintJob.create(
            document_type="sale_ticket", source_module="sales", source_document_id=new_uuid(),
            template_version_id=version.id, requested_by_user_id="cashier-1",
        )
        rendering.start_rendering()
        job_repo.save(pending)
        job_repo.save(rendering)
        conn.commit()

        pending_jobs = job_repo.list_by_status(PrintJobStatus.PENDING)
        assert {j.id for j in pending_jobs} == {pending.id}
        rendering_jobs = job_repo.list_by_status(PrintJobStatus.RENDERING)
        assert {j.id for j in rendering_jobs} == {rendering.id}

    def test_get_by_operation_id_is_idempotency_key_not_a_domain_field(
        self, conn, template_repo, version_repo, job_repo,
    ):
        version = self._active_version(conn, template_repo, version_repo)
        job = PrintJob.create(
            document_type="sale_ticket", source_module="sales", source_document_id=new_uuid(),
            template_version_id=version.id, requested_by_user_id="cashier-1",
        )
        operation_id = new_uuid()
        job_repo.save(job, operation_id=operation_id)
        conn.commit()

        fetched = job_repo.get_by_operation_id(operation_id)
        assert fetched.id == job.id
        assert job_repo.get_by_operation_id(new_uuid()) is None

    def test_operation_id_unique_index_prevents_duplicate_job_for_same_operation(
        self, conn, template_repo, version_repo, job_repo,
    ):
        version = self._active_version(conn, template_repo, version_repo)
        operation_id = new_uuid()
        first = PrintJob.create(
            document_type="sale_ticket", source_module="sales", source_document_id=new_uuid(),
            template_version_id=version.id, requested_by_user_id="cashier-1",
        )
        job_repo.save(first, operation_id=operation_id)
        conn.commit()

        second = PrintJob.create(
            document_type="sale_ticket", source_module="sales", source_document_id=new_uuid(),
            template_version_id=version.id, requested_by_user_id="cashier-1",
        )
        with pytest.raises(sqlite3.IntegrityError):
            job_repo.save(second, operation_id=operation_id)
            conn.commit()
        conn.rollback()

    def test_list_by_source_orders_most_recent_first(self, conn, template_repo, version_repo, job_repo):
        version = self._active_version(conn, template_repo, version_repo)
        sale_id = new_uuid()
        other_sale_id = new_uuid()
        first = PrintJob.create(
            document_type="sale_ticket", source_module="sales", source_document_id=sale_id,
            template_version_id=version.id, requested_by_user_id="cashier-1",
        )
        job_repo.save(first)
        conn.commit()
        second = first.create_reprint(requested_by_user_id="cashier-2", reason="Ticket dañado")
        job_repo.save(second)
        unrelated = PrintJob.create(
            document_type="sale_ticket", source_module="sales", source_document_id=other_sale_id,
            template_version_id=version.id, requested_by_user_id="cashier-1",
        )
        job_repo.save(unrelated)
        conn.commit()

        results = job_repo.list_by_source("sales", sale_id)
        assert [j.id for j in results] == [second.id, first.id]
        assert job_repo.list_by_source("sales", new_uuid()) == []

    def test_create_reprint_persists_as_independent_job(self, conn, template_repo, version_repo, job_repo):
        version = self._active_version(conn, template_repo, version_repo)
        original = PrintJob.create(
            document_type="sale_ticket", source_module="sales", source_document_id=new_uuid(),
            template_version_id=version.id, requested_by_user_id="cashier-1",
        )
        job_repo.save(original)
        conn.commit()

        reprint = original.create_reprint(requested_by_user_id="cashier-2", reason="Ticket dañado")
        job_repo.save(reprint)
        conn.commit()

        fetched = job_repo.get(reprint.id)
        assert fetched.reprint_of_job_id == original.id
        assert fetched.reprint_reason == "Ticket dañado"
        assert job_repo.get(original.id).status is PrintJobStatus.PENDING
