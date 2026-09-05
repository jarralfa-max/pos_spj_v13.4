# BI-14 — Purchase Planning (PurchaseRecommendation)

Estado: **DONE**

## Alcance

§29: BI recomienda, Compras ejecuta — `PurchaseRecommendation` no tiene
ningún método que cree una orden de compra. Esta fase también **corrige la
violación de límite que BI-0 encontró**: el legacy `ActionableForecastService`
llama `treasury_service.estado_cuenta()` directo; la plataforma canónica usa
un puerto (`FinanceQueryPort`) en su lugar, y un guardrail de arquitectura
nuevo lo congela.

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `backend/domain/forecasting/integration_ports.py` | `FinanceQueryPort` — puerto de salida para costo estimado. Ninguna implementación concreta todavía (fase futura contra `FinanceAnalyticsQueryService`); pasar `None` es válido y produce `estimated_cost=None`, nunca un número inventado. |
| `backend/domain/forecasting/value_objects/purchase_recommendation.py` | `PurchaseRecommendation` (§29: los 10 campos exactos que pide el prompt maestro + `id`/`created_at`/`valid_until`). Sin método de ejecución — es deliberado. |
| `backend/application/forecasting/services/recent_demand_stats.py` | `compute_recent_average_daily_demand()` — extraído de `InventoryForecastService` (BI-13, refactor seguro, mismo comportamiento, tests de BI-13 siguen verdes) para que `PurchasePlanningService` no duplique la misma lógica. |
| `backend/application/forecasting/services/purchase_planning_service.py` | `PurchasePlanningService.recommend_purchase()` — llama a `InventoryForecastService` (BI-13); si `reorder_date` es `None` (no hace falta comprar) devuelve `None` sin construir nada. Si hace falta, calcula `suggested_quantity` (fórmula ya portada en BI-13), mapea urgencia→prioridad, y solo si hay un `FinanceQueryPort` inyectado pide `estimated_cost` — nunca lo calcula por su cuenta. |
| `tests/architecture/test_forecasting_never_imports_treasury_directly.py` | Guardrail nuevo: escanea `backend/domain/forecasting`/`backend/application/forecasting` por referencias a `treasury_service`/`TreasuryService`/`core.services.decision_engine`/`core.services.actionable_forecast` — falla si alguna reaparece. |

## La corrección de límite (BI-0 → BI-14)

BI-0 marcó esto como brecha: *"`ActionableForecastService` y
`core/services/decision_engine.py` llaman `treasury_service` directo —
viola §10."* `PurchasePlanningService` es el primer código de la
transformación que necesita un dato de Finanzas (`estimated_cost`) — y lo
obtiene exclusivamente vía `FinanceQueryPort`, una interfaz `Protocol` sin
ninguna importación concreta de Finance/Treasury en `backend/domain` ni
`backend/application/forecasting`. El guardrail nuevo hace que esto sea
estructuralmente imposible de romper sin que un test falle.

## Auditoría REGLA CERO

`PurchaseRecommendation.id` validado con `validate_uuidv7()`;
`PurchasePlanningService` no genera ningún otro id. N/A para el resto.

## Tests

`tests/unit/forecasting/test_purchase_recommendation.py` (7),
`test_purchase_planning_service.py` (3, incluye un caso "sin compra
necesaria ⇒ `None`" y un caso que verifica que el `FinanceQueryPort`
falso es efectivamente invocado con la cantidad correcta) +
`tests/architecture/test_forecasting_never_imports_treasury_directly.py`
(1). **11 tests nuevos, todos verdes.**

## Pendiente

- `FinanceQueryPort` no tiene implementación de infraestructura todavía
  (contra `FinanceAnalyticsQueryService` o el motor de costos real) — se
  construye cuando exista un caller de producción.
- `PurchaseRecommendation` no está unificado bajo `BusinessRecommendation`
  (§37, Decision Intelligence) todavía — es un value object de propósito
  específico; la unificación (si de verdad hace falta un envoltorio común
  para aprobar/rechazar todos los tipos de recomendación desde una sola UI)
  se evalúa en BI-18.
