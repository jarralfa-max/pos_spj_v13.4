# SDLC-CRM-003 — Dos maestros de clientes vivos (clientes y customers) con puente bidireccional

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-003

## Problema
El puente inserta en `clientes` aunque su docstring dice que nunca escribe ahí; WhatsApp crea clientes en `clientes` mientras los pedidos canónicos apuntan a `customers`.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/customers/use_cases/legacy_customer_bridge_use_cases.py:3-9,22,114-118`
- `whatsapp_service/erp/bridge.py:330-335`
- `backend/infrastructure/db/schema/orders_delivery_schema.py:29-30`

## Impacto
Clientes duplicados/divergentes entre canales.

## Objetivo
- Un solo maestro escrito; el otro sólo como vista de compatibilidad hasta retirarse.

## Alcance
- **Incluye:** Puente y escritores.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada.

## Trabajo previo relacionado
CRM-43.

## Preguntas abiertas
- Ninguna por ahora.
