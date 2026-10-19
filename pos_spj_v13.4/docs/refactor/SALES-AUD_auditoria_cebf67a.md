# SALES-AUD — Respuesta a la auditoría técnica de Ventas / POS (cebf67a)

Fecha: 2026-10-15. Auditoría recibida: «Auditoría técnica de Ventas / Punto de
Venta» sobre `cebf67a7` (10 hallazgos, V01–V10). Cada hallazgo se volvió a
comprobar contra el código actual (posterior a la auditoría) y, cuando aplicaba,
se reprodujo antes de corregir.

Migración: **341** (`sale_payment_voids`). Pruebas nuevas:
`tests/integration/sales/test_sales_audit_cebf67a.py` (19) y
`tests/architecture/test_sales_single_completion_path.py` (3).

## Decisiones del usuario (2026-10-15)

| Tema | Decisión |
|---|---|
| Cancelar una venta con pagos registrados (V02) | **Compensar y avisar**: la cancelación anula cada pago — retira el cargo de CxC del crédito, suelta el vale — y dice al cajero qué devolver (efectivo, tarjeta, transferencia, Mercado Pago). Queda registro de cada pago anulado. |
| Alcance por sucursal (V05) | **Sólo la propia**: cada caja lee y opera sólo ventas de su sucursal activa. Devoluciones entre sucursales serían un permiso explícito futuro (no existe hoy). |
| Fallo de Caja (V06) | **Todo o nada**: Caja entra en la misma transacción que la venta, la devolución y el reverso. Si Caja rechaza, nada se registra y el cajero ve el motivo. |

## Hallazgo por hallazgo

| # | Sev. | Estado | Qué se encontró / qué se hizo | Prueba |
|---|---|---|---|---|
| V01 | Crítica | Ya cerrado | Lo cerró la auditoría de Finanzas F03 antes de esta revisión: un documento y una CxC por venta, un cargo por pago (`receivable_charges`), idempotente por pago. Re-verificado: 30 + 20 → 50; reintentar el de 20 no cambia nada. | `test_v01_…` |
| V02 | Crítica | Cerrado | El dominio ya no cancela con pagos vivos (`SaleCancellationPolicy`). `CancelSaleUseCase` anula cada pago (`Sale.void_payment` → `SalePaymentVoid`), compensa en la misma transacción (crédito: `VoidSaleCreditChargeUseCase`, nuevo; vale: suelta su apartado) y devuelve `refunds` con la instrucción para el cajero. El diálogo de cancelar lista los pagos antes de confirmar y la pantalla muestra qué devolver. | `test_v02_…` (4) |
| V03 | Alta | Cerrado | `BeginSaleCheckoutUseCase` retoma un cobro abierto (`resumed`); el diálogo arranca desde la venta: carga los pagos guardados y el saldo real, permite quitar un pago ya registrado (`VoidSalePaymentUseCase`, con el permiso del método) y «Cerrar» ya no es «Cancelar». Sin pagos, cerrar regresa la venta al carrito (`ReturnSaleToCartUseCase`, transición nueva CHECKOUT_PENDING → ACTIVE). Con pagos, la pantalla avisa que quedó en cobro y cómo seguir. | `test_v03_…` (4) |
| V04 | Alta | Cerrado | El precio se resuelve **en el caso de uso** (`_SalesBaseUseCase._price`, `pricing=` inyectado): clic, escáner (`ScanCodeRouter` usa el mismo `AddSaleLineUseCase`), cambio de cantidad (otro tramo) y asignación de cliente (lista del cliente) reprecian. El presentador dejó de consultar Precios. El snapshot marca `price_source` (PRICING/CATALOG). Una línea con descuento propio conserva su precio. Matiz: el catálogo ya mostraba el precio de la sucursal; la diferencia real era cliente y volumen. | `test_v04_…` (3) |
| V05 | Alta | Cerrado | `SalesAuthorizationPolicy.require_branch` + `SalesSessionPermissionChecker.can_access_branch` (sucursal ACTIVA de la sesión). Todo caso de uso carga la venta por `_load_sale` (25 sitios); `SaleQueryService`, el ticket, la evaluación de beneficios y la pantalla del cliente también comprueban. Error `OUT_OF_BRANCH_SCOPE`. Guarda de arquitectura contra `uow.sales.get` directo. | `test_v05_…`, arquitectura |
| V06 | Alta | Cerrado | `CashRegisterUnitOfWork(owns_transaction=False)`; cobro, devolución y reverso llaman a Caja DENTRO de su transacción y, si falla, deshacen todo (`CASH_EFFECTS_FAILED`). **Dos defectos más aparecieron al probarlo**: (1) Inventario confirmaba la reserva y su cumplimiento a mitad del cobro (`ReserveStockForSaleUseCase`/`FulfillReservationUseCase`/`ReleaseReservationUseCase` no aceptaban `owns_transaction`), así que un cobro fallido ya dejaba el stock apartado; ahora se unen a la transacción. (2) Caja exige la referencia del vale (`REFUND_VOUCHER`) y Ventas no la mandaba: **toda venta con vale era rechazada por Caja y el error se tragaba** — el efectivo de un cobro vale + efectivo nunca llegaba al cajón, y la devolución de una venta con vale fallaba en Caja. Se manda el instrumento y el vale ya no pasa por el reembolso de Caja (Fidelidad lo restituye). Pedidos/Delivery (sin turno de mostrador) conserva su efecto de Caja posterior al commit, como antes. | `test_v06_…` (2), `test_sales_returns` |
| V07 | Media | Cerrado | `CompleteSaleUseCase` eliminado (sólo lo usaban pruebas); sus 3 pruebas pasan por `CheckoutSaleUseCase`. Guarda: nadie más define la clase ni llama `sale.complete()` en Ventas. | arquitectura |
| V08 | Media | Cerrado (parcial) | Existencia del catálogo sumada en `Decimal` en Python (0.1 + 0.2 = 0.3 exacto); el catálogo sólo se vuelve a consultar cuando cambia la venta, no en cada cambio del carrito. **Abierto**: paginación/virtualización de la cuadrícula (sigue el tope de 200). | `test_v08_…` |
| V09 | Media | Parcial | El indicador del escáner ya no dice «listo» sin haber leído nada («esperando lectura»). **Abierto (proyectos aparte)**: terminal/adquirente con autorización verificada para tarjeta y Mercado Pago, estado de timbrado PAC visible, y operación desconectada. | — |
| V10 | Baja | Cerrado | La prueba exige que la barra de caja sea lo primero del CUERPO (debajo del PageHeader compartido) y antes del divisor. | `test_sales_pos_workspace` |

## Verificación en copia de la base real

Copia de `data/spj_pos_database.db` (esquema 340): migración 341 dos veces sin
cambios ni errores de llave foránea. Con el cajero y la sucursal reales (Alas, por
peso): cobro a medias → retomado con $10 registrados → pago anulado («Devuelve
$10.00 en efectivo») → de vuelta al carrito; cobro con $5 → cancelado con la
instrucción de devolución; venta completa → folio V-COR-000008 y su movimiento de
Caja; otra sucursal: no la ve y no la reimprime (`OUT_OF_BRANCH_SCOPE`).
En la base real los datos estaban sanos: las 7 ventas cobradas tienen su
movimiento de Caja y ninguna cancelada tenía pagos — los defectos eran latentes.

## Cierre de pendientes (2026-10-16)

Pedido del usuario: cerrar lo pendiente salvo terminales y devolución entre
sucursales.

| Tema | Qué se hizo | Prueba |
|---|---|---|
| Venta en curso perdida (V03, nuevo hallazgo) | MEDIDO en la base real: 10 carritos con productos y 58 borradores vacíos abandonados — cada apertura del POS creaba otra venta y una a medio cobrar quedaba inalcanzable. `OpenSaleForCashierUseCase`: al abrir la pantalla retoma la venta abierta del cajero en su sucursal (primero la que está en cobro, con aviso si hay dinero registrado); después de cobrar o cancelar reutiliza un borrador vacío. | `test_v03_opening_…`, `test_v03_a_new_sale_reuses_…` |
| Paginación del catálogo (V08) | Páginas de 60 (`catalog_page`, `OFFSET`), botón «Mostrar más productos» que AGREGA tarjetas sin reconstruir las existentes. | `test_v08_the_catalog_comes_in_pages` |
| Estado de timbrado (V09) | F11 sobre una venta con facturas muestra cada solicitud (Solicitada / Timbrada con folio fiscal / Con error y motivo); registrar el timbrado (UUID con formato SAT, validado en el dominio) o el error; tras un error, nueva solicitud. Mientras no haya PAC el resultado se registra a mano. | `test_v09_…` (3) |
| Precio en el diálogo de peso | Muestra el precio que se cobrará (`SalePricePreviewService`, misma regla `resolve_sale_price` que el caso de uso). | `test_v04_the_weight_dialog_…` |
| Operación sin conexión (V09) | Revisado, sin construcción: el POS trabaja contra la base LOCAL; cobrar, inventario, Caja, vales, puntos y cupones no dependen de la red, y lo que sí (Finanzas, WhatsApp, notificaciones) sale por outbox con reintento. Lo que no existe es un servidor central que sincronice sucursales: es un proyecto de arquitectura, no un defecto del POS. | — |
| Crédito a «Público en general» (pregunta del usuario) | MEDIDO en la base real: el único cliente con crédito autorizado ($300, 15 días) es de tipo «Público en general» y el POS lo rechazaba SIEMPRE con un mensaje que no explicaba nada. Solicitar y aprobar crédito para ese tipo ahora se rechaza; el POS agrega el motivo. Con el tipo corregido (en una copia) la venta a crédito valida, crea la CxC con vencimiento y asienta Dr 1130 Clientes / Cr 4101 Ingresos (+ costo de ventas). | `TestPublicCustomerHasNoCredit` (3) |

## Pendientes (excluidos por el usuario o externos)

* Terminal/adquirente para tarjeta y Mercado Pago (excluido por el usuario).
* Devolución entre sucursales con permiso explícito (excluido por el usuario).
* Conectar un PAC para timbrar automáticamente: requiere elegir proveedor y
  credenciales; hoy el resultado se registra a mano.
* Servidor central de sincronización entre sucursales (arquitectura).
* Dato real: el cliente CLI-000001 «Jose Rodriguez» es «Público en general» con
  $300 de crédito autorizado; hay que cambiar su tipo en Clientes para que el
  crédito sirva (no se cambió sin permiso del usuario).
* Una venta abandonada a medio cobrar con pago a crédito mantiene el cargo en
  CxC hasta que se retoma o cancela (ahora se recupera al abrir el POS).
