# Auditoría born-clean UUIDv7 — schema activo (FASE 0)

Generado por `tools/born_clean_audit.py` sobre una DB temporal con el
bootstrap normal (`m000_base_schema.up` + `migrations.engine.up`).

## Censo

| Métrica | Valor |
|---|---|
| Tablas totales | 260 |
| `id TEXT PRIMARY KEY` (born-clean) | 99 |
| PK entera (`find_integer_pks`) | **139** |
| PK natural/compuesta | 22 |
| Sin PK | 0 |
| Con AUTOINCREMENT | 126 |
| Tablas con FK funcional INTEGER | 142 |
| Tablas con `DEFAULT 1` en FK funcional | 40 |

## Tablas legacy restantes (PK entera) y archivo creador

| Tabla | PK | Creador(es) |
|---|---|---|
| ajustes_inventario | id | migrations/m000_base_schema.py; migrations/standalone/031_inventory_engine.py |
| anticipo_reglas | id | migrations/standalone/047_v13_schema.py |
| audit_log | id | migrations/standalone/063_audit_log_table.py |
| audit_logs | id | migrations/m000_base_schema.py |
| batch_movements | id | migrations/m000_base_schema.py |
| batch_tree_audits | id | migrations/m000_base_schema.py |
| batches | id | migrations/m000_base_schema.py |
| branch_inventory | id | migrations/m000_base_schema.py; migrations/standalone/027_inventory_hardening.py; migrations/standalone/106_inventario_actual_branch.py |
| branch_inventory_batches | id | migrations/m000_base_schema.py |
| branch_products | branch_id, product_id | migrations/standalone/039_branch_products.py |
| caja_operations | id | migrations/m000_base_schema.py; migrations/standalone/023_enterprise_upgrade.py; migrations/standalone/024_enterprise_blocks_5_8.py |
| cajas | id | migrations/m000_base_schema.py |
| categorias | id | migrations/m000_base_schema.py |
| chicken_batches | id | migrations/m000_base_schema.py |
| cierre_mensual | id | migrations/m000_base_schema.py |
| cierres_caja | id | migrations/m000_base_schema.py |
| clientes_diarios | id | migrations/m000_base_schema.py; migrations/standalone/032_bi_tables.py |
| clientes_lista_precio | cliente_id | migrations/m000_base_schema.py |
| comisiones_acumuladas | id | migrations/standalone/046_comisiones_happy_hour.py |
| comisiones_config | id | migrations/standalone/046_comisiones_happy_hour.py |
| componentes_producto | id | migrations/m000_base_schema.py |
| compras_inventariables | id | migrations/m000_base_schema.py |
| compras_pollo | id | migrations/m000_base_schema.py |
| conciliation_runs | id | migrations/m000_base_schema.py |
| concurrency_events | id | migrations/standalone/016_concurrency_events.py |
| config_diseno_tarjetas | id | migrations/m000_base_schema.py; migrations/standalone/023_enterprise_upgrade.py |
| config_programa_fidelidad | id | migrations/m000_base_schema.py; migrations/standalone/096_configuration_services_schema.py |
| configuracioneses | id | migrations/standalone/031_inventory_engine.py |
| contenedor_productos | id | migrations/standalone/111_qr_containers_schema.py |
| contenedores | id | migrations/standalone/111_qr_containers_schema.py |
| contenedores_qr | id | migrations/standalone/040_qr_reception.py |
| credit_notes | id | migrations/m000_base_schema.py; migrations/standalone/029_reversals_hardening.py |
| decision_log | id | migrations/standalone/049_v134_intelligent_erp.py |
| delivery_driver_cuts | id | migrations/standalone/070_delivery_enterprise_lifecycle.py; migrations/standalone/109_delivery_driver_cuts_schema.py |
| delivery_orders | id | migrations/m000_base_schema.py |
| detalles_venta | id | migrations/m000_base_schema.py |
| devoluciones | id | migrations/m000_base_schema.py |
| devoluciones_detalle | id | migrations/m000_base_schema.py |
| driver_locations | chofer_id | migrations/m000_base_schema.py |
| drivers | id | migrations/m000_base_schema.py |
| email_config | id | migrations/m000_base_schema.py |
| email_schedule | id | migrations/m000_base_schema.py |
| facturas_cfdi | id | migrations/m000_base_schema.py |
| growth_ledger | id | migrations/m000_base_schema.py |
| growth_metas | id | migrations/m000_base_schema.py |
| growth_misiones | id | migrations/m000_base_schema.py |
| growth_misiones_progreso | id | migrations/m000_base_schema.py |
| growth_otp | id | migrations/m000_base_schema.py |
| happy_hour_rules | id | migrations/standalone/046_comisiones_happy_hour.py |
| historial | id | migrations/m000_base_schema.py |
| historial_precios | id | migrations/standalone/043_price_history.py |
| historico_puntos | id | migrations/m000_base_schema.py |
| hr_auditoria_log | id | migrations/standalone/049_v134_intelligent_erp.py |
| hr_pago_log | id | migrations/standalone/049_v134_intelligent_erp.py |
| inventario_actual | id | migrations/m000_base_schema.py; migrations/standalone/031_inventory_engine.py; migrations/standalone/106_inventario_actual_branch.py |
| inventario_diario | id | migrations/m000_base_schema.py; migrations/standalone/032_bi_tables.py; migrations/standalone/106_inventario_actual_branch.py |
| inventario_global | id | migrations/m000_base_schema.py |
| inventario_subproductos | id | migrations/m000_base_schema.py |
| inventario_sucursal | id | migrations/m000_base_schema.py |
| json_audit_log | id | migrations/m000_base_schema.py; migrations/standalone/023_enterprise_upgrade.py |
| json_log_events | id | migrations/m000_base_schema.py; migrations/standalone/024_enterprise_blocks_5_8.py; migrations/standalone/026_final_structural_hardening.py |
| legacy_branch_inventory | id | (no encontrado en migrations/) |
| legacy_inventario_actual | id | (no encontrado en migrations/) |
| legacy_movimientos_inventario | id | (no encontrado en migrations/) |
| listas_precio | id | migrations/m000_base_schema.py |
| login_attempts | id | migrations/m000_base_schema.py |
| logs | id | migrations/m000_base_schema.py |
| lotes | id | migrations/m000_base_schema.py |
| lotes_tarjetas_pdf | id | migrations/standalone/047_v13_schema.py |
| loyalty_budget_caps | id | migrations/m000_base_schema.py; migrations/standalone/023_enterprise_upgrade.py; migrations/standalone/024_enterprise_blocks_5_8.py |
| loyalty_challenge_progress | id | migrations/m000_base_schema.py; migrations/standalone/023_enterprise_upgrade.py; migrations/standalone/024_enterprise_blocks_5_8.py |
| loyalty_challenges | id | migrations/m000_base_schema.py; migrations/standalone/023_enterprise_upgrade.py; migrations/standalone/024_enterprise_blocks_5_8.py |
| loyalty_community_contributions | id | migrations/m000_base_schema.py; migrations/standalone/024_enterprise_blocks_5_8.py |
| loyalty_community_goals | id | migrations/m000_base_schema.py; migrations/standalone/023_enterprise_upgrade.py; migrations/standalone/024_enterprise_blocks_5_8.py |
| loyalty_level_history | id | migrations/m000_base_schema.py; migrations/standalone/024_enterprise_blocks_5_8.py |
| loyalty_multiplier_rules | id | migrations/m000_base_schema.py; migrations/standalone/023_enterprise_upgrade.py; migrations/standalone/024_enterprise_blocks_5_8.py |
| loyalty_programs | id | migrations/m000_base_schema.py |
| loyalty_redemption_limits | branch_id | migrations/m000_base_schema.py; migrations/standalone/023_enterprise_upgrade.py; migrations/standalone/024_enterprise_blocks_5_8.py |
| loyalty_roi_tracking | id | migrations/m000_base_schema.py; migrations/standalone/023_enterprise_upgrade.py; migrations/standalone/024_enterprise_blocks_5_8.py |
| loyalty_scores | cliente_id | migrations/m000_base_schema.py; migrations/standalone/024_enterprise_blocks_5_8.py |
| loyalty_snapshots | id | migrations/m000_base_schema.py |
| loyalty_ticket_messages | id | migrations/m000_base_schema.py; migrations/standalone/023_enterprise_upgrade.py |
| marketing_messages | id | migrations/m000_base_schema.py; migrations/standalone/036_whatsapp_rasa.py |
| meat_production_runs | id | migrations/standalone/032_meat_production.py; migrations/standalone/053_meat_production_tables.py |
| meat_production_yields | id | migrations/standalone/032_meat_production.py; migrations/standalone/053_meat_production_tables.py |
| merma_log | id | migrations/standalone/067_meat_erp_improvements.py |
| mermas | id | migrations/m000_base_schema.py; migrations/standalone/031_inventory_engine.py |
| movimientos_caja | id | migrations/m000_base_schema.py; migrations/standalone/024_enterprise_blocks_5_8.py |
| movimientos_inventario | id | migrations/m000_base_schema.py; migrations/standalone/105_movimientos_inventario.py |
| movimientos_lote | id | migrations/m000_base_schema.py |
| movimientos_trazabilidad | id | migrations/m000_base_schema.py |
| ordenes_cotizacion | id | migrations/standalone/047_v13_schema.py |
| paquetes | id | migrations/m000_base_schema.py |
| paquetes_componentes | id | migrations/m000_base_schema.py |
| payments | id | migrations/m000_base_schema.py; migrations/standalone/028_sales_transaction_hardening.py |
| permisos | id | migrations/m000_base_schema.py |
| plantillas_compra | id | migrations/standalone/075_plantillas_compra.py |
| plantillas_compra_items | id | migrations/standalone/075_plantillas_compra.py |
| precios_lista | lista_id, producto_id | migrations/m000_base_schema.py |
| precios_volumen | id | migrations/m000_base_schema.py |
| product_recipes_abarrotes | id | migrations/m000_base_schema.py |
| production_alerts | id | migrations/m000_base_schema.py; migrations/standalone/032_bi_tables.py |
| production_cost_ledger | id | migrations/m000_base_schema.py; migrations/standalone/032_bi_tables.py |
| productos_deletion_guard | producto_id | migrations/m000_base_schema.py; migrations/standalone/023_enterprise_upgrade.py |
| promotion_rules | id | migrations/m000_base_schema.py |
| purchase_request_items | id | migrations/standalone/076_purchase_requests.py; migrations/standalone/077_purchase_requests.py |
| purchase_requests | id | migrations/standalone/076_purchase_requests.py; migrations/standalone/077_purchase_requests.py |
| rasa_sessions | id | migrations/standalone/036_whatsapp_rasa.py |
| recepciones_pollo | id | migrations/m000_base_schema.py |
| receta_componentes | id | migrations/m000_base_schema.py |
| recetas | id | migrations/m000_base_schema.py; migrations/standalone/030_recetas_industriales.py |
| referidos | id | migrations/m000_base_schema.py |
| rendimiento_derivados | id | migrations/m000_base_schema.py |
| rendimiento_pollo | id | migrations/m000_base_schema.py |
| rol_permisos | id | migrations/m000_base_schema.py; migrations/standalone/047_v13_schema.py |
| roles | id | migrations/m000_base_schema.py |
| roles_permisos | rol_id, permiso_id | migrations/m000_base_schema.py |
| sale_refunds | id | migrations/m000_base_schema.py; migrations/standalone/029_reversals_hardening.py |
| suppliers | id | migrations/m000_base_schema.py; migrations/standalone/035_finance_erp.py |
| sync_version_history | version | migrations/m000_base_schema.py; migrations/standalone/023_enterprise_upgrade.py; migrations/standalone/025_sync_batch_log.py |
| system_locks | id | migrations/m000_base_schema.py |
| temp_purchase_drafts | id | migrations/standalone/073_temp_purchase_drafts.py |
| tipos_cambio | id | migrations/m000_base_schema.py |
| transfer_suggestions | id | migrations/standalone/038_transfer_suggestions.py |
| transferencia_detalle | id | migrations/m000_base_schema.py; migrations/standalone/031_inventory_engine.py |
| transferencias | id | migrations/m000_base_schema.py; migrations/standalone/031_inventory_engine.py |
| transferencias_inventario | id | migrations/m000_base_schema.py |
| traspasos_inventario | id | migrations/m000_base_schema.py |
| traspasos_pollo | id | migrations/m000_base_schema.py |
| trazabilidad_qr | id | migrations/m000_base_schema.py |
| turno_actual | sucursal_id | migrations/m000_base_schema.py |
| turnos_caja | id | migrations/m000_base_schema.py |
| unidades_conversion | id | migrations/m000_base_schema.py; migrations/standalone/031_inventory_engine.py |
| unidades_medida | id | migrations/m000_base_schema.py; migrations/standalone/031_inventory_engine.py |
| usuarios | id | migrations/m000_base_schema.py |
| usuarios_roles | usuario_id, rol_id, sucursal_id | migrations/m000_base_schema.py |
| usuarios_sucursales | usuario_id, sucursal_id | migrations/standalone/047_v13_schema.py |
| ventas | id | migrations/m000_base_schema.py |
| ventas_diarias | id | migrations/m000_base_schema.py; migrations/standalone/032_bi_tables.py |

## AUTOINCREMENT

- ajustes_inventario
- anticipo_reglas
- audit_log
- audit_logs
- batch_movements
- batch_tree_audits
- batches
- branch_inventory
- branch_inventory_batches
- caja_operations
- cajas
- categorias
- chicken_batches
- cierre_mensual
- cierres_caja
- clientes_diarios
- comisiones_acumuladas
- comisiones_config
- componentes_producto
- compras_inventariables
- compras_pollo
- conciliation_runs
- concurrency_events
- config_diseno_tarjetas
- config_programa_fidelidad
- configuracioneses
- contenedor_productos
- contenedores
- contenedores_qr
- credit_notes
- decision_log
- delivery_driver_cuts
- delivery_orders
- detalles_venta
- devoluciones
- devoluciones_detalle
- drivers
- email_schedule
- facturas_cfdi
- growth_ledger
- growth_metas
- growth_misiones
- growth_misiones_progreso
- growth_otp
- happy_hour_rules
- historial
- historial_precios
- historico_puntos
- hr_auditoria_log
- hr_pago_log
- inventario_actual
- inventario_diario
- inventario_global
- inventario_subproductos
- inventario_sucursal
- json_audit_log
- json_log_events
- legacy_branch_inventory
- legacy_inventario_actual
- legacy_movimientos_inventario
- listas_precio
- login_attempts
- logs
- lotes
- lotes_tarjetas_pdf
- loyalty_budget_caps
- loyalty_challenge_progress
- loyalty_challenges
- loyalty_community_contributions
- loyalty_community_goals
- loyalty_level_history
- loyalty_multiplier_rules
- loyalty_programs
- loyalty_roi_tracking
- loyalty_snapshots
- loyalty_ticket_messages
- marketing_messages
- meat_production_runs
- meat_production_yields
- merma_log
- mermas
- movimientos_caja
- movimientos_inventario
- movimientos_lote
- movimientos_trazabilidad
- ordenes_cotizacion
- paquetes
- paquetes_componentes
- payments
- permisos
- plantillas_compra
- plantillas_compra_items
- precios_volumen
- product_recipes_abarrotes
- production_alerts
- production_cost_ledger
- promotion_rules
- purchase_request_items
- purchase_requests
- rasa_sessions
- recepciones_pollo
- receta_componentes
- recetas
- referidos
- rendimiento_derivados
- rendimiento_pollo
- rol_permisos
- roles
- sale_refunds
- suppliers
- system_locks
- temp_purchase_drafts
- tipos_cambio
- transfer_suggestions
- transferencia_detalle
- transferencias
- transferencias_inventario
- traspasos_inventario
- traspasos_pollo
- trazabilidad_qr
- turnos_caja
- unidades_conversion
- unidades_medida
- usuarios
- ventas
- ventas_diarias

## FK funcionales INTEGER

- accounts_payable: supplier_id
- accounts_receivable: venta_id
- ajustes_inventario: producto_id, sucursal_id
- anticipo_reglas: sucursal_id
- audit_log: user_id, entity_id, sucursal_id
- audit_logs: entidad_id, sucursal_id
- batch_movements: batch_id, bib_id, branch_id, producto_id, referencia_id
- batch_tree_audits: root_batch_id
- batches: producto_id, parent_batch_id, root_batch_id
- bot_sessions: sucursal_id
- branch_inventory: branch_id, product_id, batch_id
- branch_inventory_batches: batch_id, branch_id, producto_id, batch_padre_id
- branch_products: branch_id, product_id
- caja_operations: branch_id, venta_id, sucursal_id
- chicken_batches: branch_id, producto_id, compra_global_id, parent_batch_id
- cierre_mensual: sucursal_id
- cierres_caja: sucursal_id, turno_id
- clientes_diarios: sucursal_id
- clientes_lista_precio: cliente_id, lista_id
- comisiones_acumuladas: venta_id, sucursal_id
- comisiones_config: sucursal_id
- componentes_producto: producto_compuesto_id, producto_componente_id
- compras: sucursal_id, purchase_order_id
- compras_inventariables: gasto_id, producto_id, sucursal_id
- conciliation_runs: branch_id
- concurrency_events: sucursal_id
- contenedor_productos: contenedor_id, producto_id
- contenedores: proveedor_id, compra_id, parent_id
- cotizaciones: venta_ref_id
- credit_notes: sale_id
- decision_log: sucursal_id
- delivery_cut_items: order_id
- delivery_driver_cuts: driver_id, sucursal_id
- delivery_orders: venta_id, driver_id, cliente_id, sucursal_id, corte_id
- demand_forecast: product_id, branch_id
- detalles_venta: venta_id, producto_id, batch_id
- devoluciones: venta_id, sucursal_id
- devoluciones_detalle: devolucion_id, producto_id
- driver_locations: chofer_id
- drivers: sucursal_id, usuario_id
- facturas_cfdi: venta_id
- fixed_assets: supplier_id
- forecast_metrics: product_id, branch_id
- forecast_run_log: branch_id
- growth_ledger: cliente_id, sucursal_id, ticket_id, cajero_id
- growth_metas: sucursal_id
- growth_misiones_progreso: cliente_id, mision_id
- growth_otp: cliente_id
- happy_hour_rules: sucursal_id
- historial: sucursal_id
- historial_precios: producto_id, sucursal_id
- historico_puntos: cliente_id, venta_id
- hr_auditoria_log: empleado_id, sucursal_id
- hr_pago_log: empleado_id, sucursal_id
- inventario_actual: producto_id, sucursal_id
- inventario_diario: producto_id, sucursal_id
- inventario_global: producto_id, compra_ref_id
- inventario_subproductos: compra_pollo_id, producto_id
- inventario_sucursal: sucursal_id, producto_id
- inventory_reservations: branch_id, product_id
- json_audit_log: branch_id
- json_log_events: sucursal_id, branch_id
- legacy_branch_inventory: branch_id, product_id, batch_id
- legacy_inventario_actual: producto_id, sucursal_id
- legacy_movimientos_inventario: producto_id, referencia_id, proveedor_id, batch_id, bib_id, sucursal_id, lote_id
- lotes: producto_id, proveedor_id, sucursal_id, lote_padre_id
- lotes_tarjetas_pdf: sucursal_id
- loyalty_budget_caps: branch_id
- loyalty_challenge_progress: challenge_id, cliente_id
- loyalty_challenges: branch_id
- loyalty_community_contributions: goal_id, cliente_id, venta_id
- loyalty_community_goals: branch_id
- loyalty_level_history: cliente_id
- loyalty_redemption_limits: branch_id
- loyalty_roi_tracking: branch_id
- loyalty_scores: cliente_id
- loyalty_snapshots: cliente_id
- maintenance_records: supplier_id
- meat_production_runs: branch_id, source_product_id, user_id
- meat_production_yields: run_id, yield_product_id
- merma_log: producto_id, lote_id, produccion_id, sucursal_id
- mermas: producto_id, sucursal_id
- movimientos_caja: sucursal_id, venta_id, turno_id, reference_id, caja_id
- movimientos_inventario: producto_id, referencia_id, proveedor_id, batch_id, bib_id, sucursal_id, lote_id
- movimientos_lote: lote_id
- movimientos_trazabilidad: sucursal_id
- nomina_pagos: source_id
- operating_supplies: supplier_id
- ordenes_compra: pr_id, sucursal_id
- ordenes_cotizacion: cotizacion_id, cliente_id, sucursal_id
- paquetes: producto_id
- paquetes_componentes: paquete_id, corte_producto_id
- payments: venta_id
- pedidos_whatsapp: sucursal_id
- personal: usuario_id
- plantillas_compra: proveedor_id, sucursal_id
- plantillas_compra_items: plantilla_id, producto_id
- precios_lista: lista_id, producto_id
- precios_volumen: producto_id, lista_id
- produccion_detalle: lote_id
- product_recipe_components: legacy_receta_componente_id
- product_recipes: legacy_receta_id, output_product_id
- product_recipes_abarrotes: producto_id, ingrediente_id
- production_batches: product_source_id, branch_id, lote_origen_id
- production_cost_ledger: product_id
- production_outputs: product_id, lote_hijo_id
- productos: producto_padre_id
- productos_deletion_guard: producto_id
- promotion_rules: sucursal_id, target_id
- purchase_request_items: pr_id, producto_id
- purchase_requests: proveedor_id, sucursal_id
- rasa_sessions: pedido_activo_id
- recepcion_items: lote_id
- recepciones_pollo: sucursal_id, producto_id, compra_global_id, batch_id
- receta_componentes: receta_id, producto_id
- recetas: producto_base_id
- rendimiento_derivados: producto_pollo_id, producto_derivado_id, producto_padre_id
- rendimiento_pollo: producto_pollo_id
- replenishment_recommendations: product_id, branch_id
- rol_permisos: rol_id
- roles_permisos: rol_id, permiso_id
- sale_refunds: sale_id, sale_item_id, product_id
- suppliers: proveedor_id
- system_locks: branch_id
- tarjetas_fidelidad: lote_origen_id
- temp_purchase_drafts: sucursal_id
- transfer_items: product_id, batch_id
- transfer_suggestions: product_id, origin_branch_id, dest_branch_id
- transferencia_detalle: transferencia_id, producto_id
- transferencias: origen_id, destino_id
- transferencias_inventario: producto_id
- transfers: branch_origin_id, branch_dest_id
- traspasos_inventario: sucursal_origen_id, sucursal_destino_id, producto_id
- traspasos_pollo: sucursal_origen_id, sucursal_destino_id, producto_id
- trazabilidad_qr: producto_id, proveedor_id, lote_id, sucursal_id, venta_id, cliente_id, recepcion_id
- turno_actual: sucursal_id
- turnos_caja: sucursal_id
- usuarios: sucursal_id, empleado_id, sucursal_principal_id, personal_id
- usuarios_roles: usuario_id, rol_id, sucursal_id
- usuarios_sucursales: usuario_id, sucursal_id
- ventas: sucursal_id, cliente_id, turno_id, pedido_wa_id
- ventas_diarias: sucursal_id

## DEFAULT 1 en FK funcional

- audit_log: sucursal_id
- audit_logs: sucursal_id
- bot_sessions: sucursal_id
- caja_operations: sucursal_id
- cierre_mensual: sucursal_id
- cierres_caja: sucursal_id
- comisiones_acumuladas: sucursal_id
- comisiones_config: sucursal_id
- compras: sucursal_id
- compras_inventariables: sucursal_id
- concurrency_events: sucursal_id
- decision_log: sucursal_id
- delivery_driver_cuts: sucursal_id
- delivery_orders: sucursal_id
- devoluciones: sucursal_id
- drivers: sucursal_id
- growth_metas: sucursal_id
- happy_hour_rules: sucursal_id
- historial: sucursal_id
- historial_precios: sucursal_id
- hr_auditoria_log: sucursal_id
- hr_pago_log: sucursal_id
- legacy_movimientos_inventario: sucursal_id
- lotes: sucursal_id
- lotes_tarjetas_pdf: sucursal_id
- merma_log: sucursal_id
- movimientos_inventario: sucursal_id
- movimientos_trazabilidad: sucursal_id
- ordenes_compra: sucursal_id
- ordenes_cotizacion: sucursal_id
- pedidos_whatsapp: sucursal_id
- plantillas_compra: sucursal_id
- production_batches: branch_id
- purchase_requests: sucursal_id
- temp_purchase_drafts: sucursal_id
- trazabilidad_qr: sucursal_id
- turnos_caja: sucursal_id
- usuarios: sucursal_id, sucursal_principal_id
- usuarios_roles: sucursal_id
- ventas: sucursal_id

## Sin PK

- (ninguna)
