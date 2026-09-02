"""SET-25 follow-up #3 — real CRUD for "Documentos": create a document
template + its first version, create next versions, and drive the full
7-state approval lifecycle. Against a real (in-memory) SQLite born-clean
schema.
"""

from __future__ import annotations

import pytest

from backend.application.use_cases.configuracion.document_template_use_cases import (
    ChangeDocumentTemplateStatusUseCase,
    ChangeTemplateVersionStatusUseCase,
    CreateDocumentTemplateUseCase,
    CreateNextTemplateVersionUseCase,
    DocumentTemplateStatusAction,
    TemplateVersionAction,
    UpdateDocumentTemplateUseCase,
)
from backend.domain.document_output.enums import DocumentTemplateVersionStatus
from backend.domain.document_output.exceptions import (
    DocumentInvalidValueError,
    DocumentTemplateNotFoundError,
    TemplateTransitionNotAllowedError,
    TemplateVersionNotFoundError,
)
from backend.infrastructure.db.repositories.document_output.document_template_repository import (
    SqliteDocumentTemplateRepository,
)
from backend.infrastructure.db.repositories.document_output.document_template_version_repository import (
    SqliteDocumentTemplateVersionRepository,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


def _template_and_v1(conn, **overrides):
    kwargs = dict(
        document_type="SALE_TICKET", name="Ticket de venta estandar", module="ventas",
        content_format="ESC_POS", content="{{items}}", created_by_user_id="admin-1",
    )
    kwargs.update(overrides)
    return CreateDocumentTemplateUseCase(conn).execute(**kwargs)


class TestCreateDocumentTemplateUseCase:
    def test_creates_template_and_first_draft_version(self, conn):
        template, version = _template_and_v1(conn)
        assert template.module == "ventas"
        assert version.version == 1
        assert version.status is DocumentTemplateVersionStatus.DRAFT

    def test_accepts_string_or_enum_types(self, conn):
        from backend.domain.document_output.enums import DocumentType, RenderFormat

        template, version = CreateDocumentTemplateUseCase(conn).execute(
            document_type=DocumentType.LOT_LABEL, name="Etiqueta de lote", module="inventario",
            content_format=RenderFormat.ZPL, content="^XA^FD{{lot}}^FS^XZ",
        )
        assert template.document_type is DocumentType.LOT_LABEL


class TestCreateNextTemplateVersionUseCase:
    def test_chains_from_the_given_version(self, conn):
        template, v1 = _template_and_v1(conn)
        use_case = CreateNextTemplateVersionUseCase(conn)
        v2 = use_case.execute(version_id=v1.id, content="{{items}} v2", created_by_user_id="admin-1")
        assert v2.version == 2
        assert v2.previous_version_id == v1.id
        assert v2.status is DocumentTemplateVersionStatus.DRAFT

    def test_unknown_version_raises(self, conn):
        use_case = CreateNextTemplateVersionUseCase(conn)
        with pytest.raises(TemplateVersionNotFoundError):
            use_case.execute(version_id=new_uuid(), content="x")


class TestChangeTemplateVersionStatusUseCase:
    def test_full_approval_lifecycle(self, conn):
        template, v1 = _template_and_v1(conn)
        use_case = ChangeTemplateVersionStatusUseCase(conn)

        submitted = use_case.execute(version_id=v1.id, action=TemplateVersionAction.SUBMIT_FOR_APPROVAL)
        assert submitted.status is DocumentTemplateVersionStatus.PENDING_APPROVAL

        approved = use_case.execute(
            version_id=v1.id, action=TemplateVersionAction.APPROVE, actor_user_id="admin-2",
        )
        assert approved.status is DocumentTemplateVersionStatus.APPROVED

        activated = use_case.execute(
            version_id=v1.id, action=TemplateVersionAction.ACTIVATE, actor_user_id="admin-2",
        )
        assert activated.status is DocumentTemplateVersionStatus.ACTIVE

        deactivated = use_case.execute(version_id=v1.id, action=TemplateVersionAction.DEACTIVATE)
        assert deactivated.status is DocumentTemplateVersionStatus.INACTIVE

        archived = use_case.execute(version_id=v1.id, action=TemplateVersionAction.ARCHIVE)
        assert archived.status is DocumentTemplateVersionStatus.ARCHIVED

    def test_reject_returns_to_draft_with_reason(self, conn):
        template, v1 = _template_and_v1(conn)
        use_case = ChangeTemplateVersionStatusUseCase(conn)
        use_case.execute(version_id=v1.id, action=TemplateVersionAction.SUBMIT_FOR_APPROVAL)
        rejected = use_case.execute(
            version_id=v1.id, action=TemplateVersionAction.REJECT, reason="Falta el logo",
        )
        assert rejected.status is DocumentTemplateVersionStatus.DRAFT
        assert rejected.reason == "Falta el logo"

    def test_reject_requires_a_reason(self, conn):
        template, v1 = _template_and_v1(conn)
        use_case = ChangeTemplateVersionStatusUseCase(conn)
        use_case.execute(version_id=v1.id, action=TemplateVersionAction.SUBMIT_FOR_APPROVAL)
        with pytest.raises(DocumentInvalidValueError):
            use_case.execute(version_id=v1.id, action=TemplateVersionAction.REJECT, reason="   ")

    def test_activating_a_new_version_deactivates_the_previously_active_one(self, conn):
        template, v1 = _template_and_v1(conn)
        use_case = ChangeTemplateVersionStatusUseCase(conn)
        use_case.execute(version_id=v1.id, action=TemplateVersionAction.SUBMIT_FOR_APPROVAL)
        use_case.execute(version_id=v1.id, action=TemplateVersionAction.APPROVE, actor_user_id="admin-2")
        use_case.execute(version_id=v1.id, action=TemplateVersionAction.ACTIVATE, actor_user_id="admin-2")

        v2 = CreateNextTemplateVersionUseCase(conn).execute(version_id=v1.id, content="v2")
        use_case.execute(version_id=v2.id, action=TemplateVersionAction.SUBMIT_FOR_APPROVAL)
        use_case.execute(version_id=v2.id, action=TemplateVersionAction.APPROVE, actor_user_id="admin-2")
        use_case.execute(version_id=v2.id, action=TemplateVersionAction.ACTIVATE, actor_user_id="admin-2")

        version_repo = SqliteDocumentTemplateVersionRepository(conn)
        assert version_repo.get(v1.id).status is DocumentTemplateVersionStatus.INACTIVE
        assert version_repo.get(v2.id).status is DocumentTemplateVersionStatus.ACTIVE

    def test_cannot_activate_before_approval(self, conn):
        template, v1 = _template_and_v1(conn)
        use_case = ChangeTemplateVersionStatusUseCase(conn)
        with pytest.raises(TemplateTransitionNotAllowedError):
            use_case.execute(version_id=v1.id, action=TemplateVersionAction.ACTIVATE, actor_user_id="admin-2")

    def test_unknown_version_raises(self, conn):
        use_case = ChangeTemplateVersionStatusUseCase(conn)
        with pytest.raises(TemplateVersionNotFoundError):
            use_case.execute(version_id=new_uuid(), action=TemplateVersionAction.SUBMIT_FOR_APPROVAL)


class TestUpdateDocumentTemplateUseCase:
    """SET-11 follow-up — `DocumentTemplate.update_details()` had no use
    case at all before this; a template family could never be renamed
    or redescribed after creation."""

    def test_updates_name_module_and_description(self, conn):
        template, _v1 = _template_and_v1(conn)
        use_case = UpdateDocumentTemplateUseCase(conn)
        updated = use_case.execute(
            template_id=template.id, name="Ticket de venta (v2)", module="ventas",
            description="Nueva descripción",
        )
        assert updated.name == "Ticket de venta (v2)"
        assert updated.description == "Nueva descripción"
        fetched = SqliteDocumentTemplateRepository(conn).get(template.id)
        assert fetched.name == "Ticket de venta (v2)"

    def test_unknown_template_raises(self, conn):
        use_case = UpdateDocumentTemplateUseCase(conn)
        with pytest.raises(DocumentTemplateNotFoundError):
            use_case.execute(template_id=new_uuid(), name="X", module="ventas")

    def test_requires_name_and_module(self, conn):
        template, _v1 = _template_and_v1(conn)
        use_case = UpdateDocumentTemplateUseCase(conn)
        with pytest.raises(DocumentInvalidValueError):
            use_case.execute(template_id=template.id, name="   ", module="ventas")


class TestChangeDocumentTemplateStatusUseCase:
    """SET-11 follow-up — `DocumentTemplate.activate()`/`deactivate()`
    (the whole family, not one version's content) existed since the
    original cut but were never wired to any use case."""

    def test_deactivate_and_activate(self, conn):
        template, _v1 = _template_and_v1(conn)
        use_case = ChangeDocumentTemplateStatusUseCase(conn)

        deactivated = use_case.execute(
            template_id=template.id, action=DocumentTemplateStatusAction.DEACTIVATE,
        )
        assert deactivated.active is False

        activated = use_case.execute(
            template_id=template.id, action=DocumentTemplateStatusAction.ACTIVATE,
        )
        assert activated.active is True

    def test_deactivating_a_template_does_not_touch_its_versions(self, conn):
        # Family-level active/inactive is orthogonal to a version's own
        # approval-lifecycle status.
        template, v1 = _template_and_v1(conn)
        ChangeDocumentTemplateStatusUseCase(conn).execute(
            template_id=template.id, action=DocumentTemplateStatusAction.DEACTIVATE,
        )
        fetched_version = SqliteDocumentTemplateVersionRepository(conn).get(v1.id)
        assert fetched_version.status is DocumentTemplateVersionStatus.DRAFT

    def test_unknown_template_raises(self, conn):
        use_case = ChangeDocumentTemplateStatusUseCase(conn)
        with pytest.raises(DocumentTemplateNotFoundError):
            use_case.execute(template_id=new_uuid(), action=DocumentTemplateStatusAction.DEACTIVATE)
