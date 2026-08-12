"""Entities for the Customer Service (atención al cliente) bounded context
(CRM-7).

``CustomerServiceCase`` is the aggregate root. ``ServiceCaseCategory`` is a
configurable classification catalog (mirrors CRMStageDefinition — data, not
a hardcoded enum). ``ServiceCaseResolution`` is the evidence a resolution
leaves behind (mirrors LeadQualification's split from Lead). ``ServiceCase
Escalation`` is an immutable history row per escalation event (mirrors
OpportunityStageHistory). ``ServiceLevelPolicy``/``SLAInstance`` implement
§30-32's SLA tracking.

§30-32 also names ``ServiceCaseActivity`` as a fourth core entity — that is
NOT a new class here. It is ``backend.domain.crm.entities.crm_activity.
CRMActivity`` linked via ``related_entity_type=CRMRelatedEntityType.CASE``,
the exact reuse CRM-6 reserved that enum value for. A parallel
"ServiceCaseActivity" table would just duplicate CRMActivity for no
differentiating reason — the same call CRM-6 already made for
CRMInteraction.
"""
