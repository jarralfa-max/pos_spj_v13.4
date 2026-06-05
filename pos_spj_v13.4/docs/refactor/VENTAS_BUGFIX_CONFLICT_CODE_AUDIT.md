# VENTAS_BUGFIX_CONFLICT_CODE_AUDIT

## Fase 0 — Mapeo de código conflictivo

| Archivo | Método/Sección | Problema | Conflicto | Acción | Fase |
|---|---|---|---|---|---|
| `pos_spj_v13.4/modulos/ventas.py` | `calcular_totales` | UI recalcula subtotal/total/puntos preview | Duplica fuente de verdad backend | Reemplazar uso post-cobro por resultado canónico | 3 |
| `pos_spj_v13.4/modulos/ventas.py` | `_on_checkout_success` | reconstruye `datos_ticket` desde `compra_actual`/`totales` snapshot | Puede no coincidir con venta persistida | Reemplazar por `ticket_payload` del backend | 3 |
| `pos_spj_v13.4/modulos/ventas.py` | `_imprimir_ticket_consolidado`, `_imprimir_ticket_legacy_real` | rutas de impresión paralelas/legacy | Inconsistencia de errores y éxito | Consolidar vía PrinterService + resultado real | 4 |
| `pos_spj_v13.4/modulos/ventas.py` | `guardar_ticket_pdf`, `_guardar_ticket_pdf_async` | PDF generado desde datos reconstruidos UI | Riesgo de divergencia | Generar desde `ticket_payload` canónico | 4 |
| `pos_spj_v13.4/modulos/ventas.py` | `obtener_stock_producto`, `agregar_al_carrito`, `suspender_venta` | consulta/reserva stock dispersa en UI | Diferente fuente de stock | Mantener lectura UI, mover decisión transaccional al backend | 5 |
| `pos_spj_v13.4/modulos/ventas.py` | `procesar_pago` validación crédito | validación previa en UI | potencial divergencia backend | mantener UX pero backend manda | 2 |
| `pos_spj_v13.4/modulos/ventas.py` | `DialogoPago.get_datos_pago` | armado DTO pago en UI | mezcla reglas de dominio | normalizar y validar en backend | 2 |
| `pos_spj_v13.4/modulos/ventas.py` | `cancelar_venta`/post-success | limpieza carrito acoplada a errores postventa | puede mostrar “fallida” tras commit | separar resultado de persistencia vs post-commit | 3 |
| `pos_spj_v13.4/modulos/ventas.py` | varios `except ...: pass` (ej. 2692, 3818, 4166, 4496) | silencian fallos críticos | oculta bugs reales | reemplazar por warning/error explícito | 4 |
| `pos_spj_v13.4/core/services/sales_service.py` | `execute_sale` | aplica normalizaciones/promos/puntos/eventos y retorna tuple incompleto | UI no recibe desglose real | introducir `execute_sale_result` canónico | 1-2 |
| `pos_spj_v13.4/core/services/sales_service.py` | publicación de eventos | efectos postventa mezclados con retorno mínimo | trazabilidad parcial | mantener eventos pero enriquecer resultado | 2 |
| `pos_spj_v13.4/core/use_cases/venta.py` | `ejecutar` | consulta `venta_id` por folio; no propaga operation_id/loyalty/payment breakdown | pérdida de datos reales | consumir `execute_sale_result` | 1-3 |
| `pos_spj_v13.4/core/use_cases/venta.py` | fallback de ticket en UC | regenera ticket con totales estimados | posible mismatch vs venta guardada | usar ticket_html/payload real | 3 |
| `pos_spj_v13.4/core/services/printer_service.py` | `print_ticket` + cola | validaciones blandas y múltiples `pass` en carga/config | errores no propagados uniformemente | endurecer contrato de error y status | 4 |
| `pos_spj_v13.4/core/services/stock_reservation_service.py` + eventos `inventory_handler/wiring` | reserva enfocada a suspensión/confirmación diferida | semántica de confirmación/liberación ambigua | riesgo de stock inconsistente | formalizar estados de reserva y confirmación | 5 |

> Nota: este documento es inventario técnico de conflictos detectados para guiar refactor seguro por fases.
