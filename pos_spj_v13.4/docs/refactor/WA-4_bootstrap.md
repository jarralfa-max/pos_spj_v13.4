# WA-4 — Bootstrap (canal WhatsApp)

Ejecutado: 2026-09-01. `whatsapp_service/bootstrap/` (ApplicationFactory,
CompositionRoot, Lifecycle, Health checks) — la primera fase que conecta
algo de WA-2 (dominio) / WA-3 (esquema) a código que realmente corre.
Integrado de forma **aditiva** en `main.py` (la app en producción hoy):
nada de lo que ya funciona se reemplazó ni se apagó.

---

## 1. CompositionRoot (§8)

`bootstrap/composition_root.py::WhatsAppCompositionRoot` — recibe una
conexión SQLite ya abierta y construye los 6 repositorios SQLite reales
sobre las entidades de WA-2/esquema de WA-3
(`infrastructure/persistence/sqlite_*_repository.py`, uno por entidad:
Account+ProviderConfiguration, Number, Identity, Conversation+Session,
Message+Delivery), más el `SecretStore` singleton de WA-1 (reutilizado vía
el nuevo `config.settings.get_secret_store()` — nunca se construye un
segundo `SecretStore`).

Cada repositorio implementa exactamente el `Protocol` que WA-2 ya definió
en `domain/whatsapp/repository_ports.py` — verificado con round-trips
reales (guardar una entidad construida vía su propio `create()`/métodos de
transición del dominio, releerla, comparar). `save()` usa
`INSERT ... ON CONFLICT(id) DO UPDATE` (upsert) en todos los repositorios
mutables, porque las entidades de dominio son mutables y se re-guardan
después de una transición de estado — verificado con tests que llaman
`save()` dos veces sobre la misma entidad tras mutarla.

**Lo que §8 pide y todavía no existe se documenta explícitamente en el
docstring del módulo, no se inventa para completar la lista**:
`ProviderGateway`/`WebhookAuthenticator`/`WebhookProcessor` → WA-5/WA-6;
`OutboxRepository`/`IdempotencyRepository`/`OutboundMessageDispatcher` →
WA-17 (las tablas ya existen desde WA-3, sin repositorio propio todavía);
`TemplateRepository` → futuro (§24); `AgentRepository`/`HandoffCoordinator`
→ WA-16; `ERP API clients` → WA-9; `IntentResolver`/`ConversationEngine` →
WA-7/WA-8 (existe una versión legacy de `IntentResolver`, no wireada aquí).

## 2. ServiceRegistry

`bootstrap/service_registry.py::ServiceRegistry` — separa "quién
construye" (CompositionRoot) de "quién expone" (Registry), por la regla
explícita de §8 de no exponer un contenedor completo a flows. El
CompositionRoot expone además accesores tipados (`root.accounts`,
`root.identities`, etc.) para que ningún llamador futuro tenga que
hardcodear strings de nombre de servicio.

## 3. dependency_graph_validator

`bootstrap/dependency_graph_validator.py::validate_composition_root()` —
guarda real, no decorativa: si una fase futura agrega un nombre a
`composition_root.REQUIRED_SERVICES` pero olvida registrarlo en
`_build()`, el arranque falla de inmediato con un mensaje claro, en vez de
que el primer consumidor real reciba un `ServiceNotRegisteredError`
confuso más tarde, en medio de un webhook. Se llama tanto desde
`main.py::lifespan()` (integración en vivo) como desde
`bootstrap/lifecycle.py::start_composition_root()`.

## 4. Health checks (§58)

`bootstrap/health_checks.py` — vocabulario HEALTHY/DEGRADED/UNHEALTHY/
UNKNOWN exacto de §58. Tres checks reales hoy (`database`, `schema` —
verifica las 12 tablas de la migración 243 —, `secrets` — espeja el gate
de producción de WA-1 como chequeo continuo, no solo al arrancar) y cuatro
explícitamente `UNKNOWN` con la fase dueña en `detail`
(`provider_gateway`→WA-5, `inbox_worker`→WA-6, `outbox_worker`→WA-17,
`erp_api`→WA-9) — nunca se reportan como HEALTHY solo para que la lista
quede completa. `detail` nunca lleva un secreto ni una ruta local completa
(§58: "no debe devolver secretos, rutas locales ni detalles sensibles") —
verificado con test explícito.

`build_health_response()` es standalone (mismo criterio de testabilidad
que `main.py::_assert_production_secrets_configured`, WA-1) — se usa desde
`main.py::/health` (integración en vivo) y desde
`bootstrap/application_factory.py::/health` (la app nueva).

## 5. Lifecycle + ApplicationFactory (§7)

`bootstrap/lifecycle.py::start_composition_root()`/`stop_composition_root()`
— aplica el gate de producción de WA-1, abre una conexión, construye y
valida el CompositionRoot. `bootstrap/application_factory.py::WhatsAppApplicationFactory`
construye una app FastAPI completa (lifespan + `/health`) a partir de eso —
la forma que §7 pide para el `main.py` final ("crear FastAPI, invocar
ApplicationFactory, registrar lifespan, registrar routers canónicos").

**Esta factory NO es el entrypoint real todavía.** `main.py` sigue siendo
la app en producción — expone el webhook oficial de Meta, MercadoPago, y
los routers `notify`/`delivery` construidos sobre `ERPBridge`/
`MessageRouter`/`IntentParser`/`flows/`, piezas que WA-5 a WA-9 todavía no
reemplazan. Intentar el corte real de `main.py` ahora habría significado o
bien romper el webhook en vivo, o bien construir de golpe Provider
Gateway/Conversation Engine/Intent Resolution sin las fases que las
anteceden — ninguna de las dos es lo que este checklist de WA-4 pide.
`WhatsAppApplicationFactory` queda lista y probada (`test_application_factory.py`)
para cuando WA-5..WA-9 existan y el corte real sea seguro — mismo patrón
"nuevo en paralelo, sin cortar lo viejo" que domain/schema ya establecieron.

## 6. Integración aditiva en `main.py` (la app real)

Dos cambios, ambos verificados con un smoke test end-to-end contra un
bootstrap real (`scripts/bootstrap_db.py` + `TestClient(main.app)`, no solo
tests aislados):

- `lifespan()` construye `WhatsAppCompositionRoot(erp.db)` — **reutiliza la
  misma conexión** que `ERPBridge` ya gestiona, no abre una segunda — y lo
  valida con `validate_composition_root()`, justo después de conectar al
  ERP. No reemplaza nada de lo que ya se construye después (EventBus,
  ConversationStore, IntentParser, MessageRouter, webhooks) — coexiste.
- `/health` ahora llama `build_health_response()` en vez de devolver el
  `{"status": "ok", "erp_connected": ...}` fijo de antes. `service`/
  `erp_connected` se conservan para compatibilidad — el único consumidor
  ERP-side (`core/integrations/whatsapp_client.py::WhatsAppClient.health_check()`)
  solo verifica que la respuesta no sea `None`, nunca parseó la forma
  exacta, así que enriquecer el cuerpo no rompe nada (confirmado leyendo
  ese consumidor antes de cambiar la forma).

Smoke test real (`python -c "..."` con `TestClient(main.app)` contra una
base bootstrapeada desde cero con las 243 migraciones): arranca
correctamente, `/health` responde 200 con `status: DEGRADED` (correcto —
la base de prueba no tiene secretos Meta configurados, comportamiento
esperado fuera de producción) y los 4 checks `UNKNOWN` listados con su
fase dueña.

---

## Tests

60 tests nuevos, todos en verde:

- `test_service_registry.py` (7)
- `test_composition_root.py` (10 — incluye el validador fallando cuando se
  quita un servicio requerido, y listando TODOS los faltantes, no solo el
  primero)
- `test_sqlite_whatsapp_repositories.py` (23 — round-trip real de los 6
  repositorios, incluidos upserts tras mutar la entidad y las dos consultas
  no triviales: `get_open_for_identity` ignorando conversaciones cerradas,
  `get_global_numbers` filtrando por rol)
- `test_health_checks.py` (14 — los 3 checks reales en sus tres estados
  posibles, los 4 `UNKNOWN`, la lógica de severidad de `overall_status`, y
  que ningún valor de secreto aparece en `detail`)
- `test_application_factory.py` (3 — vía `fastapi.testclient.TestClient`
  real, no mockeado)
- `test_lifecycle.py` (4 — incluido el gate de producción bloqueando el
  arranque)

Suite completa `whatsapp_service/tests/`: **277 passed, 11 failed** — los
11 son los mismos fallos preexistentes y no relacionados ya documentados
en WA-1/WA-2/WA-3. Sintaxis global: sin errores. Smoke test real contra
`main.py` descrito arriba.

## Siguiente fase

WA-5 — Provider Gateway: `MetaCloudApiWhatsAppGateway` implementando
`domain/whatsapp/provider_ports.py::WhatsAppProviderGateway` (ya definido
en WA-2). La decisión de producto pendiente desde WA-0 (cuál de las tres
pipelines de pedidos es la autoritativa) sigue sin bloquear nada hasta
ahora — seguirá sin bloquear WA-5/WA-6 tampoco, pero es cada vez más
urgente resolverla antes de WA-9.
