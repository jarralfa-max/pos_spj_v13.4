"""SET-11 — DocumentTemplate + DocumentTemplateVersion state machine and
template_activation_policy. Pure domain — no DB.
"""

from __future__ import annotations

import pytest

from backend.domain.document_output.entities.document_template import DocumentTemplate
from backend.domain.document_output.entities.document_template_version import DocumentTemplateVersion
from backend.domain.document_output.enums import DocumentType, DocumentTemplateVersionStatus, RenderFormat
from backend.domain.document_output.exceptions import (
    DocumentInvalidValueError,
    TemplateApprovalSegregationError,
    TemplateTransitionNotAllowedError,
)
from backend.domain.document_output.policies.template_activation_policy import activate_version
from backend.shared.ids import is_uuidv7, new_uuid


def _template(**overrides) -> DocumentTemplate:
    kwargs = dict(document_type=DocumentType.SALE_TICKET, name="Ticket de venta", module="sales")
    kwargs.update(overrides)
    return DocumentTemplate.create(**kwargs)


def _version(template_id: str | None = None, **overrides) -> DocumentTemplateVersion:
    kwargs = dict(
        template_id=template_id or new_uuid(), content_format=RenderFormat.ESC_POS, content="<ticket/>",
    )
    kwargs.update(overrides)
    return DocumentTemplateVersion.create(**kwargs)


class TestDocumentTemplateCreate:
    def test_mints_uuidv7_and_trims_fields(self):
        template = _template(name="  Ticket  ", module="  sales  ")
        assert is_uuidv7(template.id)
        assert template.name == "Ticket"
        assert template.module == "sales"
        assert template.active is True

    def test_requires_name(self):
        with pytest.raises(DocumentInvalidValueError):
            _template(name="   ")

    def test_requires_module(self):
        with pytest.raises(DocumentInvalidValueError):
            _template(module="   ")

    def test_activate_deactivate(self):
        template = _template()
        template.deactivate()
        assert template.active is False
        template.activate()
        assert template.active is True


class TestDocumentTemplateUpdateDetails:
    """SET-11 follow-up (2026-08-22) — the UI needs to rename/redescribe
    a registered template family, same gap `Device.rename()`/
    `Workstation.update_details()` closed for their sections."""

    def test_updates_name_module_and_description(self):
        template = _template()
        template.update_details(name="  Ticket v2  ", module="  ventas  ", description="  nuevo  ")
        assert template.name == "Ticket v2"
        assert template.module == "ventas"
        assert template.description == "nuevo"

    def test_clears_description_when_blank(self):
        template = _template()
        template.update_details(name="Ticket", module="sales")
        assert template.description == ""

    def test_requires_name(self):
        template = _template()
        with pytest.raises(DocumentInvalidValueError):
            template.update_details(name="   ", module="sales")

    def test_requires_module(self):
        template = _template()
        with pytest.raises(DocumentInvalidValueError):
            template.update_details(name="Ticket", module="   ")

    def test_allowed_regardless_of_active_status(self):
        template = _template()
        template.deactivate()
        template.update_details(name="Ticket inactivo", module="sales")
        assert template.name == "Ticket inactivo"
        assert template.active is False


class TestDocumentTemplateVersionCreate:
    def test_mints_uuidv7_starts_at_version_1_and_draft(self):
        version = _version()
        assert is_uuidv7(version.id)
        assert version.version == 1
        assert version.status is DocumentTemplateVersionStatus.DRAFT
        assert version.previous_version_id is None

    def test_requires_content(self):
        with pytest.raises(DocumentInvalidValueError):
            _version(content="   ")

    def test_create_next_version_chains_and_increments(self):
        v1 = _version()
        v2 = v1.create_next_version(content="<ticket v2/>")
        assert v2.template_id == v1.template_id
        assert v2.version == 2
        assert v2.previous_version_id == v1.id
        assert v2.status is DocumentTemplateVersionStatus.DRAFT

    def test_create_next_version_requires_content(self):
        v1 = _version()
        with pytest.raises(DocumentInvalidValueError):
            v1.create_next_version(content="   ")


class TestDocumentTemplateVersionLifecycle:
    def test_full_happy_path(self):
        version = _version()
        version.submit_for_approval()
        assert version.status is DocumentTemplateVersionStatus.PENDING_APPROVAL

        version.approve(approved_by_user_id="admin-1")
        assert version.status is DocumentTemplateVersionStatus.APPROVED
        assert version.approved_by_user_id == "admin-1"

        version.activate(activated_by_user_id="admin-1")
        assert version.status is DocumentTemplateVersionStatus.ACTIVE
        assert version.activated_by_user_id == "admin-1"
        assert version.is_active() is True

        version.deactivate()
        assert version.status is DocumentTemplateVersionStatus.INACTIVE
        assert version.is_active() is False

        version.archive()
        assert version.status is DocumentTemplateVersionStatus.ARCHIVED

    def test_active_can_expire_then_archive(self):
        version = _version()
        version.submit_for_approval()
        version.approve(approved_by_user_id="admin-1")
        version.activate(activated_by_user_id="admin-1")
        version.expire()
        assert version.status is DocumentTemplateVersionStatus.EXPIRED
        version.archive()
        assert version.status is DocumentTemplateVersionStatus.ARCHIVED

    def test_reject_returns_to_draft_not_a_terminal_state(self):
        version = _version()
        version.submit_for_approval()
        version.reject(reason="Faltan datos fiscales")
        assert version.status is DocumentTemplateVersionStatus.DRAFT
        assert version.reason == "Faltan datos fiscales"
        # A rejected version can be resubmitted — proves DRAFT isn't dead-ended.
        version.submit_for_approval()
        assert version.status is DocumentTemplateVersionStatus.PENDING_APPROVAL

    def test_reject_requires_reason(self):
        version = _version()
        version.submit_for_approval()
        with pytest.raises(DocumentInvalidValueError):
            version.reject(reason="   ")

    def test_approve_requires_approved_by_user_id(self):
        version = _version()
        version.submit_for_approval()
        with pytest.raises(DocumentInvalidValueError):
            version.approve(approved_by_user_id="")

    def test_activate_requires_activated_by_user_id(self):
        version = _version()
        version.submit_for_approval()
        version.approve(approved_by_user_id="admin-1")
        with pytest.raises(DocumentInvalidValueError):
            version.activate(activated_by_user_id="")

    def test_approve_rejects_same_user_as_creator(self):
        # SET-1 (§59): creator != approver — a second, distinct reviewer
        # is required, same discipline as feature_flag_approval_policy.
        version = _version(created_by_user_id="editor-1")
        version.submit_for_approval()
        with pytest.raises(TemplateApprovalSegregationError):
            version.approve(approved_by_user_id="editor-1")
        assert version.status is DocumentTemplateVersionStatus.PENDING_APPROVAL

    def test_approve_allows_distinct_reviewer(self):
        version = _version(created_by_user_id="editor-1")
        version.submit_for_approval()
        version.approve(approved_by_user_id="reviewer-2")
        assert version.status is DocumentTemplateVersionStatus.APPROVED
        assert version.approved_by_user_id == "reviewer-2"

    def test_approve_allows_same_user_when_creator_unknown(self):
        # No created_by_user_id recorded (legacy/unset) — nothing to
        # segregate against, so approval is not blocked.
        version = _version()
        version.submit_for_approval()
        version.approve(approved_by_user_id="admin-1")
        assert version.status is DocumentTemplateVersionStatus.APPROVED

    @pytest.mark.parametrize(
        "method,kwargs",
        [
            ("submit_for_approval", {}),
            ("approve", {"approved_by_user_id": "admin-1"}),
            ("reject", {"reason": "x"}),
            ("activate", {"activated_by_user_id": "admin-1"}),
            ("deactivate", {}),
            ("expire", {}),
            ("archive", {}),
        ],
    )
    def test_transitions_not_allowed_from_fresh_draft_except_submit(self, method, kwargs):
        version = _version()
        if method == "submit_for_approval":
            version.submit_for_approval()
            return
        with pytest.raises(TemplateTransitionNotAllowedError):
            getattr(version, method)(**kwargs)


class TestTemplateActivationPolicy:
    def _approved(self, template_id: str) -> DocumentTemplateVersion:
        version = _version(template_id=template_id)
        version.submit_for_approval()
        version.approve(approved_by_user_id="admin-1")
        return version

    def test_activates_first_version_with_no_current_active(self):
        template_id = new_uuid()
        version = self._approved(template_id)
        activate_version(version, activated_by_user_id="admin-1")
        assert version.status is DocumentTemplateVersionStatus.ACTIVE

    def test_supersedes_currently_active_version(self):
        template_id = new_uuid()
        v1 = self._approved(template_id)
        activate_version(v1, activated_by_user_id="admin-1")

        v2 = self._approved(template_id)
        activate_version(v2, activated_by_user_id="admin-1", currently_active_version=v1)

        assert v2.status is DocumentTemplateVersionStatus.ACTIVE
        assert v1.status is DocumentTemplateVersionStatus.EXPIRED

    def test_rejects_mismatched_template_id(self):
        v1 = self._approved(new_uuid())
        v2 = self._approved(new_uuid())
        with pytest.raises(DocumentInvalidValueError):
            activate_version(v2, activated_by_user_id="admin-1", currently_active_version=v1)

    def test_rejects_when_new_version_already_active(self):
        template_id = new_uuid()
        version = self._approved(template_id)
        activate_version(version, activated_by_user_id="admin-1")
        with pytest.raises(TemplateTransitionNotAllowedError):
            activate_version(version, activated_by_user_id="admin-1")
