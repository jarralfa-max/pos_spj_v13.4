# Lote 9 — WhatsApp

- **Rama:** `fix/lote-9`, desde `claude/erp-financial-bounded-context-uqxz6b` @ `e58f6849`
- **Fecha:** 2026-11-06
- **Migraciones:** 374 (`whatsapp_unmatched_payments`, SDLC-WA-001). Quedan libres 375 y 376.
- **Ampliación del 2026-11-09:** el responsable aprobó WA-001, 003, 004, 005 y 021 (cherry-pick `8defa04f`).

## Estado por ítem

| Ítem | Estado | Causa |
|---|---|---|
| SDLC-WA-002 | **LISTO** | Commit `e50c9f6a` |
| SDLC-WA-001 | **LISTO** | Commit `e56a5fbe` |
| SDLC-WA-005 | **LISTO** | Commit `8d0fb689` |
| SDLC-WA-003 | **BLOQUEADO** | El canal no tiene identidad de servicio; la construye SDLC-WA-009, fuera de este lote (ver abajo) |
| SDLC-WA-021 | **ESPERA** | Depende de SDLC-WA-003 |
| SDLC-WA-004 | **ESPERA** | Depende de SDLC-WA-003 |

## SDLC-WA-002: qué se cambió

El problema seguía: sin secreto y fuera de producción, los dos webhooks aceptaban sin firma (`webhook/whatsapp.py:85-89`, `webhook/mercadopago.py:53-57`). También seguía el rechazo de todo `ts` en segundos: la prueba nueva falló sobre el código anterior.

- **Webhooks:** sin secreto responden 503 en cualquier entorno. Aceptar sin firma exige `WA_ALLOW_UNSIGNED_WEBHOOKS` (`1`, `true`, `yes`), que se ignora en producción y en estación instalada. El `error` nombra el secreto faltante y dice por qué se ignoró el opt-in.
- **MercadoPago:** `ts` menor a 10¹² se trata como segundos; si no, como milisegundos. La ventana sale de `MP_SIGNATURE_MAX_AGE_SECONDS` (por defecto 300). Cada rechazo registra su motivo en el logger `wa.hmac`.
- **Arranque:** una línea con entorno, `instalado` y `webhooks_sin_firma`, más un `warning` si `APP_ENV` no se reconoce.
- **Salud:** check nuevo `webhook_signature` (HEALTHY, DEGRADED o UNHEALTHY).
- **Documentación:** docstring de `service_host.py` y entrada en `migrations/MIGRATION_LOG.md`.

Decisiones aplicadas del spec: D1=B, D2=B, D3=A.

### Pruebas que lo cubren

Corrida roja sobre el código anterior, antes del arreglo: 67 fallas, incluidos los criterios 1, 2, 4, 5 y 7.

| Criterio del spec | Prueba |
|---|---|
| 1–5 | `whatsapp_service/tests/test_webhook_production_fail_closed.py` |
| 6 | `whatsapp_service/tests/test_webhook_signature_contract.py` (32 casos; pasaban antes del arreglo, como corresponde a una regresión) |
| 7, 8 y D2 | `whatsapp_service/tests/test_mercadopago_webhook_signature.py` |
| Reglas de settings | `whatsapp_service/tests/test_settings_webhook_security.py` |
| 9 | `whatsapp_service/tests/test_main_production_gate.py` |
| 10 | `whatsapp_service/tests/test_health_checks.py` |
| 11 | Pruebas anteriores actualizadas con opt-in, ninguna borrada, incluidas 3 de `pos_spj_v13.4/tests/test_wa_phase9_regression.py` |

### Desviaciones del plan

- `describe_webhook_security()` agrega la clave `opt_in_ignored_reason`, y el arranque emite un `warning` aparte. Lo pide la sección de seguridad del spec («warning en un opt-in ignorado»), aunque no estaba en la lista de claves.
- `verify_mp_signature` también registra `X-Signature incompleto`, porque el 403 del webhook ya no da el motivo.
- Las pruebas de `test_mercadopago_webhook_signature.py` doblan `get_mp_webhook_secret` en vez de `MP_WEBHOOK_SECRET`, para no depender de la base del ERP.
- El docstring de `service_host.py` avisa que `APP_ENV=production` también bloquea las escrituras SQLite del bridge (`erp/bridge.py:214`).

## SDLC-WA-001: pagos de MercadoPago casados por venta y monto

Respuesta del responsable: «está apagado» (MercadoPago no se usa en producción).

El problema seguía, en `webhook/mercadopago.py:65` y `:99-169`:
- sólo procesaba `payment.created`;
- buscaba la venta por sufijo de teléfono e intentaba `int(pref)` contra UUID;
- se tragaba los errores y avisaba al cliente antes del match;
- la idempotencia era por venta y monto;
- respondía 200 aunque no hubiera guardado nada.

La prueba nueva dio 19 fallas sobre el código anterior.

Qué cambió:
- **Estados:** procesa `payment.created` y `payment.updated` cuando el pago consultado está `approved`.
- **Match:** por la venta de `external_reference` (`<venta_id>:<teléfono>`, el formato de `pago_flow.py`). La venta debe estar `pendiente_wa` y coincidir en teléfono, moneda MXN y monto exacto del total. Ya no hay búsqueda por sufijo de teléfono.
- **Bandeja:** lo que no casa va a `whatsapp_unmatched_payments` (migración 374), con su motivo y una sola vez por pago.
- **Idempotencia:** por el id del pago (`mp_payment:<id>`). Dos pagos reales del mismo monto ya no se funden: el segundo va a la bandeja como «venta no pendiente». Los eventos y el aviso al cliente salen sólo después del match, dentro de la operación idempotente.
- **Reintentos:**
  - 400 con JSON inválido o con ids distintos en URL y cuerpo; 413 con cuerpo de más de 64 KiB;
  - 502 si falla la consulta a MercadoPago; 503 sin token o sin ERP;
  - 500 si falla la confirmación, y el reintento deja el pago en la bandeja;
  - nada se responde 200 sin haberse guardado.

Pruebas: `whatsapp_service/tests/test_mercadopago_webhook_matching.py` (19). Se actualizaron las de firma que fijaban «ignorar `payment.updated`»: ahora usan una acción ajena a pagos.

Migración 374: probada dos veces sobre una base temporal (idempotente) y registrada en `engine.py`. **No** se probó sobre una copia de la base real.

Fuera de alcance:
- El monto esperado es el total de la venta. Si el pago es un anticipo parcial, va a la bandeja hasta WA-004, que define el monto del anticipo.
- La bandeja no tiene pantalla.

## SDLC-WA-005: imports `core.*` y bandeja del POS

El problema seguía. `test_channel_uses_qualified_imports` fallaba con los 6 imports de `core.*`, y la prueba nueva dio 13 fallas.

Qué cambió:
- **Ajuste de peso** (`erp/adjustment_approval.py`):
  - recalcula `delivery_orders.total` como la suma de subtotales a centavos, la misma regla del servicio eliminado (`DeliveryTotalPolicy`), y la proyecta a `ventas.total`;
  - registra los eventos con id UUIDv7 y la sucursal real; antes era `COALESCE(sucursal_id, 1)`;
  - si algo falla, revierte en vez de dejar el cambio a medias.
- **Respuesta del cliente:** «no acepto» ya cuenta como rechazo, porque el rechazo se evalúa primero.
- **`bridge.py`:** se quitaron la demanda programada y el aviso de escritorio, que importaban `core.*` y fallaban en silencio. La demanda programada ahora deja un `warning`: el ERP no tiene sustituto.
- **`confirm_order_use_case.py`:** se quitó la rama muerta de `core.services.anticipo_service`.
- **Bandeja del POS** (`erp/pos_notifier.py`): inserta con id UUIDv7, la tabla de respaldo usa TEXT y los fallos se registran como `error`, no como `debug`.

Pruebas:
- nueva: `whatsapp_service/tests/test_wa005_core_imports_and_inbox.py` (17);
- actualizadas al esquema real, con ids TEXT: `test_adjustment_approval_phase7.py` (antes ni se recolectaba), `test_pos_notifier_dedupe.py` y `test_bridge_notification_routing.py`. La última exigía el servicio `core` eliminado; ahora exige que el aviso no dependa de él.

## SDLC-WA-003: por qué quedó BLOQUEADO

- **El destino sí está respondido**, aunque no al pie de la pregunta de su intent:
  - WA-021 responde «costumer_orders»;
  - SDLC-ORD-003 (`fix/lote-6`, `decision.md`) eligió `customer_orders` con `quotes`, vía caso de uso canónico, y lo pone como paso 3 de su plan de corte.
- **Lo que falta es la identidad del canal.** `CaptureOrderUseCase` exige `actor_user_id` con `ORDER_CREATE` (`backend/application/orders_delivery/use_cases/capture_order_use_cases.py:114`) y lo audita por usuario. La política por defecto falla cerrada.
- **Esa identidad es SDLC-WA-009.** El responsable respondió «tabla diferente», pero esa tabla no existe y el ítem no está en este lote. Un usuario técnico en `usuarios` contradiría su respuesta, así que no se inventó.
- **También queda pendiente** el puente `clientes.id`/`customers.id` (SDLC-CRM-003, paso 2 del plan de ORD-003).
- **Pregunta:** ¿se construye antes SDLC-WA-009, la identidad de servicio en tabla propia, para que el canal cree pedidos en `customer_orders`?
- **Arrastra a otros ítems:** si el pedido cambia de origen a `customer_orders`, el match de WA-001 (hoy contra `ventas` `pendiente_wa`) deberá seguirlo.

## Resultados de pruebas

Todas corridas con `PYTHONPATH` al worktree y `ERP_DB_PATH` a una base vacía en el directorio temporal.

| Comando | Antes | Después |
|---|---|---|
| `pytest whatsapp_service/tests --continue-on-collection-errors` | 15 failed, 699 passed, 1 error | 14 failed, 807 passed, 1 error |
| `pytest tests/test_wa_*.py --continue-on-collection-errors` (desde `pos_spj_v13.4/`) | 22 failed, 67 passed, 35 errors (plan) | 22 failed, 67 passed, 35 errors |
| `tests/test_wa_phase9_regression.py` | 1 failed, 4 passed | 1 failed, 4 passed |
| `tests/architecture/test_whatsapp_runtime_imports.py` y `tests/integration/test_whatsapp_startup_regression.py` | 1 falla en el baseline | 1 failed, 4 passed |
| `python -m compileall -q .` desde `pos_spj_v13.4/`, y `compileall` de `whatsapp_service/` | — | Código 0 en ambos |
| `tests/architecture` completo | 22 failed, 879 passed, 1 skipped, 2 xfailed (plan, B3) | 22 failed, 879 passed, 1 skipped, 2 xfailed |
| Ampliación: `whatsapp_service/tests` tras WA-005 | 14 failed, 807 passed, 1 error | 13 failed, 843 passed, 0 errors |
| Ampliación: `tests/test_wa_*.py` | 22 failed, 67 passed, 35 errors | Igual |
| Ampliación: `test_whatsapp_runtime_imports.py` + `test_whatsapp_startup_regression.py` | 1 failed, 4 passed | 5 passed |
| Ampliación: guardias de migración y esquema* | — | Fallas preexistentes, ver nota |
| Ampliación: `compileall` de `whatsapp_service/`, `migrations/` y `schema/` | — | Código 0 |
| Ampliación: `tests/architecture` completo | — | **PENDIENTE** (no se relanzó, por indicación del coordinador) |

\* Guardias de migración y esquema: `test_main_database_bootstrap_is_single_sequence`, `test_uuid_cutover_migration_gated`, `test_schema_versions`, `tests/unit/bootstrap/test_steps.py`, `test_no_schema_changes_outside_migrations`, `test_clean_birth_guardrails` y `test_uuidv7_cutover_protection`. Se corrieron tras WA-001: 5 failed, 91 passed.
- Cuatro de las fallas son del baseline: `test_no_schema_changes_outside_migrations`, `test_clean_birth_guardrails`, `test_uuidv7_cutover_protection` y `test_whatsapp_runtime_imports`. Esta última ya pasa tras WA-005.
- La quinta es `test_steps.py::test_application_paths_step_creates_directories`: el worktree no tiene `pos_spj_v13.4/data`. No la toca este lote, y no se verificó sobre la rama base.
- `test_no_schema_changes_outside_migrations` lista todos los módulos de `schema/` (SDLC-CORE-008). `whatsapp_schema.py` pasa de 18 a 19 por la tabla de WA-001, siguiendo el patrón de las migraciones 243-247.

Diferencias en `whatsapp_service/tests`:
- desaparecen el error de colección de `test_adjustment_approval_phase7.py` y la falla de `test_bridge_notification_routing`;
- no hay fallas nuevas.

La única diferencia en `whatsapp_service/tests` es la falla que se corrigió, `test_webhook_accepts_valid_signature_and_ignores_non_payment_action`. No hay fallas nuevas.

La columna «Antes» de `test_wa_*.py` viene de la línea base del plan, no de una corrida propia sobre `e58f6849`.

## Fallos preexistentes (no se tocaron)

- `whatsapp_service/tests`: 14 fallas (`test_bridge_notification_routing`, `test_conversation_quote_context`, `test_cotizacion_flow_phase6`, `test_intent_resolver`, `test_intent_resolver_ai_paths`, `test_message_router_branch_switch`, `test_message_router_intent_resolver_integration`, `test_wa_event_log_insert`) y el error de colección de `test_adjustment_approval_phase7.py`.
- `tests/test_wa_*.py`: las fallas y errores de la línea base.
- `test_wa_phase9_regression.py::test_webhook_invalid_signature_returns_403`: ya fallaba porque dobla `config.settings`, no `whatsapp_service.config.settings`. Antes daba 200 y ahora da 503; sigue sin dar 403 por la misma causa.
- `test_whatsapp_runtime_imports.py::test_channel_uses_qualified_imports`: imports `core.*`, SDLC-WA-005.

## Para el responsable

1. **Corte operativo (D3=A):** una estación con el servicio local y sin `WA_APP_SECRET` deja de recibir mensajes hasta configurarlo. Va en la nota de release.
2. **`/health` de desarrollo:** sin secreto ni opt-in, el estado global pasa a UNHEALTHY. Es lo que pide el spec.
3. **`APP_ENV=production`:** el spec pide ponerlo en el ejemplo de `whatsapp.env`, pero sin `ERP_API_URL` bloquea las escrituras SQLite, que hoy son la única vía de pedidos (SDLC-WA-003). Se dejó el aviso en el docstring. Conviene no recomendarlo a las estaciones hasta cerrar WA-003.
4. **Pregunta abierta sin responder:** `BACKLOG.md:408` sigue marcando «¿Hay hoy algún despliegue sin `APP_ENV=production`?» como bloqueante, sin respuesta del responsable en `intent.md` ni en el backlog. El spec aprobado la declara no bloqueante y D3 ya decide qué hacer, así que se avanzó. Sigue sin saberse si alguna estación real tiene el servicio activo y sin secreto.
5. **Unidad de `ts`:** la deducción por magnitud sigue la documentación, pero no se probó con una notificación real de MercadoPago. Tampoco se verificó si sus reintentos llegan con `ts` nuevo; si conservan el original, la ventana de 300 s los rechazaría.
6. **`whatsapp_service/.env.example` no se actualizó:** una regla de permisos bloquea su lectura. Faltan `WA_ALLOW_UNSIGNED_WEBHOOKS` y `MP_SIGNATURE_MAX_AGE_SECONDS`.
7. **`bootstrap/application_factory.py`** tiene su propio `lifespan` y no emite la línea de estado, como dice el plan. El host real (`service_host.py`) usa `main:app`.

## Trampa del entorno

El `.venv` compartido tiene una instalación editable que apunta al repo principal. Sin `PYTHONPATH`, desde la raíz del worktree `backend` sale del repo principal, y desde `pos_spj_v13.4/` `whatsapp_service` también. En ese caso las pruebas de `pos_spj_v13.4/tests` **no ejercitan el código del worktree**, y las de `whatsapp_service/tests` leen en solo lectura la base del repo principal. La línea base inicial sin aislar salió igual a la aislada: 15 failed, 699 passed, 1 error.
