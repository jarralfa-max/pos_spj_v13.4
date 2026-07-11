"""Temporary architecture debt allowlists for SPJ FASE 1.

Each dictionary stores current violations by file. The guardrail tests allow
the existing count and fail when a file introduces additional violations or a
new file starts violating a rule. Counts may be reduced as debt is removed.
"""

# Ratchet (Remediación F): contadores APRETADOS a la realidad actual. El total
# bajó de 371 a 187 tras las extracciones de fases previas + Remediación D
# (diálogos captura-only). test_sql_in_ui_ratchet exige igualdad exacta: agregar
# SQL en UI falla, y remover SQL obliga a bajar el contador aquí (sólo decrece).
# Módulos ya en 0 (retirados): finanzas_unificadas, productos, inventario_local,
# transferencias.
SQL_IN_UI_ALLOWLIST = {
    'pos_spj_v13.4/interfaz/main_window.py': 9,
    # activos.py: SQL 100% extraído a AssetService (Remediación F) — lecturas de
    # tabla/depreciación/mantenimientos, bajas, borrados y la depreciación mensual.
    'pos_spj_v13.4/modulos/base.py': 3,
    'pos_spj_v13.4/modulos/clientes.py': 1,
    'pos_spj_v13.4/modulos/compras/actions_bar.py': 1,
    # compras_pro.py: sin SQL real (delega 100% a use cases); los 7 antiguos eran
    # falsos positivos de SQL_RE sobre docstrings ("Update"/"select") — reescritos.
    # cotizaciones.py: SQL 100% extraído a CotizacionService (Remediación F).
    'pos_spj_v13.4/modulos/delivery.py': 2,
    # etiquetas.py: SQL extraído a ProductoRepository/ConfigService/HardwareConfigRepository
    # (Remediación F). El 1 restante es falso positivo de SQL_RE sobre `.update(` de dict.
    'pos_spj_v13.4/modulos/etiquetas.py': 1,
    # loyalty_card_designer.py: SQL extraído a LoyaltyCardDesignerService (Remediación F).
    # Los 3 restantes son falsos positivos de SQL_RE sobre `.update(` de dicts
    # (self.plantilla.update / d.update), no SQL.
    'pos_spj_v13.4/modulos/loyalty_card_designer.py': 3,
    # planeacion_compras.py: SQL → ProductoRepository.listar_activos_combo +
    # PurchaseRepository.ultimo_costo_unitario (Remediación F).
    # recepcion_qr_widget.py: SQL 100% extraído a RecepcionQRService (Remediación F).
    # reportes_bi_v2.py: KPIs → BIRepository.get_kpis_dia; fallback PDF →
    # ExportService.export_ventas_hoy_pdf (Remediación F).
    # rrhh.py: SQL 100% extraído a RRHHCatalogService (Remediación F).
    # rrhh_turnos.py: SQL 100% extraído a RRHHTurnosService (Remediación F).
    'pos_spj_v13.4/modulos/sistema/backup_engine.py': 2,
    'pos_spj_v13.4/modulos/sistema/health_monitor.py': 4,
    'pos_spj_v13.4/modulos/spj_styles.py': 2,
    # ticket_designer.py: SQL de configuraciones extraído a ConfigService (Remediación F).
    # ventas.py: sin SQL real (delega a use cases). Reescritas 4 docstrings que
    # activaban SQL_RE ("Update"/"select"); el 1 restante es `payload.update(` (dict).
    'pos_spj_v13.4/modulos/ventas.py': 1,
    # payment_dialog.py: 0 SQL real; los 2 antiguos eran falsos positivos de
    # SQL_RE (docstring "select all" + payload.update() de dict) — reescritos.
}

COMMIT_ROLLBACK_IN_UI_ALLOWLIST = {
    # activos.py: commit()/rollback() movidos a AssetService (Remediación F).
    'pos_spj_v13.4/modulos/base.py': 4,
    'pos_spj_v13.4/modulos/clientes.py': 5,
    'pos_spj_v13.4/modulos/compras_pro.py': 5,
    # CONFIGURACION FASE 1: config_hardware.py, config_modules.py and
    # configuracion.py no longer call commit()/rollback() in the UI.
    # cotizaciones.py: commit() movido a CotizacionService (Remediación F).
    'pos_spj_v13.4/modulos/delivery.py': 3,
    # loyalty_card_designer.py: commit() movido a LoyaltyCardDesignerService (Remediación F).
    'pos_spj_v13.4/modulos/productos.py': 9,
    # recepcion_qr_widget.py: commit() movido a RecepcionQRService (Remediación F).
    # rrhh.py: commit()/rollback() movidos a RRHHCatalogService/repositorios (Remediación F).
    # rrhh_turnos.py: commit() movido a RRHHTurnosService (Remediación F).
    # ticket_designer.py: commit() eliminado (ConfigService persiste; Remediación F).
    'pos_spj_v13.4/modulos/transferencias.py': 2,
    'pos_spj_v13.4/modulos/ventas.py': 2,
}

SCHEMA_CHANGES_OUTSIDE_MIGRATIONS_ALLOWLIST = {
    'pos_spj_v13.4/api/routers/anticipos.py': 1,
    'pos_spj_v13.4/application/services/customer_credit_service.py': 1,
    'pos_spj_v13.4/core/auth/login_guard.py': 2,
    # Plan B: uuid_cutover es la herramienta excepcional de conservación de
    # datos (reescribe tablas por diseño); el migrador delivery añadió
    # delivery_outbox_events; born_clean_audit menciona CREATE TABLE en docstring.
    'pos_spj_v13.4/backend/infrastructure/db/uuid_cutover.py': 2,
    'pos_spj_v13.4/core/delivery/infrastructure/delivery_schema_migrator.py': 7,
    'pos_spj_v13.4/tools/born_clean_audit.py': 1,
    'pos_spj_v13.4/core/delivery/infrastructure/inventory_reservation_adapter.py': 1,
    'pos_spj_v13.4/core/events/outbox.py': 1,
    'pos_spj_v13.4/core/module_config.py': 1,
    'pos_spj_v13.4/core/repositories/hardware_config_repository.py': 1,
    'pos_spj_v13.4/core/repositories/whatsapp_config_repository.py': 1,
    'pos_spj_v13.4/core/services/ai_advisor.py': 1,
    'pos_spj_v13.4/core/services/alert_engine.py': 1,
    'pos_spj_v13.4/core/services/alertas_service.py': 2,
    'pos_spj_v13.4/core/services/cierre_caja_service.py': 2,
    'pos_spj_v13.4/core/services/compras_inventariables_engine.py': 1,
    'pos_spj_v13.4/core/services/cotizacion_service.py': 2,
    'pos_spj_v13.4/core/services/decision_engine.py': 1,
    'pos_spj_v13.4/core/services/desktop_notification_service.py': 1,
    'pos_spj_v13.4/core/services/finance/production_cost_service.py': 1,
    'pos_spj_v13.4/core/services/finance/third_party_service.py': 1,
    'pos_spj_v13.4/core/services/financial_simulator.py': 1,
    'pos_spj_v13.4/core/services/hr_rule_engine.py': 2,
    'pos_spj_v13.4/core/services/lote_service.py': 2,
    'pos_spj_v13.4/core/services/loyalty_service.py': 1,
    'pos_spj_v13.4/core/services/moneda_service.py': 1,
    'pos_spj_v13.4/core/services/pricing_service.py': 4,
    'pos_spj_v13.4/core/services/reporte_email_service.py': 2,
    'pos_spj_v13.4/core/services/sales/sale_loyalty_policy.py': 1,
    'pos_spj_v13.4/core/services/sales_service.py': 4,
    'pos_spj_v13.4/core/services/scheduled_demand_service.py': 2,
    'pos_spj_v13.4/core/services/scheduler_service.py': 2,
    'pos_spj_v13.4/core/services/stock_reservation_service.py': 3,
    'pos_spj_v13.4/core/services/whatsapp_service.py': 2,
    'pos_spj_v13.4/core/tickets/ticket_layout_repository.py': 8,
    'pos_spj_v13.4/delivery/asignacion_repartidor.py': 2,
    'pos_spj_v13.4/integrations/cfdi/cfdi_service.py': 1,
    'pos_spj_v13.4/integrations/delivery_pwa/pwa_server.py': 1,
    'pos_spj_v13.4/modulos/activos.py': 2,
    'pos_spj_v13.4/modulos/compras_pro.py': 9,
    'pos_spj_v13.4/modulos/configuracion.py': 1,
    'pos_spj_v13.4/core/services/growth_engine.py': 5,
    'pos_spj_v13.4/modulos/loyalty_card_designer.py': 3,
    'pos_spj_v13.4/modulos/productos.py': 1,
    'pos_spj_v13.4/modulos/rrhh_turnos.py': 3,
    'pos_spj_v13.4/repositories/driver_repository.py': 4,
    'pos_spj_v13.4/repositories/loyalty_repository.py': 11,
    'pos_spj_v13.4/repositories/purchase_request_repository.py': 2,
    'pos_spj_v13.4/repositories/recetas.py': 4,
    'pos_spj_v13.4/scripts/seed_demo.py': 1,
    'pos_spj_v13.4/scripts/stress_test_concurrency.py': 1,
    'pos_spj_v13.4/security/rbac.py': 4,
    'pos_spj_v13.4/sync/event_logger.py': 1,
    'pos_spj_v13.4/sync/sync_engine.py': 3,
    'pos_spj_v13.4/tests/conftest.py': 22,
    'pos_spj_v13.4/tests/finance/test_capital_service.py': 3,
    'pos_spj_v13.4/tests/finance/test_financial_trace_assets.py': 3,
    'pos_spj_v13.4/tests/finance/test_financial_trace_maintenance.py': 5,
    'pos_spj_v13.4/tests/finance/test_financial_trace_operating_supplies.py': 4,
    'pos_spj_v13.4/tests/finance/test_financial_trace_payments.py': 3,
    'pos_spj_v13.4/tests/finance/test_financial_trace_payroll.py': 4,
    'pos_spj_v13.4/tests/finance/test_financial_trace_purchase.py': 4,
    'pos_spj_v13.4/tests/finance/test_financial_trace_sale.py': 4,
    'pos_spj_v13.4/tests/finance/test_financial_trace_waste_loyalty.py': 3,
    'pos_spj_v13.4/tests/finance/test_reconciliation_service.py': 6,
    'pos_spj_v13.4/tests/purchases/test_fase5_direct_purchase_flow.py': 8,
    'pos_spj_v13.4/tests/purchases/test_fase7_documental_sidebar.py': 5,
    'pos_spj_v13.4/tests/purchases/test_fase8_po_reception_event.py': 3,
    'pos_spj_v13.4/tests/purchases/test_phase3_pr_po_documental.py': 4,
    'pos_spj_v13.4/tests/purchases/test_phase4_receive_po_adapter.py': 4,
    'pos_spj_v13.4/tests/purchases/test_purchase_cancel_flow.py': 3,
    'pos_spj_v13.4/tests/purchases/test_purchase_inventory_effects.py': 3,
    'pos_spj_v13.4/tests/purchases/test_purchase_lot_creation.py': 2,
    'pos_spj_v13.4/tests/purchases/test_qr_flow_no_regression.py': 2,
    'pos_spj_v13.4/tests/purchases/test_traditional_purchase_current_flow.py': 3,
    'pos_spj_v13.4/tests/test_analytics_profitability_fallback.py': 3,
    'pos_spj_v13.4/tests/test_bloque1_p0_fixes.py': 8,
    'pos_spj_v13.4/tests/test_bloque2_query_service.py': 6,
    'pos_spj_v13.4/tests/test_bloque3_motor_unificado.py': 9,
    'pos_spj_v13.4/tests/test_bootstrap_wiring.py': 6,
    'pos_spj_v13.4/tests/test_caja.py': 5,
    'pos_spj_v13.4/tests/test_cliente_repository_schema_compat.py': 2,
    'pos_spj_v13.4/tests/test_core_services.py': 15,
    'pos_spj_v13.4/tests/test_credit_flow_refactor.py': 3,
    'pos_spj_v13.4/tests/test_credit_sale_backend_validation.py': 8,
    'pos_spj_v13.4/tests/test_credit_sale_cxc.py': 3,
    'pos_spj_v13.4/tests/test_db_connection_transaction.py': 1,
    'pos_spj_v13.4/tests/test_delivery_application_use_cases.py': 2,
    'pos_spj_v13.4/tests/test_delivery_history_audit.py': 1,
    'pos_spj_v13.4/tests/test_delivery_inventory_projection.py': 4,
    'pos_spj_v13.4/tests/test_delivery_lifecycle.py': 5,
    'pos_spj_v13.4/tests/test_delivery_outbox.py': 1,
    'pos_spj_v13.4/tests/test_delivery_phase12_required.py': 6,
    'pos_spj_v13.4/tests/test_delivery_repository_list_orders.py': 1,
    'pos_spj_v13.4/tests/test_delivery_sale_projection.py': 2,
    'pos_spj_v13.4/tests/test_delivery_schema_migrator.py': 3,
    'pos_spj_v13.4/tests/test_delivery_service.py': 1,
    'pos_spj_v13.4/tests/test_delivery_service_compat_phase10.py': 1,
    'pos_spj_v13.4/tests/test_delivery_service_sync_sales.py': 2,
    'pos_spj_v13.4/tests/test_delivery_ticket_uses_escpos.py': 3,
    'pos_spj_v13.4/tests/test_delivery_ui_phase13.py': 1,
    'pos_spj_v13.4/tests/test_delivery_weight.py': 6,
    'pos_spj_v13.4/tests/test_delivery_whatsapp_notifier.py': 1,
    'pos_spj_v13.4/tests/test_driver_service.py': 3,
    'pos_spj_v13.4/tests/test_fase0_hardware_guards.py': 2,
    'pos_spj_v13.4/tests/test_fase0_produccion_historial_compat.py': 3,
    'pos_spj_v13.4/tests/test_fase0_recetas_integrity.py': 4,
    'pos_spj_v13.4/tests/test_fase0_theme_engine_persistence.py': 1,
    'pos_spj_v13.4/tests/test_fase0_theme_normalization.py': 1,
    'pos_spj_v13.4/tests/test_fase11_hr_rule_engine.py': 3,
    'pos_spj_v13.4/tests/test_fase1_finance_schema_compat.py': 11,
    'pos_spj_v13.4/tests/test_fase1_printer_styles.py': 3,
    'pos_spj_v13.4/tests/test_fase2_bi_cajeros.py': 2,
    'pos_spj_v13.4/tests/test_fase2_loyalty_scanner.py': 3,
    'pos_spj_v13.4/tests/test_fase2_scan_audit.py': 1,
    'pos_spj_v13.4/tests/test_fase3_capital_account.py': 1,
    'pos_spj_v13.4/tests/test_fase3_depreciacion.py': 3,
    'pos_spj_v13.4/tests/test_fase3_rrhh_retenciones.py': 2,
    'pos_spj_v13.4/tests/test_fase4_decision_engine.py': 6,
    'pos_spj_v13.4/tests/test_fase4_rrhh_turnos.py': 6,
    'pos_spj_v13.4/tests/test_fase5_forecast.py': 5,
    'pos_spj_v13.4/tests/test_fase5_inventory_availability_service.py': 1,
    'pos_spj_v13.4/tests/test_fase5_stock_reservations.py': 1,
    'pos_spj_v13.4/tests/test_fase6_ai_cfdi.py': 5,
    'pos_spj_v13.4/tests/test_fase6_franchise.py': 7,
    'pos_spj_v13.4/tests/test_fase6_mercadopago_cleanup.py': 1,
    'pos_spj_v13.4/tests/test_fase_g_api_gateway.py': 10,
    'pos_spj_v13.4/tests/test_fase_g_concurrency.py': 7,
    'pos_spj_v13.4/tests/test_fase_g_inventory_integrity.py': 7,
    'pos_spj_v13.4/tests/test_finance_audit_fixes.py': 11,
    'pos_spj_v13.4/tests/test_finance_remaining_fixes.py': 12,
    'pos_spj_v13.4/tests/test_finance_service_methods.py': 13,
    'pos_spj_v13.4/tests/test_finance_sub_services.py': 8,
    'pos_spj_v13.4/tests/test_financial_core_enforcement.py': 7,
    'pos_spj_v13.4/tests/test_financial_core_phase2.py': 2,
    'pos_spj_v13.4/tests/test_financial_core_phase3.py': 2,
    'pos_spj_v13.4/tests/test_infrastructure_persistence.py': 6,
    'pos_spj_v13.4/tests/test_loyalty_application_service.py': 2,
    'pos_spj_v13.4/tests/test_loyalty_bugfix_regression.py': 4,
    'pos_spj_v13.4/tests/test_loyalty_canonical_migration.py': 13,
    'pos_spj_v13.4/tests/test_loyalty_redemption_source.py': 3,
    'pos_spj_v13.4/tests/test_loyalty_redemption_transactional.py': 2,
    'pos_spj_v13.4/tests/test_loyalty_refactor_regression.py': 9,
    'pos_spj_v13.4/tests/test_loyalty_repository_phase2.py': 5,
    'pos_spj_v13.4/tests/test_loyalty_single_accrual.py': 3,
    'pos_spj_v13.4/tests/test_mercado_pago_webhook_confirmation.py': 1,
    'pos_spj_v13.4/tests/test_new_services.py': 20,
    'pos_spj_v13.4/tests/test_notification_policy.py': 4,
    'pos_spj_v13.4/tests/test_order_badge_service.py': 8,
    'pos_spj_v13.4/tests/test_order_totals_phase8.py': 3,
    'pos_spj_v13.4/tests/test_phase0_hardening_regression.py': 5,
    'pos_spj_v13.4/tests/test_phase3_query_services.py': 4,
    'pos_spj_v13.4/tests/test_phase6_sale_loyalty_policy.py': 2,
    'pos_spj_v13.4/tests/test_production_cost_service.py': 6,
    'pos_spj_v13.4/tests/test_production_query_service.py': 14,
    'pos_spj_v13.4/tests/test_purchase_repository.py': 4,
    'pos_spj_v13.4/tests/test_raffle_financial_safety.py': 1,
    'pos_spj_v13.4/tests/test_raffle_rules_engine.py': 1,
    'pos_spj_v13.4/tests/test_receta_repository_phase3.py': 4,
    'pos_spj_v13.4/tests/test_recipe_components_quantities_phase4.py': 8,
    'pos_spj_v13.4/tests/test_recipe_engine_costing_phase6.py': 8,
    'pos_spj_v13.4/tests/test_recipe_engine_tipo_receta_normalization.py': 7,
    'pos_spj_v13.4/tests/test_recipe_resolver.py': 4,
    'pos_spj_v13.4/tests/test_recipe_service.py': 4,
    'pos_spj_v13.4/tests/test_refactor_v133.py': 5,
    'pos_spj_v13.4/tests/test_rrhh_application_services_phase3.py': 5,
    'pos_spj_v13.4/tests/test_rrhh_finance_phase6.py': 1,
    'pos_spj_v13.4/tests/test_rrhh_phase10_payroll_application_service.py': 2,
    'pos_spj_v13.4/tests/test_rrhh_phase7_payroll_financial_trace_integration.py': 4,
    'pos_spj_v13.4/tests/test_rrhh_phase8_cleanup.py': 5,
    'pos_spj_v13.4/tests/test_rrhh_phase9_identity_links.py': 3,
    'pos_spj_v13.4/tests/test_rrhh_repositories_phase1.py': 6,
    'pos_spj_v13.4/tests/test_sale_fulfillment_phase5.py': 4,
    'pos_spj_v13.4/tests/test_sale_inventory_handler.py': 4,
    'pos_spj_v13.4/tests/test_sales_customer_loyalty.py': 16,
    'pos_spj_v13.4/tests/test_sales_no_duplication.py': 7,
    'pos_spj_v13.4/tests/test_sales_no_duplication_real.py': 10,
    'pos_spj_v13.4/tests/test_sales_stock_validation_regression.py': 8,
    'pos_spj_v13.4/tests/test_sync_service_cursor_compat.py': 3,
    'pos_spj_v13.4/tests/test_third_party_service_unified.py': 2,
    'pos_spj_v13.4/tests/test_ticket_branding_from_system_config.py': 1,
    'pos_spj_v13.4/tests/test_ticket_layout_repository_regression.py': 1,
    'pos_spj_v13.4/tests/test_ticket_rendering_regression.py': 7,
    'pos_spj_v13.4/tests/test_traceability_phase9.py': 12,
    'pos_spj_v13.4/tests/test_uc_inventario.py': 2,
    'pos_spj_v13.4/tests/test_ventas_fixes.py': 3,
    'pos_spj_v13.4/tests/test_wa_bridge.py': 10,
    'pos_spj_v13.4/tests/test_wa_parser.py': 2,
    'pos_spj_v13.4/tests/test_wa_refactor.py': 3,
    'pos_spj_v13.4/tests/test_wa_repositories.py': 5,
}

HARDCODED_NUMERIC_DEFAULTS_IN_UI_ALLOWLIST = {
    'pos_spj_v13.4/interfaz/diagnostico.py': 3,
    'pos_spj_v13.4/modulos/caja.py': 1,
    'pos_spj_v13.4/modulos/compras/totals_panel.py': 1,
    'pos_spj_v13.4/modulos/compras_pro.py': 2,
    'pos_spj_v13.4/modulos/config_hardware.py': 1,
    'pos_spj_v13.4/modulos/configuracion.py': 5,
    'pos_spj_v13.4/modulos/cotizaciones.py': 1,
    'pos_spj_v13.4/modulos/delivery.py': 3,
    'pos_spj_v13.4/modulos/etiquetas.py': 2,
    'pos_spj_v13.4/modulos/fidelidad_config.py': 5,
    'pos_spj_v13.4/modulos/loyalty_card_designer.py': 1,
    'pos_spj_v13.4/modulos/modulo_growth_engine.py': 3,
    'pos_spj_v13.4/modulos/planeacion_compras.py': 2,
    'pos_spj_v13.4/modulos/productos.py': 1,
    'pos_spj_v13.4/modulos/recepcion_qr_widget.py': 2,
    'pos_spj_v13.4/modulos/rrhh.py': 3,
    'pos_spj_v13.4/modulos/rrhh_turnos.py': 1,
    'pos_spj_v13.4/modulos/ticket_designer.py': 2,
    'pos_spj_v13.4/modulos/transferencias.py': 1,
}

PLAIN_PHONE_INPUTS_ALLOWLIST = {
    'pos_spj_v13.4/modulos/configuracion.py': 9,
    'pos_spj_v13.4/modulos/finanzas_unificadas.py': 1,
    'pos_spj_v13.4/modulos/whatsapp/panels/credentials_panel.py': 1,
    'pos_spj_v13.4/modulos/whatsapp/panels/numbers_panel.py': 1,
}

ENTITY_COMBO_MASS_LOADING_ALLOWLIST = {
    'pos_spj_v13.4/modulos/activos.py': 7,
    'pos_spj_v13.4/modulos/compras_pro.py': 14,
    'pos_spj_v13.4/modulos/config_modules.py': 3,
    'pos_spj_v13.4/modulos/configuracion.py': 13,
    'pos_spj_v13.4/modulos/cotizaciones.py': 1,
    'pos_spj_v13.4/modulos/delivery.py': 9,
    'pos_spj_v13.4/modulos/dialogs/receta_dialog.py': 5,
    'pos_spj_v13.4/modulos/finanzas_unificadas.py': 2,
    'pos_spj_v13.4/modulos/loyalty_card_designer.py': 1,
    'pos_spj_v13.4/modulos/planeacion_compras.py': 2,
    'pos_spj_v13.4/modulos/produccion.py': 5,
    'pos_spj_v13.4/modulos/productos.py': 7,
    'pos_spj_v13.4/modulos/recepcion_qr_widget.py': 5,
    'pos_spj_v13.4/modulos/rrhh.py': 6,
    'pos_spj_v13.4/modulos/ticket_designer.py': 1,
    'pos_spj_v13.4/modulos/transferencias.py': 3,
    'pos_spj_v13.4/modulos/ventas.py': 1,
    'pos_spj_v13.4/modulos/whatsapp/panels/numbers_panel.py': 2,
}

HARDCODED_RELATIVE_PATHS_ALLOWLIST = {
    'pos_spj_v13.4/core/integrations/whatsapp_client.py': 1,
    'pos_spj_v13.4/core/ticket_escpos_renderer.py': 1,
    'pos_spj_v13.4/interfaz/menu_lateral.py': 1,
    'pos_spj_v13.4/modulos/base.py': 1,
    'pos_spj_v13.4/modulos/clientes.py': 2,
    'pos_spj_v13.4/tests/test_fase0_finanzas_syntax.py': 3,
    'pos_spj_v13.4/tests/test_fase0_menu_lateral.py': 3,
    'pos_spj_v13.4/tests/test_fase0_ventas_canje.py': 2,
    'pos_spj_v13.4/tests/test_fase0_ventas_peso_hal.py': 3,
    'pos_spj_v13.4/tests/test_fase1_plan_mejora.py': 1,
    'pos_spj_v13.4/tests/test_fase1_uiux_module_guards.py': 5,
    'pos_spj_v13.4/tests/test_fase2_ui_resultado_venta_postcommit.py': 1,
    'pos_spj_v13.4/tests/test_fase5_inventory_availability_service.py': 1,
    'pos_spj_v13.4/tests/test_fase8_no_legacy_conflicts.py': 1,
    'pos_spj_v13.4/tests/test_finanzas_kpi_refresh_wiring.py': 2,
    'pos_spj_v13.4/tests/test_loyalty_event_wiring_phase7.py': 3,
    'pos_spj_v13.4/tests/test_phase11_payment_dialog_extraction.py': 2,
    'pos_spj_v13.4/tests/test_phase2_pos_venta_usa_uc.py': 2,
    'pos_spj_v13.4/tests/test_ticket_pipeline_integration.py': 3,
    'pos_spj_v13.4/tests/test_transferencias_event_bus_usage.py': 1,
    'pos_spj_v13.4/ver_table.py': 1,
}

APPCONTAINER_PASSED_TO_SERVICES_ALLOWLIST = {
    'pos_spj_v13.4/application/purchases/purchase_order_uc.py': 2,
    'pos_spj_v13.4/application/purchases/purchase_request_uc.py': 2,
    'pos_spj_v13.4/application/purchases/receive_po_adapter.py': 1,
    'pos_spj_v13.4/application/purchases/traditional_purchase_uc.py': 2,
    'pos_spj_v13.4/application/use_cases/registrar_compra_uc.py': 1,
    'pos_spj_v13.4/core/services/cotizacion_service.py': 1,
    'pos_spj_v13.4/core/services/production_application_service.py': 2,
    'pos_spj_v13.4/core/services/sales_service.py': 2,
    'pos_spj_v13.4/core/use_cases/cliente.py': 2,
    'pos_spj_v13.4/core/use_cases/compra.py': 2,
    'pos_spj_v13.4/core/use_cases/nomina.py': 1,
    'pos_spj_v13.4/core/use_cases/venta.py': 2,
    'pos_spj_v13.4/notifications/service.py': 1,
    'pos_spj_v13.4/services/bot_pedidos.py': 1,
    'pos_spj_v13.4/services/mercado_pago_service.py': 1,
    'pos_spj_v13.4/tests/test_production_application_service.py': 1,
}

DEPRECATED_SERVICES_WITH_BUSINESS_LOGIC_ALLOWLIST = {
    'pos_spj_v13.4/core/delivery/application/legacy_event_bridge.py': 1,
}

# Remediación D — Diálogos que aún ejecutan lógica de persistencia/publicación.
# Contrato objetivo: un QDialog SOLO captura → DTO/Command; el módulo delega en
# un servicio. Cada entrada es "path::Clase" con las llamadas prohibidas que aún
# contiene. Este allowlist es un RATCHET: no se admiten entradas nuevas y, cuando
# un diálogo se limpia, su entrada DEBE retirarse (el test falla si queda obsoleta).
# Referencia: DEEP_AUDIT_ALL_MODULES §8 y §17 (Remediación D), test T8.
DIALOG_BUSINESS_LOGIC_ALLOWLIST = {
    # Vacío: ningún QDialog en modulos/, ui/ o interfaz/ ejecuta SQL/commit/
    # publish/asiento. El contrato queda enforced sin deuda tolerada.
}
