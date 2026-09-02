# LOY-7 — Niveles

Fecha: 2026-08-31
Alcance: master prompt §14, fase LOY-7 (Reglas, Evaluación, Historial, Beneficios).

## Qué se construyó

`backend/domain/loyalty/entities/{loyalty_tier,loyalty_tier_history}.py` — `LoyaltyTier` (config por programa,
sin nombres/umbrales hardcodeados, a diferencia de la tabla legacy `loyalty_programs` con sus columnas
`nivel_bronce`/`nivel_plata`/`nivel_oro`/`nivel_platino` fijas — hallazgo de LOY-0/LOY-3) y
`LoyaltyTierHistory` (registro inmutable, append-only).

`backend/domain/loyalty/policies/tier_evaluation_policy.py` — `LoyaltyTierEvaluationPolicy.evaluate()`, pura,
recibe `TierEvaluationStats` (lifetime_points/total_spend/visit_count) y la lista de niveles activos, devuelve
el de mayor `rank` que califica.

`backend/infrastructure/db/schema/loyalty_schema.py` — extendida con `loyalty_tiers`
(`UNIQUE(program_id, code)`, `UNIQUE(program_id, rank)`) y `loyalty_tier_history`. Migración 227 (reinvoca
`create_loyalty_schema()`, idempotente — mismo patrón que CRM-26 usó para extender un schema existente sin
crear un módulo hermano).

`backend/infrastructure/db/repositories/loyalty/tier_repository.py` — `LoyaltyTierRepository`,
`LoyaltyTierHistoryRepository` (solo `add()`, sin update — la entidad es inmutable).

`backend/application/loyalty/use_cases/tier_use_cases.py` — `CreateLoyaltyTierUseCase`,
`EvaluateLoyaltyMembershipTierUseCase`.

## Decisión real: alcance honesto de la evaluación

Este bounded context solo posee `lifetime_points` de forma nativa (`LoyaltyBalancePolicy.lifetime_earned()`,
LOY-2). `total_spend`/`visit_count` son datos de OTRO bounded context (Ventas posee el historial de compras)
— la política los recibe como parámetros explícitos del llamador en vez de leer tablas ajenas directamente.
Sin integración real con Ventas todavía, un llamador puede pasar cero para ambos: eso simplemente significa
que solo los niveles gateados por puntos son alcanzables — una degradación honesta documentada y probada
(`test_honest_degradation_with_zero_spend_and_visits`), no una respuesta silenciosamente incorrecta.

`EvaluateLoyaltyMembershipTierUseCase` es una evaluación disparada por sistema (sin `actor_user_id` ni gate de
permiso, mismo criterio que `ExpireLoyaltyPointsUseCase` de LOY-6) — usa `SYSTEM_ACTOR_ID` (LOY-6) para el
evento emitido. Es el primer y único consumidor real de `LoyaltyMembership.change_tier()` (construido en
LOY-2, sin uso hasta ahora): todo cambio de nivel pasa por este único caso de uso, que SIEMPRE escribe un
`LoyaltyTierHistory` en la misma transacción — satisface §14 ("toda modificación de nivel debe dejar
historial") literalmente, porque no existe otra ruta de código que llame `change_tier()`.

## Tests

21 tests nuevos, todos pasando: `tests/unit/loyalty/test_loyalty_tier.py` (12, dominio + política) y
`tests/unit/loyalty/test_loyalty_tier_use_cases.py` (9, repositorio + casos de uso, incluyendo que una
segunda evaluación sin cambio de nivel NO duplica historial). Verificado con bootstrap real
(`scripts/bootstrap_db.py`) — migración 227 corre limpia, tablas con columnas esperadas.

187 tests LOY-1..7 corridos juntos, sin regresión.

## Pendiente para fases futuras

- LOY-8 (Recompensas): `Reward`/`RewardRedemption` — el `benefit_multiplier` del nivel actual todavía no
  alimenta ningún cálculo de recompensa real.
- Nada llama `EvaluateLoyaltyMembershipTierUseCase` automáticamente todavía (p. ej. después de cada
  acreditación de puntos) — es un caso de uso aislado, listo para integrarse.
