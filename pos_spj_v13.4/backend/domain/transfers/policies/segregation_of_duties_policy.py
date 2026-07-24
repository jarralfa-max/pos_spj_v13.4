"""Pure segregation rules for transfer custody and sensitive decisions."""
from ..exceptions import SegregationOfDutiesError


class TransferSegregationOfDutiesPolicy:
    def requester_cannot_approve(self, requester_id: str, approver_id: str, *, elevated: bool) -> None:
        if elevated and requester_id and requester_id == approver_id:
            raise SegregationOfDutiesError("El solicitante no puede aprobar su propia transferencia elevada")

    def dispatcher_cannot_receive(self, dispatcher_id: str, receiver_id: str) -> None:
        if dispatcher_id and dispatcher_id == receiver_id:
            raise SegregationOfDutiesError("Quien despacha no puede confirmar la recepción")

    def difference_reporter_cannot_resolve(self, reporter_id: str, resolver_id: str, *, critical: bool) -> None:
        if critical and reporter_id and reporter_id == resolver_id:
            raise SegregationOfDutiesError("Quien reporta una diferencia crítica no puede resolverla solo")

    def custody_handover_requires_distinct_parties(self, delivered_by: str, received_by: str) -> None:
        if delivered_by and delivered_by == received_by:
            raise SegregationOfDutiesError("La entrega y recepción de custodia requieren usuarios distintos")

    def reversal_requires_independent_authorizer(self, requested_by: str, authorized_by: str) -> None:
        if not authorized_by or requested_by == authorized_by:
            raise SegregationOfDutiesError("La reversión requiere una autorización independiente")
