# SDLC-SALES-005 — Modelo de ventas legacy (ventas/detalles_venta) sigue vivo como fuente de lectura

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`v_ventas_unificada` y su respaldo a la tabla legacy siguen leyéndose; el único escritor es el seed de demo, así que las ventas de demo nunca llegan a `sales` ni a Finanzas. `SalesReadRepository` lee sólo legacy y no tiene importadores.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/infrastructure/db/sales_read_source.py:1-52`
- `backend/infrastructure/db/repositories/sales_read_repository.py:49-88`
- `scripts/seed_demo.py:279-300`

## Impacto
Dos verdades de ventas; demos que no reflejan el sistema real.

## Objetivo
- Lecturas de ventas sólo desde el modelo canónico; seed de demo escribe por casos de uso.

## Alcance
- **Incluye:** Fuente de lectura y seed.
- **No incluye:** Pipelines de pedidos (ORD-003).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada.

## Trabajo previo relacionado
Memoria 'Sales: two live persistence models'.

## Preguntas abiertas
- Ninguna por ahora.
