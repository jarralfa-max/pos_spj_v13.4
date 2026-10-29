# SDLC-CORE-006 — Float residual en dinero y cantidades (lealtad, recibos, analítica, proveedores, depreciación)

- **Prioridad:** P3
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
Vista previa de lealtad y cliente de recibos convierten a float; `CAST(... AS REAL)` en calidad y analítica de inventario; saldos de proveedor formateados con float; la corrida de depreciación suma el total con la moneda del primer activo.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/infrastructure/integrations/sales_loyalty_client.py:25-26,118-127`; `sales_receipt_client.py:133-147`
- `backend/application/quality/queries.py:31`; `backend/application/inventory/analytics/inventory_analytics_service.py:95,130`
- `backend/application/suppliers/queries/supplier_read_services.py:200,217`
- `backend/application/use_cases/finance/run_depreciation_use_case.py:68,72`

## Impacto
Errores de redondeo menores.

## Objetivo
- Decimal de punta a punta en esas rutas; guardia de arquitectura.

## Alcance
- **Incluye:** Rutas citadas.
- **No incluye:** Disponibilidad de producción (PROC-002).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada.

## Trabajo previo relacionado
Memoria PROD-22 (guardia float→Decimal en whatsapp_service).

## Preguntas abiertas
- Ninguna por ahora.
