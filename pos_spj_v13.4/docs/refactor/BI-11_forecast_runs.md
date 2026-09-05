# BI-11 — Forecast Runs (persistencia/versionado, ForecastResult)

Estado: **DONE** (persistencia real + `ForecastRunner` end-to-end sobre
datos falsos determinísticos; ningún caller de producción todavía)

## Alcance

Primera persistencia real del `ForecastingPlatform`: tablas nuevas
(migración 254), implementaciones SQLite de los 3 puertos de BI-7, y
`ForecastRunner` — el componente que efectivamente produce y guarda un
`ForecastRun`/`ForecastResult` usando BI-8 (datos) + BI-9 (modelos) + BI-10
(evidencia de error para el intervalo de confianza).

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `backend/infrastructure/db/schema/forecasting_schema.py` | DDL: `forecast_models`, `forecast_runs`, `forecast_result_points`, `forecast_backtests`. Mismo patrón que `procurement_schema.py` (`create_forecasting_schema`/`drop_forecasting_schema`, `CREATE TABLE IF NOT EXISTS`, ids `TEXT`, dinero/métricas `TEXT` decimal). `UNIQUE(model_key, version)` en `forecast_models`. |
| `migrations/standalone/254_forecasting_schema.py` | Migración que delega en el schema de arriba; registrada en `migrations/engine.py` (`_Migration("254", ...)`). Tablas 100% nuevas, cero solapamiento con las tablas legacy (`demand_forecast`, `replenishment_recommendations`, `product_forecast_config`) — esas se retiran en BI-32, no se tocan aquí. |
| `backend/infrastructure/db/repositories/forecasting/sqlite_forecast_model_repository.py` | `SqliteForecastModelRepository` — `save()` es un **UPSERT por `id`**: una transición de estado (`DRAFT→APPROVED→ACTIVE`) actualiza la misma fila (mismo `id`, mismo `model_key`+`version`); una iteración de entrenamiento nueva usa un `id`+`version` nuevos → INSERT nuevo. `get`/`get_active`/`list_versions` completan el puerto. |
| `backend/infrastructure/db/repositories/forecasting/sqlite_forecast_run_repository.py` | `SqliteForecastRunRepository` — `save_run()` inserta el run + todos sus puntos en una transacción, **append-only** (§69, sin UPDATE). Valida que `result.run_id == run.run_id` antes de escribir nada. |
| `backend/domain/forecasting/services/confidence_interval.py` | `build_bounds()` (§25) — deriva `(lower_bound, upper_bound)` por punto a partir del RMSE de un backtest real (BI-10) y una tabla Z fija (80/90/95/99%, mismo patrón que `SafetyStockCalculator` legacy). `clamp_min` opcional para series que no pueden ser negativas (cantidades). Niveles de confianza no soportados **fallan explícito** en vez de aproximar. |
| `backend/domain/forecasting/value_objects/forecast_model_comparison.py` | `ForecastModelComparison` + `compare()` (§23, champion/challenger) — compara dos `ForecastBacktest` por MAE/RMSE/WAPE, nunca reemplaza al campeón automáticamente, solo produce el registro de evidencia. |
| `backend/application/forecasting/services/forecast_runner.py` | `ForecastRunner.run()` — **rechaza correr un modelo que no esté `ACTIVE`** (`ForecastModelNotApprovedError`) y **rechaza un `reference_backtest` que no pertenezca al modelo** (`model_key`+`version` deben coincidir) antes de generar nada. Entrena vía `TimeSeriesDatasetBuilder.build()`, pronostica vía `run_baseline_model` (BI-9), construye intervalos vía `build_bounds()` usando el RMSE del backtest de referencia, arma `ForecastRun`+`ForecastResult`, persiste vía el puerto inyectado. |

## Por qué el intervalo de confianza viene de un backtest, no de una fórmula genérica

§25 exige intervalos siempre, pero un intervalo inventado (p. ej. ±10% fijo)
sería peor que no tener ninguno — daría falsa confianza. `ForecastRunner`
exige un `ForecastBacktest` real y **verificado como perteneciente al mismo
modelo** (mismo `model_key`+`version`) antes de construir cualquier bound;
no hay ruta para generar un `ForecastRun` sin evidencia de error real
detrás.

## Auditoría REGLA CERO

| Componente | Hallazgo | Estado |
|---|---|---|
| `forecasting_schema.py` | Todas las PK `TEXT` (UUIDv7), dinero/métricas `TEXT` | ✅ |
| `sqlite_forecast_model_repository.py` | No genera ids nuevos (recibe `ForecastModelDefinition.id` ya validado) | ✅ N/A |
| `sqlite_forecast_run_repository.py` | Genera `new_uuid()` solo para las filas de `forecast_result_points` (identidad de fila, no de negocio — el run ya trae su propio `run_id`) | ✅ |
| `forecast_runner.py` | No genera ids (recibe `run_id` del llamador) | ✅ N/A |
| `confidence_interval.py` / `forecast_model_comparison.py` | Sin ids | ✅ N/A |

## Tests

`tests/unit/forecasting/test_confidence_interval.py` (7),
`test_forecast_model_comparison.py` (3), `test_forecast_runner.py` (3, con
fakes — no toca DB), y
`tests/integration/test_sqlite_forecasting_repositories.py` (12, SQLite real
vía `create_forecasting_schema` directo, mismo patrón que BI-8 para evitar
el bootstrap roto de `fresh_db()`). 23 tests nuevos, todos verdes. Se
verificó además que `create_forecasting_schema()` es idempotente
(doble-ejecución sin error) y que la migración 254 importa y queda
registrada correctamente en `migrations/engine.py`.

## Pendiente

- Ningún caller real (Use Case/scheduler) invoca `ForecastRunner` con datos
  de producción todavía — eso empieza en BI-12 (Demand Planning), el primer
  consumidor real de todo el stack BI-7..BI-11.
- Los eventos canónicos `FORECAST_RUN_STARTED/COMPLETED/FAILED` (BI-2) no se
  publican todavía — `ForecastRunner` no tiene ningún publisher inyectado.
  Se agrega cuando exista un caller de producción real que necesite que
  otros módulos reaccionen a un run completado (evitar wiring especulativo).
- `ForecastModelComparison` no está conectado a ninguna transición de
  `ForecastModelDefinition.status` — eso es un flujo de aprobación (UI/Use
  Case) que todavía no existe.
