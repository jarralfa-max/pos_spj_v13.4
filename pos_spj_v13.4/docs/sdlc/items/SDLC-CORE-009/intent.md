# SDLC-CORE-009 — Resto de guardias de arquitectura en rojo (UI, deuda visual, herramientas de refactor)

- **Prioridad:** P3
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
Fallan además: Precios con `select` en `pricing_workspace.py`, Inventario con permiso grueso `INVENTARIO`, carga masiva en `QComboBox`, defaults numéricos fijos en UI, rutas relativas sueltas (`.test_tmp/`, `database_relocation.py`, `sqlite_backup.py`), deuda visual nueva (overflow, `QTableWidget` nativo), campo DTO `price_basis`, contrato LOSS-10 (`release_quarantine`), puente legacy de clientes (19 violaciones), y 7 pruebas de herramientas de refactor (`refactor_orchestrator`, `refactor_state`, `docs` fuera del paquete). La de imports `core.*` del microservicio está cubierta por SDLC-WA-005.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `docs/sdlc/baseline/2026-10-28.md` — lista completa de las 22 fallas *(verificado directamente en el triage)*
- `frontend/desktop/modules/pricing/pricing_workspace.py` (guardia `test_pricing_ui_has_no_database_access`)
- `frontend/desktop/modules/inventory/shell_registration.py` (`"INVENTARIO"`)
- `frontend/desktop/modules/pricing/dialogs/pricing_dialogs.py:207`; `frontend/desktop/modules/finance/pages/expenses_page.py:129`; `frontend/desktop/modules/hr/dialogs/hr_dialogs.py:317`
- `backend/application/customers/use_cases/legacy_customer_bridge_use_cases.py` (19 violaciones) — relacionado con SDLC-CRM-003
- `tests/architecture/test_refactor_orchestrator.py` (4), `test_refactor_state_json_is_valid.py`, `test_refactor_paths_inside_package.py`

## Impacto
Ruido que oculta regresiones reales; deuda de UI.

## Objetivo
- Cada guardia queda verde o se retira con decisión registrada (p. ej. herramientas de refactor obsoletas).

## Alcance
- **Incluye:** Clasificación por guardia; puede dividirse en Design.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada.

## Trabajo previo relacionado
Memoria UI Design System (2026-10-28).

## Preguntas abiertas
- ¿Las herramientas de `tools/refactor_control` y el orquestador Codex siguen en uso?
