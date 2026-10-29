# SDLC-LOG-001 — Logística ejecuta SQL contra tablas de Compras y Productos

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
La capa de aplicación de Logística consulta `purchase_orders`, `direct_purchases`, `purchase_requisition_lines` y `products` directamente en lugar de puertos de consulta de esos contextos.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/logistics/service.py:185-208`
- `backend/application/logistics/mobile_workflow.py:37-77,192-214`

## Impacto
Acoplamiento que rompe con cualquier cambio de esquema de Compras.

## Objetivo
- Logística usa query services de Compras y Productos.

## Alcance
- **Incluye:** Logística.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada.

## Trabajo previo relacionado
Memoria LOG-INT 32cfbf.

## Preguntas abiertas
- Ninguna por ahora.
