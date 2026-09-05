"""Domain layer for the decision_intelligence bounded context (BI-18).

Separate from `backend.domain.forecasting` (§7) — forecasting produces
purpose-built recommendation types (`PurchaseRecommendation`,
`ProductionRecommendation`, `PriceRecommendation`, `BranchRecommendation`/
`StockTransferRecommendation`, BI-14..BI-17); this package is the unifying
`BusinessRecommendation` wrapper (§37) with the one shared approval
lifecycle (§39) all of them go through when a human needs to act on them.
"""
