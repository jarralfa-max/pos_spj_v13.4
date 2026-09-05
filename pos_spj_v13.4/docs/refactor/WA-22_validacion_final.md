# WA-22 — Validación final (canal WhatsApp, batch WA-13..WA-20)

Ejecutado: 2026-09-02. Cierra la sesión que cubrió WA-13 a WA-20 (WA-21
diferido por decisión explícita del usuario; WA-23/24 descartados — el
roadmap real termina en WA-22, confirmado con el usuario en esta misma
sesión).

## Verificación ejecutada

1. **Sintaxis global** (`whatsapp_service/` + `pos_spj_v13.4/`, recursivo,
   excluyendo `.venv`/`.git`/`__pycache__`): **sin errores**. Se encontró
   y corrigió en el camino un archivo corrompido externamente
   (`erp_ports.py` con un prefijo `+456` literal en la línea 1, ver
   `WA-20_observabilidad.md`).
2. **Suite completa de `whatsapp_service/tests/`**: **686 passed, 11
   failed**. Los 11 son los mismos preexistentes desde WA-1
   (`DummyParser` sin atributo `.matcher` en `ai/intent_resolver.py`,
   confirmados no relacionados con ningún archivo tocado en toda esta
   iniciativa — mismos 11 en cada corrida desde WA-1 hasta hoy).
3. **Tests dirigidos de `pos_spj_v13.4/tests/`** para cada archivo tocado
   fuera de `whatsapp_service/`: `test_wa_admin_bounded_context_visibility.py`
   (WA-19, 12 tests), `tests/unit/customer_privacy/` + `tests/integration/customer_privacy/`
   (WA-14, `CustomerConsent.decline()`, 80 tests) — **92 passed, 0
   failed**. (No se corrió `pos_spj_v13.4/tests/` completo — la memoria
   del proyecto ya documenta que esa carpeta tiene fallos preexistentes
   masivos no relacionados en todo el repo; se usó la lista curada de
   paquetes realmente tocados, mismo criterio que toda la sesión.)
4. **Cadena de migraciones**: 243/244/245/246/247 registradas en
   `migrations/engine.py::MIGRATIONS`, en orden, sin duplicados (226
   migraciones totales). Bootstrap completo desde cero
   (`scripts/bootstrap_db.py`) ejecuta las 5 limpio — los 3 errores que
   el bootstrap reporta (migraciones 024/029/080) son preexistentes, no
   relacionados con WhatsApp (columnas/tablas de otros módulos
   financieros ausentes en una BD vacía).
5. **Smoke test real** contra `main.py` bootstrapeado desde cero
   (`TestClient`, no mockeado):
   - `dependency_graph_validator.validate_composition_root()` — las 41
     entradas de `REQUIRED_SERVICES` presentes, sin excepción.
   - `/health` → 200, `DEGRADED` (correcto: sin secretos Meta en este
     entorno de prueba) — `database`/`schema`/`inbox_worker`/
     `outbox_worker`/`erp_api` todos `HEALTHY` contra la BD real
     (confirma que WA-9/17 resolvieron implementaciones reales, no
     `UnavailableErpClient`, contra el esquema legacy completo).
   - `/diagnostics` → 200, forma completa de métricas.
   - 19 rutas montadas sin colisión: webhook Meta/MercadoPago,
     `/api/notify/*` (legacy) + `/api/notify/v2/*` (WA-18) coexistiendo,
     `/api/delivery/*`, `/health`, `/diagnostics`.
   - **Nota, no un bug**: `/diagnostics` respondió 200 sin firma HMAC en
     este smoke test porque el entorno no tiene `internal_api_key`
     configurado — comportamiento fail-open FUERA de producción, diseño
     deliberado y ya testeado de WA-1
     (`test_missing_secret_outside_production_allows_with_warning`), el
     MISMO criterio que ya aplica a `/api/notify/*`/`/api/delivery/*`.
     El test unitario de `/diagnostics`
     (`test_diagnostics_router.py::test_rejects_unsigned_request`) sí
     configura un secreto real y confirma el rechazo cuando corresponde.

## Estado consolidado del canal (WA-0 → WA-20)

| Fase | Qué entrega | Tests |
|---|---|---|
| WA-0 | Auditoría (6 docs) | — |
| WA-1 | SecretStore, firmas webhook, HMAC interno, redacción | incl. en 86 iniciales |
| WA-2 | Dominio (entidades/enums/puertos) | 104 |
| WA-3 | Esquema limpio (12 tablas iniciales) | 27 |
| WA-4 | Bootstrap/CompositionRoot/health | 60 |
| WA-5 | Provider Gateway (Meta real) | 67 |
| WA-6 | Webhook/Inbox | 49 |
| WA-7 | Conversation Engine | 69 |
| WA-8 | Intent Resolution | 41 |
| WA-9 | ERP Contracts (6 clientes) | 38 |
| WA-10 | Pedidos (idempotente) | 65 |
| WA-11 | Cotizaciones (idempotente) | 79 |
| WA-12 | Pagos (idempotente) | 44 |
| WA-13 | Delivery (idempotente) | 31 |
| WA-14 | Consentimiento (primer productor real) | 45 |
| WA-15 | Fidelidad (lectura real) | 45 |
| WA-16 | Handoff (7mo cliente ERP: StaffDirectory) | 56 |
| WA-17 | Outbox/Dispatcher (cierra gap desde WA-0) | 75 |
| WA-18 | Notificaciones (primer consumidor de outbox) | 108 |
| WA-19 | UI (panel admin lee el bounded context nuevo) | 12 (+80 CRM-9) |
| WA-20 | Observabilidad (`/diagnostics`) | 24 |
| **Total** | **41 servicios en `CompositionRoot`** | **686 (whatsapp_service) + 92 (pos_spj_v13.4)** |

`REQUIRED_SERVICES` creció de 8 (WA-4) a 41 — cada fase agregó
repositorio(s)/servicio(s) reales, verificados dos veces por fase (tests
unitarios + smoke test contra `main.py` real), nunca solo uno.

## Gaps honestos que quedan abiertos (no ocultos, documentados fase por fase)

- **Nada de WA-1..20 está conectado al webhook en vivo.**
  `webhook/whatsapp.py` sigue procesando síncronamente vía
  `MessageRouter`/`flows/` legacy — el cutover real es el trabajo más
  grande que queda, no intentado en ningún punto de esta iniciativa por
  diseño ("paralelo, no conectado todavía" en cada fase).
- **`whatsapp_messages` no persiste texto/interactive_id crudo**
  (documentado desde WA-8, confirmado de nuevo en WA-19) — bloquea que
  `IntentResolutionService` procese mensajes reales del inbox hasta que
  se decida una política de retención (§16, nunca construida).
- **WA-21 (eliminación de legacy) sigue diferido** — la decisión de
  producto sobre qué pipeline(s) retirar y si invalidar la regla de
  CLAUDE.md que preserva los 3 shims de WhatsApp, pendiente desde WA-9,
  reconfirmada como diferida por el usuario en esta sesión.
- **Redención de puntos de fidelidad por WhatsApp**: cortado
  explícitamente en WA-15 (acoplado a venta en curso del lado POS).
- **`HandoffCoordinator` (WA-16) envía síncrono, no vía outbox** (WA-17
  se construyó después) — candidato a migrar, no forzado retroactivamente.
- **`test_wa_repositories.py`** (pos_spj_v13.4, 19/23 tests) es deuda
  preexistente de un ciclo de refactor anterior (v12), confirmada NO
  relacionada con esta iniciativa vía `git stash` — no se tocó,
  consistente con dejar deuda de test ajena fuera de alcance.

## Cierre

WA-0 a WA-20 (saltando WA-21 por decisión del usuario) quedan cerrados,
documentados individualmente en `docs/refactor/WA-*.md`, y verificados
tanto por tests automatizados como por un arranque real del
microservicio. El siguiente hito real — sea que continúe en esta sesión o
en una futura — es el cutover al webhook en vivo, no una fase WA-N
adicional.
