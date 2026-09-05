# BI-13 — Inventory Forecast

Estado: **DONE**

## Alcance

§28: proyectar `projected_stock`/`days_of_supply`/`stockout_probability`/
`overstock_probability`/`reorder_date` combinando la demanda pronosticada
(BI-12) con la posición de inventario actual. §72: safety stock con 4
métodos configurables (legacy solo tenía `SERVICE_LEVEL`).

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `backend/domain/forecasting/enums.py` (ampliado) | `SafetyStockMethod` (`FIXED_DAYS`/`SERVICE_LEVEL`/`DEMAND_VARIABILITY`/`CUSTOM`) + `RecommendationPriority` (`LOW`/`MEDIUM`/`HIGH`/`CRITICAL`, reutilizable por BI-14+). |
| `backend/domain/forecasting/services/safety_stock_policy.py` | `std_dev`, `safety_stock()` (despacha por método), `reorder_point`, `recommended_quantity`, `days_coverage`, `urgency_level` — las 4 últimas son las fórmulas puras que BI-6 catalogó de `SafetyStockCalculator` legacy, portadas literal. `SERVICE_LEVEL` reproduce exactamente la fórmula legacy (`Z·σ·√(lead_time)`); `DEMAND_VARIABILITY` es nueva — combina varianza de demanda **y** de lead time (el legacy asumía lead time fijo); `FIXED_DAYS`/`CUSTOM` son triviales pero completan el conjunto que pide §72. |
| `backend/domain/forecasting/value_objects/inventory_forecast.py` | `InventoryPosition` (snapshot de stock/reservas/pedidos entrantes/lead time — la costura hacia Inventario, §10: BI consume, no posee) + `InventoryForecastPoint`/`InventoryForecast`. |
| `backend/domain/forecasting/services/inventory_forecast_builder.py` | `build_inventory_forecast()` — función pura, camina día a día sobre el `ForecastResult` de demanda (BI-11) acumulando demanda point/lower/upper, produce `projected_stock` y deriva `stockout_probability`/`overstock_probability` **del propio intervalo de confianza del forecast** (nunca un modelo de probabilidad inventado aparte). |
| `backend/application/forecasting/services/inventory_forecast_service.py` | `InventoryForecastService` — conecta `DemandPlanningService` (BI-12) con el builder: llama al forecast de demanda, calcula demanda promedio reciente vía `TimeSeriesDatasetBuilder.build_test_window()`, arma `safety_stock` según el método pedido, y produce el `InventoryForecast`. |

## Cómo se derivan las probabilidades (decisión de diseño)

En vez de ajustar una distribución nueva, se usa el hecho de que
`ForecastResultPoint` ya trae `lower_bound`/`upper_bound` a un
`confidence_level` conocido (BI-11) — la probabilidad de cola asociada a
"la demanda real supera el upper_bound" es, por definición del intervalo,
`1 - confidence_level`. Entonces:

- `stockout_probability = 1` si el escenario **puntual** ya deja stock
  negativo; `1 - confidence_level` si solo el escenario de **demanda alta**
  (upper bound acumulado) lo deja negativo; `0` en otro caso.
- `overstock_probability` es simétrico usando el escenario de **demanda
  baja** (lower bound acumulado) contra un umbral de sobre-stock en
  cantidad (`overstock_threshold_days × demanda_promedio_reciente`,
  parámetro obligatorio — sin default arbitrario, §23 del skill de refactor).

Es una aproximación honesta (banda de confianza, no una distribución
ajustada) — documentada como tal, no presentada como más precisa de lo que
es.

## Auditoría REGLA CERO

Todo el código de esta fase es cálculo puro o composición de servicios ya
auditados (BI-9..BI-12); sin ids nuevos, sin persistencia nueva. N/A.

## Tests

`test_safety_stock_policy.py` (20, incluye una verificación cruzada
`SERVICE_LEVEL` contra el cálculo manual `Z·σ·√(lead_time)` en vez de un
valor hardcodeado), `test_inventory_forecast.py` (7, validación de value
objects), `test_inventory_forecast_builder.py` (8, escenarios calculados a
mano: reorder_date, stockout definido/parcial, overstock definido/parcial,
llegada de pedido entrante en su fecha exacta, days_of_supply=None sin
demanda), `test_inventory_forecast_service.py` (1, extremo a extremo con
demanda constante — verifica safety_stock/reorder_point/reorder_date
exactos). **36 tests nuevos, todos verdes.**

## Pendiente

- Sin wiring a datos reales de `InventoryPosition` (viene de la tabla
  canónica `inventory_balances`/`InventoryAnalyticsQueryService` que ya
  existe en el bounded context de Inventario) — se cablea cuando exista un
  caller real (BI-14+ o UI).
- `recent_window_days` (default 14 en `InventoryForecastService`) es el
  único parámetro con un default numérico en toda esta fase — documentado
  como ventana de "demanda reciente" para calcular safety stock, no como
  configuración de negocio; se hace configurable de verdad si un caller
  real lo necesita distinto.
