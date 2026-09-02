# LOY-16 — Tarjetas base

Fecha: 2026-08-31
Alcance: master prompt §31 (LoyaltyCard: emisión, asignación, activación,
bloqueo, reposición) + §32 (QR público rotable), fase LOY-16.

## Primer consumidor real del cimiento de seguridad de LOY-1

LOY-1 ya había construido, por adelantado, todo el cimiento de seguridad de
este bounded context: `backend/application/loyalty_cards/{permissions,
authorization,session_authorization,audit}.py` y `backend/domain/
loyalty_cards/{exceptions,value_objects}`. Esta fase es el primer
consumidor real de ese cimiento — se extendió `exceptions.py` con las
excepciones específicas de tarjeta/token (no se tocó nada de LOY-1), y se
reutilizó `LoyaltyCardsAuthorizationPolicy`/`LoyaltyCardsPermissions.
CARD_*/QR_ROTATE` tal cual, sin modificarlos.

## Aislamiento de bounded context: la tarjeta no valida la membresía

`LoyaltyCard.membership_id`/`customer_id` se guardan sin validar contra las
tablas propias de `backend.domain.loyalty` — mismo patrón de aislamiento
entre bounded contexts que `CouponDefinition.source_program_id` (LOY-12):
cada contexto nuevo de esta sesión ha evitado consistentemente abrir una
segunda `UnitOfWork` de otro contexto dentro de su propia transacción.

## El token QR es una identidad separada de la tarjeta (§32)

`LoyaltyCardPublicToken` es una entidad aparte de `LoyaltyCard`, no un campo
de la tarjeta — precisamente para que `rotate()` pueda invalidar el token
público (p. ej. tras una fuga sospechosa) sin tocar el id interno de la
tarjeta ni su historial/ligas con el ledger. `rotate()` transiciona el token
actual a `ROTATED` y devuelve un token `ACTIVE` nuevo — nunca hay dos tokens
`ACTIVE` simultáneos para la misma tarjeta. Bloquear, desbloquear (emite un
token nuevo) y cancelar una tarjeta también revocan/rotan su token activo
en el mismo caso de uso — un token no sobrevive por accidente a una tarjeta
bloqueada o cancelada.

## Qué se construyó

Entidades `LoyaltyCard` (ISSUED→ACTIVE⇄BLOCKED→REPLACED/CANCELLED/EXPIRED)
y `LoyaltyCardPublicToken` (ACTIVE→ROTATED, ACTIVE→REVOKED).
`LoyaltyCard.issue_replacement(old_card, ...)` crea la tarjeta de reposición
ligada en ambos sentidos (`replaces_card_id`/`replaced_by_card_id`) — nunca
se reutiliza el mismo id de tarjeta perdida/dañada.

Esquema `loyalty_cards`/`loyalty_card_tokens`/`loyalty_cards_outbox`
(migración 236; verificado sin colisión contra las tablas legacy
`tarjetas_fidelidad`/`card_batches`/`card_assignment_history`/
`historico_tarjetas`/`config_diseno_tarjetas` de `m000_base_schema.py`),
repositorios + `LoyaltyCardsUnitOfWork`, y `backend/application/
loyalty_cards/use_cases/{card,token}_use_cases.py`: emisión (genera
`card_number` secuencial `LC-NNNNNNNN` y su primer token), activación,
bloqueo/desbloqueo, reposición, cancelación, rotación de QR.

## Alcance honesto

- No hay plantillas, diseñador, pliegos, lotes ni impresión física todavía
  — eso es LOY-17 en adelante. Esta fase es solo la tarjeta y su identidad.
- Ningún dispatcher conecta `loyalty_cards_outbox` a un handler real
  todavía (mismo hueco confirmado en cada bounded context de esta sesión).
- No se tocó el legacy (`modulos/tarjetas.py`, `core/services/
  card_batch_engine.py`, `core/services/loyalty_card_designer_service.py`,
  tablas `tarjetas_fidelidad`/etc.) — coexisten hasta LOY-27.

## Tests

26 tests nuevos (`tests/unit/loyalty_cards/test_loyalty_card_domain.py`: 16;
`test_loyalty_card_use_cases.py`: 10), todos pasando en el primer intento
real. Verificado con bootstrap real completo — migración 236 corre limpia,
las 3 tablas `loyalty_card*` se crean.

386 tests de todo el dominio Fidelidad/Comercial/Sorteos/Tarjetas corridos
juntos, sin regresión.

## Pendiente para fases futuras

- LOY-17 (Plantillas): `LoyaltyCardTemplate`/`LoyaltyCardTemplateVersion`.
- Vincular la emisión de tarjeta con un evento real de alta de membresía
  (hoy `IssueLoyaltyCardUseCase` se invoca de forma aislada, sin un
  disparador automático desde `EnrollLoyaltyMembershipUseCase`).
- Eliminación del legacy de tarjetas — LOY-27.
