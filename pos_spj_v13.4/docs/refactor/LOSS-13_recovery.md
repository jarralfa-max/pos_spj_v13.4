# LOSS-13 — Recuperación

## Alcance

- Reproceso mediante liberación completa de una cuarentena canónica.
- Reclasificación respaldada por un movimiento de Inventario ya posteado.
- Subproductos y coproductos respaldados por una salida productiva posteada.
- Reclamaciones reconocidas como recuperación únicamente cuando están pagadas.
- Valor recuperado `Decimal`, limitado al valor bruto pendiente del expediente.
- Registro y aprobación segregados, idempotentes y con eventos outbox.

## Workflow

1. `record` valida alcance, cantidades, referencias y valor restante.
2. La recuperación queda `PENDING_APPROVAL` sin mover inventario.
3. Un usuario distinto ejecuta `approve`.
4. Sólo `REWORK` libera la cuarentena dentro del mismo `SAVEPOINT`.
5. Los demás tipos verifican el ledger productivo o la reclamación pagada.
6. Se recalculan `recoverable_value` y `net_loss_value`; cuando llega a cero el
   expediente se cierra.

## Tipos

- `REWORK`
- `RECLASSIFICATION`
- `BY_PRODUCT`
- `CO_PRODUCT`
- `CLAIM`
- `OTHER`

## Protecciones

- No se admiten `float`.
- La recuperación física no puede superar cantidad o peso perdidos.
- El reproceso debe liberar la cuarentena completa.
- El valor acumulado no puede superar la pérdida bruta.
- Quien registra no puede aprobar.
- Reclasificaciones y subproductos no crean movimientos desde Losses.

## Limpieza

Se retiró la recuperación inmediata de LOSS-10. `LossRecoveryService` es ahora
la única ruta de mutación para recuperaciones.

## Validación manual

1. Registrar un reproceso y comprobar que aún no libera stock.
2. Intentar aprobar con el mismo usuario y verificar el rechazo.
3. Aprobar con otro usuario y comprobar la liberación de cuarentena.
4. Registrar un subproducto con movimiento productivo posteado.
5. Registrar una recuperación por reclamación pagada.
6. Confirmar valor recuperado, pérdida neta, outbox y replay.
