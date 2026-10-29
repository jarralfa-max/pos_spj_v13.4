# SDLC-CORE-002 — operation_id compuesto por concatenación de cadenas en rutas de dinero e inventario

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
Rutas de dinero e inventario construyen `operation_id` como `f"{sale_id}:{payment_id}:credit-charge"`, `f"{op}:in"`, `":dispose"`, `":reversal"`. La REGLA CERO exige UUID; además Caja→Finanzas rechaza lo que no sea UUIDv7, así que el estándar es inconsistente entre contextos y la columna del ledger no valida.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/use_cases/finance/register_sale_credit_charge_use_case.py:31,52,74-75`
- `backend/infrastructure/integrations/sales_credit_client.py:78`
- `backend/infrastructure/integrations/sales_inventory_client.py:415,470-471,539,559`
- `backend/application/sales/use_cases/return_use_cases.py:239`
- `backend/application/inventory/use_cases/adjustment_use_cases.py:101`, `quarantine_use_cases.py:204`, `goods_receipt_reversed_handler.py:59`
- `backend/infrastructure/db/schema/inventory_schema.py:135`
- `backend/application/event_handlers/finance/cash_finance_router.py:30-33`
- `docs/skills/SPJ_REFACTOR_SKILL.md:13,229`

## Impacto
Bloquea replicación uniforme y la validación de identidad.

## Objetivo
- Ids derivados deterministas en formato UUID (decisión de Design) y validación en la columna/contrato.

## Alcance
- **Incluye:** Generación de operation_id derivados.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
REGLA CERO.

## Preguntas abiertas
- Los ids derivados necesitan ser deterministas para idempotencia: ¿se acepta UUIDv5/v8 derivado del UUIDv7 padre, o se exige UUIDv7 persistido? (posible contradicción con la REGLA CERO)
