# SDLC-INV-006 — Folios de ajuste, conteo y peso se repiten (new_uuid()[:8])

- **Prioridad:** P3
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
Los folios se construyen con los primeros 8 hex de un UUIDv7, que son bits de tiempo: todo documento creado en la misma ventana de ~65 s recibe el mismo folio, y el folio no es UNIQUE.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/modules/inventory/presenter.py:1215,1362,1468`
- `backend/application/inventory/use_cases/catch_weight_use_cases.py:79`

## Impacto
Documentos indistinguibles por folio.

## Objetivo
- Folios generados por un secuenciador del backend, únicos por sucursal y tipo.

## Alcance
- **Incluye:** Folios de inventario.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada.

## Trabajo previo relacionado
—

## Preguntas abiertas
- Ninguna por ahora.
