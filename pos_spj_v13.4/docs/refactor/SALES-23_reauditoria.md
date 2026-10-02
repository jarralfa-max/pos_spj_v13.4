# SALES-23 — Re-auditoría del POS contra el prompt maestro (2026-10-01/02)

El prompt maestro de Ventas/POS (73 secciones) se volvió a pegar sobre un POS que
ya tenía SALES-0..22 hechos (`modulos/ventas.py` borrado; `sales_pos/` es la única
pantalla). Esta fase no reconstruye: **mide el POS vivo contra una copia de la
base real** (capturas a 1366×768 y 1920×1080, recorrido de cobro completo) y
cierra lo que no funcionaba.

## 1. Hallazgos medidos (estado al empezar)

| # | Hallazgo | Severidad | Dónde |
|---|----------|-----------|-------|
| 1 | No se podía cobrar nada recibido por Compras: la reserva buscaba un saldo SIN lote; Compras recibe siempre con lote. 23 kg de Alas en existencia, cobrar 1.25 kg → "Sin balance disponible para reservar", venta atorada en cobro con el pago registrado | P0 | `sales_inventory_client.reserve_for_sale` |
| 2 | El POS no imprimía ningún ticket: `PrinterService` se borró con `core/`, el shell pasaba `printer_service=None`, el cobro no pedía ticket; Reimprimir llamaría a `None.print_ticket` | P0 | shell + `receipt_use_cases` |
| 3 | Los 11 productos se venden por KG y el POS agregaba "1" pieza; la unidad se guardaba "PZA" | P0 | `SalesPosWorkspace`, presentador |
| 4 | El carrito no permitía corregir ni quitar líneas (casos de uso sin llamador) | P1 | `CartTable` |
| 5 | Devolución/F10: la señal no la escuchaba nadie | P1 | workspace |
| 6 | Reimprimir/Factura actuaban sobre la venta NUEVA vacía | P1 | workspace |
| 7 | Autorizador de devolución/reverso validado con la política de sesión (sólo responde por el cajero) → ninguna devolución autorizable | P1 | `return_use_cases` |
| 8 | Reverso de varias líneas reponía sólo la primera (misma identidad de movimiento) | P1 | `ReverseSaleUseCase` |
| 9 | `sales.sale_number` (folio comercial, §6) nunca se asignaba | P1 | checkout |
| 10 | COBRAR era el botón menos visible (variante "success" reducida a gris por el sistema de diseño) | P1 visual | `ActionsPanel` |
| 11 | Barra superior sin cajero, sucursal, estado de caja, dispositivos ni Corte Z | P2 visual | `CashierBar` |
| 12 | Tarjetas en inglés ("Out Of Stock"), sin código, unidad ni existencia; tarjeta no vendible no respondía al clic | P2 | `ProductGrid` |
| 13 | Filtro de categorías mandaba el NOMBRE y la consulta filtra por id → cuadrícula vacía | P1 | `CatalogPanel` |
| 14 | Cliente asignado no se mostraba; la lista vacía del buscador ocupaba medio panel | P2 | `CustomerPanel` |
| 15 | Cancelar (F8) tiraba la venta sin confirmar, motivo fijo | P2 | workspace |
| 16 | Reanudar tomaba siempre la primera suspendida y abandonaba la venta en curso | P2 | workspace |
| 17 | Cambio en efectivo no se mostraba; tarjeta por más del total dejaba un "cambio" descontado de un efectivo inexistente | P1 financiero | `PaymentDialog`, dominio |
| 18 | Ningún producto tiene precio en la base real y el carrito vendía a $0.00 | P1 | dominio |
| 19 | Canje de puntos desde Ventas: cliente de Fidelidad sin política → falla cerrado siempre | P2 | `RedeemLoyaltyPointsUseCase` |
| 20 | Salud de dispositivos leía `hardware_config`, tabla sin ningún escritor → "sin configurar" siempre | P2 | `DeviceHealthQueryService` |
| 21 | 24 pruebas de Ventas en rojo por fixtures con tablas legacy ya borradas | deuda | `tests/unit/test_sales_*` |

## 2. Qué se hizo

**Inventario por lotes** — `backend/application/inventory/use_cases/sale_reservation_use_cases.py`:
`ReserveStockForSaleUseCase` hereda la reserva por lotes de Producción (saldo
exacto, lote y ubicación; estrategia `inventory_settings.sales.allocation_strategy`,
FEFO por omisión; admite lotes en inspección, nunca bloqueados/caducados).
`plan_sale_issue` + `LotAllocationService.allocate_partial`: vender sin existencia
autorizado saca primero de los lotes. Devolución al lote de origen. Cumplir/liberar
por reserva (no por producto).

**Folio** — `SalesFolioClient` (`V-<código>-000001`, contador `document_number_sequences`,
misma transacción del cobro); `Sale.assign_number`; migración **288** (índice único
parcial); `SaleQueryService.list_recent_posted / find_posted_by_number`.

**Ticket** — `backend/infrastructure/printing/sale_ticket_escpos_renderer.py` +
`backend/infrastructure/hardware/sales_ticket_printer.py` (ruta `SALE_TICKET` de
Document Output por sucursal → perfil de conexión → `PrintTransport`).
`PrintSaleReceiptUseCase` (original, tras confirmar) y `ReprintReceiptUseCase`
comparten ruta; un ticket no impreso vuelve como `RECEIPT_NOT_PRINTED`.

**Dominio/aplicación** — `PricingUnavailableError`, `ProductNotSellableError`,
`InvalidWeightError`, `PaymentExceedsBalanceError`, `ReceiptPrintFailedError`;
`SaleLinePolicy.ensure_priced`, `WeightPolicy`, `CashPaymentPolicy`,
`SalePaymentPolicy.ensure_amount_allowed`, `SaleDiscountPolicy.amount_for_percent`,
`ApplySaleDiscountPercentUseCase`; cambiar cantidad conserva la unidad; el escáner
pide peso (`WEIGHT_REQUIRED`) y respeta "no vendible"; catálogo con unidad legible,
`sold_by_weight`, `priced`; `category_options` por id; autorizador real en
devolución/reverso; política de Fidelidad en el canje; `DeviceHealthQueryService`
sobre Device Management; `CustomerLookupQueryService.get`.

**Pantalla** (layout del contrato intacto: barra arriba, un splitter, catálogo
izquierda, venta derecha, cliente entre carrito y totales, COBRAR dominante,
F6-F12): diálogos nuevos `WeightCaptureDialog`, `QuantityDialog`,
`CancelSaleDialog`, `ResumeSaleDialog`, `PostedSalePickerDialog`,
`InvoiceRequestDialog`, `ReturnSaleDialog`; `PaymentDialog` con cambio, métodos
por permiso, crédito sólo con cliente; énfasis `emphasis="dominant"` y
`role="amount"` en el QSS global (sin QSS local); sin emojis (§57).

## 3. Tabla obligatoria (§72)

| Elemento anterior | Destino canónico | Acción | Consumidores restantes |
|-------------------|------------------|--------|------------------------|
| modulos/ventas.py | SalesPosWorkspace + Presenter | DELETE (SALES-22) | 0 |
| compra_actual | Sale aggregate | DELETE (SALES-22) | 0 |
| container.db | UseCases/QueryServices | DELETE | 0 |
| sqlite3 en UI | repositories infra | DELETE | 0 (sólo el tipo de excepción en la raíz de composición) |
| ProductCard con reglas | `SalesCatalogQueryService` + `ProductGrid` | REWRITE | 0 |
| COM3/9600 | Device Management (perfil de conexión) | DELETE | 0 en Ventas |
| safe_serial_read | ScaleGateway | DELETE | 0 — no hay driver de báscula; captura manual |
| cálculo de pago UI | `SalePaymentPolicy` | DELETE | 0 |
| cálculo de cambio UI | `CashPaymentPolicy` | DELETE | 0 |
| loyalty en DialogoPago | `SalesLoyaltyClient` | DELETE | 0 |
| roles admin/gerente | permisos `POS.*` | DELETE | 0 |
| PIN local | `VerifyAuthorizerCredentialsUseCase` + `AuthorizerPermissionChecker` | DELETE | 0 |
| ticket HTML cache | `SalesTicketPrinter` (ESC/POS por ruta) | REWRITE | 0 |
| impresión directa | ruta Document Output → `PrintTransport` | REWRITE | 0 |
| UUID4 | UUIDv7 | DELETE | 0 |
| floats monetarios | Decimal | DELETE | 0 en la UI (`float` sólo en la frontera con el payload del ticket) |
| eventos MainWindow | `wire_sales` + outbox | DELETE | 0 |
| QTableWidget | `StandardTable` (DS) | DELETE | 0 |
| estilos inline | QSS global | DELETE | 0 |
| `hardware_config` (lectura de salud) | Device Management | REWRITE | 0 en Ventas |
| reserva sin lote | `ReserveStockForSaleUseCase` | REWRITE | 0 |

## 4. Pruebas

- Nuevas: `tests/unit/test_sales_pos_reaudit_rules.py` (22), lotes en
  `tests/unit/test_sales_inventory_reservation.py` (5; 4 fallan en HEAD),
  `tests/unit/test_sales_returns.py` (+3; las 3 fallan en HEAD),
  `tests/unit/test_sales_hardware.py` (salud canónica + impresora, 8),
  `tests/integration/sales/test_sales_pos_screen_flows.py` (13, pantalla real).
- Reparadas: 23 pruebas de Ventas con fixtures legacy; trinquete de persistencia
  fija **cero** escritores de la tabla `ventas`.
- Suite de Ventas: 607 pasan; los 26 fallos y 4 errores restantes ya fallaban en
  HEAD (importan `core.*`/`application.*` borrados), medido en un worktree de HEAD.

## 5. Decisiones del usuario — CERRADAS (2026-10-02, migración 289)

1. **Devolución parcial → reembolso por el MÉTODO ORIGINAL, efectivo primero.**
   `refund_service` (dominio puro): el importe devuelto es lo que el cliente pagó
   por esa parte —incluido su pedazo del descuento a nivel venta, antes se
   reembolsaba de más— y se reparte efectivo primero (neto del cambio), luego el
   resto; acumulado entre devoluciones, nunca se reembolsa dos veces lo mismo.
   Lo pagado a crédito baja la CxC (nota de crédito). El efectivo sale del turno
   abierto (`refund_returned_line`, tope de $5,000 por operación) con autorizador
   (gerente/admin). `SaleReturnedHandler` asienta el espejo de la venta (ingreso,
   IVA, descuento, medio de reembolso) y revierte el costo de venta.
   `SaleReversedHandler` existía sin suscriptor: ahora `wire_sales` lo cablea.
2. **Puntos por compra, configurables desde Fidelidad.** 1 punto por cada $10 del
   total pagado (después de descuentos y canje), hacia abajo; el crédito acumula
   (configurable); vigencia de 12 meses (configurable, 0 = no caducan). La cuenta
   de puntos se abre con la primera venta cobrada. Devolver retira en proporción;
   caducar quita sólo lo que QUEDA de cada acumulación (FIFO) — antes caducaba el
   original completo aunque ya se hubiera canjeado. Fidelidad → Configuración
   (ruta que existía como estado vacío) edita acumulación, vigencia y canje con
   `GROWTH_ENGINE.configuracion.editar`.
3. **Canje en el POS.** `GROWTH_ENGINE.puntos.canjear` sembrado a cajero, gerente,
   admin y system_owner. Botón «Canjear» junto al cliente cuando tiene puntos;
   diálogo con saldo, mínimo, tope y equivalencia. «Puntos a ganar» ya muestra la
   estimación con las reglas de Fidelidad. **Hueco encontrado al construirlo:** el
   canje descuenta los puntos ANTES de cobrar y cancelar la venta no los devolvía
   (se perdían). Ahora `SALE_CANCELLED` y `SALE_REVERSED` devuelven el canje
   (`RestoreSaleRedemptionUseCase`, idempotente).
4. **Suspender con faltante: se permite**, reservando lo que hay; la autorización
   de vender sin existencia se pide al cobrar (antes se rechazaba al suspender).
5. **Despacho del outbox tras devolver, reversar y cancelar.** Sólo el cobro
   despachaba `sales_outbox`: el asiento de una devolución esperaba a la siguiente
   venta. `SALE_CANCELLED` pasa a exigir consumidor.

Configuración que sigue faltando en la base real (no son errores de código):
precios de venta, impresora de tickets + ruta «Ticket de venta», báscula.

## 6. No hecho en esta fase (honesto)

- POS-21 Offline (caché, sincronización, conflictos): no existe.
- **Puntos sin asiento contable.** El outbox de Fidelidad no tiene despachador:
  `POINTS_ISSUED`/`POINTS_REDEEMED` no llegan a Finanzas (no hay pasivo por puntos
  emitidos). El canje sí reduce el total cobrado de la venta.
- **Sin planificador.** La caducidad se barre al acreditar (cada cobro con
  cliente); un cliente que no vuelve a comprar conserva puntos vencidos en su
  saldo hasta su siguiente compra.
- Golden master por píxel: las pruebas visuales son estructurales (orden,
  proporciones, dominancia), no comparan imágenes.
- Driver real de báscula y SDK de terminal de pago: no hay ninguno en el repo.
- Liga de cobro de Mercado Pago, eventos de pantalla del cliente (§50), catálogo
  de usos de CFDI.
- Los 17 guardrails con nombre del §70 no se crearon uno por uno; las reglas que
  cubren están en `test_sales_pos_ui_has_no_sql`, `..._does_not_receive_app_container`,
  `test_sales_permissions_are_granular`, `test_sales_does_not_write_inventory_tables`,
  `test_sales_persistence_split_ratchet` y las pruebas de la pantalla.
