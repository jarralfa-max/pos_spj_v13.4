# SDLC-CORE-011 — 74 fallas y 32 errores en tests/integration, en su mayoría fixtures desactualizados

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** SDLC-CORE-007

## Problema
Medido con `--continue-on-collection-errors` (el segmento real ni colecta, ver SDLC-CORE-007): 74 fallas y 32 errores en 5912 pruebas. Causas agrupadas: (a) 31 fixtures crean `usuarios` a mano sin `sucursal_id`, columna que la Fase 2 de ORG-AUD ahora lee en cada verificación de permisos; (b) ~45 pruebas de BI legacy montan la tabla `productos`, ya retirada; (c) pruebas que leen `core/`, `modulos/` o `services` eliminados; (d) 7 páginas de BI registran 'Unknown icon identifier' (emoji) y la prueba lo toma como consulta tragada; (e) 3 pruebas de corte UUID: `bi_branch_ranking` no tiene `id` (PK compuesta natural) — desviación real de la REGLA CERO; (f) `KeyError: 'direcciones'` en el expediente de clientes; (g) `loss_reasons.created_at` NOT NULL en la prueba born-clean de Mermas.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `docs/sdlc/baseline/2026-10-28.md` — `74 failed, 5797 passed, 9 skipped, 32 errors in 2854.00s` *(verificado directamente en el triage)*
- (a) `backend/infrastructure/db/repositories/security/permission_repository.py:103-107` (`SELECT sucursal_id FROM usuarios`), vía `backend/application/security/access_scope.py:79,109`; la columna sí existe en `migrations/m000_base_schema.py` (`usuarios.sucursal_id`) *(verificado directamente en el triage)*
- (b) `tests/integration/test_bi_*.py` — `no such table: productos` *(verificado directamente en el triage)*
- (c) `tests/integration/test_purchase_command_payment_payload.py`, `test_purchase_planning_no_sql_in_pyqt.py`, `test_realtime_inventory_refresh.py`, `test_settings_module_loads.py`, `integrations/test_mercadopago_credential_resolver.py` *(verificado directamente en el triage)*
- (d) `tests/integration/business_intelligence/test_every_bi_page_opens.py` — `frontend/desktop/components/icons.py:404` *(verificado directamente en el triage)*
- (e) `migrations/standalone/062_bi_analytics_tables.py:54-62` vs `migrations/standalone/_cutover_spec_generated.py:31` *(verificado directamente en el triage)*
- (f) `tests/integration/addresses/test_address_screens.py::TestCustomers` — `KeyError: 'direcciones'` *(verificado directamente en el triage)*

## Impacto
Ruido que impide usar el segmento como gate; (a) además muestra que una verificación de permisos lanza excepción (no deniega) si el esquema difiere; (e) es deuda real de identidad.

## Objetivo
- Cada grupo corregido o retirado con justificación; las pruebas de (c) sobre código eliminado se borran o se reescriben contra el reemplazo.
- Decisión sobre (a): ¿`home_branch_id` debe degradar con seguridad (denegar) ante error de esquema?
- `bi_branch_ranking` con `id TEXT` UUIDv7 o excluida del corte con decisión escrita.

## Alcance
- **Incluye:** Fixtures y pruebas de integración; `bi_branch_ranking`.
- **No incluye:** Recolección rota (CORE-007).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada.

## Trabajo previo relacionado
Memoria: `tests/integration/_born_clean_db.py` sin migración 047; ORG-AUD fase 2 (migr. 353); PROD-22 (tablas legacy retiradas).

## Preguntas abiertas
- Ninguna por ahora.
