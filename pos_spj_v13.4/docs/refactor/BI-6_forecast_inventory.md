# BI-6 — Inventario detallado de motores de forecast

Estado: **DONE**

## Alcance

BI-0 ya clasificó los 8 motores de forecast legacy (`BLOCKED`/dead-code) y
construyó una matriz de paridad de alto nivel. BI-6 profundiza a nivel de
firma de método concreta — lo que hace falta para diseñar el dominio
`ForecastingPlatform` (BI-7) sin adivinar comportamiento.

## Firmas completas por motor

### `core/forecast/demand_forecast_engine.py::DemandForecastEngine`
```
__init__(db)
moving_avg(values: List[float], window: int) -> float                  [static]
weighted_avg(values: List[float], window: int = 14) -> float           [static]
exp_smoothing(values: List[float], alpha: float = 0.3) -> float        [static]
_choose_best_method(...)                                               # auto-selección simple
forecast_product(product_id, branch_id, horizon_days=...) -> dict
save_forecast(result: dict) -> int                                     # persiste en `demand_forecast`
evaluate_accuracy(...)                                                  # MAE/RMSE/MAPE
```
Config por producto vía tabla `product_forecast_config` (lead_time,
service_level, alpha, método preferido, min_history_days) — el único de los
8 motores con **configuración por producto persistida**, no solo constantes
en código. Precedente directo de `ForecastModelDefinition.parameters` (§20).

### `core/forecast/replenishment_engine.py::ReplenishmentEngine`
```
__init__(db)
run(branch_id=...) -> ...                                # orquesta todo el ciclo
_run_branch(...) / _process_product(...)
_simple_avg(product_id: int, branch_id: int, days: int = 30) -> float
_save_recommendation(...)                                 # persiste en `replenishment_recommendations`
get_dashboard(...)
get_forecast_series(...)
get_historial_runs(limit: int = 20) -> List[Dict]
get_precision_metrics(branch_id=None) -> List[Dict]
approve_recommendation(rec_id: str) -> None
reject_recommendation(rec_id: str) -> None
```
**Es el único motor con superficie de ciclo de vida completo**: corre,
guarda historial de runs (`forecast_run_log`), expone métricas de precisión,
y tiene aprobar/rechazar sobre la recomendación — precedente funcional
directo de `ForecastRun` (§24) + `PurchaseRecommendation` (§29) + los
estados `NEW`/`APPROVED`/`REJECTED` de `BusinessRecommendation` (§39). Usa
`producto_id: int`/`branch_id: int` — **viola REGLA CERO** (ids enteros);
ninguna parte de su lógica se reutiliza literal, solo su *forma*.

### `core/forecast/safety_stock_calculator.py::SafetyStockCalculator`
```
std_dev(daily_demand: List[float]) -> float                              [static]
safety_stock(...) -> float                                               [static]
reorder_point(...) -> float                                              [static]
recommended_quantity(...) -> float                                       [static]
days_coverage(current_stock: float, avg_daily_demand: float) -> float    [static]
urgency_level(days_cov: float) -> str                                    [static]
```
100% puro (`@staticmethod`, sin `db`) — tabla Z para niveles de servicio
90-99.9%. Único método hoy: `SERVICE_LEVEL`. El prompt maestro (§72) pide
`FIXED_DAYS`/`SERVICE_LEVEL`/`DEMAND_VARIABILITY`/`CUSTOM` — se amplía en
BI-13, no se pierde nada al portar.

### `core/forecast/seasonality_detector.py::SeasonalityDetector`
```
weekly_factors(daily_series: List[Tuple[str, float]]) -> Dict[int, float]  [static]
apply_factor(base_forecast, target_date_str, ...)                          [static]
describe_week_pattern(factors: Dict[int, float]) -> str                    [static]
```
100% puro. Factor de estacionalidad **solo semanal** (día de la semana) —
el prompt maestro (§19) eventualmente quiere estacionalidad más rica
(SARIMA/ETS), pero el factor día-de-semana es una feature válida de
`TimeSeriesDatasetBuilder` (BI-8) desde el día uno.

### `core/services/enterprise/demand_forecasting.py::DemandForecastingEngine`
```
__init__(db)
_wma(series, window) -> float
_sma(series, window) -> float
_tendencia(series) -> Tuple[str, float]                    # creciente/estable/decreciente
_compra_sugerida(...) 
forecast_producto(...) -> ProductForecast
forecast_all(...) -> List[ProductForecast]
get_alertas_inventario(...) -> List[AlertaInventario]
get_rotacion_inventario(...)
```
Dataclasses propias `DemandPoint`/`ProductForecast`/`AlertaInventario` — la
única de las 8 implementaciones con **tipos de resultado explícitos** en vez
de `dict`. Buena referencia de forma (no de contenido) para
`ForecastResultPoint`/`ForecastRun` (BI-7).

### `core/services/forecast_engine.py::ForecastEngine`
```
__init__(conn, sucursal_id: int = 1, alpha=..., horizonte=...)   # default sucursal_id=1 — viola §23
run() -> list
forecast_producto(producto_id: int) -> dict
generar_forecast_diario() -> list                                 # alias para scheduler
_ses(producto_id: int) -> float
```
SES puro (α=0.3), sin persistencia de modelo/versión. El único motor con un
`sucursal_id: int = 1` hardcodeado como default de constructor — exactamente
el anti-patrón que §23 del prompt maestro prohíbe explícitamente.

### `core/services/forecast_service.py::ForecastService`
```
__init__(db_conn, module_config=None)
enabled() -> bool
generar_plan_compras(producto_id: str, sucursal_id: str, dias_historial: int,
                      dias_pronostico: int, stock_seguridad: float) -> dict
```
Holt-Winters (`statsmodels`). Es el **único motor con ids ya `str`** (UUID-
compatible) — y el único huérfano de producción. Su algoritmo (Holt-Winters)
es uno de los 7 baseline models pedidos por §19; se porta como modelo, no
como servicio.

### `core/services/actionable_forecast.py::ActionableForecastService`
```
__init__(db_conn, treasury_service=None, module_config=None)
_init_engines()                                    # lazy-crea DemandForecastEngine internamente
enabled() -> bool
analisis_demanda(producto_id: int = 0, ...) -> ...
plan_compras_semanal(sucursal_id: int = 1, ...) -> ...            # default sucursal_id=1 — viola §23
analisis_riesgos(sucursal_id: int = 1) -> List[Dict]               # default sucursal_id=1 — viola §23
forecast_producto(producto_id: int, ...) -> ...
```
Envoltorio sobre `DemandForecastEngine` + llamada directa a
`treasury_service` (ya señalada en BI-0 como violación de límite BI↔Finance).
Dos defaults `sucursal_id=1` adicionales — mismo anti-patrón que
`ForecastEngine`.

## Hallazgos que informan el diseño de BI-7

1. **Ningún motor separa "serie de tiempo" de "modelo" de "corrida"** — los
   8 mezclan lectura de datos + algoritmo + persistencia + a veces
   recomendación en una sola clase. `ForecastingPlatform` (BI-7) debe separar
   esas 4 responsabilidades en piezas independientes (`TimeSeriesDefinition`,
   `ForecastModelDefinition`, `ForecastRun`, y un puerto de persistencia
   separado) — ninguna clase legacy es un buen molde de arquitectura, solo
   de fórmulas puras.
2. **3 motores usan `producto_id: int`/`sucursal_id: int`** (`ForecastEngine`,
   `ReplenishmentEngine`, `ActionableForecastService`) — confirma que ningún
   motor legacy puede reusarse literal en el dominio nuevo sin romper REGLA
   CERO; solo se reutiliza la *fórmula matemática* (ya puros: SES, WMA, SMA,
   safety stock, estacionalidad), nunca la clase completa.
3. **4 defaults `= 1` hardcodeados** (`ForecastEngine.__init__(sucursal_id=1)`,
   `ActionableForecastService.plan_compras_semanal(sucursal_id=1)`,
   `.analisis_riesgos(sucursal_id=1)`, y el propio `forecast_producto` con
   `producto_id: int = 0`) — viola §23 explícitamente. El dominio nuevo no
   debe tener ningún default de identidad; sucursal/producto siempre
   explícitos o resueltos por `ExecutionContext`.
4. **Solo `DemandForecastEngine` persiste configuración por producto**
   (`product_forecast_config`) — es el precedente más cercano a
   `ForecastModelDefinition.parameters` (§20), aunque su tabla es legacy y
   no se reutiliza tal cual.
5. **Solo `ReplenishmentEngine` tiene aprobar/rechazar + historial de runs +
   métricas de precisión** — es la referencia de forma para el ciclo de vida
   `ForecastRun`→`ForecastResult`→(consumido por)→`PurchaseRecommendation`
   con estados `NEW`/`APPROVED`/`REJECTED` (§29/§39), aunque su
   implementación entera queda `BLOCKED` (ids enteros, sin backtesting real).
6. **Ninguno de los 8 calcula WAPE/BIAS/MASE** (§22) — todos, cuando miden
   algo, usan como máximo MAE/RMSE/MAPE (`DemandForecastEngine.evaluate_accuracy`
   es el más completo). El backtesting real (BI-10) parte de cero en ese
   sentido, no hay nada que portar salvo la mecánica general de "comparar
   forecast vs actual".

## Mapeo final motor → destino canónico (confirma/detalla BI-0 §151)

| Motor | Fórmula(s) reutilizable(s) tal cual (pura) | Reemplazo canónico (BI-7+) |
|---|---|---|
| `DemandForecastEngine` | `moving_avg`, `weighted_avg`, `exp_smoothing` | Modelos `MOVING_AVERAGE`/`WEIGHTED_MOVING_AVERAGE`/`SES` (BI-9) |
| `ForecastEngine` | `_ses` (SES α configurable) | Modelo `SES` (BI-9) |
| `ForecastService` | Holt-Winters vía `statsmodels` | Modelos `HOLT`/`HOLT_WINTERS` (BI-9) |
| `DemandForecastingEngine` | `_wma`, `_sma`, `_tendencia` | Modelos `WEIGHTED_MOVING_AVERAGE`/`MOVING_AVERAGE` + feature de tendencia (BI-9) |
| `SeasonalityDetector` | `weekly_factors`, `apply_factor` | Feature de `TimeSeriesDatasetBuilder` (BI-8) |
| `SafetyStockCalculator` | `safety_stock`, `reorder_point`, `days_coverage`, `urgency_level` | `SafetyStockPolicy` domain service (BI-13) |
| `ReplenishmentEngine` | Ninguna fórmula pura propia (orquesta las de arriba) | Forma de ciclo de vida → `ForecastRun`/`PurchaseRecommendation` (BI-11/BI-14) |
| `ActionableForecastService` | Ninguna — envoltorio + llamada directa a Treasury | Se elimina; su rol lo cubre Decision Intelligence (BI-18) consumiendo `FinanceAnalyticsQueryService` |

## Tests

Ninguno nuevo — BI-6 es un documento de análisis, no código. Los guardrails
de BI-1 (`test_bi_single_forecasting_platform_ratchet.py`) ya cubren que
esta lista de 8 no crezca mientras se construye BI-7+.
