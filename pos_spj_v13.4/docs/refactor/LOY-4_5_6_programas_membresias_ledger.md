# LOY-4/5/6 — Programas, Membresías, Ledger de puntos (capa de aplicación)

Fecha: 2026-08-30/31
Alcance: master prompt fase LOY-4 (Programas: Crear/Aprobar/Activar/Suspender), LOY-5 (Membresías:
Enrolar/Suspender/Cerrar), LOY-6 (Ledger: Acumular/Reservar/Canjear/Liberar/Expirar/Ajustar/Reversar).
Documentadas juntas porque comparten la misma infraestructura (`LoyaltyUnitOfWork`, `LoyaltyResult`,
`_LoyaltyBaseUseCase`) construida en un mismo pase.

## Corrección de numeración

El documento anterior (`docs/refactor/LOY-4_repositorios_uow.md`) usó "LOY-4" para el trabajo de
repositorios/UoW, pero el master prompt (§68) numera esa fase distinto: **LOY-4 = Programas, LOY-5 =
Membresías, LOY-6 = Ledger de puntos** — no existe una fase separada de "repositorios" en el plan original de
Fidelidad (a diferencia del prompt de Sales, que sí tenía POS-5 dedicado). Se conserva el documento anterior
como registro histórico del trabajo real (necesario y correcto), pero de aquí en adelante la numeración sigue
literalmente la lista del master prompt.

## Qué se construyó

`backend/application/loyalty/{result,dto}.py` — `LoyaltyResult`/`fail_from_domain_error` (mapeo de 15
excepciones de dominio a códigos), DTOs planos (`LoyaltyProgramDTO`, `LoyaltyAccountDTO`,
`LoyaltyMembershipDTO`, `LoyaltyTransactionDTO`, `LoyaltyAccountSummaryDTO`).

`backend/application/loyalty/use_cases/`:
- `_base.py` — `_LoyaltyBaseUseCase` (inyección de autorización + `_emit()` al outbox).
- `program_use_cases.py` — `CreateLoyaltyProgramUseCase`, `ApproveLoyaltyProgramUseCase`,
  `ActivateLoyaltyProgramUseCase`, `SuspendLoyaltyProgramUseCase`.
- `membership_use_cases.py` — `EnrollLoyaltyMembershipUseCase` (crea la cuenta si es la primera inscripción
  del cliente), `SuspendLoyaltyMembershipUseCase`, `CloseLoyaltyMembershipUseCase`.
- `ledger_use_cases.py` — `AccrueLoyaltyPointsUseCase`, `ReserveLoyaltyPointsUseCase`,
  `ConfirmReservedLoyaltyPointsUseCase`, `ReleaseLoyaltyPointsUseCase`, `RedeemLoyaltyPointsUseCase`,
  `AdjustLoyaltyPointsUseCase`, `ReverseLoyaltyTransactionUseCase`, `ExpireLoyaltyPointsUseCase` (sweep).

## Decisiones reales, no fabricadas

1. **`CreateLoyaltyProgramUseCase` envía a aprobación automáticamente** (DRAFT → PENDING_APPROVAL dentro del
   mismo caso de uso). El master prompt no lista una acción/permiso separado de "enviar a aprobación" en
   §59/§68 — dejar un programa recién creado varado en DRAFT sin ningún caso de uso capaz de moverlo habría
   sido peor que doblar ambos pasos. **Encontrado por un test que fallaba de verdad**, no anticipado en el
   diseño original.
2. **`ApproveLoyaltyProgramUseCase`/`SuspendLoyaltyMembershipUseCase`/`CloseLoyaltyMembershipUseCase` no
   emiten evento canónico** — el catálogo de §62 (LOY-2) solo nombra `LOYALTY_PROGRAM_CREATED`/
   `LOYALTY_PROGRAM_ACTIVATED` y `LOYALTY_MEMBERSHIP_ENROLLED`/`LOYALTY_MEMBERSHIP_SUSPENDED`; no existe un
   evento de "aprobado" ni de "membresía cerrada". Reutilizar `PROGRAM_CREATED` para "aprobado" habría puesto
   un nombre de evento engañoso en el outbox — se prefirió omitir la emisión y documentarlo, no fabricar
   vocabulario nuevo sin autorización.
3. **`AdjustLoyaltyPointsUseCase` exige autorización en caliente SIEMPRE**, no solo por encima de un umbral —
   §60 ("quien ajusta puntos no aprueba su propio ajuste") es incondicional en el texto del prompt, y no
   existe ningún concepto de umbral configurado en este bounded context todavía. El solicitante no necesita
   tener `POINTS_ADJUST` él mismo; solo el autorizador, que debe ser un usuario distinto (verificado con
   `LoyaltyAuthorizationPolicy.authorize_exception()`, LOY-1).
4. **El payload de `LOYALTY_POINTS_ISSUED` ya tiene la forma exacta que espera el handler de Finanzas**
   (`loyalty_transaction_id`, `estimated_fair_value`, `currency_code`, `customer_id`, `program_id`,
   `expires_at` — ver `LoyaltyPointsIssuedHandler._handle()`, hallazgo de LOY-0). Esto NO significa que el
   evento ya llegue a Finanzas: sigue sin existir ningún dispatcher que lea `loyalty_outbox` y llame al
   handler (mismo estado confirmado en LOY-2/LOY-4 para todo el patrón outbox→dispatcher en este repo) — solo
   la FORMA del payload queda lista, cablear la llamada real es trabajo de una fase futura.
5. **`ExpireLoyaltyPointsUseCase` es una barrida de sistema sin usuario humano** — se le agregó
   `SYSTEM_ACTOR_ID`, una constante UUIDv7 fija y bien conocida (`backend/domain/loyalty/events.py`), en vez
   de generar un UUID aleatorio nuevo por evento (que fabricaría una identidad falsa) o usar un string plano
   como `"SYSTEM_AUTOMATION"` (CRM-26) — REGLA CERO exige que `user_id` en cada evento sea un UUIDv7 real, así
   que un sentinel de string no habría pasado la validación de `loyalty_event_payload`.
6. **Limitación real, señalada no oculta**: la expiración no rastrea consumo por lote (FIFO). Si una parte de
   un `EARN` ya se redimió antes de que venza, la barrida igual expira el monto ORIGINAL completo de ese
   renglón, no el remanente. Un sistema de expiración correcto necesitaría rastrear de qué lote de puntos
   proviene cada redención — no existe en este bounded context y el master prompt tampoco da un algoritmo
   para ello.

## Bug real encontrado y corregido por los propios tests (no cosmético)

`ReverseLoyaltyTransactionUseCase` guardaba primero la transacción ORIGINAL (con
`reversal_transaction_id` apuntando a la fila de reverso que todavía no existía) y el reverso después —
contra una conexión con `PRAGMA foreign_keys = ON` esto viola la propia `REFERENCES
loyalty_transactions(id)` del esquema (LOY-3) y lanza `sqlite3.IntegrityError` en cada intento de reverso.
Detectado por `test_reverse_nets_balance_to_zero`/`test_cannot_reverse_twice` fallando de verdad al correr
contra el esquema real (no un mock) — corregido invirtiendo el orden: guardar primero el reverso, luego el
original.

## Tests

47 tests nuevos, todos pasando tras las dos correcciones anteriores:
- `tests/unit/loyalty/test_loyalty_program_use_cases.py` (7)
- `tests/unit/loyalty/test_loyalty_membership_use_cases.py` (7)
- `tests/unit/loyalty/test_loyalty_ledger_use_cases.py` (17, cubriendo acumular/reservar/confirmar/liberar/
  canjear directo/ajustar con segregación de funciones/reversar/expirar)

166 tests LOY-1..6 corridos juntos, sin regresión.

## Pendiente para fases futuras

- LOY-7 (Niveles): `LoyaltyTier`/`LoyaltyTierHistory` — `LoyaltyMembership.change_tier()` ya existe (LOY-2)
  pero nada lo llama todavía.
- Ningún caller real (UI/API/integración con Ventas) invoca estos casos de uso todavía — siguen aislados,
  probados, listos.
- Sin dispatcher de outbox — mismo estado confirmado en cada fase anterior.
