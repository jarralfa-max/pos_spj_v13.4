# CASH-10 — Fidelidad, cupones y vales

Caja clasifica los medios de liquidación, pero no es propietaria del saldo ni del ciclo de vida de instrumentos comerciales. Fidelidad conserva los puntos; los módulos de cupones, vales y saldo a favor conservan sus instrumentos; Finanzas conserva la obligación económica reconocida.

`LOYALTY_POINTS`, `COUPON`, `VOUCHER`, `STORE_CREDIT` y `PROMOTIONAL_BALANCE` liquidan parte de una venta sin producir entrada o salida de efectivo. En pagos mixtos sólo `CASH` afecta el ledger del cajón. El `instrument_id`, su disponibilidad, canje y reverso deben ser validados por el bounded context propietario y por Finanzas, nunca recalculados en Caja.

`GIFT_CARD` está clasificado como `FUTURE_INSTRUMENT`, no afecta el cajón y permanece deshabilitado. Esto evita tratarlo accidentalmente como efectivo antes de implementar emisión, recarga, canje, expiración y conciliación operativa completas.
