# Appflow — Plataforma completa desde cero

El recorrido principal conserva el flujo cárnico solicitado. Los siguientes recorridos amplían CRM, web, WhatsApp, RR. HH., activos y BI, siempre usando un dueño por operación. Ver [catálogo](MODULE_CATALOG.md).

## 1. Recorrido operativo objetivo

```mermaid
flowchart TD
  A{"Origen comercial"} -->|OC aprobada| B["Compras: orden"]
  A -->|Directa| C["Compras: compra directa"]
  A -->|Sin documento| D["Logística: embarque provisional"]
  B --> E["Logística: carga y custodia"]
  C --> E
  D --> E
  E --> F["Recepción: conteo y calidad"]
  F --> G["Inventario: lote aceptado"]
  G --> H{"Transformación"}
  H -->|Sí| I["Producción: consumo y salidas"]
  H -->|No| J["POS: producto base"]
  I --> K["Inventario: cortes y costos"]
  K --> L["POS: venta por corte/bundle"]
  J --> M["Pago, caja y finanzas"]
  L --> M
```

El tramo **sin documento** es propuesto; el servicio actual `OriginPurchaseWorkspaceService.create_shipment` exige documento. No permite reconocer costo, CxP ni stock vendible hasta regularizar compra y recepción. El tramo de compra directa sí existe: documento confirmado, sin OC, y `fulfillment_mode` adecuado para recoger en origen.

## 2. Hitos y responsables

| Paso | Acción del operador | Regla/resultado | Código revisado |
| --- | --- | --- | --- |
| 1. Producto | Configurar unidad, tipo, rendimiento/esquema, precio por parte, impuestos | Versionar perfil; ninguna variación de precio altera venta pasada | `backend/infrastructure/db/schema/products_schema.py`, `pricing_schema.py` |
| 2. Compra | Crear/autorizar OC o compra directa; proveedor, líneas, costo y sucursal | El documento es fuente de verdad comercial | `backend/application/procurement/use_cases/purchase_order_use_cases.py`, `direct_purchase_use_cases.py` |
| 3. Carga | Crear embarque y asociar contenedores/líneas, pesos, foto, sello | Logística posee custodia física; no contabiliza stock | `backend/application/logistics/origin_purchase_workspace.py`, `backend/application/logistics/service.py` |
| 4. Llegada | Escanear y pesar; comparar con declarado; documentar discrepancia | Recepción acepta/rechaza/cuarentena; operación idempotente | `backend/application/procurement/use_cases/`, `backend/application/logistics/origin_purchase_workspace.py` |
| 5. Entrada | Aplicar evento de compra aceptada al ledger/lote | Una única ruta canónica, sin doble handler | `backend/bootstrap/wiring/event_wiring.py`, `backend/application/event_handlers/inventory/purchase_stock_entry_bridge.py` |
| 6. Transformación | Seleccionar lote, esquema, peso; registrar cortes, subproductos y merma reales | Consumir base, crear lotes salida, costo/genealogía en una operación | `backend/application/meat_processing/use_cases/order_execution_use_cases.py` |
| 7. Venta | Buscar/escáner, peso o piezas, cliente, precio vigente y disponibilidad | Reservar por producto/lote; aplicar protección de margen/beneficios | `backend/application/sales/use_cases/cart_use_cases.py`, `inventory_use_cases.py` |
| 8. Cobro | Elegir pagos; validar vale/cupón/puntos; confirmar | Registrar venta, pago, caja, eventos y ticket una vez | `backend/application/sales/use_cases/payment_use_cases.py`, `backend/application/cash_register/` |
| 9. Cierre | Corte X/Z, entrega y contabilización | Mostrar pendientes por evento y conciliación | `backend/application/cash_register/z_cut_use_cases.py`, `backend/application/event_handlers/finance/` |

## 3. Decisiones y excepciones

**Compra sin PO:** el usuario registra compra directa, la confirma y selecciona «recoger en proveedor». El documento habilita carga/recepción. Un embarque provisional sin ningún documento requiere nuevo flujo de conciliación; no convertir un embarque en una compra implícita.

**Recepción desde Compras o Transferencias:** ambas vistas pueden iniciar la misma acción de recepción si el origen es diferente; el inventario debe reconocer `source_type`, `source_id`, `operation_id` y la línea de recepción. La recepción de transferencia pertenece a su caso de uso; la UI actual debe comprobarse antes de prometer esa ruta integrada.

**Cuarentena:** la existencia física puede estar presente sin ser vendible. Calidad decide liberar o rechazar; sólo entonces cambia disponibilidad.

**Producción directa:** la misma política de consumo/salidas admite entrada desde una orden o desde «Transformar ahora»; no crear un segundo motor de producción. Calcular salida prevista por perfil (%) y comparar con peso real. Ejemplo: 100 kg entrada, cortes 35/25/12/20 kg y 8 kg merma; reconciliar costo de 100 kg entre salidas, merma y variaciones aprobadas.

**Reconstrucción:** si se venderá una presentación física del producto base, confirmar que cada componente está disponible, consumirlos y crear base con trazabilidad. Para vender un paquete comercial de cortes, reservar y descargar los cortes como bundle virtual. La rama tiene `ReconstructBaseProductUseCase` y un top-up desde POS; hay que probar atomicidad ante fallo intermedio antes de activarlo para cierre real.

**Política de beneficios:** no cobrar dos veces ni canjear dos veces un cupón. Vales de varios usos consumen saldo según porcentaje configurado y límite financiero por evento; cupones de un uso pasan a consumido atómicamente. Devolución revierte inventario, caja/medio de pago, puntos y asiento con referencia a la venta original.

## 4. Estados que deben aparecer en pantalla

| Objeto | Estados mínimos de recorrido | Condición de salida |
| --- | --- | --- |
| Compra | Borrador → aprobada/confirmada → recibida parcial/completa → conciliada | Diferencias y factura resueltas. |
| Embarque | Borrador → carga → sellado → en tránsito → llegado → recibido/cerrado | Custodia transferida, conteo y discrepancias. |
| Lote | Pendiente/calidad → disponible/reservado → consumido/vendido | Ledger y trazabilidad íntegros. |
| Producción | Borrador → en ejecución → salida capturada → conciliada/cerrada | Masa y costo dentro de política. |
| Venta | Activa → checkout → pago pendiente → completada/devuelta | Reserva y pagos confirmados; eventos entregables. |
| Caja | Abierta → conteo → corte → entrega/cerrada | Diferencias autorizadas y finanzas notificadas. |

Los nombres exactos de enum/DB deben cotejarse antes de implementar transiciones; la tabla expresa el recorrido que el usuario necesita.

## 5. Riesgos actuales que bloquean el recorrido

1. `frontend/desktop/modules/meat_processing/dialogs.py` obtiene producto desde la opción seleccionada al cerrar; el selector puede perder su selección al refrescar. Conservar `product_id` capturado y validar antes de aceptar.
2. En el cálculo de producción, un esquema de corte expresa `quantity` como factor mientras el perfil expone porcentaje de rendimiento; verificar coherencia de fórmula y unidad antes de sugerir kilos.
3. `backend/bootstrap/wiring/event_wiring.py` deja fuera `wire_logistics()`. Una clase y eventos existentes no prueban integración viva.
4. Una recepción puede alimentar rutas distintas de inventario si se activa además el cutover adicional. Probar exactamente un movimiento por línea aceptada.
5. `backend/application/logistics/origin_purchase_workspace.py::receive_and_close` deriva un UUID5 para una operación; alinear con el contrato de UUIDv7/idempotencia sin perder el vínculo al evento original.

## 6. Prueba end-to-end exigida

En DB nueva y usuario acotado: comprar 100 kg directamente sin OC → cargar 1 contenedor → despachar y recibir 98 kg, rechazar 2 kg → inventario 98 kg aceptados → transformar 90 kg con 4 cortes y merma → vender 1 corte por peso y un bundle → pagar parcialmente en efectivo y otro medio → emitir ticket → corte Z → verificar sumas de ledger, asientos balanceados, costo/genealogía, outbox sin pendientes permanentes y ausencia de doble registro al reintentar cada comando. Repetir con calidad bloqueada, permiso denegado y red desconectada.

## 7. Captación y venta omnicanal

```mermaid
flowchart TD
  A["Lead web / WhatsApp / mostrador"] --> B["CRM: identidad y consentimiento"]
  B --> C["Actividad y oportunidad"]
  C --> D["Cotización: precio y disponibilidad"]
  D --> E{"Confirmación"}
  E -->|Pedido entrega| F["Reserva y delivery"]
  E -->|Tienda| G["POS y caja"]
  F --> H["Entrega, cobro y evidencia"]
  G --> I["Finanzas y fidelidad"]
  H --> I
```

El chat puede sugerir productos, pero no compromete precio, stock ni crédito sin respuesta de la API ERP. Convertir cotización conserva versión y genera un solo pedido/venta. Una devolución anula efectos financieros y de beneficios según política; no borra actividad CRM.

## 8. WhatsApp: mensaje a pedido

Webhook firmado → inbox duradera → deduplicación por ID Meta → identidad E.164/consentimiento → conversación → catálogo/precio desde API → borrador → confirmación explícita → CreateOrder idempotente → acuse por outbox → actualización de estado de entrega → handoff si hay incertidumbre. Si ERP está caído, guardar borrador/petición pendiente y avisar al operador; jamás confirmar un pedido inexistente. Campaña masiva exige plantilla aprobada, consentimiento por finalidad, aprobación y presupuesto.

## 9. Web Compras, Finanzas y BI

**Compras:** forecast produce sugerencia → comprador edita/requisita → aprobador distinto valida → cotizaciones comparadas → adjudicación → OC o compra directa → recepción con tolerancias → factura comparada → CxP o excepción. La web usa exactamente el mismo caso de uso de recepción que el escritorio/móvil, con permiso y alcance iguales.

**Finanzas:** evento operativo confirmado → regla posting versionada → asiento propuesto → balanceado y periodo abierto → contabilizado → extracto bancario/caja → match → conciliado. Falla de regla produce excepción visible y retry idempotente; no pérdida silenciosa. Cierre bloquea posting posterior salvo reapertura autorizada.

**BI:** proyección desde outbox/ledgers → actualización de watermark → métrica certificada → filtro RLS → drill-down → documento origen. Dashboard advierte sucursales desactualizadas y no suma pendientes como ventas finales.

## 10. Personas, activos y servicio

**RR. HH.:** alta empleado → asignación puesto/sucursal → programación turno → asistencia validada → incidencias aprobadas → nómina calculada → autorización segregada → pago/finanzas → recibo restringido. Abrir caja no sustituye por sí solo un registro de jornada si la política laboral difiere.

**Activos:** adquisición → alta con número y responsable → mantenimiento preventivo/correctivo → movimiento/custodia → depreciación financiera → baja autorizada. Un contenedor reusable puede ser activo bajo política contable, pero logística conserva su ciclo físico y finanzas su valor.

**Servicio/devolución:** queja o devolución desde CRM/WhatsApp/POS → verificación venta/lote → autorización y evidencia → retorno físico/cuarentena → reintegro o nota de crédito → reversa fidelidad/IVA/costo según caso → seguimiento y cierre.

## 11. Errores, offline y compensación

| Escenario | Estado visible | Acción de recuperación |
| --- | --- | --- |
| Red cae tras cobro local | Venta confirmada local / pendiente central | Reintento mismo `operation_id`; conciliador investiga ACK, no segundo cargo. |
| Cupón único sin autoridad central | Bloqueado o cupo previamente asignado | Nunca aceptar dos canjes globales por last-write-wins. |
| Producción falla tras consumo | Transacción revertida o estado pendiente compensable | Reversar movimiento y evitar salida parcial. |
| Webhook Meta duplicado | Ya procesado | Responder éxito sin nuevo pedido/mensaje. |
| Diferencia recepción | Incidencia abierta | Cantidad aceptada a stock; rechazo/cuaren. separado. |
| Asiento no generado | Documento válido / contabilidad pendiente | DLQ/retry con alerta y misma clave de posting. |

Estas rutas necesitan pruebas E2E por desktop/web/móvil y pruebas de contract versionado. La secuencia de implementación está en [plan de entrega](DELIVERY_PLAN.md).
