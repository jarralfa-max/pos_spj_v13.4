"""Domain layer for the analytical_alerting bounded context (§46-51, BI-20).

Separate from `backend.domain.decision_intelligence` (§7) — an alert flags a
condition; a recommendation suggests an action. They are related but
distinct artifacts with different lifecycles (§46: "No mezclar alerta con
recomendación").
"""
