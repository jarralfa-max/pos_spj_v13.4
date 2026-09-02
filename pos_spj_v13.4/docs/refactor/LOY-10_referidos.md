# LOY-10 — Referidos

Fecha: 2026-08-31
Alcance: master prompt §17, fase LOY-10 (Registro, Calificación, Recompensa, Antifraude).

## Qué se construyó

`backend/domain/loyalty/entities/referral.py` — `Referral` (REGISTERED→QUALIFIED→REWARDED, o
REJECTED/EXPIRED/FRAUD_SUSPECTED). Los bonos/mínimo de compra/plazo son argumentos explícitos del
constructor, nunca literales en el archivo (§17: "No hardcodear valores").

Esquema `loyalty_referrals` (migración 230; verificado sin colisión con la `referidos` legacy en español —
ver hallazgo de LOY-0 sobre sus columnas `INTEGER`), repositorio (`referral_repository.py`), y
`backend/application/loyalty/use_cases/referral_use_cases.py`: `RegisterReferralUseCase`,
`QualifyReferralUseCase`, `RewardReferralUseCase`, `RejectReferralUseCase`,
`FlagReferralFraudSuspectedUseCase`.

## Antifraude real, no decorativo

`RegisterReferralUseCase` resuelve `referrer_membership_id → loyalty_account_id → customer_id` y lo compara
contra `referred_customer_id`: un auto-referido se rechaza con `SelfReferralNotAllowedError` antes de crear
cualquier fila — esto no puede vivir en la entidad `Referral` (solo conoce `referred_customer_id`, no la
identidad del referidor), así que vive en el caso de uso, que sí tiene acceso a los repositorios.

`RewardReferralUseCase` usa un permiso DISTINTO (`REFERRAL_APPROVE`) del de gestión general
(`REFERRAL_MANAGE`) — separa quien registra/califica de quien aprueba el pago, y paga el bono del referidor
vía una transacción `BONUS` real del ledger (LOY-6), con guardia de idempotencia doble (verificación previa +
`UNIQUE` real del esquema vía `exists_for_source`), mismo patrón que LOY-9 aplicó a retos completados.

`ReferralRepository.count_rewarded_for_referrer_since()` da la primitiva de conteo para una futura regla de
"máximo mensual" (§17) sin fabricar el motor de reglas completo — el llamador decide ventana y tope.

## Bug propio corregido durante la escritura (no en producción)

Un primer borrador de `RewardReferralUseCase._transition` usaba `__import__("backend.domain.loyalty.enums",
fromlist=[...])` para evitar (innecesariamente) un import directo — el mismo anti-patrón ya cometido y
corregido en `AccrueLoyaltyPointsUseCase` (LOY-6). Corregido a un import normal de `TransactionType` antes de
correr ningún test.

## Tests

19 tests nuevos, todos pasando en el primer intento real (tras la corrección del import):
`tests/unit/loyalty/test_loyalty_referral.py` (10, dominio) y
`tests/unit/loyalty/test_loyalty_referral_use_cases.py` (9, incluyendo rechazo de auto-referido, flujo
calificar→recompensar con pago real de bono, y que un segundo intento de recompensa falla a nivel de dominio
antes de llegar a pagar dos veces). Verificado con bootstrap real — migración 230 corre limpia.

246 tests LOY-1..10 corridos juntos, sin regresión.

## Pendiente para fases futuras

- LOY-11 (Campañas): `Campaign` — las campañas de referidos (§19: tipo `REFERRAL`) eventualmente podrán
  disparar `RegisterReferralUseCase`.
- La migración de datos de la tabla legacy `referidos` (columnas `cliente_referidor`/`cliente_referido`
  `INTEGER`, hallazgo de LOY-0) sigue pendiente — no se tocó esta fase.
