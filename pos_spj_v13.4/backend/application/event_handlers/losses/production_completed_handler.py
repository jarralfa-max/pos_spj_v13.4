"""MEAT_PRODUCTION_COMPLETED → canonical production loss analysis."""
from decimal import Decimal

from backend.application.losses.production_loss import (
    AnalyzeProductionLossCommand, ProductionOutputInput,
)


class ProductionCompletedLossHandler:
    event_name = "MEAT_PRODUCTION_COMPLETED"

    def __init__(self, service, context_provider):
        self._service = service
        self._context_provider = context_provider

    def handle(self, payload: dict):
        context = self._context_provider()
        outputs = tuple(ProductionOutputInput(
            product_id=str(row["product_id"]),
            weight=Decimal(str(row.get("weight") or row.get("weight_kg") or "0")),
            lot_id=row.get("lot_id"), output_type=row.get("output_type", "MAIN_PRODUCT"),
            quantity=Decimal(str(row.get("quantity") or row.get("pieces") or "0")),
            species_id=row.get("species_id"),
            cut_classification_id=row.get("cut_classification_id"),
            measure_kind=row.get("measure_kind", "BY_WEIGHT"))
            for row in payload.get("outputs", ()))
        return self._service.execute(AnalyzeProductionLossCommand(
            operation_id=str(payload["operation_id"]),
            production_id=str(payload.get("production_id") or payload["entity_id"]),
            recipe_version_id=str(payload["recipe_version_id"]),
            yield_profile_version_id=str(payload["yield_profile_version_id"]),
            input_product_id=str(payload["input_product_id"]),
            input_weight=Decimal(str(payload["input_weight"])), outputs=outputs,
            context=context, warehouse_id=str(payload["warehouse_id"]),
            cutting_scheme_version_id=payload.get("cutting_scheme_version_id")))
