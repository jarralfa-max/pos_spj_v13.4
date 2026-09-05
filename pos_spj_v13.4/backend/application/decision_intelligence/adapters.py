"""Adapters: forecasting-domain recommendation → `BusinessRecommendation`
(§37, BI-18).

Pure functions, no I/O. Each preserves every field needed for §40
explainability in `evidence` (stringified — `BusinessRecommendation.evidence`
is `dict[str, str]`, a display/audit shape, not something recomputed from).
`model_reference` names the service that produced the source recommendation
so a reviewer can trace back to exactly which algorithm ran; none of these 4
carry a `rule_reference` (that field is for the future threshold-rule alert
engine, BI-20).

Not every source status/type has a sensible unified mapping — see the
`Unsupported...` raises below for the deliberately-excluded cases (a "hold
price"/"needs review" outcome is informational, not something that needs an
approval workflow).
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.decision_intelligence.enums import (
    BusinessRecommendationType,
    RecommendationStatus,
)
from backend.domain.decision_intelligence.exceptions import (
    UnsupportedRecommendationSourceError,
)
from backend.domain.decision_intelligence.value_objects.business_recommendation import (
    BusinessRecommendation,
)
from backend.domain.forecasting.enums import PriceRecommendationType, RecommendationPriority
from backend.domain.forecasting.value_objects.branch_recommendation import (
    BranchRecommendation,
    BranchRecommendationType,
    StockTransferRecommendation,
)
from backend.domain.forecasting.value_objects.price_recommendation import PriceRecommendation
from backend.domain.forecasting.value_objects.production_recommendation import (
    ProductionRecommendation,
)
from backend.domain.forecasting.value_objects.purchase_recommendation import (
    PurchaseRecommendation,
)
from backend.shared.ids import new_uuid


def from_purchase_recommendation(rec: PurchaseRecommendation) -> BusinessRecommendation:
    evidence = {
        "suggested_quantity": str(rec.suggested_quantity),
        "current_stock": str(rec.current_stock),
        "incoming_stock": str(rec.incoming_stock),
        "safety_stock": str(rec.safety_stock),
        "supplier_lead_time_days": str(rec.supplier_lead_time_days),
        "coverage_days": str(rec.coverage_days),
        "expected_demand": str(rec.expected_demand),
    }
    if rec.estimated_cost is not None:
        evidence["estimated_cost"] = str(rec.estimated_cost)
    return BusinessRecommendation(
        id=new_uuid(),
        recommendation_type=BusinessRecommendationType.PURCHASE_MORE,
        target_type="product", target_id=rec.product_id, branch_id=rec.branch_id,
        title=f"Comprar {rec.suggested_quantity} unidades de {rec.product_id}",
        summary=(
            f"El inventario proyectado de {rec.product_id} cruza el punto de reorden; "
            f"se sugiere comprar {rec.suggested_quantity} unidades para cubrir "
            f"{rec.coverage_days} días."
        ),
        evidence=evidence,
        expected_impact=f"Cobertura de inventario de {rec.coverage_days} días tras la compra",
        confidence=rec.confidence, priority=rec.priority, status=RecommendationStatus.NEW,
        valid_from=rec.created_at.date(), valid_until=rec.valid_until, created_at=rec.created_at,
        model_reference="forecasting.purchase_planning_service",
    )


def from_production_recommendation(rec: ProductionRecommendation) -> BusinessRecommendation:
    evidence = {
        "recommended_production_quantity": str(rec.recommended_production_quantity),
        "recommended_processing_date": rec.recommended_processing_date.isoformat(),
        "current_stock": str(rec.current_stock),
        "expected_demand": str(rec.expected_demand),
    }
    if rec.expected_yield_pct is not None:
        evidence["expected_yield_pct"] = str(rec.expected_yield_pct)
    if rec.required_raw_material is not None:
        evidence["required_raw_material"] = str(rec.required_raw_material)
    if rec.capacity_utilization_pct is not None:
        evidence["capacity_utilization_pct"] = str(rec.capacity_utilization_pct)
    return BusinessRecommendation(
        id=new_uuid(),
        recommendation_type=BusinessRecommendationType.INCREASE_PRODUCTION,
        target_type="product", target_id=rec.product_id, branch_id=rec.branch_id,
        title=f"Producir {rec.recommended_production_quantity} unidades de {rec.product_id}",
        summary=(
            f"El inventario proyectado de {rec.product_id} cruza el punto de reorden; "
            f"se sugiere producir {rec.recommended_production_quantity} unidades para "
            f"el {rec.recommended_processing_date.isoformat()}."
        ),
        evidence=evidence,
        expected_impact=f"Cubre la demanda proyectada de {rec.expected_demand} unidades",
        confidence=rec.confidence, priority=rec.priority, status=RecommendationStatus.NEW,
        valid_from=rec.created_at.date(), valid_until=rec.valid_until, created_at=rec.created_at,
        model_reference="forecasting.production_planning_service",
    )


_PRICE_TYPE_MAP = {
    PriceRecommendationType.INCREASE_PRICE: BusinessRecommendationType.PRICE_INCREASE,
    PriceRecommendationType.DECREASE_PRICE: BusinessRecommendationType.PRICE_DECREASE,
}


def _priority_from_confidence(confidence: Decimal) -> RecommendationPriority:
    """`PriceRecommendation` (BI-16) has no `priority` field of its own —
    unlike the other 3 source types — so the unified wrapper derives one
    from confidence, using the same bucket boundaries BI-16's
    `_CONFIDENCE_BY_ESTIMATE` already established (LOW=0, MEDIUM=0.5, HIGH=0.9)."""
    if confidence >= Decimal("0.9"):
        return RecommendationPriority.HIGH
    if confidence >= Decimal("0.5"):
        return RecommendationPriority.MEDIUM
    return RecommendationPriority.LOW


def from_price_recommendation(rec: PriceRecommendation) -> BusinessRecommendation:
    business_type = _PRICE_TYPE_MAP.get(rec.recommendation_type)
    if business_type is None:
        raise UnsupportedRecommendationSourceError(
            f"PriceRecommendationType.{rec.recommendation_type.value} is informational "
            "(hold/review), not promoted to a BusinessRecommendation approval workflow"
        )
    evidence = {"current_price": str(rec.current_price), "suggested_price": str(rec.suggested_price)}
    for key, value in (
        ("expected_volume_change_pct", rec.expected_volume_change_pct),
        ("expected_margin_change_pct", rec.expected_margin_change_pct),
        ("expected_revenue_change_pct", rec.expected_revenue_change_pct),
    ):
        if value is not None:
            evidence[key] = str(value)
    return BusinessRecommendation(
        id=new_uuid(),
        recommendation_type=business_type,
        target_type="product", target_id=rec.product_id, branch_id=rec.branch_id,
        title=f"{rec.recommendation_type.value} — {rec.product_id}: "
              f"{rec.current_price} → {rec.suggested_price}",
        summary=rec.reason,
        evidence=evidence,
        expected_impact=(
            f"Ingreso esperado: {rec.expected_revenue_change_pct}%"
            if rec.expected_revenue_change_pct is not None else "N/D"
        ),
        confidence=rec.confidence,
        priority=_priority_from_confidence(rec.confidence),
        status=RecommendationStatus.NEW,
        valid_from=rec.created_at.date(), valid_until=rec.valid_until, created_at=rec.created_at,
        model_reference="forecasting.pricing_intelligence_service",
    )


_BRANCH_TYPE_MAP = {
    BranchRecommendationType.INCREASE_STOCK: BusinessRecommendationType.PURCHASE_MORE,
    BranchRecommendationType.REDUCE_STOCK: BusinessRecommendationType.PURCHASE_LESS,
}


def from_branch_recommendation(rec: BranchRecommendation) -> BusinessRecommendation:
    business_type = _BRANCH_TYPE_MAP.get(rec.recommendation_type)
    if business_type is None:
        raise UnsupportedRecommendationSourceError(
            f"BranchRecommendationType.{rec.recommendation_type.value} has no "
            "BusinessRecommendationType mapping yet"
        )
    return BusinessRecommendation(
        id=new_uuid(),
        recommendation_type=business_type,
        target_type="branch", target_id=rec.branch_id, branch_id=rec.branch_id,
        title=f"{rec.recommendation_type.value} — sucursal {rec.branch_id}",
        summary=rec.reason,
        evidence={"affected_product_ids": ",".join(rec.affected_product_ids),
                  "affected_product_count": str(len(rec.affected_product_ids))},
        expected_impact=f"Afecta {len(rec.affected_product_ids)} producto(s)",
        confidence=rec.confidence, priority=rec.priority, status=RecommendationStatus.NEW,
        valid_from=rec.created_at.date(), valid_until=rec.valid_until, created_at=rec.created_at,
        model_reference="forecasting.branch_intelligence_service",
    )


def from_stock_transfer_recommendation(rec: StockTransferRecommendation) -> BusinessRecommendation:
    return BusinessRecommendation(
        id=new_uuid(),
        recommendation_type=BusinessRecommendationType.TRANSFER_STOCK,
        target_type="product", target_id=rec.product_id, branch_id=rec.destination_branch_id,
        title=f"Transferir {rec.suggested_quantity} unidades de {rec.product_id}",
        summary=(
            f"Sucursal {rec.source_branch_id} tiene superávit de {rec.product_id}; "
            f"sucursal {rec.destination_branch_id} lo necesita."
        ),
        evidence={
            "source_branch_id": rec.source_branch_id,
            "destination_branch_id": rec.destination_branch_id,
            "suggested_quantity": str(rec.suggested_quantity),
        },
        expected_impact=f"Cubre el déficit proyectado en {rec.destination_branch_id}",
        confidence=rec.confidence, priority=rec.priority, status=RecommendationStatus.NEW,
        valid_from=rec.created_at.date(), valid_until=rec.valid_until, created_at=rec.created_at,
        model_reference="forecasting.branch_intelligence_service",
    )
