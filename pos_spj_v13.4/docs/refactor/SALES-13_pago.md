# SALES-13 — Pago (POS-13 del master prompt)

Fecha: 2026-08-17
Fase anterior: `SALES-12_hardware.md`.

## Alcance ejecutado

Master prompt §67, fase POS-13: "Cash. Card. Transfer. Mixed. Credit. Mercado Pago. Tests."
Investigué primero (agente de research, sin escritura de archivos) seis áreas concretas antes de
modelar nada: cómo registra pago hoy `modulos/ventas.py`, el riesgo real de inconsistencia en la
validación de crédito que SALES-0 ya había marcado, qué existe realmente en Caja para el ledger
de pagos, el estado real de la integración con Mercado Pago, qué (nada) existe ya en
`backend/domain/sales`/`backend/application/sales` sobre pagos, y cómo se contabiliza hoy el
asiento contable de una venta.

## La frontera real, confirmada por investigación

| Área | Estado real |
|---|---|
| **Registro legacy** | `ventas.forma_pago`/`efectivo_recibido` son campos únicos (no por línea). Existe una tabla `payments` real, pensada explícitamente para múltiples formas de pago por venta (migración 028) — pero **nunca se le inserta nada en la ruta de venta real**, confirmado por grep: cero `INSERT INTO payments` en todo el repo. `SalesService._build_payment_breakdown` sí valida y compone un desglose mixto real (`{efectivo, tarjeta, transferencia, credito, mercado_pago}`), pero solo vive en memoria/eventos — nunca se persiste normalizado. |
| **Crédito** | Confirmado: 3 rutas de validación independientes en `procesar_pago` (asesoría CRM no bloqueante, `customer_credit_service.validate_credit` — la única que realmente bloquea —, y un fallback inline vía `ClienteRepository.get_by_id`). Hallazgo adicional de esta fase: existe una CUARTA verificación más profunda en `SalesService._validate_payment` que reutiliza el MISMO objeto que la ruta 2 — por lo que cuando ese objeto es `None` (activando el fallback de la ruta 3), la ruta 3 nunca puede realmente aprobar nada: `_validate_payment` bloqueará la venta de todas formas. |
| **Ledger de Caja** | Existe una implementación real y completa para registrar el cobro de una venta contra el turno abierto — `backend/application/cash_register/sales_integration.py::CashSalesIntegrationService.record_completed_sale` (clasifica settlements, escribe `cash_ledger_entries` tipo `CASH_SALE`) — pero está **100% sin conectar**: ningún handler real la suscribe a los eventos de Sales. La ruta legacy real usa `movimientos_caja` (solo desde la ruta bloqueada `SalesService.execute_sale`) y `treasury_ledger`. Cuatro tablas de dinero en paralelo para una sola venta en efectivo, ninguna se referencia entre sí. |
| **Mercado Pago** | Integración real y funcionando en el stack LEGACY (`services/mercado_pago_service.py`): creación de link, procesamiento de webhook, `SalesService.confirm_pending_payment_sale`. El servidor de webhook (`MPWebhookServer`) nunca se instancia en ningún entrypoint real — última milla sin conectar, ya señalado independientemente en `docs/architecture/FINANCIAL_TRACEABILITY_END_TO_END.md` (R-07). |
| **Stack nuevo** | Cero código de pago en `backend/domain/sales`/`backend/application/sales` antes de esta fase — `Sale.complete()` no tomaba argumentos, `mark_payment_pending()` existía sin ningún use case que lo llamara, y `SaleEvents.PAYMENT_PENDING`/`PAYMENT_CONFIRMED` estaban reservados pero nunca publicados. `sales_schema.py` ya documentaba desde SALES-4 que una futura tabla de pagos debía llamarse `sale_payments`, nunca `payments` (colisión con la tabla legacy). |
| **Asiento contable** | La venta completada SÍ postea un asiento balanceado real, pero por una ruta distinta a la que nombra CLAUDE.md (`finance_service.registrar_asiento()`): `SALE_ITEMS_PROCESS` → `SaleFinanceHandler` → `PostingEngine.post()` (`journal_entries`/`journal_lines`, debe=haber real). **Hallazgo de correctitud real, no fabricado**: `SaleFinanceHandler._settlements_from_legacy` arma la línea de asiento solo por keyword-match sobre `forma_pago` y **nunca lee `payment_breakdown`** — una venta "Mixto" siempre colapsa a una sola línea de asiento (CASH por default), a pesar de que `SalesService` sí calculó el desglose real. Esto vive en `core/events/handlers/finance_handler.py`, fuera del alcance de `backend/domain/sales`/`backend/application/sales` y en la ruta de producción viva — **no se tocó en esta fase** (ver más abajo). |

## Entregables

**Dominio** (`backend/domain/sales/`):
- `enums.py::PaymentMethod` — CASH/CARD/TRANSFER/CREDIT/MERCADO_PAGO. "Mixed" no es un método
  propio: una venta es mixta en cuanto `Sale.is_mixed_payment` detecta más de un método distinto
  entre sus líneas de pago registradas — igual que el legacy `forma_pago="Mixto"` es en realidad
  solo una etiqueta para "más de una línea", confirmado leyendo `_build_payment_breakdown` antes
  de modelar esto.
- `value_objects/sale_payment.py::SalePayment` — línea de pago inmutable (id, sale_id, method,
  amount, captured_by_user_id, reference, captured_at).
- `policies/payment_policy.py::SalePaymentPolicy` — `ensure_can_record_payment` (solo
  CHECKOUT_PENDING/PAYMENT_PENDING; la tabla de transiciones de SALES-3 ya permite completar
  directo desde CHECKOUT_PENDING para el caso de un solo método, o pasar por PAYMENT_PENDING para
  el caso multi-línea/mixto — esta política no duplica esa tabla) y `ensure_fully_paid` (suma de
  pagos >= total de la venta, misma regla real que `SalesService._validate_payment` ya aplica).
- `exceptions.py` — `SalePaymentIncompleteError`, `CreditNotAuthorizedError`.
- `entities.py::Sale` — `payments: list[SalePayment]`, `total_paid`/`is_mixed_payment`
  (propiedades derivadas, nunca almacenadas), `record_payment()`, y `complete()` extendido para
  exigir pago completo antes de transicionar — el hueco que SALES-6 dejó explícitamente abierto
  ("depende de confirmación de pago real, POS-13/14, no fabricado aquí").
- `events.py::SaleEvents.PAYMENT_RECORDED` — nuevo evento por línea de pago; `PAYMENT_PENDING`/
  `PAYMENT_CONFIRMED` (reservados desde SALES-3, nunca publicados) ahora sí se emiten.

**Esquema**: `sale_payments` (`backend/infrastructure/db/schema/sales_schema.py`) — nombre exacto
ya reservado desde SALES-4. Migración `migrations/standalone/201_sales_payments_schema.py`
(201 era el siguiente número libre; existe un archivo `200_uuid_identity_cutover.py` de una
sesión concurrente que tampoco está registrado en `engine.py` — no es de esta fase, se deja
intacto, solo se anota aquí como hallazgo honesto). `SaleRepository` extendido para
persistir/reconstruir `payments` con el mismo patrón delete-then-reinsert que `lines`.

**Infraestructura** (`backend/infrastructure/integrations/sales_credit_client.py::
SalesCreditClient`): el arreglo real al hallazgo de la sección "Crédito" arriba — un solo punto
de integración limpio hacia `application/services/customer_credit_service.py::
CustomerCreditService.validate_credit`/`register_credit_sale` (la ruta 2, la que de verdad
bloquea), puenteando identidad nuevo→legacy vía `EnsureLegacyCustomerBridgeUseCase` (mismo
patrón que `SalesLoyaltyClient`, SALES-11). No se tocaron ni se corrigieron las tres rutas
legacy de `modulos/ventas.py::procesar_pago` — la UI vieja sigue exactamente igual; esto solo le
da a la nueva pila un único camino honesto en vez de tener que decidir entre tres divergentes.

**Aplicación** (`backend/application/sales/use_cases/payment_use_cases.py`):
- `RecordSalePaymentUseCase` — un solo punto de entrada para los cinco métodos reales; exige el
  permiso `SalesPermissions.PAYMENT_*` correspondiente, y además `PAYMENT_MIXED` en cuanto una
  segunda línea de método distinto haría la venta mixta. Para CREDIT: exige cliente asignado,
  valida vía `SalesCreditClient.validate()` antes de aceptar la línea, y registra la CxC real
  (`cuentas_por_cobrar`, idempotente por venta) vía `SalesCreditClient.register()` tras aceptarla.
  Mercado Pago se registra como cualquier otro método con referencia externa (el id de pago de
  MP) — **deliberadamente NO se construyó ningún webhook/cliente HTTP nuevo aquí**, ver más abajo.
- `CompleteSaleUseCase` — el use case que SALES-6 dejó pendiente explícitamente. Ahora es posible
  porque `Sale.complete()` exige pago completo por sí mismo; persiste y emite
  `PAYMENT_CONFIRMED`/`COMPLETED`.

**Permisos**: cero cambios en `permission_catalog.py`/`SalesPermissions` — los seis códigos
`POS.pago.*` ya existían desde SALES-2, sin consumidor hasta ahora.

**Tests** (24 nuevos: 14 en `tests/unit/test_sales_payment.py` + regresión de fixtures en
`test_sales_domain.py`/`test_sales_hardware.py`, todos verdes; 293 en total en la suite
SALES-0..13, un solo failure preexistente no relacionado ya documentado desde SALES-9):
dominio (`record_payment` exige estado correcto, `complete()` exige pago completo, sobrepago
permitido — vuelto en cambio —, detección de mezcla solo con dos métodos distintos), caso de uso
de registro (efectivo, método desconocido falla VALIDATION, segundo método distinto exige
`PAYMENT_MIXED`, crédito sin cliente falla, crédito denegado por límite real falla con motivo
real, crédito aprobado registra CxC real con el `cliente_id` puenteado correcto), caso de uso de
completar (falla con pago parcial, completa y emite los tres eventos reales al confirmarse pago
mixto, Mercado Pago se registra con referencia y completa igual que cualquier otro método).

**Regresión real encontrada y corregida por este propio cambio** (mismo patrón "corregir el
fixture, no el comportamiento nuevo correcto" que SALES-9/10 ya establecieron): 4 tests
preexistentes (3 en `test_sales_domain.py` de SALES-3, 1 en `test_sales_hardware.py` de esta
misma sesión, SALES-12) llamaban `sale.complete()` sin registrar ningún pago — ahora
correctamente bloqueados por la nueva invariante. Corregidos agregando `record_payment()` antes
de `complete()` en cada uno, no relajando la política nueva.

## Lo que esta fase NO hizo (honesto, no fabricado)

- **No se tocó `modulos/ventas.py`.** Las tres (cuatro) rutas de validación de crédito divergentes
  siguen exactamente igual en la UI legacy — `SalesCreditClient` es un camino nuevo y limpio para
  la pila nueva, no una migración de la UI existente.
- **No se construyó ningún webhook/cliente HTTP nuevo para Mercado Pago.** Ya existe una
  integración real y funcionando en `services/mercado_pago_service.py` (creación de link,
  procesamiento de webhook, confirmación de venta) — reconstruirla en la pila nueva habría sido
  exactamente el tipo de duplicación de infraestructura real que esta pipeline se ha negado a
  hacer repetidamente. `RecordSalePaymentUseCase` solo sabe registrar un pago de MP ya confirmado
  como línea, igual que Tarjeta/Transferencia.
- **No se corrigió el colapso de línea única en el posteo contable** (`SaleFinanceHandler.
  _settlements_from_legacy` ignora `payment_breakdown`, encontrado en la investigación de esta
  fase). Es un hallazgo real y confirmado, pero vive en `core/events/handlers/finance_handler.py`,
  fuera de `backend/domain/sales`/`backend/application/sales`, y es una ruta de producción viva
  que postea asientos reales hoy — corregirlo sin autorización explícita habría sido un cambio de
  comportamiento financiero en vivo fuera del alcance de una fase de modelado de dominio. Se deja
  documentado explícitamente, no oculto, como candidato a una fase/ticket separado.
- **No se conectó `CashSalesIntegrationService`/`cash_ledger_entries`** de Caja al nuevo agregado
  `Sale` — sigue siendo código real pero sin ningún handler que lo suscriba a los eventos de
  Sales, tal como se encontró (no era el foco de esta fase, que es el "Pago" del lado de Ventas,
  no la integración Ventas↔Caja).
- **Nada de esto se conectó a `modulos/ventas.py` ni a ninguna UI/API real.** El flujo de pago en
  vivo sigue siendo `SalesService`/`_execute_sale_core` exactamente como hoy.

## Siguiente fase

El master prompt continúa con POS-14 (Checkout) — confirmar alcance con el usuario antes de
asumir.
