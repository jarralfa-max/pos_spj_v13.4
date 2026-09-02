# LOY-3 — Esquema limpio (UUIDv7, Decimal, Constraints, Índices, Outbox)

Fecha: 2026-08-28
Alcance: master prompt §8 (UUIDv7/Decimal), §12 (idempotencia), fase LOY-3 del plan (1. UUIDv7. 2. Decimal.
3. Constraints. 4. Índices. 5. Outbox. 6. Bootstrap. 7. Tests). Mismo alcance que SALES-4.

## Hallazgo real: colisión de nombre que LOY-0 no detectó

Un primer borrador de este esquema nombró la tabla de programas `loyalty_programs` (el nombre obvio, dado
que la entidad de dominio LOY-2 es `LoyaltyProgram`). Al bootstrapear una base real desde cero para validar
(no en una fixture aislada), la migración falló:

```
ERROR: Migración 225 falló: no such column: status — haciendo rollback.
```

Investigando la causa: `migrations/m000_base_schema.py::_create_loyalty` (línea ~1538) **ya crea una tabla
`loyalty_programs`** — el propio esquema legacy del Growth Engine, con columnas en español
(`nombre`, `activo`, `puntos_por_peso`, `nivel_bronce`/`nivel_plata`/`nivel_oro`/`nivel_platino` — floats
`REAL` y umbrales de nivel hardcodeados, exactamente el anti-patrón que este refactor completo existe para
eliminar en LOY-27). `CREATE TABLE IF NOT EXISTS` no hizo nada porque la tabla legacy ya existía, y el
`CREATE INDEX ... loyalty_programs(status)` posterior falló porque esa tabla real no tiene columna `status`.

`docs/refactor/LOY-0_auditoria.md` no menciona esta tabla — la auditoría original (agente de investigación)
no llegó a esta función específica dentro de las ~3000 líneas de `m000_base_schema.py`. Se corrige aquí, no
se reabre LOY-0 completo: la tabla legacy `loyalty_programs` (y sus vecinas `loyalty_config`,
`loyalty_scores`, `loyalty_level_history`, `loyalty_challenges`, `loyalty_challenge_progress`,
`loyalty_community_goals/contributions`, `loyalty_budget_caps`, `loyalty_multiplier_rules`,
`loyalty_redemption_limits`, `loyalty_roi_tracking`, `loyalty_snapshots`, `loyalty_ticket_messages`,
`config_programa_fidelidad`) forman parte del mismo Growth Engine legacy ya calificado para eliminación
completa en LOY-27 — quedan añadidas al inventario, no se tocan en esta fase.

**Corrección aplicada**: la tabla nueva se renombró a `loyalty_program_definitions` (nunca `_v2`/`_new` — se
aplicó el mismo criterio de desambiguación que SALES-4 ya usó para `sale_payments` frente a la `payments`
legacy). `loyalty_accounts`/`loyalty_memberships`/`loyalty_transactions`/`loyalty_outbox` se verificaron por
grep contra todo `migrations/` ANTES de nombrarlas — ninguna colisiona.

## Qué se construyó

`backend/infrastructure/db/schema/loyalty_schema.py` — `create_loyalty_schema()`/`drop_loyalty_schema()`,
mirrors `sales_schema.py` exactamente:

| Tabla | Corresponde a (LOY-2) | Idempotencia/constraints propios |
|---|---|---|
| `loyalty_program_definitions` | `LoyaltyProgram` | `UNIQUE(code)` |
| `loyalty_accounts` | `LoyaltyAccount` | `UNIQUE(customer_id)` — un cliente, una cuenta |
| `loyalty_memberships` | `LoyaltyMembership` | `UNIQUE(loyalty_account_id, program_id)` |
| `loyalty_transactions` | `LoyaltyTransaction` (ledger) | `UNIQUE(operation_id)` + `UNIQUE(source_module, source_document_id, transaction_type, reason_code)` (§12) |
| `loyalty_outbox` | eventos de `LoyaltyEvents` (LOY-2) | `UNIQUE(event_id)` |

Reglas aplicadas (idénticas a `sales_schema.py`): todo id `TEXT PRIMARY KEY` (UUIDv7); `points_amount` es
`TEXT` (nunca `REAL`); sin `CHECK` de enum (el dominio es la única fuente de verdad de transiciones válidas,
mismo criterio ya establecido en `sales_schema.py`/`inventory_schema.py`); `customer_id` en
`loyalty_accounts` es una referencia lógica, sin FK SQL, al Customer Master — Fidelidad nunca posee identidad
de cliente (§4/§52).

`migrations/standalone/225_loyalty_bounded_context_schema.py` — registrada en `migrations/engine.py`
(`MIGRATIONS`, versión "225", siguiente número libre confirmado antes de escribir el archivo).

## Verificación real, no solo en memoria

Se corrió `scripts/bootstrap_db.py` contra una base SQLite real desde cero (no una fixture in-memory) para
confirmar: (1) la migración 225 se ejecuta sin error en el primer intento tras la corrección de nombre;
(2) las 5 tablas existen con exactamente las columnas esperadas; (3) `PRAGMA foreign_key_check` devuelve
`[]` (sin violaciones de integridad referencial). Las 3 fallas preexistentes y no relacionadas (024, 029, 080)
siguen apareciendo igual que antes de este cambio — ya documentadas en memoria, no introducidas aquí.

## Tests

7 tests nuevos en `tests/unit/loyalty/test_loyalty_schema.py`: todas las tablas se crean; **la tabla nueva
nunca colisiona con `loyalty_programs`** (test explícito, protege contra que alguien reintroduzca el nombre
colisionado); sin `AUTOINCREMENT`/`REAL`; `UNIQUE(operation_id)` bloquea duplicados en el ledger;
`UNIQUE(source_module, source_document_id, transaction_type, reason_code)` bloquea doble acreditación para el
mismo documento fuente; `UNIQUE(customer_id)` en cuentas; drop limpia todo; la migración 225 está registrada
y su `run`/`up` son el mismo callable. 108 tests LOY-1+2+3 corridos juntos, sin regresión.

## Pendiente para fases futuras

- LOY-4/5 (repositorios/casos de uso): primer consumidor real de este esquema.
- El inventario completo de tablas legacy del Growth Engine (`loyalty_programs`, `loyalty_config`,
  `loyalty_scores`, etc., listadas arriba) queda registrado para LOY-27 (eliminación de legacy) — no
  descubierto por LOY-0, corregido aquí.
