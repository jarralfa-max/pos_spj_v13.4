# BI-29 — Scenarios UI

Estado: **DONE**, alcance deliberadamente limitado a what-if de precio (ver
justificación abajo)

## Alcance

§14/§41-45: página "Escenarios" — simular un cambio hipotético sin
guardarlo (§42: un what-if nunca escribe).

## Decisión central: reusar toda la plomería de BI-27, solo cambiar el servicio final

BI-19 ya construyó `PricingWhatIfService.simulate()` reusando
`compute_price_change_impact` — la MISMA fórmula que
`PricingIntelligenceService` (BI-16/BI-27) usa para su recomendación
auto-elegida, aplicada aquí a un cambio de precio arbitrario que el usuario
quiere explorar. Como BI-27 ya construyó `PriceHistoryQueryService` +
`estimate_price_elasticity` + búsqueda de producto/sucursal reales, BI-29
reutiliza exactamente esa plomería — el presenter es casi enteramente
composición de piezas ya existentes, no una nueva query.

## Por qué solo precio, no inventario/producción/sucursal

Igual que BI-27: `InventoryWhatIfService` (BI-19) también existe, pero
necesita el mismo `InventoryPosition` (existencia, reservado, entrante,
lead time) que BI-27 ya documentó como una brecha real — no hay una
consulta agregada limpia en el repositorio para construirlo hoy. Construirlo
con datos inventados habría sido la misma "infraestructura sin consumidor
real" evitada en cada fase.

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `frontend/desktop/modules/business_intelligence/presenters/pricing_scenario_presenter.py` | `PricingScenarioPresenter.simulate()` — construye un `BusinessScenario`/`ScenarioVariable(PRICE_CHANGE_PCT)` real y lo evalúa vía `PricingWhatIfService` real, con la misma estimación de elasticidad real de BI-27 (nunca inventada). |
| `frontend/desktop/modules/business_intelligence/pages/pricing_scenario_page.py` | `PricingScenarioPage` — producto+sucursal (búsqueda, §20) + `NumericInput` con signo para "cambio de precio %" (rango -50%..+50%, arranca en 0) + botón "Simular" → KPI bar (precio simulado, cambio en volumen/ingresos/margen). |
| `business_intelligence_routes.py` (editado) | `bi_scenarios` ahora construye `PricingScenarioPage` cuando hay `connection`. |

## Auditoría REGLA CERO

`BusinessScenario.id`/`ScenarioResult.scenario_id` ya validan UUIDv7 en su
propio `__post_init__` (BI-19) — el presenter solo los invoca. N/A.

## Tests

`test_pricing_scenario_presenter.py` (10: mapeo KPI incl. deltas negativos
y margen opcional, degradación sin filas, validaciones de producto/
sucursal/cambio-de-precio-cero, sin historial → error legible, un solo
precio → `InsufficientElasticityForSimulationError` traducido, y el mismo
historial de demanda elástica de BI-27 → `ScenarioResult` real con el
precio simulado exacto), `test_pricing_scenario_page.py` (3: construcción,
selección de producto/sucursal, ruteo). **13 tests nuevos, todos verdes**
(109 en el paquete `business_intelligence` completo).

## Pendiente

- Inventory/Production/Branch what-ifs esperan una consulta agregada real
  de inventario/capacidad/sucursal (no inventada aquí, mismo hueco que
  BI-27).
- Sin historial de escenarios simulados (cada simulación es efímera, nunca
  se guarda — coherente con §42, pero sin un lugar para comparar
  simulaciones anteriores todavía).
- BI-30 construye Reports (biblioteca, programados, exportaciones).
