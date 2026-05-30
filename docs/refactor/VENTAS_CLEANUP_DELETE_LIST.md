# Ventas cleanup delete list

Inventario quirúrgico creado antes de aplicar cambios de fases 1-9.

| Archivo | Función/método | Líneas aprox. | Problema | Acción | Prueba |
|---|---|---:|---|---|---|
| `pos_spj_v13.4/modulos/ventas.py` | `_aplicar_resultado_venta` | 4156-4240 | Reconstruía ticket postventa desde UI si faltaba `ticket_payload`, usando cliente/cache y totales derivados. | DELETE/REPLACE | `test_ticket_requires_backend_payload`, `test_no_ticket_from_compra_actual_after_sale` |
| `pos_spj_v13.4/modulos/ventas.py` | `_aplicar_resultado_venta` | 4170-4182 | Convertía puntos faltantes a `0` y actualizaba `cliente_actual['puntos']` como saldo real. | REPLACE | `test_loyalty_none_does_not_display_zero`, `test_customer_cache_updated_only_with_real_balance` |
| `pos_spj_v13.4/modulos/ventas.py` | `finalizar_venta` | 3975-4023 | Mercado Pago pendiente generaba link sin reserva y luego limpiaba carrito. | REPLACE | `test_mp_pending_creates_reservation` |
| `pos_spj_v13.4/modulos/ventas.py` | `finalizar_venta` | 4080-4101 | Usaba `QThread` + `SaleCheckoutWorkerFactory` para venta transaccional con servicios clonados superficialmente. | BLOCK | `test_sale_does_not_use_shallow_cloned_worker` |
| `pos_spj_v13.4/modulos/ventas.py` | `_aplicar_resultado_venta` | 4203-4216 | Confirmaba reserva después de imprimir y podía convertir venta exitosa en fallo. | REPLACE | `test_reservation_failure_after_sale_does_not_mark_sale_failed` |
| `pos_spj_v13.4/modulos/ventas.py` / `core/services/sales_service.py` | `procesar_pago` / `_execute_sale_core` | 3860-3970 / 560-582 | `pass` silenciosos en validación de caja, crédito y margen/costo podían permitir vender sin guardrail confiable. | REPLACE/BLOCK | `test_cash_shift_validation_error_blocks_or_warns_explicitly`, `test_credit_validation_error_not_silent`, `test_margin_validation_error_blocks_sale_explicitly` |
| `pos_spj_v13.4/core/use_cases/venta.py` | `ejecutar` | 210-223 | Normalización recreaba `DatosPago` y perdía `pago_mixto`, sucursal, usuario y metadatos. | REPLACE | `test_payment_breakdown_preserved_to_ticket_payload` |
| `pos_spj_v13.4/core/use_cases/venta.py` | `ejecutar` | 302-321 | Ruta legacy `execute_sale` + SQL por folio para recuperar `venta_id`. | BLOCK | `test_legacy_venta_repository_write_blocked` |
| `pos_spj_v13.4/core/use_cases/venta.py` | `ejecutar` | 351-384 | Fallback generaba ticket con `items` originales del UC. | DELETE | `test_no_ticket_from_uc_original_items` |
| `pos_spj_v13.4/core/use_cases/venta.py` | `ejecutar` | 329-344 | Fallback de fidelidad convertía saldo no disponible a cero. | REPLACE | `test_loyalty_none_does_not_display_zero` |
| `pos_spj_v13.4/core/services/sales_service.py` | `_execute_sale_core` | 421-438 | Comentario y comportamiento permitían `SALE_ITEMS_PROCESS` sin handlers como no-op. | BLOCK | `test_sale_fails_without_inventory_handler`, `test_sale_fails_without_finance_handler`, `test_sale_items_process_not_noop_in_production` |
| `pos_spj_v13.4/core/services/sales_service.py` | `_execute_sale_core` | 499 | `loyalty_result` iniciaba ceros falsos como datos reales. | REPLACE | `test_ticket_does_not_print_fake_zero_points` |
| `pos_spj_v13.4/core/services/sales_service.py` | `_execute_sale_core` | 613-646 | `Pago Mixto` caía a efectivo y método desconocido caía a efectivo con `_map.get`. | REPLACE | `test_pago_mixto_not_mapped_to_cash`, `test_unknown_payment_method_fails` |
| `pos_spj_v13.4/core/services/sales_service.py` | `create_pending_payment_sale` | 178-225 | Intención Mercado Pago pendiente no reservaba stock. | REPLACE | `test_mp_pending_creates_reservation`, `test_mp_pending_cancel_releases_reservation` |
| `pos_spj_v13.4/presentation/sales/workers/sale_checkout_worker_factory.py` | `_clone_uc` | 25-57 | `copy.copy` de servicios y reemplazo parcial de `db`; dependencias internas quedaban con conexión vieja. | DELETE/BLOCK | `test_sale_checkout_factory_disabled_or_removed` |
| `pos_spj_v13.4/presentation/sales/workers/sale_checkout_worker.py` | `run` | 32-47 | Venta transaccional en QThread sin container por hilo real. | KEEP TEMPORARILY (no usado por UI) | `test_sale_transaction_uses_single_db_connection` |
| `pos_spj_v13.4/repositories/ventas.py` | `VentaRepository.create_sale` | 117-130 | Ruta legacy directa para escribir ventas fuera de `SalesService`. | BLOCK | `test_legacy_venta_repository_write_blocked` |

| `pos_spj_v13.4/core/services/sales_service.py` | `procesar_venta` | 1083-1165 | API legacy compatible con `UnifiedSalesService` mantenía ruta paralela fuera del UC oficial. | BLOCK | `test_sales_service_procesar_venta_legacy_blocked_by_default` |
| `pos_spj_v13.4/core/services/sales_service.py` | `_procesar_venta_legacy_minimal` | 1270-1350 | Fallback escribía `ventas`, `detalles_venta`, caja, inventario y puntos directamente, generando ticket_data desde items originales. | BLOCK | `test_legacy_minimal_sale_write_blocked_by_default`, `test_no_legacy_ticket_path_active` |
| `pos_spj_v13.4/core/services/sales/unified_sales_service.py` | `UnifiedSalesService.procesar_venta` | 73-126 | Servicio legacy rearmaba UC/servicios y mantenía entrada paralela a ventas. | BLOCK | `test_legacy_unified_sales_service_blocked_by_default` |
