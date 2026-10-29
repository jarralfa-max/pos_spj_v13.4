# SDLC-CORE-005 — Código muerto y cascarones de casos de uso (ventas, delivery, RRHH, BI)

- **Prioridad:** P3
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`DelegatingUseCase` vacíos o sin llamador (`cancel_sale_use_case.py` con el mismo nombre que el real, `execute_monthly_closing_use_case.py` con float), `settle_delivery_driver_use_case.py` sin llamador (float, totales de la UI, excepciones tragadas), cascarones de delivery, `create_hr_view` legacy, `_impl` sombreados en el bridge, ruta BI 'Producción' sin builder y docstrings que citan `MenuLateral`/`MainWindow` inexistentes.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/use_cases/cancel_sale_use_case.py:9`; `execute_monthly_closing_use_case.py:24-28`
- `backend/application/use_cases/settle_delivery_driver_use_case.py:30-139`; `create_delivery_order_use_case.py:9-10`; `backend/application/queries/delivery_query_service.py`
- `frontend/desktop/modules/hr/hr_routes.py:169-177`
- `whatsapp_service/erp/bridge.py:752,899,1022`
- `frontend/desktop/modules/business_intelligence/navigation/business_intelligence_sidebar.py:47`; `business_intelligence/shell_registration.py:8-15,30-32`

## Impacto
Ruido y riesgo de reutilizar código equivocado.

## Objetivo
- Eliminado con evidencia de cero importadores; la ruta BI Producción se oculta o se construye.

## Alcance
- **Incluye:** Eliminaciones.
- **No incluye:** Handlers de Finanzas (FIN-001), auth (SEC-004).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada.

## Trabajo previo relacionado
—

## Preguntas abiertas
- Ninguna por ahora.
