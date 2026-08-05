"""Presentation orchestration for the general loss form."""
from decimal import Decimal
from frontend.desktop.components.search_selector import SearchOption
from backend.application.losses.register_general_loss import EvidenceInput, GeneralLossLineInput, RegisterGeneralLossCommand
from backend.domain.losses.enums import LossOrigin
from backend.shared.ids import new_uuid

class LossRegistrationPresenter:
    def __init__(self, query, use_case, context_provider):
        self._query, self._use_case, self._context_provider = query, use_case, context_provider
    def search_products(self, query):
        return [SearchOption(str(r[0]), str(r[1]), str(r[2] or "")) for r in self._query.search_products(query)]
    def search_lots(self, product_id, query):
        return [] if not product_id else [SearchOption(str(r[0]), str(r[1]), str(r[2] or "")) for r in self._query.search_lots(product_id, query)]
    def classifications(self):
        return [(str(r[0]), str(r[1])) for r in self._query.classifications()]
    def reasons(self, classification_id):
        return [(str(r[0]), str(r[1]), bool(r[2])) for r in self._query.reasons(classification_id)]
    def register(self, *, warehouse_id: str, classification_id: str, reason_id: str,
                 origin: str, product_id: str, lot_id: str | None,
                 quantity: Decimal, weight: Decimal, unit: str,
                 evidence_path: str, notes: str, submit: bool):
        return self._use_case.execute(RegisterGeneralLossCommand(
            operation_id=new_uuid(), context=self._context_provider(), warehouse_id=warehouse_id,
            classification_id=classification_id, reason_id=reason_id, origin=LossOrigin(origin),
            lines=(GeneralLossLineInput(product_id=product_id, lot_id=lot_id,
                                        quantity=quantity, weight=weight, unit=unit),),
            evidence=(EvidenceInput(evidence_path),) if evidence_path else (),
            notes=notes, submit=submit))
