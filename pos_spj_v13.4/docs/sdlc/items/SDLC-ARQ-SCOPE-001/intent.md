# SDLC-ARQ-SCOPE-001 — Almacenes y plantas acoplados a sucursal; Logística necesita una sucursal anclada

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §4 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R4.3 / R4.4 Logística transversal, almacén y planta, estado `parcial`)
- **Estado:** borrador
- **Depende de:** SDLC-ARQ-PERM-003

## Problema
Existen tipos de unidad organizacional para planta, almacén y centro operativo, pero `warehouses.branch_id` es NOT NULL y cada sitio operativo se refleja como fila de `sucursales`. Toda sesión lleva una sucursal anclada; el alcance de Transferencias ignora almacén y ubicación. El documento pide que Logística opere transversalmente sin sucursal activa artificial.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/infrastructure/db/schema/inventory_schema.py:80-84`
- `backend/domain/organization/org_unit.py:7-12,34-41`
- `backend/application/transfers/session_scope_checker.py:19-25`
- Pruebas: `tests/integration/transfers/test_transfer_full_cycle_32cfbf.py` usa `for_tests` (sin autorización ni alcance); §15 T3 con usuario multi-sucursal: ninguna.

## Impacto
Operadores de logística y planta deben 'cambiar de sucursal' para operar; los almacenes centrales se modelan como sucursales ficticias.

## Objetivo
- Alcance por almacén/planta/ubicación disponible para Transferencias y Logística.
- Una sesión de Logística puede operar origen→destino dentro de su alcance sin sucursal activa.
- Prueba §15 T3.

## Alcance
- **Incluye:** Alcance por nodo; sesión sin sucursal para perfiles transversales.
- **No incluye:** Rehacer el modelo de inventario (SDLC-INV-003).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-INV-003 (ubicación distinta por flujo), SDLC-TRF-001.

## Preguntas abiertas
- Ninguna por ahora.
