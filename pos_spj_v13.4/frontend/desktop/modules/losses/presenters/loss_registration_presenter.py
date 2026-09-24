"""Presentation orchestration for the general loss form."""
from decimal import Decimal
from backend.application.products.queries.product_selection_query_service import ProductSearchQuery
from frontend.desktop.components.search_selector import SearchOption
from backend.application.losses.register_general_loss import EvidenceInput, GeneralLossLineInput, RegisterGeneralLossCommand
from backend.domain.losses.enums import LossOrigin
from backend.shared.ids import new_uuid

class LossRegistrationPresenter:
    def __init__(self, query, use_case, context_provider, product_search=None):
        self._query, self._use_case, self._context_provider = query, use_case, context_provider
        #: Preset canónico de Merma (`SearchWasteEligibleProductsQueryService`).
        #: Antes la búsqueda la hacía el repositorio con SQL propio e inválido.
        self._product_search = product_search
    def search_products(self, query):
        if self._product_search is None:
            return []
        return [SearchOption(dto.product_id, dto.name, dto.code or "")
                for dto in self._product_search.search(ProductSearchQuery(
                    text=(query or "").strip() or None))]
    def product_search_reason(self, query):
        """Por qué no hay productos. Diagnóstico: nunca lanza."""
        if self._product_search is None:
            return None
        try:
            razon = self._product_search.explain_empty(ProductSearchQuery(
                text=(query or "").strip() or None))
        except Exception:
            return None
        return razon.message if razon is not None else None
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
