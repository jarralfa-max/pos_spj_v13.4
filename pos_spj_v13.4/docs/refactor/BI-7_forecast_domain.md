# BI-7 — Forecast Domain (ForecastingPlatform base)

Estado: **DONE** (entidades/value objects base + puertos; sin algoritmos
todavía — eso es BI-9, sin infraestructura de persistencia — eso es BI-11)

## Alcance

Primera pieza real del `ForecastingPlatform` canónico (§16): las formas de
dominio que BI-9 (modelos baseline), BI-10 (backtesting) y BI-11 (persistencia
de runs) van a necesitar, diseñadas a partir de los hallazgos concretos de
BI-6 (qué le falta a los 8 motores legacy) en vez de copiar la forma de
cualquiera de ellos.

`backend/domain/forecasting/` es un **bounded context separado** de
`backend/domain/analytics/` (§7: "Separar funcionalmente: analytics
forecasting decision_intelligence..."), y explícitamente separado del
forecast operativo de CRM
(`backend/application/crm/queries/sales_pipeline_forecast_query_service.py`,
que ya documenta ese límite en su propio docstring — BI-0 gap #4).

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `backend/domain/forecasting/enums.py` | `ForecastModelFamily` (§19 — 7 modelos baseline marcados "BI-9" + 4 de etapa posterior reservados en el vocabulario sin implementar), `ForecastModelStatus` (§20: DRAFT→TESTING→APPROVED→ACTIVE→DEPRECATED→RETIRED), `ForecastRunStatus` (espeja los eventos canónicos `FORECAST_RUN_STARTED/COMPLETED/FAILED` de BI-2). |
| `backend/domain/forecasting/value_objects/time_series.py` | `TimeSeriesDefinition` (§8/§17: `dimension_keys` validado contra el vocabulario fijo `product/category/branch/channel/customer_segment/supplier/production_line`) + `TimeSeriesObservation` — **`is_imputed`/`imputation_reason` obligatorios juntos** (§18: un día sin stock nunca puede convertirse en demanda-cero silenciosa; la brecha #1 que BI-6 encontró en los 8 motores legacy). |
| `backend/domain/forecasting/value_objects/forecast_model_definition.py` | `ForecastModelDefinition` (§20, los campos exactos que pide el prompt maestro: id/model_key/model_family/parameters/training_window/minimum_history/feature_schema/status/version/created_at/approved_at) — inválido si `status` en {APPROVED,ACTIVE,DEPRECATED,RETIRED} sin `approved_at`, e inválido en sentido inverso si DRAFT/TESTING **sí** tiene `approved_at` (§20-23: la evidencia de backtest no puede preceder a la aprobación). |
| `backend/domain/forecasting/value_objects/forecast_run.py` | `ForecastRun` (§24, inmutable/append-only — §69) + `ForecastResultPoint` (§25 — **`lower_bound <= point_forecast <= upper_bound` forzado por invariante**, así un forecast nunca puede construirse como certeza sin intervalo) + `ForecastResult` (agregado run_id + puntos, exige orden cronológico). |
| `backend/domain/forecasting/repository_ports.py` | `TimeSeriesReaderPort`, `ForecastModelRepositoryPort`, `ForecastRunRepositoryPort` — `Protocol`s puros, ninguna implementación todavía (BI-11+). Es el seam que impide que un futuro Use Case repita el patrón de los 8 motores legacy (SQL directo embebido en la clase de forecast). |
| `backend/domain/forecasting/exceptions.py` | `ForecastingDomainError` + `InsufficientHistoryError`, `ForecastModelNotFoundError`, `ForecastModelNotApprovedError` (relocalizada desde `backend/domain/analytics/exceptions.py` — vivía ahí desde BI-2 sin consumidores, forecasting es su bounded context correcto), `ForecastRunNotFoundError`, `TimeSeriesNotFoundError`. |

## Decisiones de diseño derivadas directamente de BI-6

1. **Separar serie/modelo/run en 3 tipos independientes** — ningún motor
   legacy lo hace (todos mezclan lectura+algoritmo+persistencia en una
   clase); es la corrección arquitectónica central que BI-6 identificó como
   necesaria.
2. **`ForecastRun`/`ForecastModelDefinition` usan `validate_uuidv7()`**
   (`backend/shared/ids.py`) en `__post_init__` — 3 de los 8 motores legacy
   (`ForecastEngine`, `ReplenishmentEngine`, `ActionableForecastService`)
   usan `producto_id: int`/`sucursal_id: int`; el dominio nuevo lo hace
   estructuralmente imposible.
3. **Ningún parámetro tiene default de identidad** — BI-6 encontró 4 defaults
   `= 1`/`= 0` hardcodeados entre los motores legacy (viola §23). Ningún
   campo de estas value objects tiene default de sucursal/producto; todo se
   pasa explícito.
4. **`ForecastModelDefinition.is_usable_for_forecasting()`** solo es `True`
   en `ACTIVE` — refleja que ninguno de los 8 motores legacy tiene el
   concepto de "modelo aprobado pero no activo todavía" (champion/challenger,
   §23); el dominio nuevo lo soporta desde el día uno aunque BI-9/BI-10 (los
   que realmente comparan modelos) todavía no existan.

## Auditoría REGLA CERO

| Componente | Hallazgo | Estado |
|---|---|---|
| `time_series.py` | Sin ids nuevos | ✅ N/A |
| `forecast_model_definition.py` | `id` validado con `validate_uuidv7()` | ✅ |
| `forecast_run.py` | `run_id`/`model_version_id` validados con `validate_uuidv7()` | ✅ |
| `repository_ports.py` | Solo `Protocol`, sin persistencia | ✅ N/A |
| `exceptions.py` | Sin ids | ✅ N/A |

## Tests

`tests/unit/forecasting/test_time_series.py` (7),
`test_forecast_model_definition.py` (9), `test_forecast_run.py` (14) —
30 tests nuevos, todos verdes. Total acumulado de tests nuevos BI-1..BI-7
(`tests/unit/analytics/` + `tests/unit/forecasting/` + los 2 architecture
guardrails): **86 passed** (BI-4 y BI-6 no agregaron tests propios — BI-4 es
un movimiento de archivos verificado contra la suite BI existente, BI-6 es
un documento de análisis).

## Pendiente

- **BI-8** (Time Series Data): `TimeSeriesDatasetBuilder` real que
  transforme filas SQL en `TimeSeriesObservation` — hoy `TimeSeriesReaderPort`
  es solo la interfaz, sin implementación SQLite.
- **BI-9** (Baseline Models): implementar los 7 `ForecastModelFamily`
  marcados "BI-9" reutilizando las fórmulas puras ya identificadas en BI-6
  (`moving_avg`/`weighted_avg`/`exp_smoothing` de `DemandForecastEngine`,
  `_ses` de `ForecastEngine`, Holt-Winters de `ForecastService`).
- **BI-10** (Backtesting): `ForecastBacktester` + métricas MAE/RMSE/MAPE/
  WAPE/MASE/BIAS — BI-6 confirmó que ninguno de los 8 motores calcula
  WAPE/MASE/BIAS hoy, parte de cero.
- **BI-11** (Forecast Runs): implementaciones SQLite de los 3
  `*RepositoryPort` + wiring real de `ForecastRunStatus` a los eventos
  `FORECAST_RUN_*` de BI-2 (hoy nada los publica todavía).
