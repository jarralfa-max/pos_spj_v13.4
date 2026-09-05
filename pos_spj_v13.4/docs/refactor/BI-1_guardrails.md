# BI-1 — Guardrails: anti-duplicación de motores de forecast

Estado: **DONE**

## Alcance

Antes de escribir una sola línea de dominio/aplicación nueva, congelar por
test el inventario de motores de forecast/analytics ya detectado en BI-0, de
forma que sea imposible agregar un **sexto** motor paralelo sin que un test
falle explícitamente (regla §144/§150 del prompt maestro: "No eliminar
funcionalidad antes de inventariarla" + "una sola ForecastingPlatform").

## Componente creado

| Archivo | Responsabilidad |
|---|---|
| `tests/architecture/test_bi_single_forecasting_platform_ratchet.py` | Escanea `core/`, `backend/`, `modulos/` por clases cuyo nombre matchea un patrón "motor de forecast/replenishment" (`*ForecastEngine*`, `*ForecastService*`, `ReplenishmentEngine`, `SafetyStockCalculator`, `SeasonalityDetector`, `ActionableForecastService`, `DemandForecastingEngine`) y compara contra una allowlist congelada de los 8 hits ya documentados en `BI-0_legacy_audit.md`. Solo puede **decrecer** (cuando un motor se retire en BI-32 con reemplazo canónico probado). Un segundo test detecta el caso inverso: una entrada de la allowlist que ya no existe en el código (renombrado/eliminado sin actualizar el guardrail). |

Mismo patrón que `tests/architecture/test_products_legacy_consumers_ratchet.py`
(AST-scan + allowlist congelada, mono-dirección).

## Por qué class-name matching y no algo más estricto

Los 8 motores conocidos no comparten una interfaz común (`Protocol`/ABC) —
son implementaciones históricas totalmente independientes, ese es
precisamente el problema que BI-7..BI-11 va a resolver con
`ForecastModelRegistry`. Un matcher por nombre de clase es intencionalmente
laxo (falsos positivos son aceptables — obligan a revisar la allowlist; falsos
negativos serían peores porque dejarían pasar un motor nuevo sin aviso).
Cuando exista el Model Registry canónico (BI-9+), sus clases (`ForecastTrainer`,
`ForecastRunner`, etc.) deliberadamente **no** matchean el patrón porque no
terminan en `Engine`/`Service` de la misma forma — se revisará el regex en
ese momento si hace falta.

## Tests

`tests/architecture/test_bi_single_forecasting_platform_ratchet.py` (2 tests,
ambos verdes contra el estado actual del repo).

## Pendiente

- Cuando BI-3/BI-4 muevan `backend/application/queries/bi_forecast_query_service.py`
  (media móvil simple) al namespace `backend/application/forecasting/`, decidir
  si ese archivo entra también en el matcher (hoy no matchea el regex porque
  no tiene sufijo `Engine`/`Service` en el nombre de clase — es una función
  suelta, no una clase).
