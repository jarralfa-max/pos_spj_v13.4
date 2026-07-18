"""SegregationOfDutiesPolicy — keep conflicting inventory duties apart (§47).

Pure domain logic (no I/O). Each method encodes one non-negotiable separation:

- who counts does not approve their own critical variance;
- who dispatches does not confirm the destination receipt;
- who creates a high adjustment does not approve it;
- who blocks for quality does not release it when policy forbids self-release;
- who modifies an approved transfer must justify it;
- who captures a manual weight out of tolerance needs a distinct authorizer.
"""

from __future__ import annotations

from backend.domain.inventory.exceptions import SegregationOfDutiesError


class SegregationOfDutiesPolicy:
    def enforce_counter_not_self_approving_critical(
        self, counter_id: str, approver_id: str, *, is_critical: bool
    ) -> None:
        if is_critical and counter_id and counter_id == approver_id:
            raise SegregationOfDutiesError(
                "Quien realiza el conteo no puede aprobar su propia diferencia crítica")

    def enforce_dispatcher_not_receiver(
        self, dispatcher_id: str, receiver_id: str
    ) -> None:
        if dispatcher_id and dispatcher_id == receiver_id:
            raise SegregationOfDutiesError(
                "Quien despacha no puede confirmar la recepción en destino")

    def enforce_adjustment_creator_not_self_approving(
        self, creator_id: str, approver_id: str, *, requires_approval: bool
    ) -> None:
        if requires_approval and creator_id and creator_id == approver_id:
            raise SegregationOfDutiesError(
                "Quien crea un ajuste elevado no puede aprobarlo")

    def enforce_quality_blocker_not_releaser(
        self, blocker_id: str, releaser_id: str, *, self_release_forbidden: bool
    ) -> None:
        if self_release_forbidden and blocker_id and blocker_id == releaser_id:
            raise SegregationOfDutiesError(
                "Quien bloquea por calidad no puede liberar el mismo lote")

    def enforce_transfer_modification_justified(self, justification: str) -> None:
        if not (justification or "").strip():
            raise SegregationOfDutiesError(
                "Modificar una transferencia aprobada requiere justificación")

    def enforce_manual_weight_authorized(
        self, capturer_id: str, authorizer_id: str, *, within_tolerance: bool
    ) -> None:
        if within_tolerance:
            return
        if not authorizer_id or authorizer_id == capturer_id:
            raise SegregationOfDutiesError(
                "La captura manual de peso fuera de tolerancia requiere un "
                "autorizador distinto")
