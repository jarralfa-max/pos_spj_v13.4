# SDLC-SET-002 — Tablas de configuración legacy (configuraciones, feature_flags, hardware_config) siguen vivas

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-007

## Problema
Junto a `configuration_values` gobernada siguen `configuraciones` (leída/escrita por pin de sucursal, org units, credenciales WhatsApp, recibos), `feature_flags` legacy (sólo la lee una clase sin uso; las vivas están en `ff_flags`) y `hardware_config` sembrada sin escritor. Las tres usan PK natural, no UUIDv7. Además, la identidad de sucursal se escribe en tres almacenes (`sucursales`, `branch_profiles`, `org_units`) en ambos sentidos.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/infrastructure/db/schema/settings_schema.py:70`; `migrations/m000_base_schema.py:121,130,149`
- `installation_branch_repository.py:41,65`; `org_unit_repository.py:153,171-207`; `whatsapp_credential_resolver.py:55`; `sales_receipt_client.py:228`
- `backend/application/queries/module_settings_query_service.py:92,104`
- `backend/application/use_cases/configuracion/company_branch_use_cases.py:85-105`

## Impacto
Dos verdades de configuración; deriva entre almacenes de sucursal.

## Objetivo
- Configuración leída y escrita sólo por el almacén gobernado; sucursal con un dueño.

## Alcance
- **Incluye:** Plan de retiro por tabla.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada.

## Trabajo previo relacionado
`docs/refactor/work_queue.json`: lotes CONFIGURACION-07-PERSISTENCE y CONFIGURACION-14-LEGACY_REMOVAL **PENDING** (este ítem los referencia, no los duplica); ORG-AUD.

## Preguntas abiertas
- ¿Se ejecuta dentro del pipeline CONFIGURACION (lotes 07/14) o como ítem SDLC independiente?
