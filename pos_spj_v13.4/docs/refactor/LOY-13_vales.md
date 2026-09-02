# LOY-13 — Vales

Fecha: 2026-08-31
Alcance: master prompt §22, fase LOY-13 (Definición, Emisión, Ledger, Canje parcial, Reserva, Reverso).

## Mismo bounded context que Cupones, pero con ledger propio

Vales vive junto a Cupones en `backend/domain/commercial_instruments/` (mismo bounded context, §7.2), pero a
diferencia de `CouponInstance` (un solo uso), soporta canje parcial mediante un ledger append-only —
`VoucherTransaction`/`VoucherBalancePolicy` son un clon deliberado y directo del diseño de
`LoyaltyTransaction`/`LoyaltyBalancePolicy` (LOY-2): `amount` firmado y fijo desde la creación, toda
corrección es una fila nueva de signo opuesto, saldo = suma de transacciones no `PENDING`.

## Qué se construyó

`backend/domain/commercial_instruments/entities/{voucher_definition,voucher_instance,voucher_transaction,
voucher_redemption}.py` + enums (`VoucherType` [7], `VoucherInstanceStatus` [9], `VoucherTransactionType`
[9]) + `VoucherBalancePolicy`. Esquema (`voucher_definitions`, `voucher_instances`, `voucher_transactions`,
`voucher_redemptions`; migración 233, verificado sin colisión), repositorios, y
`backend/application/commercial_instruments/use_cases/voucher_use_cases.py`:
`CreateVoucherDefinitionUseCase`, `IssueVoucherInstanceUseCase`, `ReserveVoucherAmountUseCase`,
`ConfirmVoucherRedemptionUseCase`, `ReleaseVoucherReservationUseCase`.

## Decisión real: `VoucherInstance` es agnóstico de saldo

A diferencia de `LoyaltyMembership.change_tier()` (que no necesita saber el saldo), aquí SÍ hace falta decidir
si una confirmación deja el vale `PARTIALLY_REDEEMED` o `REDEEMED` — pero la entidad `VoucherInstance` nunca
sabe sumar Decimales: sus métodos `mark_redeemed(fully: bool)`/`release(restore_status:...)` reciben el
resultado ya calculado como argumento explícito, calculado por el caso de uso (que sí tiene acceso al
repositorio y a `VoucherBalancePolicy`). Esto mantiene la entidad pura, sin I/O ni dependencia del
repositorio, igual que el resto de este bounded context.

`ReleaseVoucherReservationUseCase` decide `restore_status` (ACTIVE vs PARTIALLY_REDEEMED) consultando si YA
EXISTE algún `VoucherRedemption` previo para esa instancia — no por el nivel de saldo actual (un vale podría
estar en su saldo original completo tras una recarga y aun así haber sido parcialmente canjeado antes). Un
primer borrador de esta lógica quedó innecesariamente enredado (una variable `was_untouched` calculada pero
nunca usada) — limpiado antes de correr los tests, no encontrado por ellos.

## Aplicando la lección de LOY-12 (jerarquía de excepciones)

Dado el bug real de LOY-12 (capturar `LoyaltyDomainError` alrededor de código que lanza
`CommercialInstrumentDomainError`), este archivo se escribió desde el principio con
`except CommercialInstrumentDomainError` en cada llamada a un método de dominio de Vales, reservando
`except LoyaltyDomainError` solo para las llamadas reales a `self._auth.require(...)` (que sí usa la
autorización compartida de LOY-1). Los 9 tests de casos de uso pasaron en el primer intento real — la
lección se aplicó preventivamente, no se repitió el error.

## Tests

28 tests nuevos, todos pasando en el primer intento: `tests/unit/commercial_instruments/test_voucher_domain.py`
(19, dominio + política de saldo) y `test_voucher_use_cases.py` (9, incluyendo dos canjes parciales
consecutivos hasta agotar el saldo, y liberar una reserva después de un canje previo restaura
`PARTIALLY_REDEEMED` correctamente, no `ACTIVE`). Verificado con bootstrap real — migración 233 corre limpia.

314 tests LOY-1..13 corridos juntos, sin regresión.

## Pendiente para fases futuras

- LOY-14 (Cumpleaños y retención): puede emitir vales de tipo `PROMOTIONAL_VOUCHER`/`COMPENSATION_VOUCHER`
  vía estos mismos casos de uso.
- `AdjustVoucherBalanceUseCase`/`ReverseVoucherTransactionUseCase`/`ExpireVouchersUseCase` no se construyeron
  todavía — la infraestructura del dominio (`VoucherTransaction.adjustment()`/`.reversal_of()`/`.expire_of()`)
  ya existe (mismo patrón que LOY-6), pero ningún caso de uso los invoca aún. Señalado, no fabricado.
