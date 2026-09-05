# ASSET-24 — Validación final (Activos / EAM)

Ejecutado: 2026-09-02. §113-114 del prompt maestro — cierre de la pipeline ASSET-0 a ASSET-24, todas ejecutadas en una sola sesión extendida (múltiples continuaciones, mismo día).

## Resultado de la validación técnica

- **Suite de Activos**: 228 tests (unitarios `tests/unit/assets/` + arquitectura `tests/architecture/test_assets*.py`/`test_asset_*.py`) — **228 passed, 1 skipped** (skip intencional: `assets_schema.py` no existe, documentado desde ASSET-1). Confirmado de nuevo en esta fase, sin regresiones.
- **Sintaxis**: `ast.parse` sobre `backend/domain/assets/`, `backend/application/assets/`, `tests/unit/assets/`, `tests/architecture/` y `frontend/desktop/modules/assets/` — sin errores.
- **Guardrails de frontend genéricos** (no específicos de Activos): `test_design_system_guardrails.py`, `test_no_commit_rollback_in_frontend.py`, `test_no_external_frontend_backend_imports.py`, `test_no_sql_in_frontend.py` — verificados en ASSET-18, siguen sin regresión (no se tocó UI desde entonces salvo agregados aditivos en ASSET-19).
- **Red de regresión legacy**: `tests/test_asset_service_ui_reads.py` (21/22 passed — 1 falla preexistente y no relacionada, `test_calcular_depreciacion_mensual_escribe_cuando_hay_columna`, documentada desde ASSET-1/2/3 por migraciones 024/029/080 rotas en el fixture del test, nunca tocadas por esta pipeline) y `tests/test_fase3_depreciacion.py` (14/14 passed) — el legacy sigue funcionando exactamente igual que antes de empezar esta pipeline, cero funcionalidad perdida (§1 de `CLAUDE.md`, la regla más importante de todas).
- **Suite completa `tests/architecture/`**: re-ejecutada en esta fase; el baseline de fallas preexistentes no relacionadas (Settings/Transfers/text_pk_not_null/uuidv7_cutover/refactor_state.json, ~84 en la corrida de ASSET-1) se mantiene sin fallas nuevas atribuibles a Activos.

## Checklist honesto contra §113 ("Definición de terminado")

Marcado tal como está realmente, no aspiracionalmente:

```text
[x] Activos es bounded context independiente. (domain/assets, application/assets, frontend/desktop/modules/assets)
[x] Finanzas no es dueño del ciclo operativo del activo. (Asset es entidad distinta de FixedAsset)
[x] Activos no registra asientos. (guardrail test_assets_do_not_post_journal_entries.py)
[x] Activos no ejecuta pagos. (guardrail test_assets_do_not_execute_treasury_payments.py)
[ ] Activos no administra CxP. (no aplica — nunca se construyó nada de CxP, correcto por omisión)
[x] Existe Asset aggregate. (ASSET-3)
[x] Existen categorías configurables. (AssetCategory, ASSET-3)
[x] Existe folio operativo. (Asset.asset_number, distinto del UUID interno)
[x] Todos los IDs usan UUIDv7. (guardrail test_assets_use_uuidv7.py, new_uuid() en todo el dominio)
[x] Todo dinero usa Decimal. (guardrail test_assets_use_decimal.py, Money en todas las entidades con montos)
[x] Existe ubicación jerárquica. (AssetLocation, ASSET-3)
[x] Existe custodia. (AssetAssignment, ASSET-4)
[x] Existe historial de asignación. (AssetAssignment nunca sobrescribe, cierra y crea nuevo registro)
[x] Existen transferencias. (AssetTransfer, ASSET-5, con segregación de funciones real)
[x] Existen préstamos. (AssetLoan, ASSET-4)
[x] Existe MaintenancePlan. (ASSET-6)
[x] Existe MaintenanceWorkOrder. (ASSET-6, máquina de estados completa)
[x] Existe mantenimiento preventivo. (MaintenanceType.PREVENTIVE)
[x] Existe correctivo. (MaintenanceType.CORRECTIVE)
[x] Existe mantenimiento interno. (MaintenanceProviderType.INTERNAL)
[x] Existe mantenimiento externo. (MaintenanceProviderType.EXTERNAL)
[ ] Existe integración con proveedores. (solo el Protocol SupplierLookupPort, ASSET-15 — sin adaptador concreto)
[x] Existen inspecciones. (AssetInspection, ASSET-7)
[x] Existen checklists. (InspectionChecklistTemplate/Item, ASSET-7)
[x] Existen medidores. (AssetMeter/AssetMeterReading, ASSET-8)
[x] Existen garantías. (AssetWarranty, ASSET-9)
[x] Existen seguros. (AssetInsurancePolicy, ASSET-9)
[x] Existen documentos. (AssetDocument, ASSET-9)
[ ] Existen fotografías. (AssetDocumentType.PHOTO existe como tipo; sin captura de cámara real, no aplica a un backend headless)
[x] Existe inventario físico. (AssetPhysicalInventory, ASSET-11)
[x] Existen discrepancias. (AssetPhysicalDiscrepancy, con workflow completo §45)
[x] Existe workflow de baja. (AssetDisposalRequest, ASSET-12, con segregación de funciones real)
[x] Existe pérdida/robo. (AssetDisposalReason.LOSS/THEFT con evidencia obligatoria)
[x] Existe AssetTag. (ASSET-13)
[x] Existe QR seguro. (qr_public_token distinto del UUID interno)
[x] Existe barcode. (AssetTagType.BARCODE_128)
[ ] Toda impresión usa PrintJob. (PrintJobGatewayPort es solo un Protocol, ASSET-15 — sin adaptador ni UI de impresión real)
[ ] PDF usa Document Output. (mismo estado: contrato declarado, no wireado)
[ ] Existe integración con Compras. (mismo estado que proveedores)
[x] Existe integración con Finanzas. (eventos + mapa de frontera, sin acoplamiento directo)
[ ] Existe integración con Inventario. (guardrail negativo existe — test_assets_parts_do_not_write_inventory.py — pero ningún Protocol positivo de consumo se construyó)
[ ] Existe integración con RRHH. (solo el Protocol EmployeeLookupPort, ASSET-15 — sin adaptador)
[ ] Existe integración con BI. (no construida)
[ ] Existe Notification Management. (no construida)
[x] Existe propuesta de capitalización. (AssetCapitalizationProposal, ASSET-10)
[ ] Finanzas aprueba y contabiliza capitalización. (el flujo de eventos está diseñado; nada lo consume del lado de Finanzas todavía)
[x] Depreciación financiera pertenece a Finanzas. (guardrail test_assets_do_not_own_financial_depreciation.py)
[ ] Activos muestra proyección financiera. (AssetPermissions.FINANCIAL_PROJECTION_VIEW y la ruta existen; el QueryService real no se construyó)
[ ] Existe MTBF. (no construido)
[ ] Existe MTTR. (no construido)
[x] Existen indicadores. (AssetDashboardQueryService + AssetsOverviewPage, ASSET-14/17)
[ ] Existen roles. (permisos granulares sí; roles de sistema nuevos — ASSET_CUSTODIAN etc. — nunca sembrados, decisión deliberada §82)
[x] Existen permisos granulares. (~80 códigos ACTIVOS.*, ASSET-2)
[x] Existen scopes. (AssetScopeLevel, ASSET-2 — contrato, resolver concreto no construido)
[x] Existe segregación de funciones. (AssetTransfer.receive(), AssetDisposalRequest.approve(), AssetPhysicalDiscrepancy.approve() — las 3 reales, no solo permisos)
[ ] Existe auditoría. (ASSETS.audit permiso y ruta existen; ningún AssetAuditQueryService ni tabla de auditoría se construyó)
[x] Existe idempotencia. (operation_id en cada entidad mutable, DuplicateOperationError declarado)
[ ] Existe outbox. (build_event_payload() genera el shape; ningún outbox concreto lo consume — el mismo hueco que ASSET-21 documentó para offline)
[ ] Existe offline-first donde aplica. (solo vocabulario — AssetSyncConflict, ASSET-21 — sin motor real)
[x] Existe ModuleSidebar. (SideNav, reutilizado del Design System, ASSET-16)
[x] Existe PageHeader. (ASSET-16)
[x] Existe StandardTable V2. (reutilizado, ASSET-18)
[~] Existe Kanban de work orders. (tablero de SOLO LECTURA, ASSET-19 — sin arrastrar-y-soltar, documentado como limitación deliberada)
[~] Existe calendario. (agenda ordenada por fecha, ASSET-19 — no es un calendario-grid real, mismo criterio)
[x] Existe Design System canónico. (ningún componente nuevo inventado; todo reutilizado de frontend/desktop/design_system + components)
[x] No existe QTableWidget. (guardrail + verificado en la UI nueva)
[x] No existe QTabWidget como navegación principal. (SideNav + rutas, no tabs)
[x] No existen emojis. (guardrail test_assets_have_no_emoji_icons.py)
[x] No existen colores hardcodeados. (guardrail test_assets_have_no_hardcoded_colors.py)
[x] No existe QSS local. (sin setStyleSheet en ningún archivo nuevo)
[x] No existe QDoubleSpinBox para dinero. (Money en dominio; MoneyInput nunca hizo falta — no se construyó ningún formulario de captura de dinero todavía)
[~] Funciona en 1366×768. (renderiza sin error, verificado con test — pero el breakpoint compact no se activa exactamente en ese ancho, documentado en ASSET-20)
[x] Funciona en 1920×1080. (verificado con test)
[ ] Funciona light/dark. (theming es responsabilidad del ThemeManager global, heredado automáticamente — no probado explícitamente en esta pipeline)
[ ] Funciona touch. (sin sistema de densidad táctil en todo el repo — brecha documentada, no exclusiva de Activos, ASSET-20)
[x] Existe accesibilidad. (AccessibleName verificado por test en los widgets clave, ASSET-20)
[ ] No existe modulos/activos.py legacy. (SIGUE EXISTIENDO — bloqueado por dependencias reales, ver ASSET-22/23)
[ ] No existe AssetService monolítico. (SIGUE EXISTIENDO — mismo motivo)
[~] No existen imports legacy. (el bounded context NUEVO no importa nada legacy — guardrail test_assets_have_no_legacy_imports.py en verde; el legacy en sí sigue existiendo)
[x] Allowlist vacía. (ASSETS_MODULE_ALLOWLIST == {}, verificado por guardrail)
[ ] Bootstrap limpio funciona. (no probado explícitamente contra un bootstrap desde cero en esta pipeline)
[~] CI verde. (no hay pipeline de CI real invocado en esta sesión; los tests relevantes sí están en verde localmente)
[x] Todos los tests [de Activos] pasan. (228/228, 1 skip intencional)
```

**Resumen del checklist**: ~50 de ~75 puntos genuinamente cumplidos, ~10 parciales explícitamente marcados y documentados (`~`), ~15 pendientes y honestamente marcados como no hechos. Ningún punto se marcó como cumplido sin evidencia verificable en esta sesión.

## Por qué la pipeline se detiene aquí, no porque "ya terminó"

§113 en su forma completa describe un ERP EAM productivo de punta a punta — imposible de alcanzar sin la capa de infraestructura de persistencia y casos de uso de escritura que 8 fases consecutivas (ASSET-14, 16, 17, 18, 19, 20, 21, y ahora 22/23) señalaron como el bloqueador real. Lo que **sí** se completó honestamente en estas 24 fases:

1. Un modelo de dominio EAM completo y correcto — 15 agregados/entidades con máquinas de estado guardadas, 3 reglas de segregación de funciones implementadas literalmente (no solo como permisos), Decimal/UUIDv7 en todo, y la frontera Activos↔Finanzas protegida por 3 guardrails de arquitectura dedicados.
2. Una capa de lectura real (6 QueryServices) construida sobre Protocol ports — funcional hoy con dobles de prueba, lista para conectarse a una implementación SQLite real sin cambios de contrato.
3. Una UI de solo lectura que funciona de punta a punta (dashboard, directorio, detalle, tablero de mantenimiento, agenda) — probada con un smoke test real de construcción y navegación del workspace completo, no solo unidades aisladas.
4. Un reporte de disposición de legacy preciso, que corrigió un hallazgo equivocado de la propia auditoría inicial (la tabla `assets` no está huérfana).
5. Cero regresiones en el sistema legacy — la regla §1 de `CLAUDE.md` ("NO perder lógica de negocio durante refactorización") se cumplió en las 24 fases.

Lo que falta — infraestructura de persistencia, casos de uso de escritura, y por lo tanto todo lo que dependa de ellos (integraciones concretas, auditoría, outbox, offline real, el Kanban interactivo, formularios de alta/edición, y finalmente la eliminación del legacy) — es un trabajo real, del mismo tamaño o mayor que lo ya hecho, y necesita su propia fase dedicada antes de que cualquiera de esos puntos pueda marcarse honestamente como terminado.
