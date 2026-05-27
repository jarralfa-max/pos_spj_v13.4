# LOYALTY REFACTOR BUGFIX REPORT (Post Re-audit)

## Resumen
Este documento consolida los bugs corregidos tras la re-auditoría del refactor de fidelidad en SPJ POS v13.4 y el estado técnico actual del módulo.

## Bugs corregidos

1. **Doble escritura en `loyalty_ledger`**
   - Se eliminó la ruta duplicada de registro de movimientos para evitar que una misma venta/canje impacte dos veces el saldo.
   - Se preservó la idempotencia por `(cliente_id, tipo, referencia)`.

2. **Guardado incorrecto de configuración de cumpleaños**
   - Se corrigió el flujo para persistir `cumple_bono_estrellas` y `cumple_mensaje_wa` en lugar de sobrescribir configuración de referidos.

3. **Acceso UI a atributos privados (`loyalty_service._app.repo`)**
   - La UI de fidelidad quedó desacoplada para consumir métodos públicos de `LoyaltyService`.

4. **Riesgo de `NameError` en Growth UI**
   - Se estabilizó `modulos/modulo_growth_engine.py` para evitar uso de variables de botones sin inicializar.

5. **Commit internos en rutas de fidelidad sensibles a transacción**
   - Se redujo el riesgo de ruptura de atomicidad en ventas/canjes al minimizar commits internos en rutas críticas.

6. **Regresiones cubiertas por pruebas**
   - Se agregó suite de regresión para idempotencia, configuración cumpleaños, skip de evento ya procesado y validaciones UI/sintaxis.

## Archivos modificados (áreas relevantes)
- `core/services/loyalty_service.py`
- `application/services/loyalty_application_service.py`
- `repositories/loyalty_repository.py`
- `core/services/sales_service.py`
- `core/events/wiring.py`
- `core/events/event_bus.py`
- `modulos/fidelidad_config.py`
- `modulos/modulo_growth_engine.py`
- `modulos/growth_engine.py` (shim legacy)
- `tests/test_loyalty_refactor_regression.py`

## Flujo actual de venta con fidelidad

### Venta con acumulación
1. POS prepara venta.
2. `SalesService` ejecuta flujo transaccional principal de venta/inventario/finanzas.
3. Acreditación de puntos se procesa de forma idempotente vía `LoyaltyService` -> `LoyaltyApplicationService` -> `LoyaltyRepository`.
4. Ticket recibe snapshot confiable (`puntos_ganados`, `puntos_totales`).
5. Se publica `VENTA_COMPLETADA` con bandera para evitar reprocesamiento de fidelidad.

### Venta con canje
1. Se calcula preview/descuento con reglas canónicas de loyalty.
2. En `SalesService`, el canje real ocurre dentro del tramo crítico transaccional de venta.
3. Si falla la venta, no debe quedar canje huérfano aplicado.
4. Ticket imprime estado final coherente de puntos.

## Fuente canónica de saldo
- **`loyalty_ledger` es la fuente única de verdad** para saldo de puntos.
- `clientes.puntos` y `tarjetas_fidelidad.puntos_actuales` se tratan como **snapshots derivados/recalculables**, no como verdad canónica.

## Estado de `GrowthEngine` legacy
- `modulos/growth_engine.py` permanece como **shim temporal** para compatibilidad incremental.
- Debe evitarse su uso como fuente de saldo/pasivo de cliente.
- El saldo funcional de fidelidad está centralizado en el flujo loyalty nuevo.

## Eventos de fidelidad activos
- `LOYALTY_POINTS_EARNED`
- `LOYALTY_POINTS_REDEEMED`
- `LOYALTY_POINTS_REVERSED`
- `LOYALTY_POINTS_EXPIRED`
- `LOYALTY_CARD_ASSIGNED`
- `LOYALTY_CARD_BLOCKED`
- `LOYALTY_REFERRAL_REWARDED`
- `LOYALTY_BIRTHDAY_REWARD_ISSUED`
- `LOYALTY_FRAUD_BLOCKED`

Se mantiene objetivo de publicación única e idempotencia por operación para evitar doble acreditación/descuento.

## Riesgos pendientes
1. Dependencias legacy de `GrowthEngine` aún presentes en metas/misiones.
2. Convivencia temporal de claves `growth_*` y `loyalty_*` (riesgo de configuración inconsistente si no se completa la unificación).
3. Necesidad de endurecer más pruebas de integración end-to-end en escenarios con fallos intermedios reales.
4. Requiere cierre final de deuda de migración para eliminar rutas legacy de ledger antiguo.

## TODO (siguiente fase)
- [ ] Migrar metas/misiones fuera de `modulos/growth_engine.py`.
- [ ] Eliminar `growth_ledger` cuando la migración final esté cerrada.
- [ ] Crear migración formal para referidos.
- [ ] Implementar envío real de cumpleaños por WhatsApp.
- [ ] Implementar eventos reales para tarjeta asignada/bloqueada con handlers de dominio completos.
