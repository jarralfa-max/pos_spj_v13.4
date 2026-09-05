"""Domain layer for the forecasting bounded context — pure business rules
for the canonical ForecastingPlatform (§16). Deliberately separate from
`backend.domain.analytics`: analytics observes/measures, forecasting
predicts (§3/§7) — CRM's own operational pipeline forecast stays out of this
package too (see `backend/application/crm/queries/sales_pipeline_forecast_query_service.py`'s
documented boundary)."""
