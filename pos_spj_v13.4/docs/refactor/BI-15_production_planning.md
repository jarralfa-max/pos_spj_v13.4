# BI-15 — Production Planning (ProductionRecommendation)

Estado: **DONE**

## Alcance

§30/§76: mismo patrón que BI-14 pero para producción (Procesamiento
Cárnico) — BI recomienda cantidad/fecha de producción, Producción decide y
libera la orden real. Reutiliza el disparador de `InventoryForecastService`
(BI-13): si `reorder_date` es `None`, no hace falta producir.

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `backend/domain/forecasting/integration_ports.py` (ampliado) | `ProductionCapacityPort` — `expected_yield_pct()`/`available_capacity()`. Mismo principio que `FinanceQueryPort` (BI-14): forecasting nunca posee datos de rendimiento/capacidad de Procesamiento Cárnico, solo los pide. |
| `backend/domain/forecasting/value_objects/production_recommendation.py` | `ProductionRecommendation` (§76: recommended_production_quantity, recommended_processing_date, expected_demand, current_stock, expected_yield_pct, required_raw_material, capacity_utilization_pct, priority, confidence). Sin método de ejecución. |
| `backend/application/forecasting/services/production_planning_service.py` | `ProductionPlanningService.recommend_production()` — mismo esqueleto que `PurchasePlanningService`: usa `InventoryForecastService`, calcula `recommended_production_quantity` con la misma fórmula pura de BI-13 (`recommended_quantity`), y **solo si hay `ProductionCapacityPort` inyectado** deriva `required_raw_material` (cantidad ÷ rendimiento) y `capacity_utilization_pct` (cantidad ÷ capacidad disponible, capado a 100%). |

## Por qué reutiliza `InventoryForecastService` en vez de duplicar

La pregunta "¿hace falta actuar sobre este producto?" es idéntica para
compras y producción — ambas dependen de si el stock proyectado cruza el
punto de reorden. `PurchasePlanningService` y `ProductionPlanningService`
comparten esa misma detección (`InventoryForecastService.forecast_inventory`)
y solo difieren en qué hacen **después**: una pide costo estimado
(`FinanceQueryPort`), la otra pide rendimiento/capacidad
(`ProductionCapacityPort`). Evita que la lógica de "¿hace falta reordenar?"
diverja entre los dos flujos.

## Auditoría REGLA CERO

`ProductionRecommendation.id` validado con `validate_uuidv7()`; sin otra
identidad nueva. N/A para el resto.

## Tests

`tests/unit/forecasting/test_production_recommendation.py` (6),
`test_production_planning_service.py` (4, incluye "sin producción
necesaria ⇒ `None`", "usa el puerto de capacidad para yield/utilización", y
"utilización capada en 100%"). **10 tests nuevos, todos verdes.**

## Pendiente

- `ProductionCapacityPort` no tiene implementación de infraestructura
  todavía (contra el bounded context de Procesamiento Cárnico) — se
  construye cuando exista un caller de producción real.
- `recommended_processing_date` se fija igual a `reorder_date` de
  `InventoryForecast` — no resta el lead time de producción (tiempo de
  proceso) porque `InventoryPosition.supplier_lead_time_days` está pensado
  para proveedores externos (BI-14), no para el propio ciclo de producción
  interno; una vez exista un caller real con ese dato, se ajusta.
