# BI-12 — Demand Planning

Estado: **DONE** (primer consumidor real de todo el stack BI-7..BI-11,
validado end-to-end contra SQLite real; por producto+sucursal — por
categoría/canal quedan para cuando exista la serie/dimension real)

## Alcance

§26: "Debe poder pronosticar demanda: por producto, por categoría, por
sucursal, por canal…". BI-12 entrega **producto** (+ sucursal opcional) —
la única serie que existe hoy (`daily_sales_by_product`, BI-8). Por
categoría/canal se agregan cuando esas series tengan una dimensión real
wireada (mismo criterio "no construir sin consumidor" de toda la
transformación).

Este es el primer código de la transformación que efectivamente conecta
**todas** las fases anteriores en una sola llamada: `TimeSeriesDatasetBuilder`
(BI-8) → `ForecastBacktester`/métricas (BI-10) → `ForecastRunner` +
intervalos de confianza (BI-11), sobre modelos baseline reales (BI-9).

## Componente creado

| Archivo | Responsabilidad |
|---|---|
| `backend/application/forecasting/services/demand_planning_service.py` | `DemandPlanningService.forecast_product_demand(product_id, branch_id, horizon_days, as_of, model_key=...)`. Por llamada: (1) obtiene el modelo `ACTIVE` para `model_key`, o lo **bootstrapea** si no existe (crea un `ForecastModelDefinition` SES y lo guarda directo como `ACTIVE` — ver caveat abajo); (2) corre un backtest **fresco** (ventana de holdout de 7 días terminando el día antes de `as_of`) para tener RMSE actual como evidencia del intervalo de confianza — nunca confía en un RMSE viejo de cuando el modelo se activó; (3) entrena sobre los `training_window_days` más recientes y pronostica vía `ForecastRunner`, con `clamp_min=Decimal("0")` (una cantidad de producto nunca es negativa). |

## Caveat de gobernanza documentado (no resuelto aquí, a propósito)

El bootstrap activa el modelo **sin paso de aprobación humana**
(DRAFT→TESTING→APPROVED→ACTIVE de §20 se salta). Esto es intencional para
que el pipeline sea usable de punta a punta hoy — el flujo de aprobación
real (umbral mínimo de confianza §135, un Use Case/UI que apruebe
explícitamente) es trabajo de una fase futura (BI-18 Decision Intelligence
o configuración de forecast §134). Cada llamada sí sigue re-validando con un
backtest fresco, así que el intervalo de confianza nunca es evidencia
inventada aunque la activación no esté gobernada todavía.

## Validación end-to-end contra SQLite real

`tests/integration/test_demand_planning_service_sqlite.py` es el primer
test de toda la transformación que ejercita las 6 fases (BI-7..BI-12) juntas
contra una sola conexión SQLite real (no fakes): siembra 120 días de ventas
reales en `ventas`/`detalles_venta`, corre `SqliteDailyProductSalesReader`
(BI-8) + `SqliteForecastModelRepository`/`SqliteForecastRunRepository`
(BI-11) + `DemandPlanningService` (BI-12), y verifica que el resultado
persistido se puede releer correctamente. Un segundo test siembra
deliberadamente un día sin ventas (gap) y confirma que la imputación
explícita de BI-8 (§18) fluye sin romper nada río abajo.

## Auditoría REGLA CERO

`DemandPlanningService` no genera identidad propia más allá de delegar en
`new_uuid()` para `run_id`/`backtest_id`/el `id` del modelo bootstrapeado —
mismo patrón ya auditado en BI-9/10/11. N/A.

## Tests

`tests/unit/forecasting/test_demand_planning_service.py` (6, con fakes —
incluye un caso "serie constante ⇒ intervalo de ancho cero", que es una
verificación matemática de coherencia de todo el pipeline, no solo un
mock-check) + `tests/integration/test_demand_planning_service_sqlite.py`
(2, SQLite real). 8 tests nuevos, todos verdes. **Suite acumulada BI-1..BI-12:
188/188 verdes**, cero regresiones, cero errores de sintaxis en todo el
repo.

## Pendiente

- Por categoría/sucursal-agregado/canal — requiere series nuevas en el
  catálogo de BI-8 (`daily_sales_by_category`, etc.), no construidas
  todavía (sin consumidor).
- Ningún caller de UI/Use Case invoca `DemandPlanningService` con datos de
  producción reales todavía — sigue siendo una pieza de aplicación sin
  wiring a `app_container.py` ni a ninguna pantalla. Ese wiring es objeto de
  fases de UI (BI-23+), deliberadamente fuera de esta ronda BI-8..BI-12
  centrada en backend.
- El caveat de gobernanza de arriba (bootstrap sin aprobación humana) queda
  documentado como deuda intencional, no oculta.
