# Lote 6 — Pedidos y repartos (ronda 1)

- **Rama:** `fix/lote-6`, que sale de `claude/erp-financial-bounded-context-uqxz6b` en `e58f6849`.
- **Fecha:** 2026-11-06 a 2026-11-09.
- **Fuente de verdad:** los `intent.md` aprobados el 2026-11-05 (Alfred) y sus respuestas. El backlog todavía dice `intent-borrador`; no se editó.

## Resumen por ítem
| Ítem | Estado | Commit |
|---|---|---|
| SDLC-ORD-004 | LISTO | `5b4f4d5a` |
| SDLC-ORD-001 | LISTO | `74de48cc` |
| SDLC-ORD-005 | LISTO | `6a537cdb` |
| SDLC-ORD-002 | LISTO | `56f104d2` |
| SDLC-ORD-003 | LISTO (decisión y plan; el corte queda para ítems posteriores, como fija el intent) | `c1f91053` |
| SDLC-ORD-006 | LISTO | `c6b7246d` |

## SDLC-ORD-004 — el inventario baja al salir de la sucursal
- **Decisión aplicada:** el responsable respondió «al despachar». En mostrador no hay despacho, así que la mercancía sale al entregarla.
- **Reproducido antes del cambio:** 15 de 16 pruebas nuevas fallaban. Ni siquiera se podía reservar un saldo con ubicación: `Sin balance disponible para reservar`.
- **Qué cambió:**
  - `OrdersDeliveryInventoryClient.commit_order` registra un `SALE_ISSUE` con `source_module="orders_delivery"` y cumple las reservas. Corre en la transacción de `DispatchDeliveryJobUseCase` y de `CompletePickupUseCase`; si no puede descontar, no hay despacho ni entrega.
  - Sale la cantidad final, o la preparada si no hubo ajuste. Una línea rechazada suelta su reserva. Una sustituida suelta la reserva del original y saca el sustituto.
  - Si el libro dice que el pedido ya salió, no se descuenta otra vez.
  - `restore_order` devuelve lo que el libro dice que está fuera, al mismo lote y ubicación. Lo usan `ReturnToBranchUseCase` y `ReverseCustomerOrderUseCase`.
  - `ReverseSaleUseCase(inventory_return=...)`: Ventas ya no repone lo que nunca sacó.
  - Un pedido que nunca descontó no suma existencia al reversarse, y suelta la retención que tuviera.
  - Pedidos reserva por línea con `ReserveStockForCustomerOrderUseCase`, del almacén de venta y de saldos reales con lote y ubicación. La reserva anterior buscaba un saldo sin lote ni ubicación, que ningún flujo llena y que ningún movimiento puede descontar.
  - `ORDERS_DELIVERY_GRANT` gana `MOVEMENT_CREATE`.
- **Saneamiento:** sin migración. El responsable midió cero reservas huérfanas («ni uno, estamos en desarrollo»). Si apareciera alguna, `restore_order` la suelta al reversar.
- **Pruebas:** `tests/integration/test_orders_delivery_inventory_commit.py` (16).
  - Cubren saldo y libro en mostrador y en domicilio, y la cantidad preparada distinta de la pedida.
  - Cubren el faltante con todo o nada, el regreso a sucursal, el reverso al lote de origen y el pedido que nunca descontó.
  - Prueban que no hay doble descuento con `settle_inventory` en `False` y en `True`.
  - Cubren dos líneas del mismo producto, la sustitución y la existencia del almacén de venta con lote.
- **Pruebas ajustadas:** 11 archivos de prueba sembraban saldos sin ubicación. Ahora la siembran, como dejan el saldo los flujos reales.

## SDLC-ORD-001 — el dinero de Pedidos
- **Decisión aplicada:** el responsable confirmó que el efectivo en poder de repartidores lleva cuenta propia.
- **Reproducido antes del cambio:** el cobro en efectivo sin turno completaba la venta y sólo dejaba `cash_effects_error`.
- **Qué cambió:**
  - `CheckoutSaleUseCase(cash_custody=...)`. Caja corre siempre en la transacción de la venta: si rechaza, el cobro se detiene con el motivo. Se eliminó `cash_effects_error`.
  - `"DRAWER"`: el efectivo en sucursal exige turno; un pago sin efectivo sólo pasa por Caja si hay turno.
  - `"DRIVER"`: un pedido con cobro a domicilio en efectivo no pasa por el cajón.
  - Un reintento ya no vuelve a pagar una venta ya pagada.
  - Nueva cuenta `1104 Efectivo en poder de repartidores` y perfil `DRIVER_CASH`, en el arranque y en la migración **388**.
  - Asientos de `driver_cash_handlers.py`:
    - cobro: Dr 1104 / Cr caja registradora;
    - liquidación: Dr caja general / Cr 1104;
    - diferencia: contra la caja registradora, a faltantes (7501) o sobrantes (7120).
  - La venta sigue reconociendo el ingreso. El mismo dinero no se cuenta dos veces.
  - Sólo el efectivo genera custodia. Un cobro `MIXED` no se asienta: no guarda qué parte fue efectivo.
  - `wire_orders_delivery`, despacho de `orders_delivery_outbox` al arrancar y tarea periódica. El despachador publica en modo estricto y confirma fila por fila. Los eventos contables sin consumidor quedan pendientes.
  - `CreateDriverSettlementUseCase` toma también los cobros `COLLECTED`: nada en producción los pasaba a `PENDING_SETTLEMENT`, así que ningún repartidor podía liquidarse.
- **Pruebas:** `tests/integration/test_orders_delivery_driver_cash_finance.py` (14).
  - Cubren la falla de Caja sin turno y el reintento sin doble pago, la transferencia sin turno y los asientos de cobro y de liquidación.
  - Cubren el doble conteo, el faltante, el sobrante, la tarjeta y la idempotencia.
  - Cubren la migración 388 y la cola sin consumidor o con Finanzas fallando.

## SDLC-ORD-005 — un solo flujo para "Nuevo pedido"
- **Decisión aplicada:** el responsable pidió conservar el alta rápida.
- **Qué cambió:**
  - `NewOrderDialog` envuelve `NewOrderPage`: búsqueda de producto, precio de Pricing y dirección, con `CaptureOrderUseCase`.
  - Ya no pide el UUID del producto ni un precio unitario.
  - `CreateCustomerOrderUseCase`, que respeta el precio de la línea, deja de estar expuesto a la UI. Sólo lo llama la conversión de una cotización.
- **Pruebas:** `tests/integration/orders_delivery/test_new_order_dialog.py` (6). Se quitaron las pruebas que fijaban el diálogo viejo (`test_orders_delivery_ui_pages.py`) y se adaptó `test_orders_delivery_write_authorization.py`.

## SDLC-ORD-002 — outbox sin drenar
- `orders_delivery_outbox` ya se drena (commit de SDLC-ORD-001).
- Se midió con el cableado real que los eventos de `crm_outbox`, `customer_outbox`, `quote_outbox`, `loyalty_cards_outbox`, `sweepstakes_outbox`, `customer_service_outbox` y `customer_privacy_outbox` no tienen ningún suscriptor local. Quedan declarados como `REPLICATION_ONLY_OUTBOXES`.
- **Pruebas:** `tests/integration/bootstrap/test_outbox_drain_coverage.py` (10). Fallan si alguien suscribe uno de esos eventos sin construirle despachador.

## SDLC-ORD-003 — pipeline autoritativo
- **Decisión aplicada:** la regla del responsable fue «el más avanzado», y lo es `customer_orders` con `quotes`.
- La evidencia y el plan de corte en 6 pasos están en `docs/sdlc/items/SDLC-ORD-003/decision.md`. También responde la pregunta que bloquea SDLC-WA-021: el pedido de WhatsApp nace en `customer_orders`.
- **Pruebas:** `tests/architecture/test_orders_single_pipeline_ratchet.py` (2). Impiden nuevos lectores de `delivery_orders` o `pendiente_wa` en el ERP, y la lista sólo encoge.

## SDLC-ORD-006 — avisos al cliente con reintento
- **Decisión aplicada:** el responsable eligió `whatsapp_outbox` como cola.
- **Qué cambió:**
  - Los avisos de despacho, entrega, entrega fallida, pedido listo, aprobación y su reenvío quedan en `whatsapp_outbox` en la transacción del hecho, idempotentes por `operation_id`.
  - Se intentan en seguida y la tarea de fondo `orders_delivery.customer_notices` los reintenta con espera creciente.
  - Al quinto intento el aviso pasa a `DEAD_LETTER` y avisa a gerencia con `aviso_cliente_fallido`.
  - La alerta interna de entrega fallida se escribe en la transacción del intento.
- **Riesgo declarado:** hoy ningún proceso del microservicio drena `whatsapp_outbox` (SDLC-WA-006). Si empieza a hacerlo, este drenado del ERP debe retirarse para no enviar dos veces (SDLC-WA-037).
- **Pruebas:** `tests/integration/test_orders_delivery_notice_retry.py` (6).

## Migraciones
- **388** `388_driver_cash_account`: cuenta 1104 y perfil `DRIVER_CASH`. Sólo agrega y es idempotente. Si el catálogo aún no está sembrado no hace nada. Está registrada en `migrations/engine.py` y documentada en `MIGRATION_LOG.md`.
- **Probada en memoria** sobre el catálogo sembrado. **No se corrió sobre una copia de la base real**: en este worktree no hay base, y no se tocó la carpeta principal.
- No se usaron 389, 390 ni 391.

## Resultados de pruebas
Todas desde `pos_spj_v13.4/`, con `QT_QPA_PLATFORM=offscreen` y `-p no:cacheprovider`.

| Segmento | Resultado |
|---|---|
| `python -m compileall -q .` | sin errores |
| Pedidos: `tests/integration/test_orders_delivery_*.py`, `tests/unit/test_orders_delivery_*.py`, `tests/integration/orders_delivery`, `tests/integration/logistics/test_driver_pwa_api.py` | 693 passed |
| `tests/integration/bootstrap` y `tests/integration/shell/test_desktop_shell_window_composition.py` | 51 passed |
| `tests/integration/finance`, `test_orders_delivery_driver_cash_finance.py`, `test_orders_delivery_settlement_use_cases.py`, `test_orders_delivery_outbox_dispatcher.py`, `tests/architecture/test_erp_chain_wiring_ratchet.py` | 253 passed |
| `tests/integration/cash_register`, `tests/integration/inventory`, `tests/integration/finance` | 981 passed |
| Ventas: `tests/unit/test_sales_*.py`, `tests/integration/test_sales_*.py`, `tests/integration/sales` | 581 passed, 3 failed (preexistentes, ver abajo) |
| Permisos y reversos: `test_permissions_audit_968e0bc.py`, guardias de autorización de Procesamiento, `test_sales_returns.py` | 80 passed |
| Sincronización: `tests/unit/central_sync`, `test_org_closure.py` | 36 passed |
| `tests/architecture/test_orders_single_pipeline_ratchet.py` | 2 passed |
| `tests/architecture` completo | 22 failed, 881 passed, 1 skipped, 2 xfailed (1596 s) |

## Arquitectura completa
Resultado: **22 failed, 881 passed, 1 skipped, 2 xfailed**. La línea base del 2026-10-28 daba 22 failed y 879 passed; los 2 passed de más son la guardia nueva de SDLC-ORD-003. Los 18 archivos con fallas aparecen todos en la línea base. La comparación se hizo por archivo, no caso por caso. Hay un caso a revisar: `test_design_system_guardrails.py` (deuda visual) puede contar el diálogo nuevo de SDLC-ORD-005. **No se verificó** contra la rama base.

## Fallos preexistentes (no los causa este lote)
- `tests/integration/test_sales_checkout_settles_everything.py`: 2 pruebas fallan con `no such column: sucursal_id`, igual en `5b4f4d5a` (verificado con stash). Es el grupo «fixtures sin `usuarios.sucursal_id`» de la línea base del 2026-10-28 (SDLC-CORE-011).
- `tests/unit/test_sales_pos_visual_validation.py::test_checkout_width_is_identical_at_both_resolutions`: `518 == 520`, una diferencia de geometría de 2 px. Sólo importa `sales_pos` y temas, y este lote no tocó ninguno de los dos (el diff de `frontend/` es Pedidos y la composición del shell). Es del mismo tipo que SDLC-UI-031. **No se verificó** corriéndola sobre la base.

## Hallazgos fuera de alcance (para el backlog)
- La reentrega no puede despacharse: el pedido queda `DISPATCHED` y `DispatchPolicy` exige `READY`.
- No hay caso de uso para cancelar un pedido.
- La UI de escritorio no llama a confirmar, reservar, proyectar ni cobrar un pedido. Sólo la PWA despacha, entrega y cobra.
- La venta de un pedido factura `line.product_id` aunque la línea se haya sustituido, y factura también las líneas rechazadas.
- `migrations/standalone/354_device_enrollment.py` no está en la lista de `migrations/engine.py`. Ya está en el backlog (SDLC-ARQ-TERM-005, SDLC-SYNC-001).
- La regla 12 de CLAUDE.md pide `financial_event_log`, pero el backend canónico no tiene ninguna referencia a esa tabla: el rastro es `journal_entries` más `finance_outbox`.
