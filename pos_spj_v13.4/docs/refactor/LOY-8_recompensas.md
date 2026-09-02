# LOY-8 — Recompensas

Fecha: 2026-08-31
Alcance: master prompt §15, fase LOY-8 (Definición, Elegibilidad, Reserva, Canje).

## Qué se construyó

`backend/domain/loyalty/entities/{reward,reward_redemption}.py` — `Reward` (9 tipos de §15,
`points_cost`/`value` en Decimal, sin hardcodear nombres/montos) y `RewardRedemption`
(RESERVED→CONFIRMED/CANCELLED, vincula `points_transaction_id` a la reserva del ledger de LOY-6 sin duplicar
la contabilidad de puntos).

`backend/infrastructure/db/schema/loyalty_schema.py` extendida con `loyalty_rewards`
(`UNIQUE(program_id, code)`) y `loyalty_reward_redemptions` (`UNIQUE(points_transaction_id)` — una
reservación de puntos solo puede respaldar un canje). Migración 228, mismo patrón idempotente que 227.

`backend/infrastructure/db/repositories/loyalty/reward_repository.py` — `RewardRepository`,
`RewardRedemptionRepository`.

`backend/application/loyalty/use_cases/reward_use_cases.py` — `CreateRewardUseCase`,
`RequestRewardRedemptionUseCase`, `ConfirmRewardRedemptionUseCase`, `CancelRewardRedemptionUseCase`.

## Decisión de composición

El canje reutiliza la maquinaria del ledger de LOY-6 al nivel de dominio/política
(`LoyaltyTransaction.reserve()`/`.release_of()`, `LoyaltyBalancePolicy`) en vez de invocar
`ReserveLoyaltyPointsUseCase` completo como un sub-paso: cada caso de uso de este repo posee exactamente una
transacción `LoyaltyUnitOfWork`, así que anidar el UoW de otro caso de uso pelearía por el límite de commit.
Mismo principio que `SuspendSaleUseCase` (Sales) llamando a `SalesInventoryClient` (un cliente de
infraestructura) en vez de anidar otro caso de uso completo de Sales.

## Bug real encontrado por los tests: orden de validación

`ConfirmRewardRedemptionUseCase`/`CancelRewardRedemptionUseCase` originalmente tocaban primero la transacción
de ledger subyacente (`reservation.mark_consumed()`/`.cancel_reservation()`) y DESPUÉS el propio
`RewardRedemption` (`.confirm()`/`.cancel()`). Al confirmar un canje ya cancelado, esto hacía que el error
viniera de la transacción interna (`TRANSACTION_INVALID_STATE`) en vez de un error específico sobre el canje
mismo (`REWARD_REDEMPTION_INVALID_STATE`) — un detalle de implementación filtrándose al llamador. Corregido
invirtiendo el orden: validar primero el propio `RewardRedemption`, tocar el ledger después. Detectado por
`test_cannot_confirm_a_cancelled_redemption` fallando con el código de error equivocado, no por inspección.

## Tests

18 tests nuevos, todos pasando tras la corrección de orden: `tests/unit/loyalty/test_loyalty_reward.py` (9,
dominio) y `tests/unit/loyalty/test_loyalty_reward_use_cases.py` (9, repositorio + flujo completo
reservar/confirmar/cancelar, incluyendo rechazo de canje entre programas distintos e insuficiencia de
puntos). Verificado con bootstrap real — migración 228 corre limpia.

205 tests LOY-1..8 corridos juntos, sin regresión.

## Pendiente para fases futuras

- LOY-9 (Gamificación): retos/misiones que otorgan puntos vía `AccrueLoyaltyPointsUseCase` (LOY-6) al
  completarse.
- Ningún flujo real (Ventas/WhatsApp) invoca todavía la solicitud/confirmación de canje.
