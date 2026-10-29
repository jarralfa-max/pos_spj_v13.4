# SDLC-CRM-001 — Fusión de clientes escribe crédito directo, cierra crédito con saldo y deja puntos huérfanos

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
La fusión ejecuta `UPDATE customer_credit_profiles` directo (contradice su docstring), cierra el perfil de crédito AUTHORIZED del cliente fusionado sin revisar su saldo, y no mueve cuentas de lealtad: `CUSTOMER_MERGE_EXECUTED` va a un outbox que nadie drena y Lealtad no maneja fusiones.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/customers/use_cases/merge_use_cases.py:54,126-137` (docstring 22-26)
- `customer_outbox` sin despachador (sólo `backend/infrastructure/sync/replication_sources.py`)

## Impacto
Saldo de crédito y puntos de clientes fusionados se pierden o quedan inaccesibles.

## Objetivo
- La fusión mueve crédito y lealtad mediante casos de uso de sus contextos (sin SQL cruzado).
- No se cierra un crédito con saldo sin transferirlo.
- Prueba: fusionar A en B conserva saldo de crédito y puntos totales.

## Alcance
- **Incluye:** Caso de uso de fusión y puertos hacia Crédito y Lealtad.
- **No incluye:** Unificación `clientes`/`customers` (SDLC-CRM-003).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria CRM-43/44.

## Preguntas abiertas
- Ninguna por ahora.
