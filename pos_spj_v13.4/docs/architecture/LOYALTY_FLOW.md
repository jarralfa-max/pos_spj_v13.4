# LOYALTY FLOW (SPJ POS v13.4)

## Objetivo
Describir el flujo operativo vigente de fidelidad y los puntos de control transaccional para acumulación/canje.

## Principio de diseño
- `loyalty_ledger` es la fuente canónica de saldo.
- Las operaciones de fidelidad deben ser idempotentes y auditables.
- La venta con canje debe preservar atomicidad con la transacción de venta.

## Venta con acumulación

**Flujo:**
`POS -> SalesService -> SAVEPOINT -> venta/inventario/finanzas -> award_points -> ticket -> VENTA_COMPLETADA`

### Detalle
1. POS envía solicitud de venta.
2. `SalesService.execute_sale` abre tramo transaccional (`SAVEPOINT`) para persistencia de venta.
3. Se procesa venta, inventario y asientos financieros base.
4. Se aplica acumulación de puntos de forma idempotente (`award_points_for_sale`) usando referencia única de venta.
5. Se arma ticket con `puntos_ganados` y `puntos_totales` confiables.
6. Se publica `VENTA_COMPLETADA` con metadatos de fidelidad para evitar doble procesamiento downstream.

## Venta con canje

**Flujo:**
`preview -> compute discount -> SAVEPOINT -> venta -> apply_redemption -> release -> ticket`

### Detalle
1. Se calcula preview de canje y descuento potencial (reglas canónicas loyalty).
2. `SalesService` abre `SAVEPOINT`.
3. Se registra venta.
4. Se ejecuta `apply_redemption` dentro del tramo crítico transaccional.
5. Si canje falla, la venta no debe consolidar un descuento de puntos sin registro real.
6. Se libera transacción y se emite ticket con snapshot de fidelidad final.

## Idempotencia y eventos
- Los movimientos se identifican por `(cliente_id, tipo, referencia)`.
- Los eventos loyalty deben publicarse una sola vez por operación de negocio.
- `VENTA_COMPLETADA` debe transportar bandera de ya-procesado cuando aplique para evitar doble acreditación.

## Estado legacy documentado
- `growth_ledger` se considera legacy y debe dejar de participar en cálculo de saldo canónico.
- `modulos/growth_engine.py` queda acotado progresivamente a compatibilidad de metas/misiones hasta su migración total.

## TODO técnico
- [ ] Completar migración de metas/misiones fuera de `modulos/growth_engine.py`.
- [ ] Eliminar `growth_ledger` al cerrar migración final y validaciones de datos.
- [ ] Incorporar migración formal de referidos al nuevo esquema.
- [ ] Implementar envío productivo de cumpleaños por WhatsApp.
- [ ] Completar ciclo de eventos reales para tarjeta asignada/bloqueada con handlers de dominio.
