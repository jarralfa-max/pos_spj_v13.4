# BI-9 — Baseline Models

Estado: **DONE** (7 modelos baseline de §19, todos puros, todos con
dispatcher; sin selección automática todavía — eso usa BI-10's backtests)

## Alcance

Implementar los 7 modelos baseline que pide §19, portando la *fórmula* pura
que BI-6 catalogó de cada motor legacy — nunca la clase completa (todas
tenían SQL embebido y/o ids `int`).

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `backend/domain/forecasting/services/baseline_models.py` | 7 funciones puras `Decimal`→`Decimal`: `naive`, `seasonal_naive`, `moving_average`, `weighted_moving_average`, `simple_exponential_smoothing` (SES), `holt`, `holt_winters`. Cada una valida su propio mínimo de historial (`InsufficientHistoryError`) y horizonte positivo. `holt`/`holt_winters` son reimplementaciones cerradas en `Decimal` — **sin dependencia de `statsmodels`** (el motor legacy `ForecastService` sí la usa y BI-6 encontró que ya causa un test dedicado a "maneja statsmodels ausente"; el modelo canónico no hereda esa fragilidad). |
| `backend/domain/forecasting/services/model_dispatch.py` | `BASELINE_MODEL_DISPATCH` (dict `ForecastModelFamily → función`) + `run_baseline_model(family, observations, horizon_days, parameters)`. Las 4 familias "etapa posterior" (`ARIMA`/`SARIMA`/`ETS`/`GRADIENT_BOOSTED_TREES`) levantan `NotImplementedError` explícito — nunca caen silenciosamente a otro modelo. |

## Por qué Decimal puro y no numpy/statsmodels

§131 permite arrays numéricos internos "cuando una librería lo requiera" —
ninguna de las 7 fórmulas los requiere (todas son sumas/productos/divisiones
simples, incluso Holt-Winters aditivo es aritmética cerrada). Mantenerlas en
`Decimal` de punta a punta evita el problema de redondeo float↔Decimal en la
frontera, y evita agregar una dependencia opcional (la razón por la que
`ForecastService`/Holt-Winters legacy es hoy huérfano — BI-0 encontró que
sus propios tests existen solo para el caso "statsmodels no instalado").

## Validación matemática (no solo tests unitarios aislados)

`test_holt_winters_reproduces_perfectly_periodic_pattern` construye una
serie perfectamente periódica y sin tendencia (`[10,20,10,20]` × 3
estaciones) y prueba que el modelo reconstruye el patrón exacto
**independientemente de los valores de α/β/γ** — es un punto fijo
matemático de las ecuaciones de Holt-Winters aditivo (el error en cada paso
es cero), no una coincidencia numérica. Si esa prueba falla en el futuro,
casi seguro las ecuaciones se rompieron, no solo un caso de borde.

## Auditoría REGLA CERO

Funciones puras, sin ids, sin persistencia. N/A.

## Tests

`tests/unit/forecasting/test_baseline_models.py` (15) +
`test_model_dispatch.py` (12) — 27 tests nuevos (11 dispatch + 15 modelos +
1 solapado en conteo real, ver archivo), todos verdes.

## Pendiente

- Ningún selector automático todavía elige qué familia usar para una serie
  dada — eso es `ForecastModelSelector` (BI-10, sobre resultados de
  backtest, no sobre las características de la serie directamente).
- `parameters` se pasa como `dict` crudo al dispatcher — cuando exista
  `ForecastModelDefinition.parameters` persistido (BI-11), ese dict viene de
  ahí, validado contra `feature_schema`.
