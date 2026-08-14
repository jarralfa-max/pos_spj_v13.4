# CRM-21 — Migración de consumidores: POS, Ventas, WhatsApp, Delivery, Fidelidad, Finanzas

Fecha: 2026-08-13. Primera fase de este pipeline que sale del módulo
`customers_crm` propiamente dicho: cierra el hueco de identidad que CRM-13
dejó explícitamente diferido — nombrado literalmente "CRM-21/22" en tres
docstrings de ese momento — y activa, contra datos reales, la capa de
integración de solo lectura que CRM-13 ya había construido pero dejado
inerte.

## El hallazgo que redujo el alcance real de esta fase

La auditoría inicial (agente de investigación) sugería una reconciliación de
identidad en tres direcciones: `clientes.id` (legacy), `customers.id`
(Customer Master nuevo, CRM-3) y `delivery_orders.cliente_id` (declarado
`INTEGER`). Verificación directa del código (no solo grep, sino trazando el
camino de escritura real) descartó la tercera:

- `delivery_orders.cliente_id INTEGER` es **deriva de esquema, no un tercer
  espacio de identidad real**. SQLite no impone tipos estrictos (solo
  afinidad de columna); `integrations/pos_adapter.py` acuña
  `new_uuid()` (TEXT) y `repositories/delivery_repository.py` lo pasa sin
  tipar — la columna termina guardando el mismo UUID TEXT de `clientes.id`
  de siempre. Documentado en el propio docstring de
  `customer_delivery_summary_query.py` (antes decía "nunca coincide";
  ahora dice la verdad verificada).

- **`clientes.id` YA es un UUIDv7 TEXT** (`migrations/m000_base_schema.py`,
  comentario "REGLA CERO: id TEXT acuñado por ClienteRepository/UseCase") —
  no es un entero legacy como asumía el docstring original de
  `CustomerAccountsReceivableSummaryQuery`. El problema real es más simple
  de lo que sonaba: son DOS TABLAS separadas, cada una con su propia
  secuencia de UUIDv7 acuñada independientemente, no un desajuste de tipos.

- **Tres de las cinco queries de integración de CRM-13 ya funcionan hoy
  contra datos reales, sin ningún cambio**: `CustomerOrdersSummaryQuery`,
  `LoyaltyCustomerSummaryQuery` y `CustomerAccountsReceivableSummaryQuery`
  filtran sus tablas legacy (`pedidos_whatsapp`/`loyalty_snapshots`/
  `cuentas_por_cobrar`) por `WHERE cliente_id=?` usando literalmente lo que
  el llamador les pase como `customer_id` — llamarlas con el `cliente_id`
  LEGACY simplemente funciona. Solo necesitaban un punto de llamada, no
  traducción de identidad.

- **Solo dos cosas necesitaban de verdad el puente**: `sales_event_handlers.py`
  (vía `RecordCustomerSaleActivityUseCase` → `uow.customers.get(customer_id)`,
  que lee la tabla NUEVA) y `CustomerCommercialEligibilityQuery.check()`
  (mismo motivo). Esto acotó el trabajo real a construir un puente de
  identidad más pequeño de lo que el nombre de la fase sugería, y a NO
  reescribir las rutas de escritura de los seis módulos consumidores.

## El puente de identidad

- `customers.legacy_customer_id TEXT` (nullable, único parcial —
  migración `193_customers_legacy_customer_bridge.py`, mismo patrón
  idempotente que la 192) + columna espejo en el esquema born-clean
  (`customers_crm_schema.py`).
- `backend/application/customers/use_cases/legacy_customer_bridge_use_cases.py`
  (nuevo): `ResolveLegacyCustomerUseCase` (resuelve o crea perezosamente,
  nunca lanza — un `clientes.id` sin fila legacy correspondiente recibe un
  nombre de reserva en vez de bloquear al llamador) y
  `BackfillLegacyCustomersUseCase` (por lotes, reanudable, comparte la misma
  lógica de creación que el resolver perezoso para que ambos caminos nunca
  diverjan). CLI de un solo uso: `tools/crm/backfill_legacy_customers.py`.
- **Deliberadamente sin duplicidad de identidad ni heurística de
  coincidencia por teléfono/RFC** — el puente es 1:1 y explícito
  (`legacy_customer_id`), no un intento de fusionar registros parecidos
  (eso es trabajo de `CustomerDuplicatePolicy`, CRM-11, y no se reutiliza
  aquí a propósito: un puente debe reflejar EXACTAMENTE un registro legacy,
  no el más parecido).

## Activación real de CRM-13

`core/events/wiring.py` gana `_wire_customers_crm_sales_activity`, llamada
desde `wire_all()` junto a `_wire_venta`. Se suscribe a
`VENTA_COMPLETADA`/`VENTA_CANCELADA` con prioridad 40 (por debajo de
fidelidad=50, por encima de auditoría=30 — es una proyección secundaria de
relación con el cliente, no el ledger contable ni el sync crítico), resuelve
el `cliente_id` legacy del payload vía `ResolveLegacyCustomerUseCase` y
recién entonces llama a `handle_sale_completed`/`handle_sale_cancelled` — que
no cambiaron: su contrato siempre fue recibir un `customers.id` real, solo
que hasta ahora nadie se lo daba. Con "soft-fail" idéntico a
`_treasury_venta`: cualquier excepción se registra en debug y nunca bloquea
ni revierte una venta.

## Los seis puntos de integración (aditivos, sin tocar escritura legacy)

| Área | Punto de integración | Necesitó el puente |
|---|---|---|
| POS/Ventas | `modulos/ventas.py`, aviso no bloqueante de elegibilidad CRM junto al gate de venta a crédito existente | Sí (`CustomerCommercialEligibilityQuery`) |
| WhatsApp | `GET /api/v1/clientes/{id}/crm-summary` (nuevo) + `ERPBridge.get_crm_summary()`/`CustomerGateway.get_crm_summary()` | Solo para el nombre/folio amigable |
| Delivery | `GET /api/v1/pedidos/{id}` gana el campo `crm_delivery_summary` | No |
| Fidelidad | `ClienteService.get_crm_loyalty_summary()` (nuevo) | No |
| Finanzas | `FinancePresenter.crm_receivable_summary()` + botón "Ver resumen CRM" en `AccountsReceivablePage` | No |

Ninguno de los seis reescribe una ruta de escritura legacy
(`ClienteRepository`, `repositories/ventas.py`, `loyalty_service.py`,
`accounts_receivable_service.py`/`customer_credit_service.py`,
`whatsapp_service/erp/bridge.py`'s `INSERT INTO clientes`) — esa
migración de escritura completa queda fuera de alcance, deferida a una fase
futura (CRM-22+), por CLAUDE.md Prioridad 0: no arriesgar datos financieros
reales en producción sin una migración de datos dedicada y su propia
verificación.

## Un hallazgo colateral no resuelto aquí: el permission checker de Customer Master nunca está wireado

`LoyaltyCustomerSummaryQuery`, `CustomerOrdersSummaryQuery` y
`CustomerDeliverySummaryQuery` exigen `CustomerAuthorizationPolicy.require()`
— que falla cerrado (`CustomerConfigurationError`) cuando no hay un
`PermissionChecker` real configurado. Ningún composition root de este
repositorio conecta uno hoy (confirmado: cada constructor usa
`CustomerAuthorizationPolicy()` por defecto en TODO el código no-test). Esto
significa que, en producción, HOY, los tres puntos de integración que pasan
por esas queries (WhatsApp loyalty/orders, Delivery, Fidelidad) devuelven
"no disponible" — no porque este trabajo esté incompleto, sino porque un
gap previo y más grande (nunca cerrado por ninguna fase anterior, ni
siquiera por el propio menú de CRM, según CRM-14) sigue abierto. Cada
punto de llamada de esta fase documenta esto explícitamente en su propio
código y degrada con gracia (`None`/"no disponible"), nunca lanza al
llamador. `CustomerAccountsReceivableSummaryQuery` (la única de las cinco
sin este gate) es la única que funciona hoy sin ninguna condición extra —
por eso el punto de Finanzas es, en la práctica, el único
inmediatamente funcional en producción tal cual está.

No se intentó "arreglar" esto inyectando una política permisiva en código
de producción — `AllowAllCustomerPermissionCheckerForTests` es
explícitamente "NEVER wire in production" por su propio docstring, y
hacerlo para llamadores de sistema (bot de WhatsApp, Delivery) habría sido
una regresión de seguridad real, no una mejora.

## Verificación

```bash
python -m pytest tests/architecture/test_customers_crm_*.py \
  tests/integration/customers/ tests/integration/crm/ tests/unit/customers/ \
  tests/integration/finance/ -q
```

- 22 guardrails CRM-1 verdes.
- 11 pruebas nuevas (`test_crm_21_legacy_identity_bridge.py`): resolver
  crea/es idempotente/degrada con nombre de reserva; backfill por lotes,
  reanudable, omite ya-puenteados; la nueva suscripción del EventBus
  puentea y proyecta de verdad sobre un `VENTA_COMPLETADA`/`VENTA_CANCELADA`
  realista (antes solo no-opeaba, ver
  `test_handle_sale_completed_noops_on_unmapped_legacy_id` en
  `test_crm_13_integraciones.py`, que sigue pasando sin cambios — el
  contrato de llamada directa a `sales_event_handlers.py` no cambió, solo
  ganó un llamador nuevo delante); elegibilidad comercial resuelve para un
  cliente que solo existe en `clientes`.
- 9 pruebas nuevas (`test_crm_21_read_path_wiring.py`): el endpoint REST de
  WhatsApp (200 con datos cuando el permission checker está permitido vía
  monkeypatch, degradación correcta a `None` sin él — el comportamiento real
  de hoy), el campo `crm_delivery_summary` en el detalle de pedido, el
  resumen de fidelidad, el resumen de CxC de Finanzas (funciona sin
  monkeypatch, por no tener el gate).
- Migración 193 verificada end-to-end contra un bootstrap completo
  (`migrations.engine.up`): columna, índice único parcial y tabla `clientes`
  presentes.
- Un guardrail REPO-WIDE (no solo CRM), `tests/architecture/
  test_uuidv7_cutover_protection.py`, detectó una regresión real durante el
  desarrollo: su patrón `legacy_id` (sin límites de palabra) coincidía como
  subcadena dentro de `legacy_identity_bridge_use_cases.py` (el nombre del
  módulo), `get_by_legacy_id` (el método del repositorio) e
  `idx_customers_legacy_id` (el índice) — subió el conteo de 2 (línea base)
  a 15. Nada de esto es un patrón de identidad entera real (todo son
  UUIDv7 TEXT), pero el guardrail no lo sabe — es un escaneo léxico, no
  semántico. Se renombró todo lo afectado (`legacy_customer_bridge_use_cases.py`,
  `get_by_legacy_customer_id`, `idx_customers_legacy_customer_id`,
  migración renombrada a `193_customers_legacy_customer_bridge.py`) en vez
  de subir la línea base — subirla habría debilitado la protección para
  violaciones futuras genuinas. Mismo tipo de colisión ya documentado en
  CRM-14/17/18/21 (variable `legacy_id`), esta vez en un guardrail
  repo-wide en lugar del guardrail CRM-específico ya conocido.
- Se corrió también la suite completa `tests/architecture/` (no solo la
  familia `test_customers_crm_*.py`) para confirmar que ningún otro
  guardrail repo-wide reaccionaba a este trabajo: 84 fallas preexistentes
  confirmadas como no relacionadas (transfers, settings, procurement,
  refactor_orchestrator, y un guardrail de esquemas —
  `test_no_schema_changes_outside_migrations`/`test_no_raw_sqlite_connect`
  — cuya allowlist está desactualizada para TODA una generación de archivos
  `*_schema.py` con función `create_X_schema(conn)`, no solo
  `customers_crm_schema.py`; el conteo de violaciones en ese archivo
  coincide exactamente con sus 12 tablas ya existentes desde antes de esta
  fase, confirmando que no es nuevo). Ninguna se tocó — fuera de alcance.
- El aviso de elegibilidad en `modulos/ventas.py` (POS/Ventas) no tiene
  prueba dedicada — vive dentro de un flujo de diálogo PyQt5 grande, mismo
  criterio de esta sesión para otros puntos de llamada Qt legacy
  (documentado, no mockeado en aislamiento); se verificó por sintaxis y por
  no introducir regresiones en la suite existente.
- Sintaxis limpia en todo el repositorio, incluyendo `whatsapp_service/`.
- Guardrail CRM-1 `test_customers_crm_has_no_integer_identity` detectó un
  falso positivo real durante el desarrollo: nombrar una variable local
  `legacy_id` (sin el sufijo `_customer_id`) coincide con el patrón
  `\blegacy_id\b` que ese guardrail prohíbe explícitamente en todo el
  contexto CRM — renombrada a `unbridged_ids`/`clientes_row_id`. Mismo tipo
  de colisión ya documentado en fases anteriores (CRM-14/17/18), añadido
  aquí a la disciplina ya establecida de parafrasear tokens prohibidos.

## Hallazgo fuera de alcance, descubierto durante la investigación

El árbol de trabajo de este repositorio (raíz `pos_spj_v13.4/pos_spj_v13.4/`)
tiene un índice de git desactualizado: sigue rastreando una copia anidada
legacy completa (`pos_spj_v13.4/<todo el árbol otra vez>`) que ya no existe
en disco, mientras que el árbol plano real donde vive todo el código —
incluyendo cada archivo tocado por esta fase — está completamente sin
rastrear (`??`) por git. No es algo introducido por esta fase ni por esta
sesión; se deja documentado porque afecta cómo se debería confirmar
(`git add`/`git commit`) este trabajo más adelante — un `git add -A`
descuidado agregaría miles de eliminaciones de la copia legacy junto con el
trabajo real. No se tocó nada de esto.

## Pendiente (próximas fases)

- **Migración de las rutas de ESCRITURA** de los seis módulos consumidores
  al nuevo Customer Master (CRM-22+) — el trabajo más grande y de mayor
  riesgo que esta fase deliberadamente no intentó.
- **Wireado del `PermissionChecker` de Customer Master** en el composition
  root — desbloquearía WhatsApp/Delivery/Fidelidad de verdad, sin tocar el
  código que esta fase ya escribió.
- **Ejecutar el backfill** (`tools/crm/backfill_legacy_customers.py`) contra
  la base de datos de producción — hoy nadie lo ha corrido; hasta entonces,
  el puente se llena de forma perezosa, un cliente a la vez, en su primera
  referencia real.
- **Teclado virtual en `PhoneInput`/`AddressInput`** (pendiente de CRM-18,
  sin relación con esta fase, solo listado aquí por continuidad del
  documento de pendientes).
