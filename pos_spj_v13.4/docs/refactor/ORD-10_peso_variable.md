# ORD-10 — Peso variable (catch-weight)

Fecha: 2026-08-31. Alcance: master prompt §26-27, §65 (autorización en caliente).

## Qué se construyó

- `WeightAdjustmentEvaluation` (VO) + `CatchWeightAdjustmentPolicy.evaluate()` — única
  fuente de la comparación solicitado-vs-preparado y de si está dentro de tolerancia.
  `tolerance_pct` siempre lo provee el llamador (futura Configuración §72), nunca
  hardcodeado.
- `CustomerOrderLine.apply_weight_evaluation()`/`accept_customer_adjustment()`/
  `reject_customer_adjustment()`. `CustomerOrder.apply_weight_evaluation()` (aplica a una
  línea + sincroniza `customer_approval_status` a nivel pedido) y
  `accept_customer_adjustment(line_id)`/`reject_customer_adjustment(line_id)`.
- **Corrección real en `OrderTotalsService`**: antes de esta fase sumaba
  `line.requested_subtotal`, lo que significaba que el total del pedido NUNCA reflejaba lo
  realmente pesado/preparado. Cambiado a `line.final_subtotal`, que ya degradaba
  correctamente al equivalente de "solicitado" cuando no había peso final (confirmado con
  la suite completa antes/después — cero regresiones). Corregido dentro de esta fase
  porque §1 del prompt maestro exige "Recalcular" como paso explícito del pipeline
  inmediatamente después de "Pesaje real".
- Casos de uso: `EvaluateCatchWeightUseCase`, `AcceptWeightAdjustmentUseCase`,
  `RejectWeightAdjustmentUseCase`, `OverrideWeightAdjustmentUseCase`.

## Decisiones

- **`OverrideWeightAdjustmentUseCase` es el primer llamador real de
  `OrdersDeliveryAuthorizationPolicy.authorize_exception()`** — ORD-1 la construyó como
  fundación de seguridad sin ningún consumidor; §65 del prompt maestro nombra
  explícitamente "peso fuera de tolerancia" como caso de autorización en caliente. Exige
  autorizador distinto del solicitante (segregación de funciones ya probada en ORD-1,
  ahora con un caso de uso real detrás).
- **Aceptar/rechazar en nombre del cliente reutiliza `CUSTOMER_APPROVAL_OVERRIDE`** — no
  existe todavía un canal de autoservicio (WhatsApp, ORD-23) donde el cliente decida
  directamente; por ahora el staff registra la decisión del cliente (comunicada por
  teléfono/en persona), de ahí "override" en el sentido de "un humano de staff la
  captura", no en el sentido de autorización en caliente (esa es
  `OverrideWeightAdjustmentUseCase`, con `authorize_exception()`).
- **`_sync_customer_approval_status()` es una simplificación deliberada**: PENDING si
  alguna línea está pendiente, REJECTED si alguna fue rechazada (y ninguna pendiente),
  ACCEPTED en otro caso. No intenta modelar combinaciones más finas (ej. parcialmente
  aceptado con una línea rechazada) — suficiente para pedidos de pocas líneas; revisar si
  ORD-19+ (reentregas/devoluciones parciales) necesita algo más rico.

## Tests

16 tests nuevos (9 dominio + 7 integración, esta última incluyendo el flujo completo
capturar→confirmar→reservar→asignar→iniciar→registrar peso→evaluar, y el camino de
autorización en caliente con segregación de funciones). Suite acumulada ORD-1..10:
**151/151 pasando**.

## Pendiente

- Sustituciones (§29, ORD-12) — un `OrderLineStatus.REJECTED` hoy no dispara
  automáticamente ninguna sustitución/recuperación, es un estado terminal simple.
- Expiración de la ventana de aprobación (`CustomerApprovalStatus.EXPIRED`,
  `CustomerApprovalExpiredError` ya definido) no tiene disparador todavía — requiere el
  mismo tipo de scheduler pendiente desde ORD-6.
