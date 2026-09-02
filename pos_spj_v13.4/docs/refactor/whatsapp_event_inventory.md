# Inventario de eventos — Canal WhatsApp (FASE CERO — Auditoría)

Cruza `docs/events/WHATSAPP_EVENT_CATALOG.md` (2026-05-20/28) contra el código actual. El catálogo
previo describe correctamente los *nombres* de evento pero, como se muestra abajo, varias
**prioridades documentadas ya no coinciden con las que el código realmente emite** — se corrige aquí.

Clasificación: **dominio** (impacto de negocio, debería sobrevivir el rediseño con el mismo nombre),
**canal** (actividad conversacional/mensajería, propia de WhatsApp), **legacy/alias** (mantenido solo
por compatibilidad con consumidores viejos, candidato a retiro).

---

## 1. Eventos emitidos por `WAEventEmitter`/`BusinessOrchestrator` — con prioridad real verificada en código

| Evento | Tipo | Prioridad en código | Prioridad documentada (catálogo previo) | Coincide | Emisor (archivo:línea) | Consumidor(es) conocido(s) |
|---|---|---|---|---|---|---|
| `WA_PEDIDO_CREADO` | legacy/alias de `SALE_CREATED` | **3** | 80 | **No** | `business_orchestrator.py:254-256` | No localizado un listener explícito en esta fase — requiere verificación en `core/events/wiring.py` (fuera de alcance) |
| `SALE_CREATED` | dominio | 80 | (no existía como fila propia en el catálogo previo, solo como "spec event") | — | `business_orchestrator.py:126-133, 208-211` | Ventas/Delivery — no confirmado listener específico en esta fase |
| `WA_COTIZACION_CREADA` | legacy/alias de `QUOTE_CREATED` | 5 | 50 | **No** | `business_orchestrator.py:95-99` (vía `confirmar_cotizacion`); también emitido directo desde `flows/cotizacion_flow.py:164-168` cuando NO hay orchestrator, con `sucursal_id=suc_id` pero **sin** `prioridad` explícita (usa el default `prioridad: int = 5` de `WAEventEmitter.emit`, `erp/events.py:89-90`) | `cotizaciones` |
| `QUOTE_CREATED` | dominio | 5 | — | — | `business_orchestrator.py:87-92` | — |
| `WA_VENTA_CONFIRMADA` | legacy/alias de `SALE_CREATED` | 80 | 80 | Sí | `business_orchestrator.py:135-137` | `finanzas`, `delivery` (documentado, no reverificado) |
| `WA_ANTICIPO_REQUERIDO` | legacy/alias de `PAYMENT_REQUIRED` | 80 | 80 | Sí | `business_orchestrator.py:176-179, 231-233` | `finanzas` |
| `PAYMENT_REQUIRED` | dominio | 80 | — | — | `business_orchestrator.py:169-175, 226-230` | — |
| `WA_ANTICIPO_PAGADO` | legacy/alias de `PAYMENT_RECEIVED` | **2** (vía `confirmar_anticipo`, `business_orchestrator.py:289-291`) **o 80** (vía `webhook/mercadopago.py:147-152`, que llama `events.emit(..., sucursal_id=..., prioridad=80)` — **no**, ver nota | 80 (marcado "✅ Síncrono" en catálogo previo) | **Parcial — dos caminos distintos con dos prioridades distintas** | `business_orchestrator.py:289-291` (prioridad=2); `webhook/mercadopago.py:147-152` (revisar: el `emit()` en ese archivo **no pasa `prioridad` explícita** en la llamada a `WA_ANTICIPO_PAGADO`, línea 147-152, por lo que también cae al default 5, NO 80) | `finanzas`, `delivery` |
| `PAYMENT_RECEIVED` | dominio | **2** (`business_orchestrator.py:284-287`) o default **5** (`webhook/mercadopago.py:139-146`, sin `prioridad` explícita) | — (spec event) | — | ambos archivos | — |
| `WA_CLIENTE_REGISTRADO` | legacy/alias | no verificado en esta fase (emitido desde `flows/registro_flow.py`, no leído en detalle) | 30 | requiere verificación | `flows/registro_flow.py` (no confirmado línea exacta) | `crm`, `loyalty` (documentado, no reverificado) |
| `WA_ALERTA_GENERADA` | canal | no verificado (emitido desde `notifications/alerts.py`, no leído en detalle) | 10 | requiere verificación | `notifications/alerts.py` | `dashboard` (documentado, no reverificado) |
| `WHATSAPP_QUOTE_CREATED` | canal | 5 | — | — | `business_orchestrator.py:100-105` | — |
| `WHATSAPP_QUOTE_ACCEPTED` | canal | no verificado (emitido desde `cotizacion_flow.py` en el camino sin orchestrator — buscar `WHATSAPP_QUOTE_ACCEPTED`) | — | — | `flows/cotizacion_flow.py:238-242` (prioridad no explícita → default 5) | — |
| `WHATSAPP_QUOTE_REJECTED` | canal | default 5 (sin `prioridad` explícita) | — | — | `flows/cotizacion_flow.py:199-203` | — |
| `WHATSAPP_QUOTE_CONVERTED_TO_SALE` | canal | default 5 (sin `prioridad` explícita) | — | — | `flows/cotizacion_flow.py:243-249` | — |
| `WHATSAPP_QUOTE_ACCEPTED_BY_CUSTOMER` | canal | 30 | — | — | `business_orchestrator.py:138-142` | — |
| `PURCHASE_ORDER_CREATED` | dominio | 3 | — | — | `business_orchestrator.py:332-338` | Compras/staff (`STAFF_NOTIFICATION` emitido junto) |
| `DELIVERY_SCHEDULED` | dominio | 5 | — | — | `business_orchestrator.py:247-251` | — |
| `FORECAST_DEMAND_UPDATED` | dominio | 10 | — | — | `business_orchestrator.py:311-316` | Forecast engine (documentado en catálogo previo como "consumidor esperado") |
| `STAFF_NOTIFICATION` | canal (interno) | 5 (nuevo pedido `:261-266`) / 3 (OC automática `:342-347`) / 3 (anticipo pagado `:296-299`) | — | — | `business_orchestrator.py`, múltiples líneas | `notifications/staff.py` (no reverificado) |
| `WA_DELIVERY_CREADO` | canal, **no documentado en el catálogo previo** | 3 | — no listado — | **hallazgo nuevo** | `flows/delivery_flow.py:39-43` | no confirmado |

**Hallazgo E1 — las prioridades documentadas (`docs/events/WHATSAPP_EVENT_CATALOG.md`) están
desactualizadas respecto al código real.** El catálogo previo marca `WA_ANTICIPO_PAGADO` y (por
extensión) `PAYMENT_RECEIVED` como prioridad 80 "✅ Síncrono", pero el código que efectivamente los
emite hoy usa prioridad 2 (`business_orchestrator.confirmar_anticipo`) o el default 5
(`webhook/mercadopago.py`, que omite el parámetro `prioridad` en su llamada a `events.emit(...)`).
Según la propia regla de `WAEventEmitter.emit()` (`erp/events.py:135`, `is_critical = prioridad >= 80`),
esto significa que la confirmación de un pago de anticipo **no se está tratando como evento síncrono
crítico** en la práctica, sino como uno asíncrono de baja prioridad — contradice tanto la
documentación previa como, más importante, la tabla de prioridades del CLAUDE.md del proyecto
(80 = "operaciones críticas de negocio", que un pago confirmado claramente es). Esto necesita
corrección de código, no solo de documentación, antes de fijar el catálogo definitivo del bounded
context nuevo.

**Hallazgo E2 — `WA_PEDIDO_CREADO` también diverge de lo documentado** (prioridad 3 en código vs 80
documentado), mismo patrón que E1.

**Hallazgo E3 — varios `emit()` omiten el parámetro `prioridad` por completo**
(`flows/cotizacion_flow.py:199, 238, 243`; `webhook/mercadopago.py:139, 147`), cayendo silenciosamente
al default de la función (`prioridad: int = 5`, `erp/events.py:90`) en vez de una prioridad
explícitamente pensada para ese evento — es fácil que esto sea un descuido acumulado más que una
decisión, dado que el mismo evento (`WA_ANTICIPO_PAGADO`) tiene prioridad explícita=2 en un emisor
(`business_orchestrator.py:289`) y prioridad implícita=5 en otro (`webhook/mercadopago.py:147`) para
lo que conceptualmente debería ser el mismo hecho de negocio.

---

## 2. Eventos escuchados por WhatsApp (ERP → canal)

No se re-verificó en esta fase el wiring real de listeners (`core/events/wiring.py` o equivalente) —
la tabla previa del catálogo (`STOCK_BAJO_MINIMO`, `VENTA_COMPLETADA`, `PAYROLL_DUE`,
`EMPLOYEE_REST_DAY`, `EMPLOYEE_OVERWORK`, `FORECAST_GENERADO`) se toma como referencia sin
confirmación línea-a-línea; **requiere verificación** en fase de diseño. Sí se confirmó, en cambio, el
handler real que aplica política antes de reenviar cualquiera de estos por WhatsApp a staff:

`pos_spj_v13.4/core/events/handlers/whatsapp_notification_handler.py:153-174`
(`WhatsAppNotificationHandler.handle`) mapea explícitamente:

| `event_type` recibido | Método | Resultado (según política, `NotificationPolicyService`) |
|---|---|---|
| `PEDIDO_WA_NUEVO` | `handle_pedido_wa_nuevo` (líneas 49-67) | Solo inbox ERP — **no** WhatsApp a staff |
| `ANTICIPO_REGISTRADO` / `ANTICIPO_REQUERIDO` | `handle_anticipo` (líneas 69-82) | Solo inbox ERP |
| `PEDIDO_ASIGNADO` | `handle_pedido_asignado` (líneas 84-109) | Sí WhatsApp al repartidor |
| `ALERTA_CRITICA` | `handle_alerta_critica` (líneas 111-137) | WhatsApp solo a responsables explícitamente configurados |
| `FORECAST_SUGERENCIA` | `handle_forecast` (líneas 139-151) | WhatsApp a gerentes/compras configurados |

Nótese que los nombres de evento que este handler escucha (`PEDIDO_WA_NUEVO`, `ANTICIPO_REGISTRADO`,
`ANTICIPO_REQUERIDO`, `PEDIDO_ASIGNADO`, `ALERTA_CRITICA`, `FORECAST_SUGERENCIA`) **no coinciden
literalmente** con ninguno de los nombres que `whatsapp_service/erp/events.py` define y emite
(`WA_PEDIDO_CREADO`, `PAYMENT_REQUIRED`, `PURCHASE_ORDER_CREATED`, etc.) — son un tercer vocabulario de
nombres de evento, en español, distinto tanto de los alias legacy `WA_*` como de los "spec events" en
inglés (`SALE_CREATED`, `PAYMENT_REQUIRED`...). **Requiere verificación** de si hay algún traductor de
nombre de evento entre el microservicio (que corre en un proceso Python separado y usa su propia
instancia de `EventBus` vía `core.events.event_bus.get_bus()`, `erp/events.py:73-88`) y este handler
del lado desktop, o si en la práctica este handler nunca recibe los eventos que emite
`business_orchestrator.py` porque los nombres no coinciden. Este es un candidato fuerte a bug de
integración silencioso, pero confirmarlo requeriría trazar `core/events/wiring.py`
(no leído en esta fase) — se deja como pregunta abierta explícita para la fase de diseño.

---

## 3. Eventos del contexto Delivery relacionados con WhatsApp

Tomado de `docs/EVENT_CATALOG_WHATSAPP_DELIVERY.md` (2026-05-23) y verificado parcialmente:

| Evento | Tipo | Estado verificado en esta fase |
|---|---|---|
| `WHATSAPP_ORDER_CREATED` | canal/puente | No releído en detalle; el catálogo previo lo describe como idempotency key `whatsapp_order_created:{sale_id}` — coherente con el patrón de `POSNotifier` visto en `erp/pos_notifier.py:28-30` (`EVENT_WHATSAPP_ORDER_CREATED`). |
| `WHATSAPP_SCHEDULED_ORDER_CREATED` | canal/puente | Confirmado como constante en `erp/pos_notifier.py:29`. |
| `BRANCH_NOTIFICATION_CREATED` | canal/puente | Confirmado como constante en `erp/pos_notifier.py:30`. |
| `DELIVERY_ORDER_CREATED` / `..._STATUS_CHANGED` | dominio (Delivery) | No releído; propiedad de `core/delivery/`, fuera del árbol WhatsApp propiamente dicho. |
| `DELIVERY_ADJUSTMENT_APPROVAL_REQUIRED` / `ACCEPTED` / `REJECTED` | dominio (Delivery) | `ACCEPTED`/`REJECTED` confirmados emitidos desde `whatsapp_service/erp/adjustment_approval.py:122, 134-143` con prioridad **hardcodeada 35 y 40** respectivamente (no 30/50/80 de la tabla estándar del CLAUDE.md) — **hallazgo nuevo**: estos dos valores de prioridad no corresponden a ningún nivel de la tabla oficial (100/80/50/30/10/5) del CLAUDE.md del proyecto. |
| `DeliveryEvents.TOTAL_UPDATED` | dominio (Delivery) | Confirmado emitido junto a los de arriba, `adjustment_approval.py:122-133`, prioridad 35 también. |

**Hallazgo E4**: `adjustment_approval.py` usa prioridades 35 y 40, que no existen en la escala oficial
del proyecto (100/80/50/30/10/5, CLAUDE.md tabla "EventBus — orden de prioridades"). No se pudo
determinar en esta fase si esto es intencional (una escala más fina específica de Delivery) o un
descuido — **requiere verificación**.

---

## 4. Resumen de acciones para el catálogo definitivo

1. **Corregir E1/E2/E3** en código antes de (o durante) el rediseño: decidir la prioridad correcta de
   `WA_ANTICIPO_PAGADO`/`PAYMENT_RECEIVED`/`WA_PEDIDO_CREADO`/`SALE_CREATED` y hacer que **todos** los
   emisores la usen explícitamente, no el default de la función.
2. **Confirmar o descartar E el desajuste de vocabulario** entre `erp/events.py` (nombres `WA_*` /
   inglés spec) y `whatsapp_notification_handler.py` (nombres en español tipo `PEDIDO_WA_NUEVO`) —
   es la pregunta abierta más importante de este documento, con potencial de ser un bug de
   integración real (notificaciones a staff que nunca llegan porque el evento nunca matchea).
3. **Unificar la escala de prioridad de Delivery** (35/40) con la escala oficial del CLAUDE.md, o
   documentar explícitamente por qué Delivery usa una escala más fina.
4. Los alias legacy (`WA_PEDIDO_CREADO`, `WA_COTIZACION_CREADA`, `WA_VENTA_CONFIRMADA`,
   `WA_ANTICIPO_REQUERIDO`, `WA_ANTICIPO_PAGADO`) siguen coexistiendo con sus equivalentes "dominio"
   (`SALE_CREATED`, `QUOTE_CREATED`, `PAYMENT_REQUIRED`, `PAYMENT_RECEIVED`) exactamente como
   documentaba el plan de deprecación previo (`WHATSAPP_EVENT_CATALOG.md`, sección "Plan de
   deprecación formal por consumidor", fechas objetivo 2026-06-30/07-15) — esas fechas ya pasaron
   (hoy es 2026-09-01) sin que se haya retirado ningún alias; el plan de deprecación no se ejecutó.
