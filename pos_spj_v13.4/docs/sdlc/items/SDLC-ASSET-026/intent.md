# SDLC-ASSET-026 — Dos bajas paralelas: Finanzas da de baja sin el flujo de solicitud y aprobación de Activos

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/activos.md` §46–§48, §70 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-ASSET-024, SDLC-FIN-003, SDLC-ASSET-008

## Problema
Activos tiene el flujo de baja (solicitud, revisión, aprobación, ejecución) solo como entidades, y Finanzas da de baja o vende directamente desde su pantalla, sin solicitud ni segregación. §46 prohíbe cambiar a baja sin flujo. La venta no registra comprador ni documento en Activos.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `backend/application/use_cases/finance/dispose_asset_use_case.py:43,114`
- `frontend/desktop/modules/finance/pages/fixed_assets_page.py:81-93` → `finance_routes.py:270-271`
- `backend/domain/assets/entities/asset_disposal_request.py`, `asset_disposal.py` — solo dominio

## Impacto
Bajas de equipos sin autorización de un segundo.

## Objetivo
- Una sola baja: Activos solicita, aprueba y ejecuta la disposición física; Finanzas reconoce valor en libros y resultado al recibir el evento.
- Pérdida/robo con evidencia y alerta.
- Pruebas de extremo a extremo.

## Alcance
- **Incluye:** Flujo de baja y su integración con Finanzas.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento, revisión independiente obligatoria, migraciones probadas sobre una copia de la BD en el directorio temporal.

## Trabajo previo relacionado
- ASSET-12

## Preguntas abiertas
- Ninguna por ahora.
