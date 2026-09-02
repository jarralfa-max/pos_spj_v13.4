"""SET-14 — "Label templates" + "Routing": proves label document_types
compose end to end with SET-11's `DocumentTemplate`/`DocumentTemplateVersion`
(unchanged) and SET-12's `ticket_routing_policy.create_routed_print_job`
(unchanged) — labels are documents like any other in this bounded
context, so no new template/routing machinery was needed, only the new
`DocumentType` values (§enums.py) and `RenderFormat.ZPL` (already existed
since SET-11). Pure domain — no DB.
"""

from __future__ import annotations

from backend.domain.document_output.entities.document_template import DocumentTemplate
from backend.domain.document_output.entities.document_template_version import DocumentTemplateVersion
from backend.domain.document_output.enums import DocumentType, RenderFormat
from backend.domain.document_output.policies.template_activation_policy import activate_version
from backend.domain.document_output.policies.ticket_routing_policy import create_routed_print_job
from backend.domain.document_output.value_objects.route_resolution import RouteResolution
from backend.shared.ids import new_uuid


class _FakeResolver:
    def resolve(self, document_type: str, **kwargs) -> RouteResolution:
        return RouteResolution.create(print_route_id=new_uuid(), printer_device_id=new_uuid())


class TestLabelDocumentTemplateLifecycle:
    def test_zpl_label_template_full_happy_path(self):
        template = DocumentTemplate.create(
            document_type=DocumentType.WEIGHT_LABEL, name="Etiqueta de peso variable", module="inventory",
        )
        version = DocumentTemplateVersion.create(
            template_id=template.id, content_format=RenderFormat.ZPL,
            content="^XA^FO50,50^FD{product_name}^FS^XZ",
        )
        version.submit_for_approval()
        version.approve(approved_by_user_id="admin-1")
        activate_version(version, activated_by_user_id="admin-1")
        assert version.is_active()
        assert version.content_format is RenderFormat.ZPL

    def test_every_label_document_type_creates_a_valid_template(self):
        for label_type in (
            DocumentType.LOT_LABEL, DocumentType.WEIGHT_LABEL, DocumentType.TRANSFER_LABEL,
            DocumentType.COUNT_LABEL, DocumentType.ADJUSTMENT_LABEL, DocumentType.PRODUCT_LABEL,
        ):
            template = DocumentTemplate.create(document_type=label_type, name="Etiqueta", module="inventory")
            assert template.document_type is label_type


class TestLabelRoutingReusesTicketRoutingPolicyUnchanged:
    def test_create_routed_print_job_works_for_a_label_document_type(self):
        job = create_routed_print_job(
            _FakeResolver(), document_type=DocumentType.LOT_LABEL.value, source_module="inventory",
            source_document_id=new_uuid(), template_version_id=new_uuid(), requested_by_user_id="op-1",
        )
        assert job.document_type == "LOT_LABEL"
        assert job.print_route_id and job.printer_device_id
