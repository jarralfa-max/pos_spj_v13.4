# BI-19 — Scenario Planning (What-if)

Estado: **DONE** (2 de 4 áreas de what-if nombradas en §41-45: precios y
demanda/compras; producción y sucursal quedan para cuando exista un caller
real)

## Alcance

§41-45: simular variables de negocio (precio/costo/demanda/lead time/
capacidad/merma) sin persistir el cambio como real (§42: "No guardar como
precio real"). Nuevo bounded context `backend/domain/scenario_planning/`
(§7).

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `backend/domain/scenario_planning/enums.py` | `ScenarioVariableKind` (6 valores de §41). |
| `backend/domain/scenario_planning/value_objects/scenario.py` | `ScenarioVariable` + `BusinessScenario` (rechaza variables duplicadas por tipo) + `ScenarioResult` (`baseline_metrics`/`scenario_metrics` deben compartir exactamente las mismas claves; `.delta(key)`). |
| `backend/domain/forecasting/services/price_impact.py` | `compute_price_change_impact()` — **extraído** de `pricing_decision.py` (BI-16) en un refactor seguro (tests de BI-16 siguen verdes) para que el what-if de precios reuse la fórmula exacta en vez de reimplementarla. |
| `backend/application/scenario_planning/services/pricing_what_if_service.py` | `PricingWhatIfService.simulate()` — aplica `PRICE_CHANGE_PCT` de un `BusinessScenario` sobre un precio real, usando la MISMA fórmula que la recomendación automática (BI-16), nunca una aproximación distinta. Rechaza simular si la elasticidad tiene `confidence=LOW` (§35 aplicado también a escenarios, no solo a recomendaciones). |
| `backend/application/scenario_planning/services/scaled_time_series_reader.py` | `ScaledTimeSeriesReader` — decorador de `TimeSeriesReaderPort` que multiplica cada observación por un factor fijo. Es el mecanismo detrás de `DEMAND_CHANGE_PCT`: nunca toca datos reales, solo escala lo que se lee para una corrida de simulación. |
| `backend/application/scenario_planning/services/inventory_what_if_service.py` | `InventoryWhatIfService.simulate_purchase_need()` — recibe DOS instancias ya armadas de `PurchasePlanningService` (una real, una con `ScaledTimeSeriesReader`) y compara sus recomendaciones. |

## Por qué "re-ejecutar el mismo pipeline con inputs perturbados" y no un modelo nuevo

Un what-if honesto no debería usar una fórmula distinta a la que usa la
recomendación real — si lo hiciera, el "y si…" no respondería la pregunta
que el usuario hace. Por eso:

- El what-if de precios reutiliza literalmente `compute_price_change_impact`
  (BI-16), la misma función que ya decide precios reales.
- El what-if de demanda/compras reutiliza literalmente
  `PurchasePlanningService` (BI-14) completo, con la única diferencia de
  que su fuente de datos pasa por `ScaledTimeSeriesReader` — ninguna lógica
  de negocio se duplica ni se aproxima aparte.

## Auditoría REGLA CERO

`BusinessScenario.id`/`ScenarioResult.scenario_id` validados con
`validate_uuidv7()`. N/A para el resto.

## Tests

`test_scenario.py` (7), `test_scaled_time_series_reader.py` (4),
`test_pricing_what_if_service.py` (4, incluye verificación cruzada contra
`compute_price_change_impact` llamada directamente), y
`test_inventory_what_if_service.py` (1, con cantidades calculadas a mano:
compra sugerida pasa de 20 a 80 unidades con demanda +50%). **17 tests
nuevos, todos verdes.**

## Pendiente

- What-if de producción (§44) y de sucursal (§45) — mismo mecanismo
  (`ScaledTimeSeriesReader` + el servicio de planeación correspondiente),
  se agregan cuando exista un caller real; la infraestructura ya está lista
  para reusarse sin cambios (`ProductionPlanningService` ya acepta la misma
  forma de dataset builder).
- `simulate_purchase_need()` no valida que `scenario_service` fue
  realmente construido con el factor correcto — confía en que el llamador
  ensambló ambos servicios coherentemente con el `BusinessScenario`. Un
  Use Case real (fase futura) debería construir ambos stacks desde el mismo
  `BusinessScenario` para que esto sea imposible de desalinear.
