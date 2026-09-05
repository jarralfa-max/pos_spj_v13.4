# BI-10 — Backtesting

Estado: **DONE** (7 métricas + backtester real end-to-end sobre datos falsos
determinísticos; sin wiring a datos SQLite reales en un flujo completo
todavía — eso es natural en BI-11/BI-12 cuando exista un caller real)

## Alcance

§22: "Todo modelo debe medirse antes de considerarse confiable." BI-6
confirmó que ninguno de los 8 motores legacy calcula WAPE/sMAPE/MASE/BIAS —
esta fase parte de cero, no porta nada de legacy salvo el *concepto* general
de comparar forecast vs. real que `DemandForecastEngine.evaluate_accuracy`
ya intentaba (MAE/RMSE/MAPE solamente).

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `backend/domain/forecasting/services/accuracy_metrics.py` | 7 funciones puras: `mae`, `rmse` (usa `Decimal.sqrt()`, sin numpy), `mape`, `smape`, `wape`, `bias`, `mase`. `mape`/`smape` devuelven `None` (no `0` ni excepción) cuando son estructuralmente indefinidas — puntos con actual=0 se saltan, y si **todos** se saltan el resultado es `None` (§22: "para series con cero utilizar métricas compatibles"). `wape` sí lanza si la suma de `|actual|` es 0 (ahí no hay métrica compatible que devolver — es una señal real de que la serie de prueba es degenerada). `mase` escala `mae` contra el MAE naive *del historial de entrenamiento*, no del período de prueba — devuelve `None` si ese historial es una línea plana (naive MAE = 0, división por cero evitada explícitamente, no silenciada). |
| `backend/domain/forecasting/value_objects/forecast_backtest.py` | `ForecastAccuracyMetrics` (7 campos, valida no-negatividad donde aplica, permite `None` en mape/smape/mase) + `ForecastBacktest` (id UUIDv7, model_key/version, series_definition_key, ventanas train/test, **exige `test_from > train_to`** — nunca permite evaluar "fuera de muestra" contra datos que se usaron para entrenar). |
| `backend/domain/forecasting/services/model_selector.py` | `select_best_model(backtests, metric_key="wape")` (§21) — compara solo MAE/RMSE/WAPE (nunca `None`); MASE/MAPE/sMAPE quedan fuera de la comparación automática porque pueden ser `None`. |
| `backend/application/forecasting/services/forecast_backtester.py` | `ForecastBacktester` — entrena sobre `[train_from,train_to]` vía `TimeSeriesDatasetBuilder.build()` (con gate de historial mínimo), pronostica el horizonte de la ventana de prueba con el modelo baseline pedido (BI-9), compara contra `[test_from,test_to]` real (vía el nuevo `build_test_window()`, **sin** gate de historial mínimo — una ventana de holdout de 3-7 días es legítimamente más corta que `minimum_history_days`). |
| `backend/application/forecasting/services/time_series_dataset_builder.py` (extendido) | Se agregó `build_test_window()` — mismo builder de BI-8, sin el chequeo `minimum_history_days` que sí aplica `build()` (training). |

## Decisión: MASE se escala contra el historial de entrenamiento, no el de prueba

La definición estándar de MASE escala contra el error naive *in-sample*
(entrenamiento) — usar el período de prueba (típicamente 3-14 días) daría un
denominador ruidoso y poco representativo. `ForecastBacktester.run()` pasa
`training_history` (los valores de `[train_from,train_to]`), no `actual`
(los de `[test_from,test_to]`), al llamar `accuracy_metrics.mase()`.

## Auditoría REGLA CERO

| Componente | Hallazgo | Estado |
|---|---|---|
| `accuracy_metrics.py` | Sin ids, sin persistencia | ✅ N/A |
| `forecast_backtest.py` | `id` validado con `validate_uuidv7()` | ✅ |
| `model_selector.py` | Sin ids | ✅ N/A |
| `forecast_backtester.py` | No genera ids (recibe `backtest_id` del llamador) | ✅ N/A |

## Tests

`tests/unit/forecasting/test_accuracy_metrics.py` (16),
`test_forecast_backtest.py` (6), `test_model_selector.py` (3),
`test_forecast_backtester.py` (2) — 27 tests nuevos, todos verdes. Incluye
un caso "forecast perfecto" que verifica las 7 métricas dan 0 (o `None`
donde corresponde) simultáneamente, y un caso end-to-end con
`ForecastBacktester` real (modelo `NAIVE` + datos falsos determinísticos)
que verifica MAE calculado a mano.

## Pendiente

- Ningún caller real todavía invoca `ForecastBacktester` contra
  `SqliteDailyProductSalesReader` (BI-8) con datos de producción — los
  tests usan un `_FakeReader` determinístico a propósito, para no depender
  de datos reales de ventas en esta fase. Ese wiring end-to-end (SQLite real
  + backtester + selector) es trabajo natural de BI-11/BI-12.
- Sin `ForecastModelComparison`/champion-challenger todavía (§23) — se
  construye en BI-11 cuando exista el ciclo de vida de activación de
  modelos (`ForecastModelDefinition.status` transitions).
