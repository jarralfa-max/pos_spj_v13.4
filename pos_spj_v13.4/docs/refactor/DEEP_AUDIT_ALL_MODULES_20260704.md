# DEEP AUDIT — TODOS LOS MÓDULOS · pos_spj v13.4

**Fecha:** 2026-07-04 · **Rama:** `claude/pos-spj-audit-9v5b8g` · **HEAD:** `734baf0`
**Alcance:** repositorio completo (ERP desktop + `whatsapp_service/` + `api/` + `webapp/` + migraciones + tests)
**Contrato auditado:** `docs/skills/SPJ_REFACTOR_SKILL.md` (Plan B born-clean UUIDv7), `AGENTS.md`, `docs/architecture/REFACTOR_RULES.md`, `docs/architecture/EVENT_CATALOG.md`, `docs/refactor/modules/cierre_global.md`, `docs/runbooks/dev_db_reset.md`.

> Solo auditoría. No se aplicó ningún parche. Cada hallazgo tiene archivo:línea.

---

## 1. Resumen ejecutivo

El **schema nace limpio** (verificado en DB temporal: 0 PK enteras, 0 AUTOINCREMENT, 0 `DEFAULT 1` en FKs, `PRAGMA foreign_key_check` vacío, 272 tablas) y los guardrails `test_clean_birth_guardrails.py` pasan 41/41. **Ese es el único frente realmente cerrado.**

El resto del sistema **NO cumple** `SPJ_REFACTOR_SKILL.md`:

1. **El plano de eventos está roto en los flujos de dinero.** El handler financiero de rifas tiene un `TypeError` silencioso que impide TODO asiento de rifas (`wiring.py:102`). Los eventos de Caja existen en **dos vocabularios paralelos** (`CAJA_*` y `CASH_*`) y **ninguno tiene un solo suscriptor**. La capa de trazabilidad financiera (migración 083) está suscrita a 6 canales lowercase que **nadie emite jamás**. El puente WhatsApp↔ERP escucha canales que solo se publican **en otro proceso** (no hay broker).
2. **Hay dos fuentes de verdad de stock activas**: `inventory_stock` (canónica) y `productos.existencia`, con **≥10 escritores legacy vivos**, incluyendo el repositorio "limpio" `backend/.../compras_write_repository.py`.
3. **La identidad UUIDv7 está rota en los bordes**: `SessionContext` mantiene identidad dual int/str; la API FastAPI usa `lastrowid` como identidad y contratos `int` en todos los routers; el microservicio WhatsApp usa contratos `int` de punta a punta y aún hace `int(product.get("id"))`; hay `sucursal_id=1` en ~40 sitios de código activo y un `addItem("Principal", 1)` literal en recepción QR.
4. **Los KPIs no son event-driven**: BI v2 escucha 3 eventos que nadie emite; Caja solo refresca con `VENTA_COMPLETADA`; el dashboard y badges viven de timers de 7–60 s.
5. **La UI sigue ejecutando SQL y commits**: 81 lecturas, 47 escrituras y 57 `commit()` directos en 17 archivos de `modulos/`+`ui/`+`interfaz/`, congelados en allowlists que no decrecen. 6 diálogos ejecutan SQL/commit/impresión.
6. **La suite de tests no protege**: a HEAD, con PyQt5 instalado, fallan **26 tests unit y 110 integration**; varios fallan porque **exigen IDs enteros** (contradicen el Plan B) o esperan columnas ya eliminadas (`sucursal_uuid`). `refactor_state.json` declara módulos "DONE" que el propio test de control marca incompletos. La afirmación de CLAUDE.md ("575+ tests pasando") es falsa hoy.

**Veredicto: el sistema NO cumple `SPJ_REFACTOR_SKILL.md`.** Cumple el criterio de schema born-clean, pero incumple: eventos con `operation_id` consumidos end-to-end, cero SQL/commit en UI, cero contratos int, cero fallbacks `1`/`Principal`, cero DDL runtime fuera de migrations, KPIs event-driven y tests verdes.

---

## 2. Estado real vs `SPJ_REFACTOR_SKILL.md`

| Regla del skill | Estado | Evidencia |
|---|---|---|
| REGLA CERO — UUIDv7 única identidad en schema | 🟢 CUMPLE (schema) | DB temporal: `find_integer_pks == {}`, 0 AUTOINCREMENT (sección 19) |
| REGLA CERO — sin `int(..._id)` en runtime | 🔴 NO | `whatsapp_service/ai/catalog_entity_extractor.py:52`, `whatsapp_service/flows/cotizacion_flow.py:221-244`, `integrations/delivery_pwa/pwa_server.py:105` |
| REGLA CERO — sin `lastrowid` como identidad | 🔴 NO | `api/routers/cotizaciones.py:68,149`, `api/routers/pedidos.py:57`, `api/routers/anticipos.py:63`, `integrations/pos_adapter.py:117,167,214,380`, `integrations/cfdi/cfdi_service.py:238`, `infrastructure/persistence/base.py:40-42` |
| REGLA CERO — sin contratos `int` para IDs | 🔴 NO | Todos los routers de `api/routers/*` (§10), `whatsapp_service/erp/bridge.py:49-102`, `core/session_context.py:38,48,64,119`, `modulos/ventas.py:1319` |
| Sin `sucursal_id=1` / fallback `Principal` | 🔴 NO | `core/events/wiring.py` ×20, `modulos/produccion.py:102,106`, `modulos/recepcion_qr_widget.py:2237`, `core/services/order_badge_service.py:72`, `whatsapp_service/parser/product_matcher.py:37` (§15) |
| Regla 8/9 — PyQt sin SQL ni commit | 🔴 NO | 81 SELECT / 47 write / 57 commit en 17 archivos UI (§11) |
| Regla 10/11 — DDL solo en migrations | 🔴 NO | `integrations/cfdi/cfdi_service.py:164` (AUTOINCREMENT runtime), `integrations/delivery_pwa/pwa_server.py:123` (INTEGER PK runtime) |
| Regla 15 — no pasar `AppContainer` completo | 🔴 NO | `core/app_container.py:537-540` (`TraditionalPurchaseUC(self)`, `PurchaseRequestUC(self)`, `PurchaseOrderUC(self)`, `ReceivePOAdapter(self)`) |
| Regla 17 — mutaciones críticas emiten evento consumido | 🔴 NO | Caja emite a canales sin suscriptores; CxC/CxP no emiten; trazabilidad 083 muerta (§7) |
| Regla 18 — módulos interconectados | 🟡 PARCIAL | Ventas→inventario/finanzas OK vía `SALE_ITEMS_PROCESS`; caja, BI, CxC/CxP, WA desconectados (§7, §9) |
| Cero código muerto / duplicación | 🔴 NO | 3 servicios de caja, 2 de inventario, 4 rutas de venta, 2 vocabularios de eventos (§14) |
| Tests protegen y bloquean deuda | 🔴 NO | 26 unit + 110 integration FAILED; tests exigen ints; allowlists congeladas (§18) |
| Checklist "módulo terminado" | 🔴 NO | `test_done_modules_are_complete` FALLA para MERMA, PRODUCTOS, VENTAS, … |

**No se puede declarar cumplimiento.** Deuda abierta en 11 de 13 frentes.

---

## 3. Top bugs críticos (ordenados por severidad)

| # | Sev | Bug | Evidencia | Efecto |
|---|-----|-----|-----------|--------|
| B1 | ⚫ | `raffle_id = str(...)` comparado con `<= 0` → `TypeError` capturado por `except` genérico | `core/events/wiring.py:101-102` | **Ningún asiento financiero de rifas se registra jamás** (reserva de presupuesto, entrega de premio, liberación). Pasivo de fidelización subestimado en silencio |
| B2 | ⚫ | Eventos de caja sin un solo suscriptor, en dos vocabularios (`CAJA_TURNO_ABIERTO/CAJA_MOVIMIENTO/CAJA_CORTE_Z_GENERADO/CAJA_DIFERENCIA_DETECTADA` y `CASH_SHIFT_OPENED/CASH_MOVEMENT_RECORDED/CASH_Z_CUT_GENERATED/CASH_DIFFERENCE_DETECTED`) | emisores: `application/services/caja_application_service.py:100,136,506,515,524` y `backend/application/services/cash_register_application_service.py:51,73,97,104`; 0 `subscribe` en todo el repo | Cortes Z, movimientos y diferencias de caja **no llegan a finanzas, dashboard ni auditoría por evento** |
| B3 | ⚫ | Capa de trazabilidad financiera (mig 083) suscrita a canales que nadie emite: `payment_confirmed`, `waste_recorded`, `delivery_payment_confirmed`, `driver_settlement_created` (lowercase), `maintenance_registered`, `operating_supply_purchased` | `core/events/wiring.py:1384-1391` vs grep global sin emisores | `financial_documents` / `financial_trace_log` no se alimentan para pagos, mermas, delivery, mantenimiento ni insumos |
| B4 | ⚫ | Doble fuente de verdad de stock: escritores activos sobre `productos.existencia` conviven con `inventory_stock` | `backend/infrastructure/db/repositories/compras_write_repository.py:86,105`, `core/services/distribution_engine.py:401,563,583`, `core/services/lote_service.py:53`, `services/qr_service.py:116`, `integrations/pos_adapter.py:137`, `core/services/inventory/unified_inventory_service.py:134,216`, `modulos/recepcion_qr_widget.py:1981` | Stocks divergentes según el flujo que escriba; lecturas UI mezclan ambas fuentes (`interfaz/main_window.py:1367`, `core/app_container.py:755-757` leen `existencia`) |
| B5 | 🔴 | Mismatch de canal WA↔ERP: wiring escucha literales `"SALE_CREATED"`, `"PAYMENT_RECEIVED"` (UPPERCASE); tesorería publica `payment_received` (lowercase, `domain_events`); el microservicio WA publica en el bus de **su propio proceso** | `core/events/wiring.py:737-741,844-848`, `core/services/finance/third_party_service.py:391-392`, `whatsapp_service/erp/events.py:83` | Auditoría/tesorería/BI de eventos WA muertos en el desktop; no existe cola/broker inter-proceso |
| B6 | 🔴 | BI v2 se refresca con eventos inexistentes: `venta_confirmada`, `stock_actualizado`, `pago_registrado` — sin emisor en el repo | `modulos/reportes_bi_v2.py:837` | Dashboard BI **solo** se actualiza al abrir el módulo o pulsar refresh; nunca en caliente |
| B7 | 🔴 | Inbox POS del login usa `SELECT id FROM personal WHERE activo=1 LIMIT 1` — ignora al usuario logueado | `interfaz/main_window.py:1052-1054,1085-1087` | Muestra y **marca como leídas** notificaciones de otro empleado |
| B8 | 🔴 | Arranque de badges/inbox mal ubicado: `QTimer.singleShot(800, self._mostrar_inbox_login)` y `_start_badge_refresh` están al final de `aplicar_sucursal_activa()` (re-anclaje de sucursal), no de `_propagar_usuario()` (login) | `interfaz/main_window.py:933-935` | Tras un login normal el timer de badges y el inbox **no arrancan**; solo si Configuración re-ancla sucursal |
| B9 | 🔴 | `QMetaObject.invokeMethod(self, "_on_pedido_nuevo", ...)` sobre un método sin `@pyqtSlot` → falla silenciosa | `interfaz/main_window.py:1127-1136` | El badge de pedidos NO reacciona al evento `PEDIDO_NUEVO`; solo el polling de 7 s / 30 s |
| B10 | 🔴 | `finanzas_unificadas` escucha `CXP_CREADA`/`CXC_CREADA` pero los servicios de CxC/CxP **no publican** (solo pasan `evento=` como metadata del asiento) | `modulos/finanzas_unificadas.py:3308-3309` vs `core/services/finance/accounts_receivable_service.py:144`, `accounts_payable_service.py:155` | Las pestañas CxC/CxP no se refrescan al crear cuentas |
| B11 | 🔴 | API REST viola Plan B: `lastrowid` como identidad + contratos `int` + `sucursal_id: int = 1` | `api/routers/cotizaciones.py:68,149`, `api/routers/pedidos.py:57,81`, `api/routers/anticipos.py:63`, `api/routers/ventas.py:16,105`, `api/routers/inventario.py:57` | La futura webapp/integraciones nacen con identidad entera y rutas duales |
| B12 | 🔴 | WhatsApp: `int(product.get("id", 0) or 0)` vivo + protocolo bridge 100 % `int` + `sucursal_id: int = 1` | `whatsapp_service/ai/catalog_entity_extractor.py:52`, `whatsapp_service/erp/bridge.py:49-102`, `whatsapp_service/parser/product_matcher.py:37` | Con UUIDs reales, el extractor lanza `ValueError` (capturado) → productos no matcheados; contratos int en todo el flujo conversacional |
| B13 | 🔴 | `Principal`/`1` hardcodeado en recepción QR: `self._cmb_sucursal_destino.addItem("Principal", 1)` | `modulos/recepcion_qr_widget.py:2237` | Recepciones QR pueden caer en una sucursal inexistente `1` |
| B14 | 🔴 | Producción ancla identidad a `1`: `self.sucursal_id = 1` y `RecipeEngine(self._db_wrapped, branch_id=1)` | `modulos/produccion.py:102,106` | Producción registra movimientos en la sucursal `1` (int) hasta que `set_sucursal` llegue — y los handlers de wiring crean `UnifiedInventoryService(conn=db, sucursal_id=1)` (`wiring.py:997,1098`) |
| B15 | 🔴 | DDL runtime que reintroduce schema legacy: `facturas_cfdi` con `INTEGER PRIMARY KEY AUTOINCREMENT` + `venta_id INTEGER`, y `driver_locations` con `chofer_id INTEGER PRIMARY KEY` | `integrations/cfdi/cfdi_service.py:164-167`, `integrations/delivery_pwa/pwa_server.py:123-125` | El primer CFDI o el primer ping del PWA **contamina la DB born-clean** |
| B16 | 🟡 | `INVENTARIO_ACTUALIZADO` (documentado como "evento canónico publicado por TODOS los escritores") no es escuchado por Inventario | emisores: `unified_inventory_service.py:386`, `modulos/produccion.py:619`; suscriptores: solo `modulos/produccion.py:150` — `modulos/inventario_local.py:618-623` no lo incluye | Inventario no se refresca tras producción ni tras movimientos del unified service |
| B17 | 🟡 | Handlers del bus hacen `db.commit()` sobre la conexión compartida del container (audit, loyalty audit) | `core/events/wiring.py:386,486,616,714,760`, etc. | Un handler post-commit puede confirmar transacciones a medio abrir de otro flujo que comparta la conexión |
| B18 | 🟡 | Dashboard escucha `STOCK_BAJO_MINIMO` pero solo delivery lo emite | emisor único: `core/events/handlers/delivery_handler.py:660`; ventas/ajustes/compras no lo publican | Alertas de stock bajo no se disparan desde los flujos principales |

---

## 4. Top deudas arquitectónicas

| # | Deuda | Detalle |
|---|-------|---------|
| D1 | **Tres capas de caja en paralelo** | `application/services/caja_application_service.py` (SQL directo, eventos `CAJA_*`), `backend/application/services/cash_register_application_service.py` (use cases FASE 7.7, eventos `CASH_*`), `core/services/cierre_caja_service.py` (corte Z del scheduler). `repositories/caja.py` además publica `CAJA_MOVIMIENTO` por su cuenta |
| D2 | **Cuatro rutas de venta** | `core/services/sales_service.py` (orquestador real), `core/services/sales/unified_sales_service.py`, `core/services/ventas_facade.py`, `repositories/ventas.py` (publica `VENTA_COMPLETADA` él mismo, línea 256) + `sales_reversal_service` con `_DatabaseShim` propio |
| D3 | **Dos inventarios** | `backend/.../inventory_application_service.py` (canónico) vs `core/services/inventory/unified_inventory_service.py` (usado por handlers de producción/transferencias, escribe `productos.existencia`) |
| D4 | **Dos vocabularios de eventos sin bridge** | `backend/shared/events/event_names.py` (EventName inglés) vs `core/events/event_bus.py` (constantes español) + `core/events/domain_events.py` (aliases y lowercase). El puente existe solo para delivery (`legacy_event_bridge`) |
| D5 | **AppContainer god-object** | 1 132 líneas; construye ~60 servicios; contiene lógica de negocio en el scheduler (escalación WA con UPDATE+commit `app_container.py:826-864`, recordatorios con SQL `871-907`, cierre de turno `1005-1030`) |
| D6 | **Identidad dual en sesión** | `core/session_context.py:38-40`: `_sucursal_id: int` (legacy) + `_active_branch_id: str` (UUID) + fallback `str(int)`; `AppContainer.set_sucursal_activa` pasa UUID str al parámetro tipado int |
| D7 | **`modulos/growth_engine.py` es un servicio de dominio viviendo en la capa UI** | Registrado en el container (`app_container.py:709-714`); 11 escrituras SQL + 12 commits |
| D8 | **Allowlists de deuda congeladas** | `tests/architecture/allowlists.py`: ~300 SQL en UI, ~80 commits en UI, ~90 DDL permitidos. Ningún mecanismo obliga a decrecer |
| D9 | **Shims WhatsApp** (intencionales, preservar) | `services/whatsapp_service.py`, `integrations/whatsapp_service.py` → `core/services/whatsapp_service.py` (26 KB). OK durante transición, pero el microservicio duplica catálogo/carrito |
| D10 | **Polling como sustituto de eventos** | Badges 7 s (`main_window.py:1147`), notificaciones 30 s, dashboard 60 s, KPIs finanzas 15 s (`finanzas_unificadas.py:3317`), delivery timers |

---

## 5. Matriz de módulos auditados

Clasificación: 🟢 cumple · 🟡 deuda · 🔴 violación grave / bug funcional · ⚫ riesgo crítico datos/finanzas/inventario

| Módulo | Archivos principales | Fuente de verdad esperada | Fuente actual | UI c/lógica | SQL UI (R/W/C) | Emite | Escucha | KPIs | Refresh caliente | UUID OK | Riesgo | Prioridad |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Núcleo/Shell | `app_container.py`, `session_context.py`, `main_window.py` | SessionContext + UCs | Container con SQL/commits y lógica scheduler | Sí | 9/0/0 (main_window) | ACTIVE_BRANCH_CHANGED | BRANCHES/PRODUCTS_CHANGED, PEDIDO_NUEVO | badges | Parcial (B8/B9) | 🔴 dual int/str | ⚫ | P0 |
| Ventas/POS | `modulos/ventas.py` (4 800+ líneas), `sales_service.py` | `CreateSaleUseCase` | SalesService OK; UI aún 17 SQL + 2 commit; 4 rutas paralelas | Sí | 17/†/2 | VENTA_COMPLETADA, SALE_ITEMS_PROCESS, venta_suspendida… | ninguno (sin contrato refresh) | stock por botón | 🔴 no refresca productos por evento | 🟡 (`set_sucursal(int)`, lee `existencia`) | ⚫ | P0 |
| Caja | `modulos/caja.py`, 3 servicios (D1) | `CashRegisterApplicationService` | 3 rutas paralelas | Sí | dialogo corte 448 líneas imprime | CAJA_*/CASH_* (huérfanos) | VENTA_COMPLETADA | 5 KPI cards | Solo con ventas | 🟡 | ⚫ B2 | P0 |
| Inventario | `modulos/inventario_local.py`, backend inventory | `inventory_stock` + InventoryApplicationService | Dos motores + dos tablas de stock (B4) | Media | 7/0/0 | AJUSTE_INVENTARIO, INVENTARIO_ACTUALIZADO | 10 eventos (falta INVENTARIO_ACTUALIZADO, TRASPASO_*, MERMA) | stock bajo | Parcial (B16) | 🟢 módulo / 🔴 legacy writers | ⚫ B4 | P0 |
| Productos | `modulos/productos.py`, `repositories/productos.py`, `product_catalog_service` | `CreateProductUseCase` + catalog_events | Ruta canónica emite PRODUCTS_CHANGED 🟢; UI aún 29 SQL + 9 commit | Sí | 29/†/9 | PRODUCTS_CHANGED + granular + legacy | PRODUCTO_*, PRODUCTS_CHANGED | — | 🟢 | 🟢 | 🟡 | P2 |
| Compras | `modulos/compras_pro.py` (5 300+), UCs Phase 2-4 | `TraditionalPurchaseUC`/PO/PR | UC existe; UI 58 SQL + 5 commit; recibe container completo | Sí | 58/†/5 | COMPRA_REGISTRADA, PURCHASE_ITEMS_PROCESS, RECEPCION_CONFIRMADA, CONTENEDOR_* (huérfanos) | 14 eventos + BRANCHES/PRODUCTS_CHANGED 🟢 | pestañas | 🟢 | 🟡 | 🔴 | P1 |
| Recepción QR | `modulos/recepcion_qr_widget.py` | vía UC compras | SQL directo (29) + recalcula `existencia` + `addItem("Principal",1)` | Sí | 29/2/4 | — | — | — | — | 🔴 B13 | ⚫ | P0 |
| Transferencias | `modulos/transferencias.py`, `repositories/transferencias.py` | Dispatch/ReceiveTransferUC | Repo publica dual TRANSFER_*/TRASPASO_*; UI 5 SQL | Media | 5/†/2 | TRANSFER_DISPATCHED/RECEIVED/CANCELLED + TRASPASO_* + TRANSFER_ITEMS_PROCESS | TRANSFER_* 🟢 | tránsito | 🟢 propio; no escucha BRANCHES_CHANGED | 🟡 handler `sucursal_id=1` | 🔴 | P1 |
| Producción/Recetas | `modulos/produccion.py`, RecipeEngine, ProductionEngine | `ExecuteMeatProductionUseCase` | UC existe; UI ancla `sucursal_id=1` (B14) | Sí | †/†/† | PRODUCCION_COMPLETADA/REGISTRADA (huérfano), PRODUCTION_ITEMS/BATCH | PRODUCCION_COMPLETADA, RECETA_*, INVENTARIO_ACTUALIZADO 🟢 | KPIs día | 🟢 propio | 🔴 B14 | ⚫ | P0 |
| Merma | `modulos/merma.py`, WasteApplicationService | RegisterWasteUseCase | 🟢 refactor hecho; adapter publica WASTE_REGISTERED+MERMA_REGISTRADA+AJUSTE_INVENTARIO | Baja | 0/0/0 | WASTE_REGISTERED, MERMA_REGISTRADA, AJUSTE_INVENTARIO | — | — | vía inventario | 🟢 | 🟡 (traza 083 muerta B3) | P2 |
| Clientes/Crédito/CxC | `modulos/clientes.py`, credit services | AccountsReceivableService | 3 servicios de crédito; diálogo con commit+publish | Sí | 16/†/5 | CLIENTE_ACTUALIZADO (UI directa), CLIENTE_CREADO (solo vía UC) | — | — | 🔴 no escucha nada | 🟡 | 🔴 B10 | P1 |
| Fidelización | `loyalty_service.py` (1 200+), tarjetas, growth_engine | LoyaltyApplicationService | Loyalty OK en eventos; growth_engine en modulos/ con 12 commits; rifas B1 | Sí | 33/11/12 (growth) | LOYALTY_*, RAFFLE_* (6 de 9 huérfanos), PUNTOS | LOYALTY_* (finanzas+audit) | — | — | 🟡 | ⚫ B1 | P0 |
| Finanzas/Tesorería | `finanzas_unificadas.py` (3 300+), FinanceService, Treasury, third_party, accounting_engine, trace 083 | FinanceService.registrar_asiento + journal | 5+ ledgers paralelos; trace 083 muerta (B3) | Sí | 20/†/† | MOVIMIENTO_FINANCIERO | VENTA_COMPLETADA, MOVIMIENTO_FINANCIERO, CXP/CXC (muertos), AJUSTE | KPIs 15 s timer | 🟡 timer+eventos parciales | 🟡 | ⚫ B3/B10 | P0 |
| RRHH/Nómina | `modulos/rrhh.py`, rrhh_service, hr_rule_engine, `core/rrhh/*` | GestionarNominaUC + eventos NOMINA_* | 🟢 eventos NOMINA_GENERADA/PAGADA → PayrollFinanceHandler | Sí | 20/8/7 | NOMINA_*, EMPLEADO_*, EMPLOYEE_OVERWORK | EMPLEADO_ACTUALIZADO | — | 🟡 | 🟢 backend / 🔴 UI SQL | 🔴 | P1 |
| Delivery | `modulos/delivery.py` (2 700+), core/delivery/* | Use cases + handlers v13.30 | 🟢 la cadena de handlers más completa; UI aún 37 SQL + 3 commit | Sí | 37/†/3 | DELIVERY_* lifecycle, DRIVER_SETTLEMENT_CREATED | PEDIDO_NUEVO/ACTUALIZADO, VENTA_COMPLETADA, DELIVERY_UPDATE (huérfano) | pedidos activos | 🟢 eventos+timers | 🟡 driver_repo `1` | 🔴 | P1 |
| WhatsApp (módulo+servicio) | `modulos/whatsapp_module.py`, `whatsapp_service/`, `integrations/pos_adapter.py` | Bridge REST + eventos | Bus en otro proceso (B5); pos_adapter con lastrowid y `UPDATE productos SET existencia` | Sí | †/†/† | WA_* / SALE_CREATED (proceso WA) | — (desktop nunca recibe) | panel | 🔴 catálogo cacheado sin invalidación cross-proceso | 🔴 B12 | ⚫ | P0 |
| Cotizaciones | `modulos/cotizaciones.py`, cotizacion_service, anticipo_service | QuoteApplicationService | Servicio recibe conn+sucursal congelada; UI 10 SQL | Sí | 10/2/2 | COTIZACION_ACTUALIZADA | COTIZACION_ACTUALIZADA, CLIENTE_ACTUALIZADO 🟢 | — | 🟢 propio | 🟡 | 🟡 | P2 |
| BI/Dashboard CEO | `reportes_bi_v2.py`, `ui/dashboard.py`, analytics_engine, ceo_dashboard | AnalyticsEngine único | 🟢 un motor; refresh roto (B6); dashboard 60 s + VENTA_COMPLETADA | Media | 3/0/0 | — | eventos inexistentes (B6) | todos | 🔴 B6 | 🟡 | 🔴 | P1 |
| Configuración | `modulos/configuracion.py`, configuration_settings_service | SystemSettings/CompanyProfile | 🟢 el módulo más limpio: 0 SQL UI, eventos BRANCHES_CHANGED, permisos UUID | Baja | 0/0/0 | BRANCH_*, BRANCHES_CHANGED, USER/ROLE_PERMISSIONS_UPDATED (huérfanos) | BRANCHES_CHANGED | — | 🟢 | 🟢 | 🟢 | P3 |
| Hardware | `config_hardware.py`, hardware_service, printer_service | PrinterService/ScaleService | báscula en ventas con timer; TICKET_IMPRESO/PRINT_FAILED sin listeners | Media | †/†/† | TICKET_IMPRESO, PRINT_FAILED (huérfanos) | — | — | — | 🟢 | 🟡 | P2 |
| Activos | `modulos/activos.py` | AssetApplicationService (no existe) | SQL directo en módulo y diálogos; depreciación en scheduler llama función del módulo UI (`app_container.py:793`) | Sí | 19 SQL/7 commit | — | — | — | 🔴 | 🟡 | 🔴 | P1 |
| Etiquetas | `modulos/etiquetas.py` | LabelTemplateService | funcional; escucha AJUSTE+VENTA 🟢 | Media | 4/0/0 | — | AJUSTE_INVENTARIO, VENTA_COMPLETADA | — | 🟢 | 🟡 `Principal` display | 🟡 | P3 |
| APIs (`api/`, `webapp/`) | `api/routers/*`, `webapp/api_*` | UUID + use cases compartidos | int + lastrowid + SQL propio (B11) | n/a | n/a | ninguno | ninguno | n/a | n/a | 🔴 | ⚫ | P0 |
| Migraciones/Schema | `m000_base_schema.py` (3 302), `standalone/` | born-clean UUIDv7 | 🟢 verificado en DB nueva; riesgo PK TEXT sin NOT NULL (262 tablas) | n/a | n/a | — | — | n/a | n/a | 🟢 | 🟡 | P2 |

† = incluido en los totales de la sección 11 / allowlists.

**Ningún módulo queda sin clasificar.** 🟢: Configuración, Merma (backend), Migraciones. ⚫: Núcleo, Ventas, Caja, Inventario, Recepción QR, Producción, Fidelización(rifas), Finanzas, WhatsApp, APIs.

---

## 6. Matriz de fuentes de verdad duplicadas

| Dominio | Canónica esperada | Fuentes actuales | Conflicto | Riesgo | Corrección |
|---|---|---|---|---|---|
| Sesión | `SessionContext` | SessionContext + `container.sucursal_id/sucursal_nombre` (copias) + `usuario_actual` dict en MainWindow + copias `svc.sucursal_id` en ~15 servicios | sincronización por bucle genérico `set_sucursal_activa` | Alto | SessionContext único; servicios leen por callback, no copian |
| Sucursal activa | `session.active_branch_id` (UUID) | + `session._sucursal_id` (int legacy) + `container.sucursal_id` (str) | identidad dual int/str (D6) | Alto | eliminar `_sucursal_id` int y su property |
| Usuarios/roles/permisos | `PermissionQueryService` + catálogo | 🟢 unificado (tests verdes) | — | Bajo | — |
| Configuración | ConfigService/`configuraciones` | 🟢 + lecturas directas dispersas (`wiring.py:52`, `main_window.py:1418-1447`) | lecturas fuera de servicio | Medio | QueryService |
| Productos | `repositories/productos.py` + catalog_events | + `backend/product_catalog_service` + SQL directo en 20+ módulos | doble ruta de escritura (ambas emiten 🟢) | Medio | consolidar en ProductCatalogService |
| **Inventario/stock** | `inventory_stock` | + `productos.existencia` (≥10 escritores §B4) + `lotes` FIFO + reservas | **dos ledgers vivos** | **Crítico** | matar escritores de `existencia`; vista de compatibilidad de solo lectura |
| Ventas | SalesService | + unified_sales_service + ventas_facade + repositories/ventas (publica eventos propios) | 4 rutas (D2) | Alto | 1 UC; el repo no publica eventos |
| Caja | CashRegisterApplicationService | + CajaApplicationService + CierreCajaService + repo publica CAJA_MOVIMIENTO | 3 servicios, 2 vocabularios de eventos (D1/B2) | **Crítico** | unificar en la ruta backend + bridge de eventos |
| Compras | TraditionalPurchaseUC/PO/PR | + `core/use_cases/compra.py` (deprecado pero instanciado) + `purchase_service.py` + SQL en compras_pro | 3 rutas | Alto | eliminar deprecados |
| Transferencias | repo transferencias + handler | 🟡 + distribution_engine publica TRASPASO/AJUSTE por su cuenta y escribe `existencia` | 2 rutas | Alto | consolidar |
| Producción | ProductionApplicationService | + uc_produccion + RecipeEngine/ProductionEngine directos en UI | 3 entradas | Alto | 1 UC |
| Merma | WasteApplicationService | 🟢 única | — | Bajo | — |
| Finanzas | FinanceService.registrar_asiento | + TreasuryService + ERPFinancialService + third_party + accounting_engine + trace 083 (5+ escritores GL/ledger) | ledgers paralelos (`movimientos_caja`, `treasury_movements`, `journal_entries`, `financial_event_log`) | **Crítico** | definir GL único; el resto = vistas/proyecciones |
| Tesorería | TreasuryService | + capital_service + registros directos en handlers | duplicación parcial | Alto | idem |
| CxP/CxC | accounts_payable/receivable_service | + `finance_service.pagar_cxp/cobrar_cxc` + third_party_service | 3 entradas de mutación | Alto | 1 servicio; que publique CXP/CXC_CREADA |
| Clientes | cliente_repository + GestionarClienteUC | + SQL directo en clientes.py y ventas | 2 rutas | Medio | UC único |
| Fidelización | LoyaltyService (+_app repo) | + growth_engine (modulos/) + loyalty_repository DDL allowlist | 2 motores de puntos | Alto | fusionar growth→loyalty |
| Delivery | core/delivery use cases | 🟢 + SQL en modulos/delivery.py | UI aún lee directo | Medio | QueryService |
| WhatsApp | microservicio + bridge | + core WhatsAppService + 2 shims (intencionales) + pos_adapter SQLite directo | pos_adapter escribe ventas/stock sin UCs | **Crítico** | bridge solo API; prohibir SQLite write en WA (`_assert_sqlite_write_allowed` existe, reforzar) |
| Dashboard/BI | AnalyticsEngine | 🟢 único motor; CEODashboard consume | refresh roto (B6) | Medio | corregir suscripciones |
| Tickets | TicketTemplateEngine | + caja_ticket_service + ticket_designer SQL + delivery/ticket_delivery.py | 3 renderers | Medio | contrato único de layout |
| Hardware | HardwareService/PrinterService | 🟢 razonable | — | Bajo | — |
| Migraciones/Schema | `migrations/` | + DDL runtime cfdi/pwa (B15) + delivery_schema_migrator (allowlist) | runtime DDL | Alto | mover a migrations |

---

## 7. Matriz de eventos

Método: extracción AST de todos los `publish(` / `subscribe(` (excluyendo tests) + resolución de constantes/aliases + listas `_init_refresh`. Datos crudos: `scratchpad/events.json`.

### 7.1 Cadenas críticas — estado

| Evento (canal real) | Definido en | Emitido por | Escuchado por | Inventario | Finanzas | Dashboard | UI | Estado | Bug |
|---|---|---|---|---|---|---|---|---|---|
| VENTA_COMPLETADA (=SALE_COMPLETED/SALE_CREATED alias) | event_bus | sales_service:841, repositories/ventas:256 | 7+: sync, loyalty, raffles, audit, treasury, trace, accounting_engine, analytics, dashboard, caja, etiquetas, delivery | n/a (vía SALE_ITEMS) | 🟢 | 🟢 | 🟢 | **OK** | doble emisor (repo+servicio) |
| SALE_ITEMS_PROCESS | domain_events | sales_service:717 | SaleInventoryHandler(100), SaleFinanceHandler(90), CreditSaleFinanceHandler(85) | 🟢 | 🟢 | — | — | **OK** | — |
| VENTA_CANCELADA | event_bus | sales_reversal:358 | SaleCancelledFinanceHandler, raffles_cancel | — | 🟢 | — | — | **OK** | — |
| SALE_CANCELLED / SALE_REFUNDED / SALE_CREDIT_NOTE_ISSUED / SALE_CASH_COMPENSATED / SALE_INVENTORY_RESTORED | literales | sales_reversal:367-748 | **nadie** | — | — | — | — | **HUÉRFANO** | inglés duplicado sin bridge |
| PRODUCT_CREATED/UPDATED/DEACTIVATED + PRODUCTS_CHANGED + PRODUCTO_* legacy | domain_events/catalog_events | catalog_events (ruta canónica) | MainWindow fan-out, inventario, productos, compras | — | — | — | 🟢 | **OK** | Ventas sin contrato (B-V1) |
| BRANCH_* + BRANCHES_CHANGED | domain_events | configuration_settings_service:110 | MainWindow fan-out, compras, configuración | — | — | — | 🟢 | **OK** | transferencias/delivery no implementan contrato |
| COMPRA_REGISTRADA (=PURCHASE_CREATED) | event_bus | purchase_service:198, use_cases/compra:231 | PurchaseFinanceHandler(80), trace(20), compras UI | — | 🟢 | — | 🟢 | **OK** | — |
| PURCHASE_ITEMS_PROCESS | domain_events | TraditionalPurchaseUC (dinámico) | PurchaseInventoryHandler(100) | 🟢 | — | — | — | **OK** | — |
| RECEPCION_CONFIRMADA | event_bus | receive_po_adapter:327, distribution_engine:664 | compras UI (mixin) | ❌ sin handler inventario propio (lo hace el adapter) | ❌ | — | 🟢 | PARCIAL | — |
| TRANSFER_CREATED/TRASPASO_INICIADO + TRANSFER_COMPLETED/TRASPASO_CONFIRMADO | dual | repositories/transferencias:237-238,374-375 | transferencias UI (TRANSFER_*); TRASPASO_* sin listener | vía TRANSFER_ITEMS_PROCESS 🟢 | ❌ sin asiento de tránsito | ❌ | 🟢 | PARCIAL | canal dual sin bridge |
| TRANSFER_ITEMS_PROCESS | domain_events | repositories/transferencias:171,317 | TransferInventoryHandler(100) | 🟢 | — | — | — | **OK** | handler nace con `sucursal_id=1` (wiring:1098) |
| INVENTORY_MOVEMENT_RECORDED / INVENTORY_STOCK_UPDATED (EventName) | event_names | **nadie** | **nadie** | — | — | — | — | **MUERTO** | catálogo formal sin uso |
| INVENTARIO_ACTUALIZADO | event_bus ("canónico") | unified_inventory:386, produccion:619 | solo modulos/produccion:150 | ❌ inventario_local NO | — | ❌ | parcial | **ROTO** | B16 |
| AJUSTE_INVENTARIO (=STOCK_UPDATED) | event_bus | merma adapter:55, distribution_engine:677, stock_reservation:131 | sync_ajuste(100), etiquetas, inventario_local, finanzas KPI | 🟢 | — | — | 🟢 | **OK** | — |
| WASTE_REGISTERED / MERMA_REGISTRADA (=MERMA_CREATED) | ambos | merma adapter (triple publish) | merma_ledger(50), merma_stock(80) | 🟢 | 🟢 | ❌ | ❌ | **OK core** | trace `waste_recorded` muerta (B3) |
| PRODUCTION_ITEMS_PROCESS | domain_events | recipe_engine:255, production_engine:607 | ProductionInventoryHandler(100) | 🟢 (`sucursal_id=1` en engine wiring:997) | — | — | — | **OK** | riesgo branch |
| PRODUCCION_COMPLETADA | event_bus | recipe/production engines | sync(100), ProductionFinanceHandler(45), produccion UI | — | 🟢 | — | 🟢 | **OK** | — |
| PRODUCTION_BATCH_CREATED | domain_events | production_engine:278 | batch finance handler(45) | — | 🟢 | — | ❌ | **OK** | — |
| CASH_SHIFT_OPENED / CASH_MOVEMENT_RECORDED / CASH_Z_CUT_GENERATED / CASH_DIFFERENCE_DETECTED | event_names | cash_register_application_service:51-104 | **nadie** | — | ❌ | ❌ | ❌ | **HUÉRFANO** | **B2** |
| CAJA_TURNO_ABIERTO / CAJA_MOVIMIENTO / CAJA_CORTE_Z_GENERADO / CAJA_DIFERENCIA_DETECTADA / CAJA_TURNO_CERRADO | event_bus | caja_application_service:100-524, repositories/caja:210 | **nadie** | — | ❌ | ❌ | ❌ | **HUÉRFANO** | **B2** |
| ACCOUNT_PAYABLE_CREATED (=CXP_CREADA) / ACCOUNT_RECEIVABLE_CREATED (=CXC_CREADA) | domain_events | **nadie publica** (solo metadata `evento=` en asiento) | finanzas_unificadas:3308-3309 | — | ❌ | — | ❌ | **ROTO** | **B10** |
| PAYROLL_GENERATED / NOMINA_GENERADA / NOMINA_PAGADA | event_bus + rrhh | RRHHEventPublisher (rrhh/application/services) | PayrollFinanceHandler(60), trace payroll | — | 🟢 | — | — | **OK** | `payroll_generated` lowercase de hr_rule_engine:305 huérfano |
| DELIVERY_ORDER_CREATED…DELIVERED, DRIVER_SETTLEMENT_CREATED | event_bus | delivery use cases (publisher lambda) | lifecycle audit(30), settlement finance(50), revenue(50) | commit handler 🟢 | 🟢 | ❌ | 🟢 | **OK** | traza 083 lowercase muerta |
| MOVIMIENTO_FINANCIERO | event_bus | treasury_service:135 | audit(30), finanzas UI KPI | — | 🟢 | — | 🟢 | **OK** | — |
| PEDIDO_NUEVO | event_bus | bot_pedidos:659/804, uc pedido_wa:150 | sync(100), audit(30), MainWindow badge (roto B9), delivery UI | — | — | 🟢 | parcial | PARCIAL | B9 |
| RAFFLE_BUDGET_RESERVED / PRIZE_DELIVERED / BUDGET_RELEASED | event_bus | loyalty_service:793,1135,1154 | raffle_fin_* (60) **rotos por B1** | — | ❌ | — | — | **ROTO** | **B1** |
| RAFFLE_CREATED/ACTIVATED/CLOSED/TICKET_* /WINNER | event_bus | loyalty_service | **nadie** | — | — | — | — | HUÉRFANO | — |
| LOYALTY_POINTS_EARNED/REDEEMED/EXPIRED/REVERSED | event_bus | loyalty `_publish_loyalty_fin_event` | loyalty_fin_*(60) — usa `sucursal_id` default `1` (wiring:71) | — | 🟢 | — | — | OK c/deuda | fallback 1 |
| SALE_CREATED / PAYMENT_RECEIVED / PURCHASE_ORDER_CREATED / STAFF_NOTIFICATION / FORECAST_DEMAND_UPDATED (literales WA) | wiring:737-741 | solo proceso WA (otro proceso) | wiring:844-848 | — | ❌ | ❌ | — | **MUERTO en desktop** | **B5** |
| payment_confirmed / waste_recorded / delivery_payment_confirmed / driver_settlement_created / maintenance_registered / operating_supply_purchased (lowercase 083) | domain_events | **nadie** | trace handlers wiring:1384-1391 | — | ❌ | — | — | **MUERTO** | **B3** |
| venta_confirmada / stock_actualizado / pago_registrado | — (no definidos) | **nadie** | reportes_bi_v2:837 | — | — | ❌ | ❌ | **MUERTO** | **B6** |
| STOCK_BAJO_MINIMO (=STOCK_LOW) | event_bus | solo delivery_handler:660 | log/notify(50), dashboard | 🟡 | — | 🟡 | — | PARCIAL | B18 |
| TICKET_IMPRESO / PRINT_FAILED | event_bus | printer_service:272,287 | **nadie** | — | — | — | — | HUÉRFANO | — |
| USER/ROLE_PERMISSIONS_UPDATED, MODULE_ACCESS_UPDATED | event_names | configuration_settings_service:384-496 | **nadie** | — | — | — | ❌ menú no reacciona | HUÉRFANO | permisos requieren relogin |
| ACTIVE_BRANCH_CHANGED | domain_events | main_window:868,920 | **nadie** | — | — | — | ❌ | HUÉRFANO | propagación es por llamada directa, evento decorativo |
| CONTENEDOR_GENERADO/ASIGNADO/RECIBIDO, COTIZACION_ACTUALIZADA*, CLIENTE_ACTUALIZADO*, PEDIDO_ACTUALIZADO*, PRODUCCION_REGISTRADA, NIVEL_CAMBIADO, CONCILIACION_DIFERENCIA, DECISION_URGENTE, FORECAST_GENERADO/GENERATED, FRANQUICIA_*, EMPLOYEE_REST_DAY, AI_CONSULTA_REALIZADA, SIMULACION_EJECUTADA, inventory_movement, venta_suspendida±, stock_reservado±, DELIVERY_UPDATE (sub sin pub) | varios | ver `channels.json` | (*sí escuchados vía mixin: cotizaciones/delivery) | | | | | HUÉRFANOS totales o parciales | ruido de catálogo |

### 7.2 Conteo

- **Canales emitidos y escuchados (sanos):** ~35
- **Emitidos sin ningún listener:** ~38 (tras descontar suscripciones vía mixin)
- **Escuchados sin ningún emisor (en el proceso desktop):** 17 — de ellos **10 son financieros** (B2/B3/B5/B10)
- **Canales duplicados español/inglés sin bridge:** ventas-cancelación (VENTA_CANCELADA vs SALE_CANCELLED), transferencias (TRASPASO_* vs TRANSFER_*), caja (CAJA_* vs CASH_*), merma (mitigado con triple publish), pagos (payment_received vs PAYMENT_RECEIVED)

---

## 8. Matriz de diálogos

Método: AST sobre todas las clases que heredan de `QDialog` (30 archivos con QDialog; 11 clases con violaciones).

| Diálogo | Archivo:línea | Solo captura | SQL | Commit | Llama servicio/UC | Emite evento | Imprime | Violación | Riesgo |
|---|---|---|---|---|---|---|---|---|---|
| DialogAjustePeso | `ui/ventana_pedidos.py:252` | ❌ | R+W | ✅ | ❌ | ❌ | ❌ | escribe y commitea pesos de pedido | ⚫ inventario/cobro |
| DialogoMantenimiento | `modulos/activos.py:126` | ❌ | R+W | ✅ | ❌ | ❌ | ❌ | INSERT mantenimiento + commit | 🔴 finanzas (sin asiento) |
| DialogoActivo | `modulos/activos.py:28` | ❌ | R | ✅ | ❌ | ❌ | ❌ | commit en diálogo | 🔴 |
| DialogAsignarRepartidor | `ui/ventana_pedidos.py:303` | ❌ | R | ✅ | ❌ | ❌ | ❌ | asigna repartidor con SQL | 🔴 delivery |
| DialogoCliente | `modulos/clientes.py:532` | ❌ | — | ✅ | parcial | ✅ publish | ❌ | commit + publish desde diálogo | 🔴 |
| DialogoCorteZCiego | `modulos/caja.py:117` (448 líneas) | ❌ | — | — | ✅ ejecuta corte | — | ✅ | ejecuta corte e imprime desde el diálogo | ⚫ caja |
| DialogoNuevaCotizacion | `modulos/cotizaciones.py:531` | ❌ | R | — | ✅ | — | ❌ | lecturas SQL directas | 🟡 |
| _DialogoAsignarTarjetaCliente | `modulos/clientes.py:943` | ❌ | R | — | ✅ | — | ❌ | SQL lectura | 🟡 |
| _DialogoTarjetasCliente | `modulos/clientes.py:1053` | ❌ | R | — | — | — | ❌ | SQL lectura | 🟡 |
| DialogDetallePedido | `ui/ventana_pedidos.py:341` | ❌ | R | — | — | — | ❌ | SQL lectura | 🟡 |
| DialogoLogin | `interfaz/main_window.py:195` | ❌ | R (logo/config) | — | ✅ auth | — | ❌ | SQL lectura en login | 🟡 |

Regla objetivo: diálogo = captura → DTO/Command. Los 6 primeros violan frontalmente.

---

## 9. Matriz de KPIs

| Módulo | KPI | Fuente de datos | Evento que DEBERÍA refrescar | Evento que refresca HOY | Caliente | Bug |
|---|---|---|---|---|---|---|
| Caja | fondo, efectivo, total, movimientos, cortes (`caja.py:645-649`) | SQL turnos/ventas | CAJA_/CASH_* + VENTA_COMPLETADA | solo VENTA_COMPLETADA (`caja.py:575`) | Parcial | movimiento de efectivo o corte NO refresca (B2) |
| Dashboard operativo (`ui/dashboard.py`) | ventas hoy, tickets, stock bajo | SQL directo | VENTA, AJUSTE, CASH, PEDIDO | VENTA_COMPLETADA + STOCK_BAJO_MINIMO + timer 60 s | Parcial | STOCK_BAJO_MINIMO casi nunca se emite (B18) |
| BI v2 / CEO (`reportes_bi_v2.py`) | todos los ejecutivos | AnalyticsEngine | VENTA/COMPRA/MOVIMIENTO/AJUSTE | `venta_confirmada`,`stock_actualizado`,`pago_registrado` (inexistentes) | ❌ | **B6** — solo al abrir módulo |
| Finanzas (`finanzas_unificadas.py:3315-3324`) | KPIs sección 0, CxC, CxP, proveedores | SQL | + CXP_PAGADA/CXC_COBRADA/CAJA_* | VENTA, MOVIMIENTO_FINANCIERO, CXP_CREADA†, CXC_CREADA†, AJUSTE + **timer 15 s** | Timer | † canales nunca emitidos (B10); el timer disimula |
| Inventario | stock bajo/valor | InventoryQueryService | + INVENTARIO_ACTUALIZADO, TRANSFER_*, MERMA | 10 eventos (lista §B16) | Parcial | B16 |
| Ventas POS | stock visible por producto | `productos.existencia` (legacy) | PRODUCTS_CHANGED + INVENTARIO_ACTUALIZADO | ninguno (sin contrato) | ❌ | B-V1: lee fuente incorrecta y no refresca |
| Compras | pestañas/contadores | SQL UI | 🟢 | 14 eventos vía mixin | 🟢 | — |
| Producción | KPIs día (`production_query_service`) | SQL extraído 🟢 | 🟢 | PRODUCCION_COMPLETADA, RECETA_*, INVENTARIO_ACTUALIZADO | 🟢 | — |
| Merma | — | — | WASTE_REGISTERED→dashboard | nadie escucha para KPIs | ❌ | dashboards ciegos a merma |
| Delivery | pedidos activos/badges | OrderBadgeService | 🟢 lifecycle | eventos + timer 7 s | 🟢/timer | badge por evento roto (B9); `COALESCE(sucursal_id,1)` (order_badge_service:72) |
| RRHH | nómina próximas | SQL | NOMINA_*/EMPLEADO_* | EMPLEADO_ACTUALIZADO | Parcial | — |
| Forecast | demanda | forecast engines | FORECAST_GENERADO | nadie | ❌ | huérfano |

**Patrón global:** los KPIs que "funcionan" lo hacen por timers (7/15/30/60 s), no por eventos. Prohibido por contexto obligatorio ("KPIs que dependan de reiniciar/timer").

---

## 10. Matriz UUID/int

| Archivo:línea | Patrón | Clasificación | Riesgo | Acción |
|---|---|---|---|---|
| `core/session_context.py:38,48,64` | `_user_id: int`, `_sucursal_id: int` + property | identidad dual runtime | Alto | eliminar rama int |
| `core/session_context.py:107-110,127-128` | fallback `str(sucursal_id)` int→str | ruta dual | Alto | idem |
| `modulos/ventas.py:1319` | `set_sucursal(self, sucursal_id: int, ...)` | type hint int en UI | Medio | str |
| `modulos/produccion.py:102,106` | `sucursal_id = 1`, `branch_id=1` | fallback + int | Alto | sesión UUID |
| `core/events/wiring.py:71,313,337,381,461,481,513,532,558,585,612,709,756,767,781,802,877,913` | `data.get("sucursal_id", 1)` | fallback 1 en 18 handlers | Alto | sin default; descartar y loguear |
| `core/events/wiring.py:997,1098` | `UnifiedInventoryService(conn=db, sucursal_id=1)` | fallback 1 en motor de inventario | **Crítico** | branch del payload |
| `core/services/order_badge_service.py:72` | `COALESCE(sucursal_id,1)` | fallback 1 SQL | Medio | filtrar por UUID o excluir NULL |
| `api/routers/*.py` (ventas:16,82,105; pedidos:57,81,101; cotizaciones:68,95,115,149; inventario:32-57,130; clientes:47,112; anticipos:15,63,78,124; ordenes_compra:71,86) | `: int` + `lastrowid` + `sucursal_id: int = 1` | API int | **Crítico** | reescribir routers a UUID + UCs |
| `infrastructure/persistence/base.py:40-42` | helper `_lastrowid` | infraestructura legacy | Alto | eliminar helper |
| `integrations/pos_adapter.py:117,167,214,380` | `lastrowid` identidad ventas/pedidos WA | **crítico** | ⚫ | usar UCs del ERP |
| `integrations/cfdi/cfdi_service.py:165,238` | AUTOINCREMENT + lastrowid | runtime legacy | Alto | migración + new_uuid |
| `integrations/delivery_pwa/pwa_server.py:105,124` | `int(pedido_id)`, `chofer_id INTEGER PK` | int cast + DDL | Alto | UUID |
| `whatsapp_service/ai/catalog_entity_extractor.py:52` | `int(product.get("id", 0) or 0)` | cast ID dominio | **Crítico** (el bug reportado sigue vivo) | tratar como str |
| `whatsapp_service/erp/bridge.py:49-102` | Protocolos `cliente_id: int`, `pedido_id: int`, `producto_id: int`, `venta_id: int`, `sucursal_id: int` | contrato int completo | **Crítico** | str en todo el protocolo |
| `whatsapp_service/flows/cotizacion_flow.py:221-244` | `int(quote_id)` ×5 | cast | Alto | str |
| `whatsapp_service/parser/product_matcher.py:37,77,89` | `sucursal_id: int = 1`, `product_id: int` | int + default 1 | Alto | str sin default |
| `whatsapp_service/models/context.py:43` | `producto_id: int` | DTO int | Alto | str |
| `core/services/notificaciones` (`services/notificaciones.py:105`) | `MAX(id)` watermark | patrón MAX(id) (funciona con UUIDv7 lexicográfico, pero prohibido) | Bajo | usar `created_at` |
| `modulos/config_modules.py:55` | `getattr(container,'sucursal_id',1)` | fallback 1 | Medio | "" |
| `repositories/driver_repository.py` (4 hits), `services/bot_pedidos.py` (3), `core/services/production_application_service.py` (3), `distribution_engine.py` (3), `application/purchases/purchase_*_uc.py` (5), `rasa/actions/actions.py` (2), y ~15 más (ver `scratchpad/g_suc1.txt`) | `sucursal_id ... 1` | fallbacks activos | Medio-Alto | limpiar por lote |
| Falsos positivos típicos | `activo INTEGER DEFAULT 1`, `factor_base DEFAULT 1.0`, contadores/cantidades | booleanos/números de negocio | — | ninguna |

---

## 11. Matriz SQL directo en UI

Conteo por regex sobre `modulos/`, `interfaz/`, `ui/`, `frontend/` (R=SELECT, W=INSERT/UPDATE/DELETE, C=commit):

| Archivo | R | W | DDL | C | Riesgo | Acción |
|---|---|---|---|---|---|---|
| `modulos/growth_engine.py` | 5 | **11** | 0 | **12** | ⚫ puntos/dinero | mover a LoyaltyService |
| `modulos/loyalty_card_designer.py` | 3 | 9 | 0* | 8 | 🔴 | servicio de plantillas |
| `modulos/rrhh.py` | 12 | 8 | 0 | 7 | 🔴 nómina | UC nomina |
| `modulos/rrhh_turnos.py` | 7 | 6 | 0 | 7 | 🔴 | idem |
| `modulos/activos.py` | 6 | 4 | 0 | 7 | 🔴 | AssetApplicationService |
| `ui/ventana_pedidos.py` | 7 | 3 | 0 | 4 | ⚫ pedidos | use cases delivery |
| `modulos/recepcion_qr_widget.py` | 7 | 2 | 0 | 4 | ⚫ stock (recalcula `existencia`, línea 1981) | UC compras |
| `modulos/cotizaciones.py` | 7 | 2 | 0 | 2 | 🔴 | QuoteQueryService |
| `modulos/ticket_designer.py` | 5 | 1 | 0 | 1 | 🟡 | repo layouts |
| `interfaz/main_window.py` | 9 | 0 | 0 | 0 | 🟡 (búsqueda global, logo, tema, inbox) | QueryService |
| `modulos/clientes.py` | 4 | 0 | 0 | 2 | 🔴 | UC cliente |
| `ui/themes/theme_engine.py` | 1 | 1 | 0 | 1 | 🟡 | ThemeService |
| `modulos/base.py` | 1 | 0 | 0 | 2 | 🟡 | — |
| `modulos/etiquetas.py` | 3 | 0 | 0 | 0 | 🟡 | — |
| `modulos/sistema/health_monitor.py` | 2 | 0 | 0 | 0 | 🟡 diagnóstico | tolerable documentado |
| `modulos/planeacion_compras.py` | 1 | 0 | 0 | 0 | 🟡 | — |
| `modulos/spj_styles.py` | 1 | 0 | 0 | 0 | 🟡 | — |
| **TOTAL** | **81** | **47** | 0 | **57** | | |

Además, la allowlist (`tests/architecture/allowlists.py`) tolera SQL en 28 archivos UI (compras_pro 58, delivery 37, productos 29, ventas 17, finanzas 20…): la deuda real es mayor que la de esta tabla porque la allowlist usa otro matcher. **Las escrituras + commits desde UI son deuda; ninguna es DDL** (único DDL UI histórico ya eliminado).

---

## 12. Matriz DDL fuera de migrations

| Archivo:línea | DDL | Clasificación | Riesgo | Acción |
|---|---|---|---|---|
| `integrations/cfdi/cfdi_service.py:164` | `CREATE TABLE facturas_cfdi (... INTEGER PRIMARY KEY AUTOINCREMENT, venta_id INTEGER ...)` | **código activo** — se ejecuta al facturar | ⚫ contamina born-clean | mover a migration UUIDv7 |
| `integrations/delivery_pwa/pwa_server.py:123` | `CREATE TABLE driver_locations (chofer_id INTEGER PRIMARY KEY ...)` | **código activo** | 🔴 | migration UUID |
| `core/delivery/infrastructure/delivery_schema_migrator.py` | 7 sentencias (allowlist) | migrador propio de delivery fuera de `migrations/` | 🟡 | consolidar en migrations |
| `backend/infrastructure/db/uuid_cutover.py` | reescritura de tablas | herramienta excepcional documentada (OK, gated) | 🟢 | mantener gated |
| `api/routers/anticipos.py` (allowlist: 1) | ALTER/CREATE | API con DDL | 🔴 | eliminar |
| `core/auth/login_guard.py`, `core/events/outbox.py`, `core/module_config.py`, `core/repositories/*_config_repository.py`, `core/services/*` (≈25 archivos en `SCHEMA_CHANGES_OUTSIDE_MIGRATIONS_ALLOWLIST`) | `CREATE TABLE IF NOT EXISTS` defensivos | mayormente **stale**: spot-check de 4 archivos (cierre_caja, alertas, module_config, cotizacion) da 0 hits hoy — la allowlist está desactualizada y esconde el estado real | 🟡 | regenerar allowlist a cero y fijar guardrail |
| `tests/**` (conftest 22, finance, purchases) | DDL de fixtures | test | 🟢 | ok |

---

## 13. Matriz de módulos sin refresh en caliente

Contrato canónico: `on_products_changed/refresh_products`, `on_branches_changed/refresh_branches` (fan-out de MainWindow `catalog_events.py:142-190`) o suscripción propia.

| Módulo | Catálogos usados | Carga inicial | Refresh en caliente | Evento requerido | Evento actual | Bug |
|---|---|---|---|---|---|---|
| **Ventas** | productos, clientes, precios, promos | `cargar_productos_interactivos` | **NO** — sin `refresh_products`, sin `actualizar_datos` (el fallback `registrar_actualizacion` en `ventas.py:4624-4628` chequea un método que no existe = código muerto) | PRODUCTS_CHANGED, BRANCHES_CHANGED, CLIENTE_* | ninguno | producto/precio nuevo invisible hasta refiltrar; cliente nuevo hasta reabrir |
| **Transferencias** | sucursales, productos | `_load_transfers` | solo eventos TRANSFER_* propios | BRANCHES_CHANGED, PRODUCTS_CHANGED | ninguno de catálogo | sucursal nueva no aparece hasta reiniciar (bug conocido confirmado) |
| **Delivery** | repartidores, productos, sucursales | timers | eventos de pedidos, no de catálogo | PRODUCTS/BRANCHES_CHANGED, EMPLEADO_* | — | repartidor/producto nuevo no aparece |
| **Recepción QR** | sucursales | combo hardcodeado `("Principal", 1)` `recepcion_qr_widget.py:2237` | **NO** | BRANCHES_CHANGED | — | ⚫ |
| **Etiquetas** | productos | SQL | stock sí (AJUSTE/VENTA), catálogo no | PRODUCTS_CHANGED | parcial | plantillas con productos viejos |
| **Cotizaciones** | clientes, productos | SQL | COTIZACION_ACTUALIZADA, CLIENTE_ACTUALIZADO 🟢 | + PRODUCTS_CHANGED | parcial | productos viejos |
| **RRHH** | empleados, sucursales | SQL | EMPLEADO_ACTUALIZADO | + BRANCHES_CHANGED | parcial | — |
| **WhatsApp (microservicio)** | catálogo productos (`product_matcher` cachea) | carga al boot | **NO cross-proceso** — `PRODUCTS_CHANGED` no viaja entre procesos | invalidación vía API/webhook | ninguno | WA vende catálogo viejo hasta reinicio del servicio |
| **Finanzas** | proveedores 🟢, clientes parcial | SQL | PROVEEDOR_* 🟢 | + BRANCHES_CHANGED | parcial | — |
| Compras 🟢 / Inventario 🟢 / Productos 🟢 / Configuración 🟢 | — | — | contrato implementado | — | — | inventario: falta INVENTARIO_ACTUALIZADO (B16) |

---

## 14. Matriz de repositorios/servicios duplicados

| Área | Duplicados | Canónico propuesto | Eliminar/absorber |
|---|---|---|---|
| Caja | `application/services/caja_application_service.py` ↔ `backend/.../cash_register_application_service.py` ↔ `core/services/cierre_caja_service.py` | backend (use cases FASE 7.7) | los otros dos → adaptadores finos y luego borrar |
| Ventas | `sales_service` ↔ `unified_sales_service` ↔ `ventas_facade` ↔ eventos en `repositories/ventas.py` | SalesService→CreateSaleUseCase | facade y unified; repo sin publish |
| Inventario | `backend InventoryApplicationService` ↔ `core UnifiedInventoryService` | backend | Unified → interno del backend o borrar |
| Compras | `TraditionalPurchaseUC` ↔ `core/use_cases/compra.py` (deprecado, aún instanciado `app_container.py:556`) ↔ `purchase_service` | TraditionalPurchaseUC | borrar deprecado del container |
| Producción | `ProductionApplicationService` ↔ `uc_produccion` ↔ engines directos | ProductionApplicationService | — |
| Crédito clientes | `customer_credit_service` ↔ `credit_validation_service` ↔ `accounts_receivable_service` ↔ `finance_service.cobrar_cxc` ↔ `third_party_service` | AccountsReceivableService | consolidar entradas de mutación |
| Fidelidad | `loyalty_service` ↔ `modulos/growth_engine.py` | LoyaltyService | growth → application service |
| Finanzas GL | `finance_service` ↔ `treasury_service` ↔ `erp_financial_service` ↔ `accounting_engine` ↔ trace 083 | FinanceService (asientos) + proyecciones | definir tabla GL única |
| WhatsApp | 3 shims (intencionales — preservar) + `core WhatsAppService` + microservicio | microservicio para conversación; core para envío saliente | pos_adapter escribe DB directo → API |
| Tickets | `TicketTemplateEngine` ↔ `caja_ticket_service` ↔ `delivery/ticket_delivery.py` | TicketTemplateEngine + renderers | — |
| Eventos | `backend/shared/events/*` ↔ `core/events/*` | ver Remediación A | — |

---

## 15. Matriz de fallbacks legacy

| Tipo | Sitios activos (no tests/docs) | Peores casos |
|---|---|---|
| `sucursal_id=1` / `get(...,1)` | ~40 archivos (lista completa: `g_suc1.txt`) | `wiring.py` ×20, `wiring.py:997,1098` (motor inventario), `order_badge_service.py:72`, `produccion.py:102`, `config_modules.py:55`, `product_matcher.py:37` |
| `"Principal"` | 7 activos | `recepcion_qr_widget.py:2237` (**dato**, no display), `ventas.py:1213`, `transferencias.py:83`, `produccion.py:103`, `delivery/ticket_delivery.py:32`, `labels/generador_etiquetas.py:64,82` (display) |
| `lastrowid` identidad | 9 sitios | `api/routers/*` (3), `pos_adapter.py` (4), `cfdi_service.py`, `persistence/base.py` |
| `MAX(id)` | 1 activo | `services/notificaciones.py:105` (watermark; tolerable, documentar o migrar a `created_at`) |
| Identidad dual int/str | núcleo | `session_context.py`, `main_window.py`/container handoffs |
| Nota positiva | `auth_repository.py`, `branch_resolution.py`, `session_context.clear()` documentan y evitan el fallback — el patrón correcto ya existe, falta aplicarlo en los bordes | |

---

## 16. Matriz de riesgos por módulo

| Módulo | Riesgo dominante | Clase |
|---|---|---|
| Fidelización/Rifas | asientos nunca registrados (B1) | ⚫ financiero |
| Caja | cortes/movimientos invisibles para finanzas y BI (B2) | ⚫ financiero |
| Finanzas | trazabilidad 083 muerta + CxC/CxP sin evento (B3/B10) + 5 ledgers | ⚫ financiero |
| Inventario | doble ledger stock (B4) + handlers `sucursal_id=1` | ⚫ inventario |
| WhatsApp | bus inter-proceso inexistente + int contracts + catálogo cacheado (B5/B12) | ⚫ ventas/datos |
| Recepción QR | sucursal `Principal/1` + recálculo `existencia` (B13) | ⚫ inventario |
| Producción | anclaje sucursal 1 (B14) | ⚫ inventario multi-sucursal |
| APIs | lastrowid + int (B11) | ⚫ datos |
| Ventas | catálogo sin refresh + 4 rutas + lee `existencia` | 🔴 |
| BI | KPIs congelados (B6) | 🔴 decisión |
| Núcleo | inbox de otro empleado (B7), badges muertos (B8/B9), identidad dual | 🔴 |
| Activos | mantenimiento sin asiento, SQL en diálogos | 🔴 financiero |
| RRHH | SQL/commit en UI sobre nómina | 🔴 |
| Delivery | UI con SQL, DELIVERY_UPDATE huérfano | 🟡-🔴 |
| Transferencias/Compras/Cotizaciones/Etiquetas/Hardware | deuda de capa y refresh | 🟡 |
| Configuración / Merma / Migraciones | — | 🟢 |

---

## 17. Plan de remediación por fases

### Remediación 0 — Hotfixes quirúrgicos (1 PR, sin refactor)
1. `wiring.py:102` — validar `raffle_id` como string no vacío (elimina el TypeError). **Desbloquea B1.**
2. `main_window.py` — mover inbox/badges a `_propagar_usuario`; filtrar `personal` por el usuario logueado; decorar `_on_pedido_nuevo` con `@pyqtSlot()`. **B7/B8/B9.**
3. `recepcion_qr_widget.py:2237` — poblar combo desde `sucursales` activas (UUID). **B13.**
4. `produccion.py:102,106` — sucursal desde sesión. **B14.**
5. Publicar `CXP_CREADA`/`CXC_CREADA` desde accounts services. **B10.**
6. `reportes_bi_v2.py:837` — suscribir `VENTA_COMPLETADA`, `COMPRA_REGISTRADA`, `MOVIMIENTO_FINANCIERO`, `AJUSTE_INVENTARIO`. **B6.**

### Remediación A — EventBus canónico global
- Un solo catálogo: `backend/shared/events/event_names.py` como fuente; `core/events/event_bus.py` conserva constantes como aliases al MISMO string (patrón ya usado en domain_events).
- **Bridge legacy↔nuevo** genérico (generalizar `legacy_event_bridge` de delivery): CAJA_*↔CASH_*, TRASPASO_*↔TRANSFER_*, VENTA_CANCELADA↔SALE_CANCELLED, payment_received↔PAYMENT_RECEIVED.
- Conectar consumidores de caja: handler de finanzas para CASH_Z_CUT_GENERATED/CASH_DIFFERENCE_DETECTED; refresh de dashboard.
- Decidir por evento huérfano: conectar o borrar (lista §7.2 — prohibido mantener eventos que nadie consume).
- Reparar/retirar la traza 083: o los flujos publican los canales lowercase, o se eliminan handlers y tablas muertas.
- Cola/broker (o polling de outbox `core/events/outbox.py`, que ya existe) para WA↔ERP inter-proceso.
- Test: matriz emit/subscribe automatizada (ver §18-T1).

### Remediación B — Refresh en caliente global
- Contratos formales por widget: `refresh_products/branches/customers/suppliers/inventory/cash/dashboard`.
- MainWindow ya es propagador (fan-out) — extender a CUSTOMERS_CHANGED, SUPPLIERS_CHANGED, INVENTORY_CHANGED, CASH_CHANGED, FINANCE_CHANGED, DASHBOARD_REFRESH_REQUIRED.
- Implementar contrato en: **Ventas (prioridad 1)**, Transferencias, Delivery, Etiquetas, Cotizaciones, RRHH.
- Inventario: añadir INVENTARIO_ACTUALIZADO/INVENTORY_CHANGED a su lista.
- Sustituir timers de KPIs por eventos (timer solo como fallback ≥60 s).

### Remediación C — UUIDv7 total (bordes)
- SessionContext: eliminar `_sucursal_id` int.
- Barrido `sucursal_id=1` (§15) — sin default; si falta branch en payload, log ERROR y descartar.
- API FastAPI: routers a UUID + use cases compartidos; eliminar `lastrowid` y `_lastrowid` helper.
- WhatsApp: protocolo bridge a `str`, extractor sin `int()`, matcher sin default 1.
- Eliminar DDL runtime cfdi/pwa → migrations UUIDv7 (B15).
- Endurecer schema: `id TEXT PRIMARY KEY NOT NULL` (riesgo NULL-PK en 262 tablas, §19).

### Remediación D — Dialogs limpios
- Los 6 diálogos rojos (§8) → capturan DTO, el módulo llama al servicio.
- Guardrail nuevo: AST que falle si una clase QDialog contiene `execute(`, `commit(`, `publish(`, `registrar_asiento`, `print`hardware.

### Remediación E — KPIs y dashboards
- Declarar por KPI: fuente, eventos que lo invalidan, método refresh (matriz §9 como spec).
- Prohibir cálculo de KPI en UI (mover a QueryServices — BI ya tiene AnalyticsEngine).

### Remediación F — SQL directo
- Orden de ataque por riesgo: growth_engine → ventana_pedidos/recepcion_qr → rrhh(+turnos) → activos → clientes/cotizaciones → resto.
- Allowlists con **ratchet**: todo PR debe dejar el contador ≤ actual; CI falla si sube.

### Remediación G — Schema born-clean (mantener)
- Ya en verde; añadir: NOT NULL en PK TEXT, prohibición de `sqlite3.connect` fuera del pool, test de humo "insert por writer ⇒ id no NULL" (sugerido en cierre_global.md §6).

**Orden recomendado:** 0 → A → B → C → D/E en paralelo → F → G. A y B destraban el valor visible (finanzas y KPIs) sin tocar reglas de negocio.

---

## 18. Tests requeridos

Estado actual: `tests/architecture` **228 pass / 6 fail** (orquestador + `test_done_modules_are_complete`: declara DONE módulos incompletos), `tests/unit` **226 pass / 26 fail**, `tests/integration` **125 pass / 110 fail** (con PyQt5 + QT_QPA_PLATFORM=offscreen). Causas dominantes de fallos: código que ya exige UUID contra tests que siembran ints (`ValueError: Legacy integer...`, `driver_id debe ser str (UUID)`), columna `sucursal_uuid` inexistente (test_uuid_migration_103), asserts financieros en 0 (consistente con B1-B3). **Tests que contradicen Plan B** (ej.: `test_sale_inventory_handler_uses_decrease_stock.py:34` espera `product_id: 7` int): deben corregirse al contrato UUID, no el código.

Nuevos tests propuestos:

| ID | Test | Bloquea |
|---|---|---|
| T1 | `test_event_matrix_no_orphans.py` — AST global: todo canal suscrito tiene emisor y viceversa (allowlist explícita para canales inter-proceso) | B2, B3, B5, B6, B10 |
| T2 | `test_cash_events_have_finance_consumers.py` — CASH_Z_CUT/CASH_DIFFERENCE con handler de finanzas registrado | B2 |
| T3 | `test_raffle_finance_handler_posts.py` — publicar RAFFLE_BUDGET_RESERVED con UUID y verificar asiento | B1 |
| T4 | `test_no_int_id_contracts_in_api.py` — routers FastAPI sin `: int` en `*_id` ni `lastrowid` | B11 |
| T5 | `test_wa_bridge_uses_str_ids.py` — protocolos del bridge sin `int` | B12 |
| T6 | `test_no_sucursal_default_one.py` — cero `get("sucursal_id", 1)` / `sucursal_id=1` en código activo (allowlist decreciente con ratchet) | §15 |
| T7 | `test_no_principal_fallback_data.py` — `"Principal"` solo permitido en labels de display listados | B13 |
| T8 | `test_dialogs_capture_only.py` — QDialog sin execute/commit/publish/print | §8 |
| T9 | `test_kpis_subscribe_real_events.py` — todo `bus.subscribe` de módulos UI apunta a canal con emisor | B6 |
| T10 | `test_single_stock_writer.py` — ningún `UPDATE productos SET existencia` fuera de la capa canónica/migrations | B4 |
| T11 | `test_no_runtime_ddl.py` — cero `CREATE TABLE` en `integrations/` (retirar de allowlist) | B15 |
| T12 | `test_text_pk_not_null.py` — nuevas tablas con `TEXT PRIMARY KEY NOT NULL` | §19 |
| T13 | `test_allowlists_ratchet.py` — falla si un contador de allowlist sube; job periódico que exige decrecer | D8 |
| T14 | Smoke DB nueva → login → venta → corte → verificar asientos + KPIs refrescados por evento | end-to-end |

---

## 19. Comandos ejecutados

```bash
# Greps de deuda (resultados en scratchpad: g_*.txt)
grep -rn --include="*.py" "lastrowid|INTEGER PRIMARY KEY|AUTOINCREMENT|MAX\(id\)" …
grep -rn --include="*.py" "sucursal_id=1|get('sucursal_id', 1)|branch_id=1" …
grep -rn --include="*.py" "'Principal'" …
grep -rn --include="*.py" "int\(.*(producto|product|sale|branch|cliente|user|…)_id" …

# Matriz de eventos: AST sobre publish/subscribe + resolución de constantes/aliases
python3 <script AST>  # → scratchpad/events.json, channels.json

# Dialogs: AST sobre clases QDialog buscando execute/commit/publish/print
# SQL en UI: regex R/W/DDL/commit sobre modulos/, interfaz/, ui/, frontend/

# FASE 10 — Schema en DB temporal
python3 -c "m000_base_schema.up(conn); migrations.engine.up(conn)"
#   → 272 tablas, foreign_key_check: 0
#   → AUTOINCREMENT: [] · INTEGER PK: [] · dual id+uuid: [] · DEFAULT 1 en *_id: []
#   → tablas sin PK: 0 · PK TEXT sin NOT NULL: 262  ← riesgo residual

# Tests (con pytest + PyQt5 + QT_QPA_PLATFORM=offscreen)
python3 -m pytest pos_spj_v13.4/tests/architecture -q   # 228 pass, 6 fail, 4 skip
python3 -m pytest pos_spj_v13.4/tests/architecture/test_clean_birth_guardrails.py -q  # 41 pass
python3 -m pytest pos_spj_v13.4/tests/unit -q           # 226 pass, 26 fail
python3 -m pytest pos_spj_v13.4/tests/integration -q    # 125 pass, 110 fail
```

---

## 20. Evidencia por archivo/línea (índice)

Toda la evidencia citada inline en §3–§15. Referencias maestras:

- **Eventos:** `core/events/wiring.py` (101-102, 71, 737-741, 844-848, 997, 1098, 1384-1391), `application/services/caja_application_service.py:100-524`, `backend/application/services/cash_register_application_service.py:51-104`, `core/services/finance/third_party_service.py:391-392`, `modulos/reportes_bi_v2.py:837`, `core/services/finance/accounts_receivable_service.py:144`, `accounts_payable_service.py:155`, `modulos/finanzas_unificadas.py:3305-3324`, `modulos/inventario_local.py:618-623`, `modulos/produccion.py:147-150`, `core/events/catalog_events.py:142-190`.
- **UUID/int:** `core/session_context.py:38-40,64,104-110,119-128`, `api/routers/*` (§10), `whatsapp_service/erp/bridge.py:49-102`, `whatsapp_service/ai/catalog_entity_extractor.py:52`, `integrations/pos_adapter.py:117-380`, `infrastructure/persistence/base.py:40-42`.
- **Fallbacks:** `modulos/recepcion_qr_widget.py:2237`, `modulos/produccion.py:102-106`, `core/services/order_badge_service.py:72`, `modulos/config_modules.py:55`.
- **UI/SQL:** tabla §11; `interfaz/main_window.py:1052-1054,1085-1087,1361-1394,1418-1447`; diálogos §8.
- **DDL runtime:** `integrations/cfdi/cfdi_service.py:164-167`, `integrations/delivery_pwa/pwa_server.py:123-125`.
- **Stock dual:** `backend/infrastructure/db/repositories/compras_write_repository.py:86,105`, `core/services/distribution_engine.py:401,563,583`, `core/services/inventory/unified_inventory_service.py:134,216`, `services/qr_service.py:116`, `core/services/lote_service.py:53`, `modulos/recepcion_qr_widget.py:1981`.
- **Container:** `core/app_container.py:537-540` (container completo a UCs), `690` (`branch_id` default 1 en invalidación BI), `755-757` (lee `existencia`), `826-907` (lógica de negocio + commits en scheduler), `1005-1030` (cierre de turno con `%d` sobre UUID).
- **Tests:** `tests/architecture/allowlists.py`, `tests/unit/test_sale_inventory_handler_uses_decrease_stock.py:34`, `tests/integration/test_uuid_migration_103.py` (columna `sucursal_uuid`), `test_refactor_state_json_is_valid.py::test_done_modules_are_complete`.

---

### Apéndice — Top bugs por módulo (FASE 13, formato requerido)

**Caja** — Bug 1: eventos CAJA_*/CASH_* sin suscriptores (B2). Bug 2: corte Z ejecutado desde diálogo de 448 líneas que además imprime. Deuda: 3 servicios paralelos (D1). Riesgo: ⚫ financiero. Prioridad: P0. Fix: unificar en CashRegisterApplicationService + bridge de eventos + handler de finanzas. Tests: T1, T2, T14.

**Ventas** — Bug 1: sin refresh de catálogo (código muerto `registrar_actualizacion`). Bug 2: stock visible desde `productos.existencia`. Deuda: 4 rutas de venta; `set_sucursal(int)`; 17 SQL + 2 commit UI. Riesgo: ⚫. Prioridad: P0. Fix: contrato refresh + CatalogQueryService + consolidar rutas. Tests: T6, T9, T10.

**Inventario** — Bug 1: doble ledger (B4). Bug 2: no escucha INVENTARIO_ACTUALIZADO (B16). Deuda: dos motores. Riesgo: ⚫. Prioridad: P0. Fix: matar escritores de `existencia`; añadir canal a la lista del módulo. Tests: T10.

**Productos** — Bug: ninguno funcional grave; ruta canónica emite bien. Deuda: 29 SQL + 9 commit UI. Riesgo: 🟡. Prioridad: P2. Fix: QueryService. Tests: ratchet T13.

**Compras** — Bug 1: CONTENEDOR_* huérfanos. Bug 2: recepción QR con `Principal/1` y recálculo de `existencia` (B13). Deuda: 58 SQL UI; container completo a UCs; UC deprecado instanciado. Riesgo: ⚫ (QR). Prioridad: P0 (QR) / P1. Fix: combo desde catálogo; retirar deprecado. Tests: T6, T7.

**Transferencias** — Bug 1: canal dual TRASPASO/TRANSFER sin bridge. Bug 2: sin BRANCHES_CHANGED (sucursal nueva invisible). Deuda: distribution_engine paralelo; handler `sucursal_id=1`. Riesgo: 🔴. Prioridad: P1. Fix: bridge + contrato refresh. Tests: T1, T6.

**Producción** — Bug: `sucursal_id=1` + `branch_id=1` (B14) y `UnifiedInventoryService(sucursal_id=1)` en wiring. Deuda: 3 entradas. Riesgo: ⚫ multi-sucursal. Prioridad: P0. Fix: branch de sesión/payload. Tests: T6.

**Recetas** — Bug: RECETA_CREADA/ACTUALIZADA solo las escucha producción; etiquetas/ventas no. Deuda: recipe_engine también en UI. Riesgo: 🟡. Prioridad: P2. Fix: PRODUCTS_CHANGED al cambiar receta de producto. Tests: T9.

**Merma** — Bug: traza financiera 083 (`waste_recorded`) muerta (B3). Deuda: ninguna mayor (módulo refactorizado). Riesgo: 🟡. Prioridad: P2. Fix: publicar canal o retirar handler. Tests: T1.

**Clientes** — Bug: CLIENTE_CREADO solo se emite vía UC; la UI publica CLIENTE_ACTUALIZADO directo; finanzas escucha CLIENTE_CREADO. Deuda: diálogo con commit+publish. Riesgo: 🔴. Prioridad: P1. Fix: UC único. Tests: T8.

**Crédito** — Bug: 3 servicios de crédito con reglas potencialmente divergentes. Deuda: consolidación. Riesgo: 🔴 financiero. Prioridad: P1. Fix: AccountsReceivableService único + eventos. Tests: T1.

**Fidelización** — Bug: asientos de rifas jamás registrados (B1); 6 eventos RAFFLE_* huérfanos. Deuda: growth_engine en `modulos/` con 12 commits. Riesgo: ⚫. Prioridad: P0. Fix: hotfix str + mover growth. Tests: T3.

**Finanzas** — Bug 1: trace 083 muerta (B3). Bug 2: CXP/CXC sin evento (B10). Deuda: 5 ledgers; KPIs por timer 15 s. Riesgo: ⚫. Prioridad: P0. Fix: Remediación A + GL único. Tests: T1, T2, T14.

**Tesorería** — Bug: `payment_received` lowercase no llega al handler WA uppercase (B5-mismatch local). Deuda: solapamiento con capital_service. Riesgo: 🔴. Prioridad: P1. Fix: canal único. Tests: T1.

**RRHH** — Bug: `payroll_generated` (hr_rule_engine:305) huérfano vs NOMINA_GENERADA canónico. Deuda: 20 SQL + 7 commit en UI de nómina. Riesgo: 🔴. Prioridad: P1. Fix: usar RRHHEventPublisher; extraer SQL. Tests: T1, T13.

**Delivery** — Bug 1: DELIVERY_UPDATE suscrito sin emisor. Bug 2: badge por evento roto (B9); `COALESCE(sucursal_id,1)`. Deuda: 37 SQL UI. Riesgo: 🔴. Prioridad: P1. Fix: pyqtSlot + canal correcto. Tests: T9.

**WhatsApp** — Bug 1: eventos WA→ERP no cruzan procesos (B5). Bug 2: `int(product.get("id"))` (B12). Bug 3: catálogo cacheado sin invalidación. Deuda: bridge int completo; pos_adapter escribe DB con lastrowid. Riesgo: ⚫. Prioridad: P0. Fix: outbox/cola + protocolo str + invalidación por webhook. Tests: T5.

**Cotizaciones** — Bug: menor. Deuda: servicio con sucursal congelada al construir; 10 SQL UI. Riesgo: 🟡. Prioridad: P2. Fix: QueryService. Tests: T13.

**Dashboard/BI** — Bug: refresco por eventos inexistentes (B6); dashboard operativo depende de STOCK_BAJO_MINIMO casi nunca emitido (B18). Deuda: timers. Riesgo: 🔴. Prioridad: P1 (hotfix trivial en R0). Tests: T9.

**Configuración** — Bug: USER/ROLE_PERMISSIONS_UPDATED y MODULE_ACCESS_UPDATED emitidos sin consumidor (menú no reacciona; requiere relogin). Deuda: mínima — módulo modelo. Riesgo: 🟢/🟡. Prioridad: P3. Fix: MainWindow escucha y llama `refresh_module_access`. Tests: T1.

**Hardware** — Bug: TICKET_IMPRESO/PRINT_FAILED huérfanos (sin reintentos ni alertas). Deuda: — . Riesgo: 🟡. Prioridad: P2. Fix: handler de reintento/notificación o retirar eventos. Tests: T1.

**APIs** — Bug: lastrowid identidad + int en todos los routers + `sucursal_id: int = 1` (B11). Deuda: la API no comparte use cases. Riesgo: ⚫. Prioridad: P0 antes de exponer. Fix: reescritura sobre UCs. Tests: T4.

**Migraciones/Schema** — Bug: ninguno en cadena; DDL runtime externo la contamina (B15). Deuda: PK TEXT sin NOT NULL (262). Riesgo: 🟡. Prioridad: P2. Fix: migrar cfdi/pwa; endurecer NOT NULL. Tests: T11, T12.

---

*Auditoría generada sin aplicar cambios de código. Próximo paso recomendado: PR "Remediación 0 — hotfixes quirúrgicos" (6 fixes, ~60 líneas, todos con test).*
