# SDLC-ARQ-IDEM-004 — Ventas tienen columna version pero el repositorio la sobrescribe sin compararla

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §12 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R12.2 Concurrencia controlada (ventas), estado `defectuoso`)
- **Estado:** borrador
- **Depende de:** SDLC-ARQ-IDEM-003

## Problema
`sales.version` existe, pero `sale_repository` hace upsert sin `AND version=?`, así que dos sesiones que editan la misma venta (por ejemplo, reanudar desde otra caja) se pisan en silencio.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/infrastructure/db/repositories/sales/sale_repository.py:60-105`
- Contraste: inventario sí lo hace en `inventory_balance_repository.py:62-83`
- Pruebas: ninguna para ventas concurrentes.

## Impacto
Pérdida silenciosa de líneas o descuentos en ventas editadas en paralelo.

## Objetivo
- Guardar una venta exige la versión leída; un conflicto devuelve error explícito.
- Prueba con dos conexiones.

## Alcance
- **Incluye:** Repositorio de ventas y su prueba.
- **No incluye:** Caja (SHIFT-004).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
—

## Preguntas abiertas
- Ninguna por ahora.
