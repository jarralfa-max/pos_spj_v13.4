# Lote 5 — Núcleo y configuración

- **Rama:** `fix/lote-5`, sobre `claude/erp-financial-bounded-context-uqxz6b`.
- **Aprobaciones:** `e58f6849` traído con cherry-pick (`88acabf5`).
- **Migraciones:** ninguna. No se usó el rango 365–367.

## Estado por ítem

| Ítem | Estado | Commit | Prueba que lo cubre |
|---|---|---|---|
| SDLC-SET-001 | LISTO | `b09b1514` | `tests/integration/shell/test_installation_branch_session_follow.py`, `tests/unit/bootstrap/test_application_context_service.py`, `tests/unit/test_empresa_page_installation_branch.py` |
| SDLC-CORE-012 | LISTO | `0a524a0f` | `tests/unit/test_core012_*`, `tests/integration/transfers/test_core012_*`, `tests/integration/meat_processing/test_core012_*` |
| SDLC-BI-001 | LISTO | `d1ac20a6` | `tests/integration/test_bi_branch_scope.py`, `tests/unit/business_intelligence/test_bi_filter_bar.py` |
| SDLC-CORE-001 | LISTO | `ebd59dde` | `tests/integration/bootstrap/test_event_wiring_isolation.py` |
| SDLC-CORE-007 | LISTO | `a53e523b` | `tests/integration/test_sqlite_sales_repository_uuid.py` + colección completa |
| SDLC-ARQ-TEST-001 | LISTO | `374ccf98` | `tests/integration/test_multi_station_harness.py`, `tests/integration/configuracion/test_installation_branch_resolution.py` |

Ninguno quedó DESCARTADO, BLOQUEADO ni en ESPERA.

## Qué cambió

**SDLC-SET-001.** Anclar la sucursal mueve la sesión abierta en caliente, como respondió el responsable. `ApplicationContextService.follow_installation_anchor` reconstruye el contexto con los mismos puertos del login (`ApplicationContextBuilder.context_service`) y `InstallationBranchFollower` actualiza adaptador de sesión, router, barras y menú. No exige `APPLICATION_CONTEXT_SWITCH`: el anclaje ya se autorizó y ese permiso no está sembrado. Si en el sitio nuevo el usuario no tiene rol, se avisa y se cierra la sesión; si sólo pierde la pantalla actual, pasa a la primera ruta permitida. Se quitaron el `hasattr` y el `except: pass`.

**SDLC-CORE-012.** 20 pruebas de caracterización, sin cambios de producción. Cada una nombra el ítem que la cambia o la conserva: SDLC-TRF-001, SDLC-TRF-003, SDLC-PROC-002, SDLC-SALES-001. Además fija dos comportamientos sin ítem asignado: una línea agregada tras reservar no se descuenta, y `confirm` sin reservas regresa sin avisar.

**SDLC-BI-001.** `BiDashboardService` ya no concede nada por omisión y `section_data` exige permiso. `backend/application/analytics/access.py` arma el acceso desde `BranchScopeQueryService` más el sitio de la sesión. Las rutas, los presenters y las búsquedas de sucursal quedan acotados. Resumen, secciones y reportes tienen filtros de sucursal y periodo (`BiFilterBar`). Exportar reportes exige `INTELIGENCIA_BI.exportar`.

**SDLC-CORE-001.** Cada contexto se importa y se cablea por separado, y los despachos de arranque corren aunque alguno falle. Las fallas quedan en log estructurado (`event_wiring_failed`), degradan el `HealthReport` y se avisan en la barra de estado.

**SDLC-CORE-007.** La prueba rota se migró al agregado canónico de Ventas, con el mismo contrato de identidad UUIDv7. `pytest tests/integration --collect-only`: 5949 pruebas, 0 errores. El responsable pidió el segmento completo en verde como gate: `ci-segmented.yml` ya corre el segmento completo, así que no hubo que cambiar CI, pero seguirá en rojo hasta cerrar SDLC-CORE-011.

**SDLC-ARQ-TEST-001.** Fixture `multi_station` (`tests/integration/multi_station.py`): N estaciones con SQLite real en archivo y central con la ingesta real sobre el libro en memoria, con caída de red, respuesta perdida y reinicio de proceso. Se retiraron 173 archivos de `tests/*.py`; el detalle y los 39 que quedan por revisar están en `docs/sdlc/items/SDLC-ARQ-TEST-001/pruebas-retiradas.md`. El contrato vigente del ancla se reescribió contra el código actual. La matriz §15 enlaza el arnés.

## Decisiones que conviene revisar

- **Permiso nuevo `INTELIGENCIA_BI.sucursales.todas`.** Da el alcance de toda la empresa. No se sembró: lo tienen los roles de acceso total y a los demás se les otorga desde la matriz. Cualquier otro usuario con BI queda limitado a sus sucursales.
- **Multi-sucursal sin alcance global.** Ve una sucursal a la vez; no tiene opción «Todas».
- **El sitio de la sesión siempre entra al alcance de BI**, aunque no esté en `usuarios_sucursales`, porque ya se validó al iniciar sesión.

## Riesgos y choques previstos

- **Turno abierto al re-anclar.** Hasta integrar SDLC-ARQ-TERM-002, re-anclar con un turno abierto en la sucursal anterior ahora sí mueve la sesión en vivo. Esa rama trae la guarda `OPEN_CASH_SHIFT`; conviene integrarla pronto.
- **Choques con `sdlc/sdlc-arq-term-002`:**
  - `test_installation_branch_session_follow.py`: `_gerente_local` debe recibir `CONFIGURACION.estacion.reanclar`, porque `CONFIGURACION.empresa.editar` dejará de bastar.
  - `configuracion_presenter.py`: los cambios son contiguos a `set_installation_branch`; no deberían chocar, pero hay que revisarlo.
  - `application_context_builder.py`: `context_service` se agregó al final para no pisar `_session_site`. La sesión de reparación pasa a operativa al anclar porque se recalculan las capacidades del sitio.
- **Choque con SDLC-ARQ-AUD-001** (`sdlc/sdlc-ui-003-auto`): toca `change_branch`, de donde salió `_rebuild_at`. Al integrar, pasar `audit_sink=build_security_audit_sink(conn)` en `context_service`; hoy el seguimiento del ancla no deja rastro propio en `audit_logs`.
- **Vistas abiertas.** Las rutas se reconstruyen al navegar, pero la pantalla actual de Configuración no se repinta al re-anclar, y una ventana propia como el monitor de cliente no se revisó.
- **`bi_seed` roto.** `tests/integration/bi_seed.py::add_product` escribe en `productos`, ya retirada; por eso `test_bi_permissions.py` y sus pares fallan antes de llegar a lo que prueban. Sus llamadas se actualizaron, pero sólo se verán en verde con SDLC-CORE-011.

## Pruebas finales

RESULTADOS_PENDIENTES

## Fallos preexistentes

Comparados contra `docs/sdlc/baseline/2026-10-28.md`:

- `tests/integration/business_intelligence/test_every_bi_page_opens.py`: 8 fallos, los 8 por avisos `Unknown icon identifier` de los emoji de KPI y ninguno por consulta. Línea base: «avisos de iconos emoji en BI» (SDLC-CORE-011).
- `tests/integration/test_bi_*.py`: `add_product` sobre la tabla retirada `productos` (SDLC-CORE-011).
- `tests/architecture/test_no_entity_combo_mass_loading.py`: `pricing_dialogs.py:207`, ajeno al lote (SDLC-CORE-009).
- `tests/unit/bootstrap/test_steps.py::test_application_paths_step_creates_directories`: falta el directorio `data` en este worktree; el lote no toca ese paso. No se confirmó contra la rama base.
