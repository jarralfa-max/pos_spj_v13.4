# LOY-4 — Repositorios y Unit of Work

Fecha: 2026-08-28
Alcance: fase LOY-4 del plan (Ports, Implementaciones, UnitOfWork, Atomicidad, Tests). Mismo alcance que
SALES-5, contra el esquema construido en LOY-3.

## Decisión de convención

Igual que Sales/Inventory (no la familia con `Protocol` en `domain/` que usan Transfers/CRM/Customers):
clases concretas, sin puerto explícito — `backend/infrastructure/db/schema/loyalty_schema.py` ya declara
seguir las convenciones de `sales_schema.py`, así que la consistencia dentro del mismo bounded context pesó
más que adoptar la otra familia.

## Qué se construyó

`backend/infrastructure/db/repositories/loyalty/`:
- `base.py` — helpers compartidos (`dec_str`/`to_decimal`/`enum_value`/`bool_to_int`/`int_to_bool`,
  `_query`/`_query_one`/`_execute`/`_scalar`), idéntico a `sales/base.py`.
- `program_repository.py` — `LoyaltyProgramRepository` (`save`/`get`/`get_by_code`/`list_active`).
- `account_repository.py` — `LoyaltyAccountRepository` (`save`/`get`/`get_by_customer_id`).
- `membership_repository.py` — `LoyaltyMembershipRepository`
  (`save`/`get`/`get_by_account_and_program`/`list_for_account`).
- `transaction_repository.py` — `LoyaltyTransactionRepository`, el ledger. Ver decisión de diseño abajo.
- `outbox_repository.py` — `LoyaltyOutboxRepository` (`enqueue`/`list_pending`/`get_by_event_id`/
  `mark_dispatched`), sin dispatcher todavía (mismo hallazgo ya documentado en LOY-2: ningún dispatcher de
  outbox está realmente wireado en este repo, ni siquiera para el de referencia de Inventario).
- `unit_of_work.py` — `LoyaltyUnitOfWork(connection, *, owns_transaction=True)`, mismo diseño exacto que
  `SalesUnitOfWork` (mismo flag, mismo `__enter__`/`__exit__`) — un checkout/acreditación real necesitará
  componer escrituras de Loyalty + Sales + Finance dentro de un mismo SAVEPOINT externo.

## Decisión de diseño: `LoyaltyTransactionRepository.save()` es un upsert restringido, no un upsert completo

El `ON CONFLICT(id) DO UPDATE SET` de `loyalty_transactions` **solo** toca `status` y
`reversal_transaction_id` — nunca `points_amount`/`transaction_type`/`operation_id`/etc. Esto no es un
descuido: es la traducción literal a SQL de la regla que `LoyaltyTransaction` (LOY-2) ya impone en el dominio
("No modificar movimientos originales" — §11). Test explícito
(`test_status_update_never_touches_points_amount`) simula un caller que muta `points_amount` en memoria
antes de volver a guardar, y prueba que el valor persistido no cambia — más un guardrail de arquitectura
(`test_transaction_repository_never_updates_points_amount_on_conflict`) que analiza el propio texto del SQL
para bloquear que alguien amplíe esa cláusula en el futuro.

`exists_for_source()` traduce la constraint `UNIQUE(source_module, source_document_id, transaction_type,
reason_code)` (§12, LOY-3) a un probe explícito — usa `IS ?` en vez de `= ?` para que `source_document_id
NULL` compare correctamente contra otro `NULL` (SQLite: `NULL = NULL` es `NULL`/falso; `NULL IS NULL` es
verdadero), necesario porque ajustes manuales legítimamente no tienen documento fuente.

## Tests

37 tests nuevos, todos pasando en el primer intento:
- `tests/unit/loyalty/test_loyalty_repositories.py` (23) — round-trip completo de las 4 entidades,
  preservación de `Decimal`, violación de constraints únicas (customer_id, enrollment, operation_id), el
  guardrail de "solo status cambia" descrito arriba, `exists_for_source` con y sin documento nulo.
- `tests/unit/loyalty/test_loyalty_unit_of_work.py` (8) — commit conjunto, rollback conjunto, atomicidad
  ante `operation_id` duplicado, comportamiento de `owns_transaction`.
- `tests/architecture/test_loyalty_unit_of_work_boundary.py` (3) — ningún repositorio hace
  `commit()`/`rollback()`/DDL fuera del propio UoW; el UoW expone las 5 repos; el guardrail de la cláusula
  `ON CONFLICT` del ledger.

137 tests LOY-1..4 corridos juntos, sin regresión.

## Pendiente para fases futuras

- LOY-5/6 (casos de uso): primer consumidor real de este `LoyaltyUnitOfWork` — acreditar/canjear/reservar/
  liberar/expirar/ajustar/reversar puntos, cada uno con su propia validación de permisos
  (`LoyaltyAuthorizationPolicy`, LOY-1) y publicación real al `loyalty_outbox`.
- Sin dispatcher de outbox — mismo estado que Sales/Inventory, no fabricado aquí.
