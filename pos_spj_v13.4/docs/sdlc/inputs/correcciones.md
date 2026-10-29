# Correcciones solicitadas por el responsable — entrada para `/sdlc-plan`

- **Origen:** `docs/audits/auditoria_integral_produccion_recepcion_transferencias_productos_precios_2026-10-26.md` (auditada en `ee449a82`; el triage del 2026-10-28 confirmó que sus archivos no cambiaron hasta `16eb1d8e`).
- **Responsable:** Alfred.
- **Uso:** Claude Code aplica el Modo B de `/sdlc-plan` a cada punto. Si un punto ya existe en `BACKLOG.md` (el triage ya leyó esta auditoría; por ejemplo SDLC-TRF-001, SDLC-PROC-001, SDLC-PROC-002), **actualiza ese ítem** con lo que aquí se agrega en lugar de crear otro. Los IDs de abajo son provisionales; si hay un ítem equivalente, manda el ID existente.
- **Regla de verificación:** cada punto se vuelve a comprobar en el código actual con ruta:línea antes de escribir el intent. Si algo ya está corregido, se marca `descartado` con la evidencia.

## Orden de trabajo (oleadas)

| Oleada | Puntos | Por qué en este orden | ¿Espera a `/sdlc-plan arquitectura`? |
|---|---|---|---|
| 0 | C-00 | Pruebas de protección antes de tocar nada en recepción, producción y precios | No |
| 1 | C-01, C-02, C-04, C-05 | Recibir bien el producto de peso variable, que llegue al almacén correcto, unidades exactas y precio que no cambie en silencio. Bloquean el flujo real o ponen dinero en riesgo | No (se pueden diseñar ya) |
| 2 | C-09 | Bandeja única de recepciones, sobre C-01 ya corregido | No |
| 3 | C-03, C-06 | Coordinador recepción → despiece con idempotencia y conciliación de estimados. Usan outbox, operation_id y política offline | **Sí**: diseñar después de la matriz de brechas (idempotencia, sincronización, autoridad por entidad) |
| 4 | C-07, C-08 | Revisión puntual de precios y lista por cliente; requieren decisiones de negocio | C-08 sí (permisos granulares y RBAC canónico) |
| 5 | C-10, C-11 | Destinatarios de alertas y ficha guiada de producto | C-10 sí (RBAC y alcance por sucursal) |

## Puntos

### C-00 — Pruebas de protección del flujo actual
- **Prioridad / nivel:** P0 · T0 · área PROD/TRF/PROC/PRICE
- **Qué:** pruebas que fijen el comportamiento actual antes de cambiarlo: un recibo aceptado produce exactamente una entrada; una transformación produce un consumo y sus salidas; una venta consume solo los SKU reservados; precio resuelto actual por base/canal/cliente/volumen.
- **Nota:** el entorno de pruebas necesita `argon2-cffi`; sin él falla la construcción del POS y la ruta de cobro queda sin validar (auditoría §8). Incluirlo como dependencia de prueba es parte de este ítem.
- **Depende de:** nada.

### C-01 — La recepción de transferencias no captura peso, piezas, lote, temperatura ni caducidad
- **Prioridad / nivel:** P0 · T0 · TRF
- **Evidencia (auditoría §3):** `frontend/desktop/modules/transfers/dialogs/cycle_dialogs.py::ReceiveTransferDialog`; `backend/application/transfers/cycle_service.py::receive` arma `ReceiveTransferLineCommand` con peso/piezas en cero; `ConfirmTransferReceiptUseCase` rechaza `catch_weight` con cero y exige lote según perfil.
- **Resultado esperado:** recibir una canal entera desde la pantalla con neto observado, piezas, lote, fecha y temperatura según el perfil del producto; recepción completa y parcial correctas; rechazo y cuarentena no pasan a venta.
- **Aceptación:** prueba UI → comando → ledger para completa y parcial; 100 kg enteros de planta a POS.
- **Depende de:** C-00.

### C-02 — El almacén por defecto de la transferencia no alimenta el despiece
- **Prioridad / nivel:** P0 · T0 · TRF/PROD
- **Evidencia:** `transfers_inventory_gateway.py::_destination` cae a almacén `PURCHASE`; `direct_transformation_query_service.py::lots` solo lee almacenes `PRODUCTION`.
- **Resultado esperado:** el almacén destino se elige explícitamente al recibir; si difiere del de producción, movimiento interno autorizado y trazable. Nunca saldo modificado desde UI ni doble recepción.
- **Depende de:** C-01.

### C-03 — No hay coordinación durable entre recepción y transformación
- **Prioridad / nivel:** P0 · T0 · PROD
- **Evidencia:** `DirectTransformationPage` es una acción separada; `ExecuteDirectTransformationUseCase` hace commits entre etapas, fuera de la transacción de Compras/Transferencias.
- **Resultado esperado:** petición de transformación única por `receipt_line_id + inventory_lot_id + yield_version_id + logical_attempt`, con estados visibles `RECIBIDO`, `PENDIENTE_DE_LOTE`, `ESPERA_CALIDAD`, `PENDIENTE_DE_MOVIMIENTO`, `TRANSFORMANDO`, `COMPLETADO`, `ERROR_REINTENTABLE`. Reutilizar outbox, bus y composition root. Reintentos y reinicios no duplican consumo, lotes ni costo.
- **Decisión requerida:** política por destino `NEVER` / `OFFER_AFTER_RECEIPT` / `AUTO_ESTIMATE_AFTER_RECEIPT` con alcance producto + sucursal + almacén + origen. ¿Qué productos y sucursales usan cada una?
- **Depende de:** C-01, C-02, C-04 y de los ítems de arquitectura de idempotencia/outbox.

### C-04 — Unidades y precisión en la disponibilidad productiva
- **Prioridad / nivel:** P0 · T0 · PROD/INV
- **Evidencia:** `direct_transformation_query_service.py::lots` suma `inventory_balances.quantity` con `CAST(... AS REAL)` y lo presenta como `available_kg`.
- **Resultado esperado:** unidad base, unidad inventariable, piezas y peso neto definidos por producto; consultas con Decimal y conversión explícita; si falta peso neto en un perfil expresado en kg, se bloquea el despiece automático y se pide pesaje.
- **Depende de:** C-00.

### C-05 — El POS puede cobrar el precio de catálogo en silencio cuando falla el motor de precios
- **Prioridad / nivel:** P0 · T0 · PRICE/SALES
- **Evidencia:** `PricingReadFacade.sale_price_amount` y `SalesPricingClient.effective_price` devuelven solo el número; `backend/application/sales/pricing_resolution.py` atrapa cualquier excepción y regresa `None`, lo que lleva al precio de catálogo; `below_minimum` se pierde.
- **Resultado esperado:** resultado de precio con origen, versión, mínimo y estado; distinguir "sin precio configurado" de "falló el motor"; ante error o precio bajo el mínimo, bloquear o pedir autorización registrada.
- **Decisión requerida:** ante falla del motor, ¿se bloquea la venta o se permite con autorización de supervisor?
- **Depende de:** C-00.

### C-06 — Rendimiento estimado: venta, pesaje posterior y conciliación
- **Prioridad / nivel:** P1 · T0 · PROD/INV
- **Evidencia:** `DirectTransformationDialog` copia porcentajes; `order_execution_use_cases.py` guarda `weight_source=ESTIMATED` y mueve inventario con kg estimados.
- **Resultado esperado:** venta de saldo estimado solo según configuración y tolerancia; pesaje posterior por lote/corte con movimientos compensatorios auditados, sin sobrescribir la genealogía.
- **Decisiones requeridas:** ¿se permite vender cortes estimados antes de pesar? ¿con qué tolerancia?
- **Depende de:** C-03.

### C-07 — Cambiar un solo precio obliga a duplicar toda la lista
- **Prioridad / nivel:** P1 · T1 · PRICE
- **Evidencia:** `PriceList.is_editable` solo en borrador/revisión; `product_prices_page.py::_edit` duplica la lista completa; `UNIQUE(price_list_id, product_id, branch_id)` impide versiones por línea.
- **Resultado esperado:** "Cambiar precio" en lista aprobada crea una revisión de esa línea con vigencia, motivo, autor, aprobador y mínimo; sin reescribir el histórico; consulta canónica elige la versión vigente sin traslapes. Requiere migración de esquema (T0 para la migración).
- **Depende de:** C-05.

### C-08 — Asignación de lista de precios por cliente ambigua
- **Prioridad / nivel:** P1 · T1 · PRICE/CRM
- **Evidencia:** `PricingRepository.assign_customer_list` es `INSERT OR IGNORE` sin caso de uso ni UI; `customer_price_list` admite varias listas; `customer_list_id` usa `LIMIT 1` sin orden.
- **Resultado esperado:** una asignación vigente por cliente/sucursal/canal con altas, reemplazos y bajas bajo el permiso `PRECIOS.lista.cliente.asignar`, fechas y auditoría; una sola regla de prioridad.
- **Decisiones requeridas:** ¿el precio por volumen reemplaza o complementa el precio negociado? ¿el descuento global se suma al precio de cliente?
- **Depende de:** C-07 y de los ítems de arquitectura de permisos.

### C-09 — Bandeja única de recepciones (compras y transferencias)
- **Prioridad / nivel:** P1 · T1 · TRF/PROC/LOG
- **Resultado esperado:** una bandeja con tipos `Compra` y `Transferencia` alimentada por QueryServices; enrutamiento: OC → `ReceivePurchaseOrderUseCase`; compra sin OC → `ReceiveDirectPurchaseUseCase`; embarque → servicio de llegada de Logística; traslado → `ConfirmTransferReceiptUseCase`. Permisos independientes; solo Compras genera factura/CxP.
- **Depende de:** C-01, C-02.

### C-10 — Destinatarios de alertas de stock fuera del RBAC
- **Prioridad / nivel:** P2 · T1 · INV/WA
- **Evidencia:** `ProductSettingsQuery.alert_user_ids` lee `usuarios.rol` como texto y teléfonos globales.
- **Resultado esperado:** destinatarios desde la fuente RBAC con alcance por sucursal, responsables por almacén, cola de WhatsApp persistente y reintentable en el `.exe` y offline. No crear otro centro de notificaciones.
- **Depende de:** ítems de arquitectura de permisos.

### C-11 — Ficha de producto guiada con ruta a precios
- **Prioridad / nivel:** P2 · T2 · PROD/UI
- **Resultado esperado:** ficha "Datos → Operación/almacenes → Imagen → Comercialización" con enlace a capturar precio en la lista vigente o borrador; reutilizar `StandardDialog`, `SearchInput`, `StandardTable` y tokens.
- **Depende de:** C-07.

## Decisión de negocio pendiente (fuera de un solo punto)

- **Reconstrucción virtual del producto entero vendido por kg:** equivalencias entre cortes de pesos distintos, redondeo, merma real, saldos por lote y origen del costo; y si el negocio arma físicamente unidades (eso sería otra orden de Producción). Registrar como pregunta abierta; no crear ítem de build hasta tener la regla.
