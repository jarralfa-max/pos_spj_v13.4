# LOY-12 — Cupones (bounded context Commercial Instruments)

Fecha: 2026-08-31
Alcance: master prompt §21, fase LOY-12 (Definición, Emisión, Validación, Reserva, Redención, Expiración,
Reverso).

## Nuevo bounded context, no un sub-módulo de Fidelidad

Cupones vive en `backend/domain/commercial_instruments/` (paquete nuevo), separado de
`backend/domain/loyalty/` — §7.2 del master prompt ya los declara como bounded contexts distintos, y varios
tipos de cupón (`SUPPLIER_FUNDED`, `EMPLOYEE_GRANTED`) ni siquiera son conceptos de fidelidad. La
autorización SÍ se reutiliza: `LoyaltyPermissions.COUPON_*` (definidos en LOY-1 bajo `GROWTH_ENGINE`) siguen
siendo el mecanismo real, porque cupones comparte la misma superficie de navegación/permisos que Fidelidad
(§6: "Cupones" es un ítem del sidebar de Fidelidad) — separación de dominio, autorización compartida.

## Qué se construyó

`backend/domain/commercial_instruments/entities/{coupon_definition,coupon_instance,coupon_redemption}.py` +
enums (`CouponType` [10], `CommercialBenefitType` [6], `CouponInstanceStatus` [7]) + `events.py`
(`CommercialInstrumentEvents`, 4 de 6 alineados byte-a-byte con los handlers reales de Finanzas —
`COUPON_ISSUED/REDEEMED/EXPIRED/CANCELLED` — mismo patrón de LOY-2).

Esquema completo nuevo (`backend/infrastructure/db/schema/commercial_instruments_schema.py`:
`coupon_definitions`, `coupon_instances`, `coupon_redemptions`, `commercial_instruments_outbox`; migración
232, verificado sin colisión), repositorios (`backend/infrastructure/db/repositories/commercial_instruments/`)
y `backend/application/commercial_instruments/use_cases/coupon_use_cases.py`: `CreateCouponDefinitionUseCase`,
`IssueCouponInstanceUseCase`, `ValidateAndReserveCouponUseCase`, `ConfirmCouponRedemptionUseCase`,
`ReleaseCouponReservationUseCase`, `CancelCouponInstanceUseCase`, `ExpireCouponsUseCase`.

## "No marcar redención antes de completar la venta" — por construcción

`ConfirmCouponRedemptionUseCase` es la ÚNICA función en todo el bounded context que llama
`CouponInstance.confirm_redemption()`, y solo puede hacerlo sobre una instancia ya `RESERVED` (con
`sale_id` real). No existe ninguna ruta que marque un cupón `REDEEMED` sin pasar primero por
`ValidateAndReserveCouponUseCase` — el flujo de §21 queda garantizado estructuralmente, no solo por
convención.

## Bug real encontrado por los tests (fallo real, no aserción)

Un primer borrador de `coupon_use_cases.py` capturaba `except LoyaltyDomainError` alrededor de CADA llamada a
un método de dominio de Commercial Instruments (`instance.reserve()`, `.confirm_redemption()`, `.release()`,
`.cancel()`, `CouponDefinition.create()`) — pero esos métodos lanzan `InvalidCouponInstanceStateError`/
`InvalidCouponDefinitionError`, que heredan de `CommercialInstrumentDomainError`, NO de `LoyaltyDomainError`
(son jerarquías de excepción de bounded contexts distintos). El `except` nunca capturaba nada real y la
excepción se propagaba sin control. Confirmado por `test_cancel_requires_reason` fallando con un traceback
real (no un `result.success is False`), no por inspección — corregido a `except
CommercialInstrumentDomainError` en las 5 ubicaciones afectadas (los 3 usos correctos de `LoyaltyDomainError`
alrededor de `self._auth.require(...)`, que sí pertenece a la jerarquía compartida de LOY-1, se dejaron
intactos).

## Simplificación honesta documentada

`CouponInstance.issue()` produce directamente estado `ACTIVE`, no `ISSUED` — ningún tipo de cupón real de
§21 (código público, automático, personalizado...) necesita una ceremonia de activación manual separada en
los flujos que existen hoy en este repo. `ISSUED` se conserva en el enum (vocabulario literal de §21) para
una fase futura que sí necesite un paso de activación real (p. ej. un cupón físico enviado por correo).

## Tests

40 tests nuevos, todos pasando tras la corrección de jerarquía de excepciones:
`tests/unit/commercial_instruments/test_coupon_domain.py` (14, dominio) y `test_coupon_use_cases.py` (26,
incluyendo el flujo completo validar→reservar→confirmar, rechazo de cupón personalizado para otro cliente,
rechazo de doble canje, y expiración por barrida de sistema). Verificado con bootstrap real — migración 232
corre limpia.

286 tests LOY-1..12 (incluyendo Commercial Instruments) corridos juntos, sin regresión.

## Pendiente para fases futuras

- LOY-13 (Vales): mismo bounded context `commercial_instruments`, con ledger propio (a diferencia de cupones,
  de un solo uso) — `VoucherDefinition`/`VoucherInstance`/`VoucherTransaction`/`VoucherRedemption`.
- `max_redemptions_per_instance` existe como campo pero no se implementa (`CouponInstance` es de un solo
  uso) — reservado para una fase futura de cupones reutilizables.
- Sin dispatcher de outbox — mismo estado que todos los demás bounded contexts de este repo.
