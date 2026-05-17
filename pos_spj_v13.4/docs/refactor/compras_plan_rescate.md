# PLAN DE RESCATE — Módulo Compras Pro
> Generado: 2026-05-17 | Basado en: PROMPT MAESTRO ESTRICTO

---

## Objetivo

Transformar `ModuloComprasPro` de un módulo PyQt5 con lógica de negocio embebida en UI a un módulo de presentación puro que delegue al dominio/aplicación, sin perder ninguna funcionalidad operativa.

---

## Restricciones absolutas (activas en TODAS las fases)

| # | Prohibición |
|---|-------------|
| P1 | NO tocar lógica QR (`recepcion_qr_widget.py` motor existente) |
| P2 | NO modificar RecepcionQRWidget tabs 0-3 (Generar, Asignar, Recepcionar, Historial) |
| P3 | NO cambiar reglas de negocio |
| P4 | NO duplicar lógica de inventario |
| P5 | NO meter SQL nuevo en UI |
| P6 | NO usar colores hardcodeados (solo `Colors.*`, `Typography.*`, `Spacing.*`) |
| P7 | NO usar `background:white` ni `background:#ffffff` en widgets principales |
| P8 | NO usar `Colors.NEUTRAL.SLATE_50` como fondo fijo en Compra Tradicional |
| P9 | NO usar `setStyleSheet` manual para colores principales si existe componente estándar |
| P10 | NO agregar 4° tab externo en `ModuloComprasPro` |
| P11 | NO romper atributos de instancia que usa la lógica de negocio (ver compras_auditoria_real.md §5) |
| P12 | NO eliminar el autosave timer (`_autosave_timer`) |
| P13 | NO romper el EventBus refresh mixin |
| P14 | NO cambiar la firma de `_procesar_compra()` ni `_procesar_como_pr()` |
| P15 | NO eliminar `_fallback_compra_directa` sin audit trail garantizado |

---

## Fases del plan

### FASE 0 — Auditoría real (✅ COMPLETADA 2026-05-17)

**Entregables:**
- [x] `docs/refactor/compras_auditoria_real.md`
- [x] `docs/refactor/compras_ui_errors.md`
- [x] `docs/refactor/compras_backend_errors.md`
- [x] `docs/refactor/compras_qr_no_touch_policy.md`
- [x] `docs/refactor/compras_po_reception_tab_error.md`
- [x] `docs/refactor/compras_plan_rescate.md`

---

### FASE 1 — Correcciones de arranque + smoke tests (🔄 EN CURSO)

**Objetivo:** El módulo arranca sin errores. Los smoke tests pasan.  
**Regla:** Sin rediseño. Sin cambios de lógica de negocio.

**Correcciones de arranque:**
- [x] Fix `apply_spj_buttons` AttributeError (`fixedSize` → `minimumWidth`)
- [x] Fix C++ deleted object en `_refresh_stepper` (guardar referencia `_hidden_stepper`)
- [x] Fix C++ deleted object en doctype toolbar (guardar referencia `_hidden_doctype_toolbar`)

**Tests a crear:**
- [ ] `tests/purchases/test_compras_module_imports.py`
- [ ] `tests/purchases/test_compras_tabs_contract.py`
- [ ] `tests/purchases/test_qr_no_extra_po_tab.py`
- [ ] `tests/purchases/test_traditional_purchase_smoke.py`

**Criterio de éxito:** Todos los smoke tests pasan. Baseline de tests no regresa (≤ 88 failing).

---

### FASE 2 — Eliminar tab PO externo incorrecto (si reaparece) (✅ COMPLETADA 2026-05-17)

**Objetivo:** Garantizar por código y test que nunca haya 4° tab externo.  
**Estado:** El error no existía en el código. Verificación formal completada.

**Hallazgos de la verificación:**
- `compras_pro.py._build_ui()`: exactamente 3 `addTab` (L722, L726, L730) — sin 4ª tab
- `recepcion_qr_widget.py._build_ui()`: exactamente 5 tabs internas — `_tab_po_recv` en lugar correcto
- `_accion_enviar_recepcion_doc` usa `setCurrentIndex(1)` (tab QR) — sin salto a índice 3/4
- `_build_tab_po_recepcion`: implementación completa (no stub) — 50+ líneas de UI real
- Sin TODO/FIXME sobre agregar 4ª tab en compras_pro.py

**Correcciones aplicadas:**
- Renombrado `test_original_4_tabs_still_registered` → `test_original_qr_tabs_still_present` (nombre confuso)
- Agregado `test_phase6_added_fifth_tab_po_recv` — clarifica que hay 5 tabs, no 4
- Agregado `TestTabSwitchIndexes` — verifica que `setCurrentIndex` usa índices 0-2 solamente

---

### FASE 3 — Reconstruir UI Compra Tradicional (3 columnas) (✅ COMPLETADA 2026-05-17)

**Objetivo:** Layout de 3 columnas igual al HTML de referencia.

**Checklist:**
- [x] Columna izquierda (260px): `_build_documental_toolbar()` — fijo `setFixedWidth(260)` ✅
- [x] Columna central (stretch): `_build_center_column()` — proveedor→documento→búsqueda→partidas ✅
- [x] Columna derecha (440px): `_build_summary_panel()` — totales+acción, `minWidth=400` ✅
- [x] QSplitter con `setSizes([260, 500, 440])` y `setStretchFactor(1, 1)` ✅
- [x] KPI bar FUERA de las tabs (en `_build_ui` antes de crear el QTabWidget) ✅
- [x] Sin PROVEEDOR RÁPIDO visible en columna izquierda (está como attrs ocultos) ✅

**Hallazgos:**
- `_build_provider_sidebar()` (L2349) es **dead code** — nunca se llama desde ningún método de layout. Contiene colores prohibidos (SLATE_50, background:white) pero no se renderiza. Documentada con comentario de DEAD CODE; remoción en FASE 10.
- Widgets backward-compat (`_sidebar_prov_search`, `_sidebar_prov_list`, `_sidebar_templates_list`, `_sidebar_recent_list`) están correctamente ocultos en `_build_documental_toolbar()`.
- `_hidden_doctype_toolbar` y `_hidden_stepper` están correctamente guardados en `_build_center_column()`.

**Cambios de código:**
- Docstring de `_build_provider_sidebar()` actualizado a "DEAD CODE — never added to any layout"

**Tests creados (46 nuevos, todos en verde):**
- `tests/purchases/test_fase3_layout_contract.py`

---

### FASE 4 — Tema Dark/Light sin fondos hardcodeados (✅ COMPLETADA 2026-05-17)

**Objetivo:** El módulo es 100% compatible con Dark y Light theme.

**Correcciones aplicadas:**
- [x] L815 QSplitter handle: `rgba(0,0,0,0.08)` → `rgba(148,163,184,0.25)` (visible en dark mode)
- [x] L4201 `_hist_timeline_bar`: `SLATE_50` → `transparent`
- [x] L4368 `_build_hist_kpi_sidebar`: `SLATE_50` → `transparent`
- [x] L2359 dead code `_build_provider_sidebar`: `SLATE_50` → `transparent` (preventivo)
- [x] L2386 dead code `_build_provider_sidebar`: `background:white` → eliminado de QListWidget style
- [x] L4984 `_generar_html_compra`: `Colors.NEUTRAL.SLATE_50/.WHITE` → literales `"#f8fafc"/"#ffffff"`
  **Decisión documentada:** HTML de impresión es EXEMPT — CSS de tema no aplica a QPrinter output

**Tests creados (63 tests, todos en verde):**
- `tests/purchases/test_fase4_dark_light_theme.py`
  - `TestHistorialTabTheme`: verifica `transparent` en `_hist_timeline_bar`
  - `TestHistKPISidebarTheme`: verifica `transparent` en KPI sidebar
  - `TestSplitterHandleVisibility`: verifica rgba visible en dark mode
  - `TestPrintHTMLExemption`: verifica que HTML print usa literales (no tokens)
  - `TestNoSLATE50InActiveWidgets`: 17 métodos × parametrize
  - `TestNoBackgroundWhiteInActiveWidgets`: 17 métodos × parametrize
  - `TestNoNeutralWhiteBackgroundInWidgets`: 17 métodos × parametrize
  - `TestDeadCodeColorStatus`: dead code es dead y está documentado

---

### FASE 5 — Estabilizar compra directa (DIRECT) (✅ COMPLETADA 2026-05-17)

**Objetivo:** El flujo DIRECT completo funciona sin errores.

**Checklist:**
- [x] `_procesar_compra()` delega a `RegistrarCompraUC` para DIRECT — verificado por AST
- [x] `RegistrarCompraUC.execute()` valida carrito vacío, qty <= 0, costo negativo
- [x] Flujo feliz: folio generado, purchase header guardado, inventario actualizado
- [x] Pago CREDITO marca estado "credito" en DB
- [x] Múltiples ítems correctamente guardados en `detalles_compra`
- [x] `PurchaseRepository` round-trip (create/read items, save/load/delete draft)
- [x] Auto-save timer (`_autosave_timer`) inicializado con 45 000 ms en `__init__`
- [x] `_build_draft_dict` / `_restore_draft_dict` / `_auto_save_draft` tienen la estructura correcta
- [x] `_fallback_compra_directa` NO se llama desde el flujo principal (P15 cumplido)
- [x] Audit trail: `RegistrarCompraUC._escribir_auditoria()` → `audit_write()` en flujo feliz

**Hallazgo documentado — ERROR-BE-09 (gap conocido):**
- `_fallback_compra_directa` NO escribe audit trail (`financial_event_log`). Permanece como safety
  net (P15 prohíbe eliminarla sin garantizar el audit trail). Fix pendiente FASE 10.

**Hallazgo documentado — SAVEPOINT partial-commit:**
- Cuando `inventory.add_stock` falla, `PurchaseService` hace `RELEASE SAVEPOINT` (commit) antes de
  lanzar RuntimeError → el header de compra queda en DB pero el inventario NO se actualiza.
  Debería ser `ROLLBACK TO SAVEPOINT`. Documentado en tests como comportamiento actual conocido.
  Fix pendiente en fase futura (fuera del scope de FASE 5).

**Tests creados (53 nuevos, todos en verde):**
- `tests/purchases/test_fase5_direct_purchase_flow.py`
  - `TestRegistrarCompraUCValidation`: 4 tests — validaciones de entrada
  - `TestRegistrarCompraUCHappyPath`: 6 tests — flujo feliz con SQLite in-memory
  - `TestPurchaseRepositoryRoundTrip`: 4 tests — create/read/cancel
  - `TestDraftRepositoryRoundTrip`: 4 tests — save/load/delete/upsert draft
  - `TestProcesarCompraRouting`: 9 tests — AST routing DIRECT/PR/PO
  - `TestDraftDictStructure`: 13 tests — estructura de métodos de borrador
  - `TestAutoSaveTimer`: 4 tests — timer inicializado en __init__
  - `TestFallbackAuditTrailGap`: 5 tests — documenta gap ERROR-BE-09
  - `TestPurchaseServiceSavepoint`: 3 tests — SAVEPOINT rollback y partial-commit

---

### FASE 6 — Separar rutas doctypes (DIRECT / PR / PO) (✅ COMPLETADA 2026-05-17)

**Objetivo:** Al cambiar `_doc_type`, la UI adapta campos y acciones correctamente.

**Checklist:**
- [x] DIRECT: sin stepper, botón "✓ Autorizar compra" en SUCCESS (verde) ✅
- [x] PR: stepper visible, botón "📋 Crear solicitud" en PRIMARY (azul) ✅
- [x] PO: stepper visible, botón "📦 Ver instrucciones" en WARNING (ámbar) ✅
- [x] `_doctype_buttons` resalta el tipo activo (`_apply_doctype_button_styles`) ✅
- [x] Al cambiar tipo, `_refresh_doctype_ui()` adapta badge, botón, stepper y hint ✅
- [x] Hint text actualiza según el tipo (`self._lbl_hint`) ✅

**Cambios de código:**
- `_build_center_column()`: doctype toolbar y stepper promovidos a layout visible (FASE 3 los tenía ocultos como transición)
- `_build_dynamic_action_button()`: `hint` local → `self._lbl_hint` (atributo de instancia)
- `_refresh_doctype_ui()`: extendido con `btn_color`, `btn_hover`, `show_stepper`, `hint_txt` por doc type
- `_build_tab_tradicional()`: llama `_refresh_doctype_ui()` después de construir todos los paneles

**Tests actualizados:**
- `test_fase3_layout_contract.py`: `test_hidden_doctype_toolbar_is_hidden` → `test_doctype_toolbar_added_to_layout` (refleja nuevo comportamiento FASE 6)

**Tests creados (42 nuevos, todos en verde):**
- `tests/purchases/test_fase6_doctype_ui.py`
  - `TestDoctypeToolbarVisible`: toolbar en layout, no oculto sin condición
  - `TestStepperInCenterColumn`: stepper en layout, oculto inicial, visibilidad via refresh
  - `TestRefreshDoctypeUICompleteness`: 3 doc types + fallback DIRECT
  - `TestButtonColorPerDoctype`: SUCCESS/PRIMARY/WARNING + setStyleSheet en btn_autorizar
  - `TestStepperVisibilityConfig`: show_stepper True para PR/PO, False para DIRECT
  - `TestHintLabelAsAttr`: _lbl_hint como atributo, añadido al layout, actualizado en refresh
  - `TestRefreshCalledOnBuild`: _refresh_doctype_ui() llamado DESPUÉS de _build_summary_panel()
  - `TestDoctypeButtonsHighlight`: _apply_doctype_button_styles, _on_doctype_changed wiring
  - `TestNoBannedColorsInFase6Methods`: 12 parametrize (6 métodos × 2 bans)

---

### FASE 7 — PR / Aprobación / PO en Compra Tradicional (✅ COMPLETADA 2026-05-17)

**Objetivo:** Flujo documental completo PR → APROBACIÓN → PO desde la UI.

**Checklist:**
- [x] Sidebar izquierda lista PRs pendientes (`_build_documental_toolbar()` + `_cargar_docs_erp()`)
- [x] Botón "Aprobar PR" funciona → estado cambia → sidebar actualiza (`_accion_aprobar_pr()` → `PurchaseRequestUC.aprobar()`)
- [x] Botón "Convertir a PO" funciona → PO creada → aparece en lista PO (`_accion_convertir_a_po()` → `PurchaseRequestUC.convertir_a_po()`)
- [x] Stepper refleja paso actual del documento seleccionado (`_refresh_stepper_for_doc()` wired to `_on_doc_item_clicked()`)
- [x] No hay SQL directo en ninguno de estos flujos (verificado AST)

**Tests:**
- [x] `tests/purchases/test_fase7_documental_sidebar.py` — 65 tests, todos pasando
  - TestDocumentalSidebarStructure (10)
  - TestCargarDocsERPPattern (5)
  - TestActionMethodsDelegation (9)
  - TestRefreshStepperForDoc (8)
  - TestOnDocItemClickedWiring (5)
  - TestPurchaseRequestUCStateMachine (9)
  - TestConvertirAPO (5)
  - TestNoPrimarySQL (6)
  - TestNoBannedColorsInFase7Methods (7)

**Baseline tras FASE 7:** 88 failed / 1606 passed (+65 nuevos tests)

**Notas:**
- `_refresh_stepper_for_doc()` guarda contra stepper invisible (DIRECT mode); solo actualiza cuando `_hidden_stepper.isVisible()`
- Mapa estado→paso: BORRADOR=0, PENDIENTE_APROBACION=2, APROBADA=3, estados PO=3
- Test `TestNoPrimarySQL` usa regex `\bSELECT\s+\w` para evitar falso positivo en `_selected_doc_id`
- Schema `ordenes_compra` en fixture de tests incluye `subtotal, iva_monto, metodo_pago, condicion_pago, plazo_dias, moneda, notas, doc_ref, fecha_entrega_esperada` (alineado con `purchase_order_repository.py`)

---

### FASE 8 — Recepción QR puede manejar PO (✅ COMPLETADA 2026-05-17)

**Objetivo:** El tab `_tab_po_recv` (ya existente en RecepcionQRWidget) recibe artículos de una PO y actualiza el estado de la PO en el sidebar documental de ModuloComprasPro.

**Checklist:**
- [x] `ReceivePOAdapter.register_partial_receipt()` emite `RECEPCION_CONFIRMADA` con `source="PO"` — ya existía, verificado con test de integración
- [x] `ModuloComprasPro._on_refresh()` detecta `RECEPCION_CONFIRMADA` + `source="PO"` → llama `QTimer.singleShot(50, self._cargar_docs_erp)` 
- [x] Estado PO cambia a "PARCIAL" o "RECIBIDA" en la lista documental (via `po_repo.update_estado()` en ReceivePOAdapter)

**Decisiones de diseño:**
- Evento ya existía: `ReceivePOAdapter` ya publicaba `RECEPCION_CONFIRMADA` con `source="PO"` desde la fase anterior. Solo faltaba el branch en `_on_refresh()`.
- No se creó un nuevo tipo de evento `PO_RECIBIDA_PARCIAL` — se reutilizó `RECEPCION_CONFIRMADA` con `source="PO"` para no duplicar la tabla de eventos del EventBus.
- `QTimer.singleShot(50ms)` en lugar de 0ms — 50ms garantiza que los writes de `register_partial_receipt()` ya están visibles en SQLite cuando el sidebar carga los datos.
- Zero cambios a `recepcion_qr_widget.py` — la lógica QR no fue tocada.

**Tests:**
- [x] `tests/purchases/test_fase8_po_reception_event.py` — 31 tests, todos pasando
  - TestOnRefreshHandlesPOEvent (8): verifica el nuevo branch en `_on_refresh`
  - TestOnRefreshIgnoresNonPOEvents (1): sidebar no refresca en eventos no-PO
  - TestPublishRecepcionPayload (6): payload incluye `source="PO"`, `po_id`, `completion`
  - TestReceivePOAdapterStateTransitions (10): ABIERTA→PARCIAL/RECIBIDA, acumulación, guardas
  - TestNoDuplicateInventoryInOnRefresh (4): `_on_refresh` no duplica `add_stock`/`register_purchase`/lotes/CXP
  - TestNoBannedColorsInFase8Methods (2): no colores hardcodeados

**Baseline tras FASE 8:** 88 failed / 1637 passed (+31 nuevos tests, 0 regresiones)

---

### FASE 9 — Historial documental completo (✅ COMPLETADA 2026-05-17)

**Objetivo:** El tab Historial muestra el ciclo de vida completo de cada compra.

**Checklist:**
- [x] Timeline: PR → APROBACIÓN → PO → RECEPCIÓN → CXP — nodos completos con estado visual
- [x] Filtros por estado, tipo_doc, po_estado y rango de fechas — ya existían; búsqueda cubre proveedor
- [x] KPI sidebar actualizado — `_actualizar_hist_kpi_sidebar()` llamada desde `_poblar_historial()`
- [x] Export CSV funciona — `_exportar_historial_csv()` con filtros activos, conectada al botón
- [x] `_refresh_hist_timeline()` usa repositorio (no SQL directo) — eliminados los dos fallbacks SQL

**Cambios en `_refresh_hist_timeline()`:**
- Eliminados SQL fallback para PO (`db.execute("SELECT folio, estado, pr_id FROM ordenes_compra")`)
- Eliminado SQL fallback para PR (`db.execute("SELECT folio FROM purchase_requests")`)
- Repos: `purchase_order_repo.get_by_id()` y `purchase_request_repo.get_by_id()`
- Degradación graceful: si repo no disponible → muestra nodo mínimo PO-{id}
- Colores: eliminados `#EFF6FF`, `#F0FDF4`, `#BFDBFE`, `#BBF7D0` hardcodeados → `Colors.SUCCESS_BASE`, `Colors.PRIMARY_BASE`, `Colors.NEUTRAL.SLATE_*`
- Nodos extendidos: PR (con estado) → APROBACIÓN (si `aprobado_por` presente) → PO (con estado) → RECEPCIÓN (PARCIAL/RECIBIDA/pendiente) → Compra → CXP (pendiente indicador)
- `done` boolean controla estilo: ✅ success verde, 🔵 primary azul (activo), ⬜ slate (pendiente)

**Decisiones de diseño:**
- "Filtro proveedor": no se agregó combo específico — el campo de búsqueda ya filtra por nombre de proveedor (cubriendo el caso de uso sin complejidad extra)
- CXP/PAGADA: nodo CXP mostrado como indicador de ciclo (no data-driven) — sin consulta a repo CXP para evitar dependencia inexistente. PAGADA se omite hasta FASE 10 cuando se confirme si existe repo de pagos.
- PO ABIERTA/PARCIAL → nodo Recepción en estado `active` (azul). PO RECIBIDA/CERRADA → `done` (verde).

**Tests:**
- [x] `tests/purchases/test_fase9_historial_documental.py` — 55 tests, todos pasando
  - TestTimelineNoSQL (8): sin db.execute, sin fetchone, repos via getattr
  - TestTimelineNodesPresent (8): PR, APROBACIÓN, PO, RECEPCIÓN, CXP, COMPRA, PARCIAL, RECIBIDA
  - TestTimelineNoHardcodedColors (7): sin #EFF6FF/#F0FDF4/#BFDBFE/#BBF7D0, usa Colors.*
  - TestKPISidebarWiring (7): kpi sidebar llamada desde poblar, atributos existentes
  - TestExportCSV (8): cache, headers (Folio/Proveedor/Estado/TipoDoc/EstadoPO), filtros, csv.writer
  - TestHistFilterBar (6): estado/tipo_doc/po_estado/fechas/csv/kpi presentes
  - TestNoBannedColorsInFase9Methods (6): no background:white ni SLATE_50 como fondo
  - TestHistorialLoaderPattern (4): loader asíncrono, sin SQL inline, conecta a poblar

**Baseline tras FASE 9:** 88 failed / 1692 passed (+55 nuevos, 0 regresiones)

---

### FASE 10 — Tests, limpieza, documentación final

**Objetivo:** El módulo está listo para producción.

**Checklist:**
- [ ] Suite de tests completa pasa (≥ 1239 passed, ≤ 88 failed baseline)
- [ ] No hay SQL directo en capa UI
- [ ] No hay `background:white` ni `SLATE_50` como fondo principal
- [ ] `_fallback_compra_directa` tiene audit trail o está eliminada
- [ ] MIGRATION_LOG.md actualizado
- [ ] Este plan marcado como COMPLETADO

---

## Secuencia de commits esperada

```
fase-1: test(purchases): add smoke tests for module startup
fase-1: fix(compras): correct stepper guard for DIRECT doc_type
fase-3: refactor(compras): validate 3-column layout renders correctly
fase-4: fix(compras): remove hardcoded SLATE_50/white backgrounds
fase-5: test(purchases): add integration test for direct purchase flow
fase-6: feat(compras): connect doctype buttons to UI refresh
fase-7: feat(compras): implement PR approval and PO conversion in sidebar
fase-8: feat(compras): link PO reception events to sidebar update
fase-9: feat(compras): complete documental timeline in historial tab
fase-10: test(purchases): full regression suite + cleanup
```

---

## Métricas de éxito

| Métrica | Baseline | Objetivo Fase 10 |
|---------|----------|------------------|
| Tests passing | 1239 | ≥ 1239 |
| Tests failing (pre-existentes) | 88 | ≤ 88 |
| SQL directo en compras_pro.py UI | ~9 métodos | 0 |
| Colores hardcodeados (white/SLATE_50) | 5 líneas | 0 |
| Tabs externas | 3 ✅ | 3 |
| Fallback con audit trail | ❌ | ✅ |
