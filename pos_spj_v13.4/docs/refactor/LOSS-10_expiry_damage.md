# LOSS-10 — Caducidad y daño

## Alcance entregado

- Evaluación persistente por lote que combina caducidad configurada y severidad de daño.
- Riesgos `NORMAL`, `WARNING`, `HIGH` y `CRITICAL`, con cantidad y peso en `Decimal`.
- Bloqueo mediante la cuarentena canónica de Inventario (`AVAILABLE → QUARANTINED`).
- Recuperación mediante liberación canónica (`QUARANTINED → AVAILABLE`).
- Disposición autorizada y completada mediante la baja canónica de cuarentena.
- Segregación obligatoria entre quien autoriza y quien completa una disposición.
- Idempotencia por `operation_id`, eventos outbox y cierre atómico del expediente.

## Límites del bounded context

Losses conserva el motivo, el snapshot de riesgo, la recuperación y la disposición. No
actualiza saldos ni estados físicos directamente. Todo cambio de stock pasa por los
casos de uso productivos de Inventario y comparte el `SAVEPOINT` externo para evitar
una cuarentena o baja sin su correspondiente registro de pérdidas.

## Persistencia

La migración `174_losses_bounded_context_schema.py` incorpora
`loss_lot_risk_assessments`, sus constraints UUIDv7/Decimal, índices de consulta y la
unicidad del bloqueo activo por expediente y lote. Se reutilizan
`loss_recoveries`, `loss_dispositions`, `loss_outbox` y
`loss_processed_operations`.

## Permisos

- Consulta/evaluación: `LOSSES_EXPIRY_DAMAGE_VIEW`.
- Bloqueo: `LOSSES_REVIEW` más el permiso canónico de cuarentena de Inventario.
- Recuperación: `LOSSES_RECORD_RECOVERY` más liberación de cuarentena.
- Autorización: `LOSSES_AUTHORIZE_DISPOSAL`.
- Ejecución: `LOSSES_COMPLETE_DISPOSAL` más disposición de Inventario.

## Verificación

Las pruebas cubren clasificación combinada, rechazo de `float`, idempotencia,
integración por gateway, cierre por recuperación y segregación de disposición. La
suite `unittest` también ejecuta la migración limpia y la regresión LOSS-6.
