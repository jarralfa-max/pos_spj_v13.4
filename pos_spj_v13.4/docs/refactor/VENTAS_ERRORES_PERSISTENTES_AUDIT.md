# Auditoría FASE 0 — Errores persistentes vivos en ventas

Fecha: 2026-05-28
Alcance: diagnóstico sin cambios funcionales de código.

## Resumen ejecutivo

Se identificaron rutas conflictivas activas que explican los síntomas reportados: pérdida de datos de `SaleExecutionResult` en `ProcesarVentaUC`, reconstrucción de ticket/postventa desde estado local de UI, éxito falso de impresión al ignorar `PrintTransport.send()==False`, liberación de reserva con estado ambiguo, posible bloqueo de UI en rutas Mercado Pago y uso de UC con dependencias potencialmente no thread-safe dentro de `QThread`.

---

## Hallazgos detallados

| ID | Archivo | Método / zona (línea aprox.) | Bug vivo | Impacto | Corrección propuesta | Fase |
|---|---|---|---|---|---|---|
| H01 | `core/services/sales/sale_execution_result.py` | dataclasses (`SaleExecutionResult`) ~46-60 | El resultado rico **sí existe** (`operation_id`, `ticket_payload`, `payment`, `loyalty`, `warnings`). | Base correcta, pero no llega completa a UI. | Usarlo como fuente primaria end-to-end. | 1-2 |
| H02 | `core/use_cases/venta.py` | `ResultadoVenta` ~133-145 | `ResultadoVenta` no contiene `ticket_payload`, `payment_breakdown`, `loyalty_result`, `warnings`. | Pérdida estructural de datos backend al salir del UC. | Extender dataclass y mapear todos los campos ricos. | 1 |
| H03 | `core/use_cases/venta.py` | `ProcesarVentaUC.ejecutar` ~250-266 | Con `execute_sale_result()` solo mapea `folio/ticket_html/venta_id/total`; pierde `operation_id/payment/loyalty/ticket_payload/warnings`. | UI no puede usar verdad backend completa post-commit. | Mapear `rich.*` completo y propagar advertencias. | 1 |
| H04 | `core/use_cases/venta.py` | `ProcesarVentaUC.ejecutar` ~295-297 | Fuerza `puntos_ganados=0`, `puntos_totales=0`, `nivel_cliente='Bronce'`. | UI muestra puntos inconsistentes aunque backend tenga datos reales. | Tomar puntos de `rich.loyalty`; fallback a saldo real con warning. | 1 |
| H05 | `modulos/ventas.py` | `_on_checkout_success` ~4128-4149 | Reconstruye ticket desde `_items_snapshot=list(self.compra_actual)` y `_totales_snapshot=dict(self.totales)`. | Ticket puede divergir de venta persistida. | Aplicar resultado desde `result.ticket_payload`; fallback mínimo desde `result`. | 2 |
| H06 | `modulos/ventas.py` | `_on_checkout_success` ~4132 | Usa `'venta_id': folio`. | Identificador incorrecto; puede romper trazabilidad/reimpresión. | Usar `result.venta_id`. | 2 |
| H07 | `modulos/ventas.py` | `_on_checkout_success` ~4151-4155 | Toast usa `self.totales['total_final']` postventa. | Monto mostrado puede no coincidir con total backend real. | Usar `result.total`. | 2 |
| H08 | `modulos/ventas.py` | `_on_checkout_success` ~4094-4118 | Puntos UI se calculan con `puntos_resultado` local y fallback parcial; depende de campos legacy `_r.puntos_*`. | Riesgo de mostrar saldo dummy/cache no real. | Consumir `result.loyalty_result`; si incompleto consultar `loyalty_service.saldo(cliente_id)`. | 2 |
| H09 | `core/services/printer_service.py` | `PrintQueue._worker` ~271-274 | Ignora retorno de `PrintTransport.send(...)`; marca éxito siempre si no lanza excepción. | Éxito falso de impresión; ticket no sale y sistema reporta OK. | Fallar job cuando `send()` devuelva `False`. | 3 |
| H10 | `core/services/printer_service.py` | callbacks en `_worker` ~279-282, 311-314, bus publish ~295-296/326-327 | `except Exception: pass` en callbacks/eventos críticos. | Silencia errores operativos, difícil diagnóstico. | Reemplazar por `logger.exception(...)` y manejo explícito. | 3 |
| H11 | `core/services/printer_service.py` | `_load_configs`/init ~390-394, 420-433 | Múltiples `pass` silenciosos al cargar config/bus. | Fallas de configuración quedan ocultas. | Loggear y devolver validación detallada. | 3 |
| H12 | `core/services/printer_service.py` | `has_ticket_printer`/`validate_ticket_printer_config` ~585+ | Validación aparentemente insuficiente (según síntoma y uso en UI). | Puede anunciar impresora disponible sin disponibilidad real transporte. | Hacer que `has_ticket_printer` dependa de validación real de transporte. | 3 |
| H13 | `modulos/ventas.py` | `finalizar_venta` ~4048 | Para no-efectivo, `monto_pagado` se fuerza con `self.totales['total_final']`. | Desglose de pago (mixto/tarjeta/transferencia/crédito) se degrada. | Propagar breakdown real del diálogo al UC/backend. | 4 |
| H14 | `core/services/sales_service.py` | mapeo de pago en payload ticket ~626+ | Mapeo de método sensible a variantes de texto/acento (riesgo reportado). | Crédito podría caer en bucket incorrecto (efectivo). | Normalización robusta acento/case para `credito`. | 4 |
| H15 | `core/services/stock_reservation_service.py` | `liberar` ~159-164 | Estado se guarda como `liberada:{motivo}`; hoy se usa `motivo='confirmada'` desde UI. | Estado ambiguo/conflictivo (`liberada:confirmada`). | Introducir `confirmar(reserva_id, venta_id, folio)` con estado `confirmada`. | 5 |
| H16 | `modulos/ventas.py` | `_on_checkout_success` ~4156-4158 | Al cobrar venta reanudada hace `liberar(..., motivo='confirmada')`. | Inconsistencia semántica reserva vs venta confirmada. | Confirmar reserva, no liberarla. | 5 |
| H17 | `modulos/ventas.py` | `finalizar_venta` MercadoPago ~3976-4013 | Ruta MP retorna temprano; depende de señal `finished` para desbloqueo. Riesgo de bloqueo en rutas de error/cancelación parciales. | Botón cobrar/flag `_venta_checkout_running` puede quedar mal en ciertos retornos. | Garantizar cleanup en todas rutas (`finally` / `_on_checkout_finished`). | 6 |
| H18 | `presentation/sales/workers/sale_checkout_worker.py` | `run` ~25 | Worker ejecuta `uc_venta.ejecutar()` en QThread con UC inyectado desde contenedor UI (potencial misma conexión SQLite). | Error intermitente SQLite por hilo compartido. | Worker factory con conexión/container propio por hilo o guardrail thread-safe. | 7 |
| H19 | `modulos/ventas.py` | `finalizar_venta` ~4050-4054 | Se mueve worker a `QThread` pero no se evidencia aislamiento de conexión DB. | Riesgo de cross-thread DB access. | Instrumentar thread-id/conn-id + separar conexión. | 7 |
| H20 | `core/events/wiring.py` y `modulos/ventas.py` | múltiples bloques con `except Exception: pass` (~56, ~211, ~387, ~486, ~515, etc.; ventas ~4165-4166, ~4496) | `pass` en caminos de negocio/observabilidad. | Oculta fallas críticas (inventario/loyalty/eventos). | Sustituir por logging estructurado y tratamiento según criticidad. | 8 |

---

## Cobertura pedida en FASE 0

1. **Dónde se usa `SaleExecutionResult`:** `core/services/sales_service.py::execute_sale_result()` y dataclass en `core/services/sales/sale_execution_result.py`.  
2. **Dónde se pierde información:** `core/use_cases/venta.py::ProcesarVentaUC.ejecutar()` al mapear parcial.  
3. **No propagación en UC (`operation_id`, `ticket_payload`, `payment`, `loyalty`, `warnings`):** mismo bloque ~250-266 y `ResultadoVenta` ~133-145.  
4. **UI usando `compra_actual`/`self.totales`/`cliente_actual`/`folio como venta_id`:** `_on_checkout_success` ~4128-4137, ~4154, ~4132, ~4135.  
5. **Ticket armado con datos locales:** `datos_ticket` en `_on_checkout_success` ~4130-4146.  
6. **Puntos desde dummy/cache:** `_on_checkout_success` `puntos_resultado` local ~4094-4118.  
7. **Dónde se valida/imprime ticket:** `modulos/ventas.py` usa `ps.has_ticket_printer()` (~2254, ~4230, ~4618, ~4632) y `_imprimir_ticket_consolidado`; `PrinterService.validate_ticket_printer_config()` ~588+.  
8. **`PrinterService` trata `False` como éxito:** `PrintQueue._worker` ~271-274.  
9. **Reserva/liberación/confirmación stock:** `stock_reservation_service.py::reservar` y `liberar`; UI confirma venta llamando `liberar(..., 'confirmada')` ~4157.  
10. **Mercado Pago bloquea UI:** `finalizar_venta` ruta MP ~3976-4013 con returns tempranos.  
11. **SQLite en worker/QThread:** `SaleCheckoutWorker.run` ~25 y armado de hilo en `ventas.py` ~4050-4054.  
12. **`pass` críticos:** múltiples en `printer_service.py`, `wiring.py`, `ventas.py`, `stock_reservation_service.py`, `sales_service.py`.

---

## Riesgos transversales detectados

- El sistema mezcla “éxito de venta” con “éxito de post-procesos” (impresión/PDF/refresh), lo que puede producir mensajes erróneos de falla global.  
- Estados de reserva no normalizados complican conciliación de inventario.  
- Falta trazabilidad por silenciamiento de excepciones.

---

## Plan de corrección por fases (siguiente paso)

- **Fase 1:** Propagación completa de `SaleExecutionResult` en UC + tests de mapeo.  
- **Fase 2:** Limpieza postventa UI para depender solo de `ResultadoVenta` enriquecido.  
- **Fase 3+:** Impresión robusta, pagos/crédito, reservas, MP, QThread/SQLite y eliminación de legado conflictivo.

