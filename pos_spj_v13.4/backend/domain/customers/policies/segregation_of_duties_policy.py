"""CustomerSegregationOfDutiesPolicy — keep conflicting Customer/CRM duties
apart (§73). Pure domain logic (no I/O), mirrors
backend/domain/inventory/policies/segregation_of_duties_policy.py.

Each method encodes one non-negotiable separation from the master prompt:

- who requests credit does not approve their own request;
- who proposes a customer merge does not approve it alone;
- who submits a sensitive import does not approve it alone;
- who reassigns a customer's ownership/portfolio must justify it;
- who exports sensitive data must leave evidence (a reason).

Not encoded here (no actor-pair to compare, just distinct permission codes
doing the separating): "quien administra permisos no obtiene acceso a datos
sensibles por defecto" and "quien configura pipelines no puede marcar
oportunidades ganadas sin permiso" — those are permission-catalog design
choices (see CustomerPermissions/CRMPermissions), not runtime SoD checks.
"""

from __future__ import annotations

from backend.domain.customers.exceptions import CustomerSegregationOfDutiesError


class CustomerSegregationOfDutiesPolicy:
    def enforce_credit_requester_not_self_approving(
        self, requested_by: str, approved_by: str
    ) -> None:
        if requested_by and requested_by == approved_by:
            raise CustomerSegregationOfDutiesError(
                "Quien solicita crédito no puede aprobar su propia solicitud")

    def enforce_merge_proposer_not_self_approving(
        self, proposed_by: str, approved_by: str
    ) -> None:
        if proposed_by and proposed_by == approved_by:
            raise CustomerSegregationOfDutiesError(
                "Quien propone una fusión de clientes no puede aprobarla solo")

    def enforce_sensitive_import_approver_distinct(
        self, submitted_by: str, approved_by: str, *, is_sensitive: bool
    ) -> None:
        if is_sensitive and submitted_by and submitted_by == approved_by:
            raise CustomerSegregationOfDutiesError(
                "Quien importa clientes no puede aprobar una importación sensible")

    def enforce_ownership_reassignment_justified(self, reason: str) -> None:
        if not (reason or "").strip():
            raise CustomerSegregationOfDutiesError(
                "Reasignar cartera/propietario requiere un motivo")

    def enforce_sensitive_export_evidenced(self, reason: str) -> None:
        if not (reason or "").strip():
            raise CustomerSegregationOfDutiesError(
                "Exportar datos sensibles requiere dejar evidencia (motivo)")

    def enforce_anonymization_preserves_audit(self, audit_retained: bool) -> None:
        if not audit_retained:
            raise CustomerSegregationOfDutiesError(
                "La anonimización no puede eliminar el rastro de auditoría")
