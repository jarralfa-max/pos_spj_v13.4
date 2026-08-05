# LOSS-9 — Rendimientos

Estado: implementado el 2026-08-03.

## Métricas

`ProductionYieldCalculator` produce con `Decimal`:

- salida y rendimiento esperados;
- salida y rendimiento reales;
- variación absoluta y porcentual;
- merma normal y anormal;
- límite inferior, límite superior y severidad.

La banda usa la suma de `minimum_yield_pct` y `maximum_yield_pct` de todos los
outputs productivos cuando el perfil las define completamente. En caso
contrario usa `expected_yield_pct ± tolerance_pct` de la versión activa.

## Severidades y alertas

- `NORMAL`: rendimiento dentro de banda.
- `WARNING`: rendimiento superior al límite máximo; se alerta pero no se
  fabrica una pérdida.
- `OUT_OF_TOLERANCE`: rendimiento debajo del mínimo.
- `CRITICAL`: producción con rendimiento real cero cuando se esperaba salida.

Toda severidad distinta de `NORMAL` crea una única `loss_yield_alerts`, emite
`YIELD_ALERT_RAISED` por outbox y queda enlazada con `yield_variances` y el
expediente. El replay de la operación devuelve el mismo `alert_id`.

`YieldMonitoringQueryService` expone variaciones recientes y alertas abiertas
sin SQL en UI o Application. Las alertas se ordenan por severidad y fecha.

## Verificación

- Banda explícita asimétrica.
- Tolerancia simétrica de versión.
- Rendimiento bajo, alto y cero.
- Persistencia y outbox idempotentes.
- QueryService para variaciones y alertas abiertas.
