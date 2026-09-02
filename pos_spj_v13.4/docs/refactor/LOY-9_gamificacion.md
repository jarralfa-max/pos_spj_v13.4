# LOY-9 — Gamificación

Fecha: 2026-08-31
Alcance: master prompt §16, fase LOY-9 (Retos, Misiones, Rachas, Progreso).

## Decisión de alcance (documentada, no fabricada)

§16 nombra 6 clases (`LoyaltyChallenge`, `LoyaltyMission`, `LoyaltyStreak`, `LoyaltyMilestone`,
`LoyaltyBadge`, `ChallengeProgress`) pero solo da una lista de tipos de criterio y estados — sin campos
distintivos para Challenge/Mission/Milestone. Se colapsaron esas tres en una sola entidad `LoyaltyChallenge`
con un discriminador `mode` (`CHALLENGE`/`MISSION`/`MILESTONE`) en vez de tres clases casi idénticas —
consistente con "una sola ruta canónica" (§3/§64). `LoyaltyStreak` y `LoyaltyBadge` sí son entidades separadas
porque tienen una forma genuinamente distinta (contadores corriendo / registro de premio).

## Colisión real encontrada ANTES de escribir el esquema (aprendizaje de LOY-3 aplicado)

Se verificó por grep contra `m000_base_schema.py` antes de nombrar las tablas nuevas — `loyalty_challenges` y
`loyalty_challenge_progress` YA existen como tablas legacy del Growth Engine (columnas en inglés pero
`REAL`/`INTEGER`, `cliente_id` en vez de `membership_id`). Se usaron `loyalty_challenge_definitions` y
`loyalty_challenge_member_progress` en su lugar — mismo criterio de desambiguación que
`loyalty_program_definitions` (LOY-3). `loyalty_streaks`/`loyalty_badges` sí son nombres nuevos, verificados
sin colisión.

## Qué se construyó

`backend/domain/loyalty/entities/{loyalty_challenge,challenge_progress,loyalty_streak,loyalty_badge}.py` +
enums (`ChallengeMode`, `ChallengeCriteriaType` [10 valores de §16], `ChallengeStatus`).

`ChallengeProgress`'s field shape (`current_value`/`completed`/`completed_at`/`points_awarded`) preserva
deliberadamente la forma real de la tabla legacy `loyalty_challenge_progress` — es un buen diseño que
sobrevive aunque la tabla en sí quede reemplazada (CLAUDE.md Prioridad 0).

Esquema (migración 229, mismo patrón idempotente), repositorios (`gamification_repository.py`), y
`backend/application/loyalty/use_cases/gamification_use_cases.py`: `CreateLoyaltyChallengeUseCase`,
`ActivateLoyaltyChallengeUseCase`, `RecordChallengeProgressUseCase`, `RecordLoyaltyStreakActivityUseCase`.

## Decisiones reales

- `RecordChallengeProgressUseCase`/`RecordLoyaltyStreakActivityUseCase` son disparados por sistema (sin
  `actor_user_id`/permiso), mismo criterio que la barrida de expiración (LOY-6) y la evaluación de nivel
  (LOY-7) — el progreso avanza en reacción a un evento real (una venta, un referido) en otro lugar del
  sistema, no por un comando directo de usuario.
- Completar un reto otorga puntos vía una transacción `BONUS` del ledger de LOY-6
  (`source_module="loyalty_challenges"`, `reason_code=f"CHALLENGE:{membership_id}"`), con doble guardia de
  idempotencia (verificación previa + `UNIQUE` real del esquema) — cumple literalmente §16: "No otorgar
  puntos sin operación idempotente". Otorga además una `LoyaltyBadge` en la misma transacción.
- `LoyaltyStreak.record_period()` no tiene lógica de calendario propia — el llamador decide si un período es
  consecutivo (`is_consecutive: bool`), ya que solo el llamador conoce la semántica de calendario del
  `streak_type` (semanal/mensual/etc.).

## Tests

22 tests nuevos, todos pasando: `tests/unit/loyalty/test_loyalty_gamification.py` (15, dominio) y
`tests/unit/loyalty/test_loyalty_gamification_use_cases.py` (7, incluyendo que completar un reto no paga dos
veces al seguir avanzando después). Verificado con bootstrap real — migración 229 corre limpia, coexiste con
las tablas legacy sin colisión.

227 tests LOY-1..9 corridos juntos, sin regresión.

## Pendiente para fases futuras

- LOY-10 (Referidos): `Referral` — puede eventualmente disparar `RecordChallengeProgressUseCase` para retos
  de tipo `REFERRAL`.
- Nada llama todavía a estos casos de uso desde un evento real (venta completada, etc.).
