from __future__ import annotations


class ApproveDeliveryAdjustmentUseCase:
    """Adapter use case for customer adjustment responses.

    The current production flow is implemented in whatsapp_service.erp.adjustment_approval
    because WhatsApp runs as a separate process. This use case provides the
    application-layer entry point expected by Delivery without importing PyQt/UI.
    """

    def __init__(self, approval_service) -> None:
        self.approval_service = approval_service

    def execute(self, phone: str, accepted: bool):
        return self.approval_service.respond_latest_for_phone(phone, accepted=accepted)
