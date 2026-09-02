# LOY-2 — Dominio base (Programas, Cuentas, Membresías, Ledger, Policies, Events)

Fecha: 2026-08-28
Alcance: master prompt §9-§12 (Programa, Cuenta/Membresía, Ledger de puntos, Idempotencia) + §62 (eventos).
Precede a esquema (LOY-3) y repositorios/use cases — dominio puro, sin I/O, mismo alcance que SALES-3.

## Investigación previa (por qué la forma final es esta)

Antes de diseñar, se investigó cómo llegan hoy los eventos `EventName.LOYALTY_*` a los 12 handlers de Finanzas
que el LOY-0 encontró ya construidos y probados:

- `backend/application/event_handlers/finance/loyalty_points_issued_handler.py::LoyaltyPointsIssuedHandler`
  expone `.handle(payload_dict)`, autocontenido (abre su propio `FinanceUnitOfWork`), idempotente por
  `event_id`. No requiere ninguna infraestructura de EventBus — cualquier código con una conexión puede
  llamarlo directamente.
- El patrón real de "puente" que SÍ está construido para otro bounded context (`core/events/handlers/
  finance_handler.py::PayrollFinanceHandler`) traduce un evento del bus legacy a este contrato canónico y
  llama `.handle()` — pero **se confirmó que `PayrollFinanceHandler` nunca se instancia en ningún lugar del
  código de producción** (cero resultados de `grep "PayrollFinanceHandler("` fuera de su propia definición).
  El nuevo `PayPayrollRunUseCase` tampoco llama al handler directamente: solo escribe a una tabla outbox
  (`uow.outbox.enqueue(..., EventName.PAYROLL_PAID.value, ...)`) que **no tiene ningún dispatcher wireado en
  `core/app_container.py`**.
- Conclusión: todo el patrón "outbox → dispatcher → handler de Finanzas" es infraestructura aspiracional en
  TODO el repo hoy, no solo en Fidelidad (mismo hallazgo ya documentado para `InventoryOutboxDispatcher` en
  memoria de CRM/Sales). Construir un "LoyaltyFinanceHandler" puente igual de desconectado habría sido
  infraestructura decorativa — el mismo tipo de fabricación que CRM-26/SALES-4 ya rechazaron explícitamente.

**Decisión**: LOY-2 se mantiene estrictamente en el alcance que el propio master prompt le asigna (dominio
puro: Programas, Cuentas, Membresías, Ledger, Policies, Events, Tests) sin fingir un wiring a Finanzas que no
existe. El catálogo de eventos que se construye aquí SÍ se diseña para ser compatible byte-a-byte con lo que
Finanzas ya espera (ver más abajo) — cerrar el wiring real es trabajo de una fase posterior de aplicación
(probablemente LOY-6 "Ledger de puntos", que construirá los use cases reales).

## Qué se construyó

`backend/domain/loyalty/enums.py` — `ProgramStatus`, `AccountStatus`, `MembershipStatus`, `TransactionType`
(10 valores, §11), `TransactionStatus` (7 valores, §11).

`backend/domain/loyalty/entities/`:
- `loyalty_program.py` — `LoyaltyProgram`. Aprobación y activación son pasos separados a propósito
  (`programa.aprobar`/`programa.activar` son permisos distintos, §59/§60) — `approve()` registra
  `approved_by_user_id` sin cambiar de estado; `activate()` exige que ya esté aprobado. `activate()` también
  permite reactivar desde `SUSPENDED` (no hay un "REACTIVATE" separado en el enum de 6 estados de §9).
- `loyalty_account.py` — `LoyaltyAccount`. Solo referencia `customer_id`; test explícito
  (`test_never_duplicates_customer_fields`) prueba que ningún campo de identidad del cliente vive aquí (§4/§52).
- `loyalty_membership.py` — `LoyaltyMembership`. `current_tier_id` es un puntero simple; LOY-7 (Niveles)
  poseerá la evaluación/historial real.
- `loyalty_transaction.py` — `LoyaltyTransaction`, el ledger. Ver la decisión de diseño explícita abajo.

`backend/domain/loyalty/policies/balance_policy.py` — `LoyaltyBalancePolicy` (`balance`, `reserved_amount`,
`lifetime_earned`), única fuente de verdad para reconstruir saldo desde el ledger.

`backend/domain/loyalty/events.py` — `LoyaltyEvents` (15 constantes, cobertura literal de §62) +
`loyalty_event_payload()`.

`backend/domain/loyalty/exceptions.py` — extendido con 10 errores operacionales nuevos (§66, subconjunto
detectable sin I/O): `InvalidLoyaltyProgramStateError`, `LoyaltyProgramInactiveError`,
`InvalidLoyaltyAccountStateError`, `LoyaltyAccountSuspendedError`, `InvalidLoyaltyMembershipStateError`,
`InvalidLoyaltyTransactionAmountError`, `InvalidLoyaltyTransactionStateError`,
`LoyaltyProgramNotFoundError`, `LoyaltyAccountNotFoundError`, `LoyaltyMembershipNotFoundError`,
`DuplicateOperationError`.

## Decisión de diseño del ledger (documentada, no improvisada)

El master prompt da el vocabulario de §11 (tipos y estados de transacción) pero no un algoritmo ejecutable
de saldo. Se decidió, y se documentó en el docstring de `LoyaltyTransaction`:

1. `points_amount` es siempre el efecto **firmado** sobre el saldo (positivo=crédito, negativo=débito), fijo
   desde la creación y nunca editado ("No modificar movimientos originales" — §11).
2. Toda corrección (liberar una reserva, expirar puntos, reversar) es SIEMPRE una transacción nueva con el
   monto de signo opuesto — nunca una edición retroactiva del monto original.
3. Por lo tanto, el saldo es simplemente `SUM(points_amount)` de toda transacción que no esté `PENDING`
   (`LoyaltyBalancePolicy.balance`). Los cambios de `status` posteriores (`RESERVED`→`CONSUMED`/`CANCELLED`,
   `AVAILABLE`→`EXPIRED`/`REVERSED`) son metadatos de negocio ("¿todavía se puede liberar esta reserva?") y de
   reporte, no una segunda fuente de verdad del saldo.
4. Una reserva (`RESERVE`, monto negativo) descuenta el saldo **en el momento en que se crea** — no hace
   falta un segundo evento para que "cuente". Confirmarla (`mark_consumed()`) no cambia el saldo; liberarla
   crea una transacción `RELEASE` nueva (monto positivo espejo) y dispara `cancel_reservation()` sobre la
   original.

Esta decisión se probó exhaustivamente en `tests/unit/loyalty/test_loyalty_balance_policy.py` (earn+redeem,
reserva reduce saldo de inmediato, liberar restaura, consumir no cambia nada más, reverso neta a cero,
expiración vía fila nueva).

## Catálogo de eventos — compatibilidad deliberada con Finanzas

4 de los 15 nombres de `LoyaltyEvents` (`POINTS_ISSUED`, `POINTS_EXPIRED`, `REWARD_GRANTED`,
`TRANSACTION_REVERSED`) son **exactamente** los mismos strings que
`backend.shared.events.event_names.EventName.LOYALTY_POINTS_ISSUED/EXPIRED/REWARD_GRANTED/
TRANSACTION_REVERSED` — los que los 12 handlers de Finanzas ya escuchan. Test
`test_finance_aligned_events_are_real_event_name_members` (arquitectura) verifica que esto siga siendo cierto
si cualquiera de los dos catálogos cambia en el futuro. Los otros 11 nombres (`PROGRAM_CREATED`,
`MEMBERSHIP_ENROLLED`, `POINTS_RESERVED`, `POINTS_REDEEMED`, `POINTS_RELEASED`, `POINTS_ADJUSTED`,
`TIER_CHANGED`, `CHALLENGE_COMPLETED`, `REFERRAL_QUALIFIED`, `PROGRAM_ACTIVATED`, `MEMBERSHIP_SUSPENDED`) son
vocabulario nuevo sin consumidor todavía. El vocabulario legacy del bus (`LOYALTY_POINTS_EARNED`/
`LOYALTY_POINTS_REDEEMED`, que sigue siendo lo único que corre en producción hoy vía
`core/services/loyalty_service.py`) es una **tercera** vocabulario deliberadamente NO reutilizada aquí — test
`test_legacy_bus_names_do_not_leak_into_the_new_catalog` lo bloquea.

**Explícitamente NO hecho, señalado no oculto**: `LoyaltyEvents` no está cableado a ningún EventBus real ni a
`core/events/wiring.py` — igual que `SaleEvents` en SALES-3, es vocabulario objetivo para cuando exista un
use case real (LOY-6+) que persista una transacción y necesite publicar. Ningún código de producción llama
todavía a `LoyaltyProgram`/`LoyaltyAccount`/`LoyaltyMembership`/`LoyaltyTransaction` — el `LoyaltyService`
legacy (`core/services/loyalty_service.py`) sigue siendo la única ruta operativa.

## Tests

60 tests nuevos, todos pasando en el primer intento:
- `tests/unit/loyalty/test_loyalty_program.py` (11), `test_loyalty_account.py` (6),
  `test_loyalty_membership.py` (5), `test_loyalty_transaction.py` (20), `test_loyalty_balance_policy.py` (10),
  `test_loyalty_events.py` (6).
- `tests/architecture/test_loyalty_domain_contract.py` (6) — sin I/O/UI/floats, cobertura del catálogo de
  eventos, alineación con `EventName`, entidades presentes, único ensamblador de saldo, `Decimal` obligatorio.

100 tests LOY-1+LOY-2 corridos juntos, sin regresión.

## Pendiente para fases futuras

- LOY-3 (esquema limpio): tablas `loyalty_programs`, `loyalty_accounts`, `loyalty_memberships`,
  `loyalty_transactions` con `UNIQUE(operation_id)` y `UNIQUE(source_module, source_document_id,
  transaction_type, reason_code)` (§12) — ninguna existe todavía.
- LOY-4/5 (repositorios/casos de uso): primer consumidor real de estas entidades y de
  `LoyaltyAuthorizationPolicy.require()` (LOY-1).
- Cierre real del wiring a Finanzas: publicar `LoyaltyEvents.POINTS_ISSUED` etc. desde un use case real y
  conectarlo (vía bridge estilo `finance_handler.py`, o llamando el handler directamente en la misma
  transacción) a `LoyaltyPointsIssuedHandler` — no fabricado en esta fase.
- `referidos.cliente_referidor`/`cliente_referido` siguen siendo `INTEGER` (hallazgo LOY-0) — pendiente de
  LOY-10 (Referidos) o de una migración de datos dedicada.
