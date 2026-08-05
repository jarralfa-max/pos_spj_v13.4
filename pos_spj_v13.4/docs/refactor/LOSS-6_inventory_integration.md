# LOSS-6 — Integración con Inventario

Estado: implementado el 2026-08-03.

## Contrato

Losses no modifica balances ni ledger directamente. El servicio
`LossInventoryIntegrationService` coordina los casos de uso canónicos de
Inventario mediante `LossesInventoryGateway`.

Flujo protegido:

1. `request`: exige expediente `APPROVED`, permiso `LOSSES_POST_INVENTORY` y
   emite `LOSS_INVENTORY_POSTING_REQUESTED`.
2. `post`: exige solicitud previa, crea un movimiento canónico `WASTE`,
   `SHRINKAGE` o `EXPIRY_DISPOSAL`, proyecta el saldo y pasa el expediente a
   `INVENTORY_POSTED`.
3. `reverse`: exige `LOSSES_REVERSE_INVENTORY`, motivo explícito y crea un
   movimiento `REVERSAL`; el expediente pasa a `REVERSED`.

Producto, lote, sucursal, almacén, expediente, operaciones, movimientos y
eventos conservan UUIDv7. Cantidad y peso permanecen como `Decimal`. La salida
se realiza desde la ubicación técnica `AVAILABLE`; si el almacén no la tiene,
el flujo falla cerrado.

## Atomicidad e idempotencia

Inventario participa en el savepoint externo con `owns_transaction=False`.
Ledger, proyección, outbox de Inventario, estado/outbox de Losses y operación
procesada se confirman o revierten juntos. Cada comando se deduplica por su
`operation_id` y un movimiento posteado nunca se edita: solo se reversa.

## Verificación

- Prueba real: saldo `10 → 7.5 → 10`.
- Replay de solicitud y posteo sin duplicación.
- Rollback inducido después de proyectar inventario.
- Contrato arquitectónico: la capa Application de Losses no escribe tablas de
  Inventario ni instancia sus casos de uso concretos.
- Siete pruebas `unittest` de integración y cuatro pruebas unitarias/de
  arquitectura ejecutadas correctamente.

`pytest` continúa ausente en el entorno local.
