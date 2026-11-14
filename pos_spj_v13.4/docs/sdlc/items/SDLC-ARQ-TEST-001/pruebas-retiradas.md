# SDLC-ARQ-TEST-001 — Pruebas retiradas

118 archivos de `tests/*.py` importaban, a nivel de módulo, paquetes del repositorio que
ya no existen (`core.*`, `repositories.*`, `modulos.*`…). No colectaban: `ModuleNotFoundError` antes
de la primera prueba, así que no protegían nada, y ningún job de `ci-segmented.yml` los corre
(CI usa `tests/architecture`, `tests/unit`, `tests/integration` y `tests/ui`). No se resucitó código.

Medición: análisis AST de los imports de cada archivo contra el árbol real, sin ejecutarlos.

| Archivo | Módulos que ya no existen | Destino |
|---|---|---|
| `tests/test_analytics_profitability_fallback.py` | `core.services.analytics.analytics_engine` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_bi_charts.py` | `modulos.bi_charts` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_bi_dashboard_view.py` | `modulos.bi_dashboard_view` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_bloque2_query_service.py` | `core.services.production_query_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_card_subsystem_born_clean.py` | `core.services.card_batch_engine`, `repositories.tarjetas` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_catalog_hot_refresh.py` | `core.events.catalog_events`, `core.events.domain_events`, `core.events.event_bus` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_cliente_repository_schema_compat.py` | `repositories.cliente_repository` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_crm_29_session_permission_wildcard.py` | `core.session_context` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_action_policy.py` | `modulos.delivery` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_application_use_cases.py` | `core.delivery.application.activate_scheduled_order`, `core.delivery.application.adjust_delivery_weight`, `core.delivery.application.cancel_delivery_order`, `core.delivery.application.change_delivery_status`, `core.delivery.application.create_delivery_order`, `core.delivery.application.sync_whatsapp_orders`, `core.delivery.projections.sale_delivery_projection`, `core.services.delivery_service`, `core.services.order_total_service`, `repositories.delivery_repository` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_board_query_route.py` | `core.delivery.application.query_service`, `core.delivery.domain.value_objects` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_domain_entities.py` | `core.delivery.domain.entities`, `core.delivery.domain.states`, `core.delivery.domain.value_objects` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_domain_events.py` | `core.delivery.domain.events` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_finance_integration.py` | `core.events.handlers.delivery_finance_handler`, `core.events.handlers.delivery_handler` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_history_audit.py` | `core.delivery.application.activate_scheduled_order`, `core.delivery.application.cancel_delivery_order`, `core.delivery.application.change_delivery_status`, `repositories.delivery_repository` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_inventory_projection.py` | `core.delivery.application.process_delivery_outbox`, `core.delivery.infrastructure.delivery_outbox_repository`, `core.delivery.infrastructure.inventory_reservation_adapter`, `core.delivery.projections.delivery_inventory_projection`, `repositories.delivery_repository` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_legacy_event_bridge.py` | `core.delivery.application.legacy_event_bridge`, `core.delivery.domain.events`, `core.events.event_bus` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_lifecycle.py` | `core.events.handlers.delivery_handler` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_outbox.py` | `core.delivery.application.change_delivery_status`, `core.delivery.application.create_delivery_order`, `core.delivery.application.process_delivery_outbox`, `core.delivery.infrastructure.delivery_outbox_repository`, `repositories.delivery_repository` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_phase12_required.py` | `core.delivery.application.change_delivery_status`, `core.delivery.application.create_delivery_order`, `core.delivery.application.process_delivery_outbox`, `core.delivery.infrastructure.delivery_outbox_repository`, `core.delivery.infrastructure.inventory_reservation_adapter`, `core.delivery.projections.delivery_inventory_projection`, `core.delivery.projections.sale_delivery_projection`, `core.services.delivery_service`, `core.services.order_total_service`, `repositories.delivery_repository` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_printing.py` | `core.delivery.application.print_coordinator`, `core.delivery.domain.print_policy` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_refactor.py` | `core.delivery.application.action_policy`, `core.delivery.application.dto`, `core.delivery.application.kanban_config`, `core.delivery.application.quantity_formatter`, `core.delivery.application.query_service`, `core.delivery.domain.value_objects`, `core.delivery.domain.workflow_policy` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_repository_list_orders.py` | `repositories.delivery_repository` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_reservation_credit.py` | `core.delivery.domain.credit_policy`, `core.services.reservation_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_sale_projection.py` | `core.delivery.projections.sale_delivery_projection`, `core.services.delivery_service`, `core.services.order_total_service`, `repositories.delivery_repository` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_schema_migrator.py` | `core.delivery.infrastructure.delivery_schema_migrator`, `core.services.delivery_service`, `repositories.delivery_repository` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_service.py` | `core.services.delivery_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_service_action_policy.py` | `core.services.delivery_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_state_machine.py` | `core.delivery.domain.entities`, `core.delivery.domain.state_machine`, `core.delivery.domain.states` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_ticket_uses_escpos.py` | `core.services.ticket_printer_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_ui_filters.py` | `core.utils.delivery_ui_filters` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_ui_phase13.py` | `core.delivery.infrastructure.delivery_schema_migrator`, `core.services`, `core.services.delivery_service`, `integrations.delivery_pwa` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_unit_formatter.py` | `core.delivery.application.quantity_formatter`, `core.delivery.domain.value_objects` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_unit_resolution.py` | `core.delivery.domain.value_objects`, `core.services.delivery_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_weight_policy.py` | `core.delivery.domain.policies`, `core.delivery.domain.states`, `core.delivery.domain.workflow_policy` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_delivery_whatsapp_notifier.py` | `core.delivery.application.adjust_delivery_weight`, `core.delivery.application.change_delivery_status`, `core.delivery.application.create_delivery_order`, `core.delivery.infrastructure.delivery_outbox_repository`, `core.delivery.infrastructure.whatsapp_delivery_notifier`, `core.events.handlers.delivery_handler`, `repositories.delivery_repository` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_desktop_notification_service.py` | `core.services.desktop_notification_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_domain_entities.py` | `domain.entities.customer`, `domain.entities.product`, `domain.entities.purchase`, `domain.entities.sale`, `domain.services.sale_domain_service`, `domain.value_objects.money`, `domain.value_objects.quantity` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_driver_service.py` | `core.services.driver_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_event_factory_produccion.py` | `core.events.event_factory`, `core.events.handlers.production_handler` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_eventbus_strict.py` | `core.events.event_bus` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_fase0_hardware_guards.py` | `core.services.hardware_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_fase1_finance_schema_compat.py` | `core.services.enterprise.finance_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_fase1_procesar_venta_uc_rich_mapping.py` | `core.use_cases.venta` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_fase3_printer_service_reliability.py` | `core.services.printer_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_fase4_payment_mapping.py` | `core.services.sales.payment_policy` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_fase4_stock_validation.py` | `core.use_cases.venta` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_fase5_inventory_availability_service.py` | `core.services.inventory_availability_service`, `core.services.stock_reservation_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_fase5_stock_reservations.py` | `core.services.stock_reservation_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_fase6_mercadopago_cleanup.py` | `core.services.sales_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_fase7_critical_handlers.py` | `core.events.domain_events`, `core.events.event_bus`, `core.services.sales_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_fase8_no_silent_passes.py` | `core.events.domain_events`, `core.events.event_bus` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_fase9_legacy_sales_blocked.py` | `core.services.sales.unified_sales_service`, `core.services.sales_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_installation_branch_resolution.py` | `core.services.branch_resolution`, `repositories.auth_repository`, `repositories.config_repository` | Reescrita: `tests/integration/configuracion/test_installation_branch_resolution.py`. |
| `tests/test_inventory.py` | `core.services.inventory.unified_inventory_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_legacy_venta_repository_guardrail.py` | `repositories.ventas` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_loyalty_application_service.py` | `application.services.loyalty_application_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_loyalty_bugfix_regression.py` | `application.services.loyalty_application_service`, `core.events.event_bus`, `core.events.wiring`, `core.services.loyalty_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_loyalty_raffle_issue_tickets.py` | `core.services.loyalty_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_loyalty_redemption_transactional.py` | `core.services.loyalty_service`, `core.services.sales_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_loyalty_refactor_regression.py` | `application.services.loyalty_application_service`, `core.events.event_bus`, `core.events.wiring`, `core.services.loyalty_service`, `core.services.sales_service`, `repositories.loyalty_repository` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_loyalty_repository_phase2.py` | `repositories.loyalty_repository` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_loyalty_single_accrual.py` | `core.events.event_bus`, `core.events.wiring`, `core.services.loyalty_service`, `core.use_cases.venta` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_main_window_repository.py` | `repositories.main_window_repository` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_mercado_pago_webhook_confirmation.py` | `core.services.sales_service`, `services.mercado_pago_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_order_badge_service.py` | `core.services.order_badge_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_order_mappers.py` | `core.domain.order_models`, `core.mappers.order_mapper`, `core.mappers.status_mapper` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_order_totals_phase8.py` | `core.services.delivery_service`, `core.services.order_total_service`, `repositories.delivery_repository` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_payment_method_normalization.py` | `core.services.payment_normalization` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_phase0_hardening_regression.py` | `core.events.outbox`, `core.events.outbox_dispatcher`, `core.services.auth_service`, `core.services.sales.unified_sales_service`, `core.services.sales_reversal_service`, `core.services.sales_service`, `repositories.auth_repository` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_phase10_sales_reversal_events.py` | `core.services.sales_reversal_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_phase12_regression_matrix.py` | `core.services.sales.cart_calculator`, `core.services.sales.payment_policy`, `core.use_cases.venta` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_phase2_procesar_venta_uc.py` | `core.use_cases.venta` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_phase3_query_services.py` | `core.services.sales.customer_lookup_service`, `core.services.sales.product_catalog_query_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_phase4_cart_calculator.py` | `core.services.sales.cart_calculator` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_phase5_payment_policy.py` | `core.services.sales.payment_policy` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_phase6_sale_loyalty_policy.py` | `core.services.sales.sale_loyalty_policy` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_printer_service_config_validation.py` | `core.services.printer_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_procesar_venta_uc_no_duplicate_side_effects.py` | `core.use_cases.venta` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_production_application_phase8_flow.py` | `core.services.production_application_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_production_application_service.py` | `core.services.production_application_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_production_cost_service.py` | `core.events.handlers.production_handler`, `core.services.finance.production_cost_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_production_query_service.py` | `core.services.production_query_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_raffle_financial_safety.py` | `core.events`, `core.services.loyalty_service`, `repositories.loyalty_repository` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_raffle_rules_engine.py` | `core.services.loyalty_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_raffle_sales_pos_cutover.py` | `core.services.loyalty_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_receta_repository_phase3.py` | `repositories.recetas` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_recipe_components_quantities_phase4.py` | `core.services.recipe_engine`, `repositories.recetas` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_recipe_engine_costing_phase6.py` | `core.services.recipe_engine` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_recipe_engine_tipo_receta_normalization.py` | `core.services.recipe_engine` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_recipe_events.py` | `core.events.event_bus`, `core.services.recipes.recipe_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_recipe_service.py` | `core.services.recipes.recipe_service`, `repositories.recetas` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_recipe_validation.py` | `core.services.recipes.recipe_validation_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_rrhh_phase8_cleanup.py` | `core.services.driver_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_sale_execution_result.py` | `core.services.sales.sale_execution_result`, `core.services.sales_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_sales.py` | `core.services.sales.unified_sales_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_sales_event_flow.py` | `core.events.handlers.finance_handler` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_sales_no_duplication_real.py` | `core.events.event_bus`, `core.services.loyalty_service`, `core.services.sales_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_sales_phase1_dtos.py` | `core.use_cases.venta` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_sales_service_single_event_flow.py` | `core.services.sales_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_scheduled_demand_service.py` | `core.services.scheduled_demand_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_sync_service_cursor_compat.py` | `core.services.sync_service` | `SyncService` se retiró; la cola la lleva `ReplicationOutboxService`, cubierta por `tests/integration/sync/test_replication_outbox.py`. |
| `tests/test_system_health_repository.py` | `repositories.system_health_repository` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_ticket_branding_from_system_config.py` | `core.tickets.branding_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_ticket_escpos_renderer.py` | `core.ticket_escpos_renderer` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_ticket_layout_config.py` | `core.tickets.ticket_layout_config` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_ticket_layout_repository_regression.py` | `core.tickets.ticket_layout_config`, `core.tickets.ticket_layout_repository` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_ticket_message_engine.py` | `core.tickets.ticket_message_engine` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_ticket_pipeline_integration.py` | `core.ticket_escpos_renderer`, `core.tickets.ticket_message_engine`, `core.tickets.ticket_print_model` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_ticket_print_model.py` | `core.tickets.ticket_print_model` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_ticket_rendering_regression.py` | `core.services.printer_service`, `core.ticket_escpos_renderer`, `core.tickets.raffle_ticket_renderer`, `core.tickets.ticket_layout_config` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_traceability_phase9.py` | `core.services.recipe_engine`, `core.services.sales_service` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_uc_cliente.py` | `core.use_cases.cliente` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_uc_compra.py` | `core.use_cases.compra` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_ventas_cleanup_regression.py` | `core.services.sales.sale_execution_result`, `core.services.sales_service`, `core.use_cases.venta` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_wa_admin_bounded_context_visibility.py` | `core.repositories.whatsapp_history_repository`, `core.repositories.whatsapp_metrics_repository` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_wa_client.py` | `core.integrations.whatsapp_client` | Código borrado; sin reemplazo directo en esta prueba. |
| `tests/test_wa_repositories.py` | `core.repositories.whatsapp_config_repository`, `core.repositories.whatsapp_history_repository`, `core.repositories.whatsapp_metrics_repository`, `core.services.whatsapp_admin_service`, `core.services.whatsapp_credential_service` | Código borrado; sin reemplazo directo en esta prueba. |

## Segundo grupo: importan código borrado dentro de cada prueba

55 archivos colectaban, pero el import faltante está dentro de las funciones y
ninguna de sus pruebas pasa. Medido con la corrida de los archivos sueltos restantes:
`774 failed, 158 passed, 14 skipped, 159 errors`; el motivo dominante es
`ModuleNotFoundError` (1361 apariciones) y `FileNotFoundError` (193).

| Archivo | Módulos que ya no existen | Fallan | Error |
|---|---|---|---|
| `tests/test_application_layer.py` | `application.dtos.sale_dto`, `application.use_cases` | 7 | 0 |
| `tests/test_asset_service_ui_reads.py` | `core.services.asset_service` | 0 | 8 |
| `tests/test_audit_service_registrar.py` | `core.services.audit_service` | 3 | 0 |
| `tests/test_bi_rentabilidad_franchise_bugs.py` | `core.services.analytics.analytics_engine`, `core.services.decision_engine`, `core.services.franchise_manager` | 7 | 0 |
| `tests/test_bi_reportes_service_reads.py` | `core.services.export_service`, `repositories.bi_repository` | 4 | 0 |
| `tests/test_bloque3_motor_unificado.py` | `core.production.production_engine`, `core.services.production_application_service`, `core.services.recipe_engine` | 21 | 0 |
| `tests/test_bootstrap_wiring.py` | `core.services.enterprise.finance_service`, `core.services.forecast_engine`, `core.services.inventory_service` | 15 | 0 |
| `tests/test_compras_pro_prov_repo.py` | `repositories.proveedor_repository` | 1 | 0 |
| `tests/test_core_services.py` | `core.services.alertas_service`, `core.services.audit_service`, `core.services.compras_inventariables_engine` y 3 más | 29 | 0 |
| `tests/test_cotizacion_service_ui_reads.py` | `core.services.cotizacion_service` | 3 | 0 |
| `tests/test_credit_sale_backend_validation.py` | `core.events.handlers.finance_handler`, `core.services.payment_normalization`, `core.services.sales_service` y 1 más | 6 | 0 |
| `tests/test_credit_sale_cxc.py` | `application.services.customer_credit_service`, `core.events.handlers.finance_handler` | 14 | 0 |
| `tests/test_delivery_architecture_invariants.py` | `core.delivery.domain`, `core.delivery.domain.value_objects` | 7 | 0 |
| `tests/test_delivery_inventory_integration.py` | `core.services.delivery_service`, `core.services.inventory_balance_service` | 6 | 0 |
| `tests/test_delivery_weight.py` | `core.events.handlers.delivery_handler`, `core.services.delivery_service`, `core.services.delivery_whatsapp_service` y 3 más | 5 | 13 |
| `tests/test_etiquetas_repos.py` | `core.repositories.hardware_config_repository`, `core.services.config_service`, `repositories.config_repository` y 1 más | 3 | 0 |
| `tests/test_event_bus_aliases.py` | `core.events.event_bus` | 5 | 0 |
| `tests/test_event_bus_new_constants.py` | `core.events.event_bus` | 7 | 0 |
| `tests/test_fase0_menu_lateral.py` | `core.module_config` | 10 | 0 |
| `tests/test_fase0_produccion_historial_compat.py` | `core.services.recipe_engine` | 1 | 0 |
| `tests/test_fase0_qss_vars.py` | `config` | 5 | 0 |
| `tests/test_fase0_recetas_integrity.py` | `repositories.recetas` | 4 | 0 |
| `tests/test_fase0_theme_engine_persistence.py` | `ui.themes` | 2 | 0 |
| `tests/test_fase0_theme_normalization.py` | `core.services.theme_service` | 5 | 0 |
| `tests/test_fase11_expansion_analyzer.py` | `core.services.expansion_analyzer` | 30 | 0 |
| `tests/test_fase1_design_tokens.py` | `modulos.spj_styles` | 9 | 0 |
| `tests/test_fase1_plan_mejora.py` | `core.services.printer_service` | 4 | 0 |
| `tests/test_fase1_printer_transport.py` | `core.services.printer_service` | 12 | 0 |
| `tests/test_fase1_uiux_runtime.py` | `modulos.ui_components` | 3 | 0 |
| `tests/test_fase2_scan_audit.py` | `core.services.qr_parser_service` | 14 | 0 |
| `tests/test_fase3_capital_account.py` | `core.services.finance.treasury_service` | 17 | 0 |
| `tests/test_fase3_depreciacion.py` | `core.services.asset_service` | 14 | 0 |
| `tests/test_fase4_decision_engine.py` | `core.services.decision_engine` | 11 | 0 |
| `tests/test_fase5_forecast.py` | `core.services.actionable_forecast`, `core.services.forecast_engine` | 15 | 0 |
| `tests/test_fase6_ai_cfdi.py` | `core.services.ai_advisor`, `core.services.cfdi_service` | 16 | 0 |
| `tests/test_fase6_franchise.py` | `core.services.franchise_manager` | 12 | 0 |
| `tests/test_fase_g_inventory_integrity.py` | `core.services.erp_application_service` | 9 | 0 |
| `tests/test_finance_service_methods.py` | `core.services.enterprise.finance_service` | 25 | 0 |
| `tests/test_financial_core_enforcement.py` | `application.services.customer_credit_service`, `core.events.domain_events`, `core.events.handlers.finance_handler` y 2 más | 16 | 0 |
| `tests/test_financial_core_phase3.py` | `core.services.finance.treasury_service`, `core.services.loyalty_service` | 13 | 0 |
| `tests/test_financial_core_phase4.py` | `core.services.sales_reversal_service` | 21 | 0 |
| `tests/test_infrastructure_persistence.py` | `infrastructure.persistence.sqlite_sales_repository` | 0 | 12 |
| `tests/test_login_no_silent_quit.py` | `core.app_container`, `interfaz`, `interfaz.main_window` | 3 | 4 |
| `tests/test_loyalty_card_designer_service.py` | `core.services.loyalty_card_designer_service` | 5 | 0 |
| `tests/test_loyalty_redemption_source.py` | `core.services.loyalty_service` | 17 | 0 |
| `tests/test_notification_policy.py` | `core.services.notification_service`, `core.services.notifications.notification_dispatcher`, `core.services.notifications.notification_policy_service` | 4 | 17 |
| `tests/test_refactor_v133.py` | `core.domain.events`, `core.events.event_bus`, `sync.conflict_resolver` y 4 más | 28 | 0 |
| `tests/test_sales_customer_loyalty.py` | `application.services.customer_credit_service`, `core.events.domain_events`, `core.events.event_bus` y 5 más | 0 | 8 |
| `tests/test_sales_no_duplication.py` | `core.services.sales_service`, `repositories.sales_repository`, `repositories.ventas` | 5 | 0 |
| `tests/test_ticket_designer_config_route.py` | `core.services.config_service`, `repositories.config_repository` | 0 | 3 |
| `tests/test_ticket_three_bugs.py` | `core.engines.template_engine`, `core.services.sales_service`, `core.ticket_escpos_renderer` | 11 | 0 |
| `tests/test_uc_finanzas.py` | `core.use_cases.finanzas` | 3 | 6 |
| `tests/test_uc_inventario.py` | `core.use_cases.inventario` | 12 | 0 |
| `tests/test_uc_produccion.py` | `core.use_cases.produccion` | 14 | 0 |
| `tests/test_ventas_fixes.py` | `core.services.inventory.unified_inventory_service`, `repositories.cliente_repository`, `repositories.productos` | 11 | 0 |

## Se conservan: requieren revisión prueba por prueba

No se retiraron porque algo en ellos pasa, o porque no importan código borrado y su fallo
puede ser una señal real. No corren en CI. Quedan para SDLC-CORE-011 o un ítem nuevo.

**Con pruebas que pasan y otras que fallan (20):** `tests/test_bloque1_p0_fixes.py`, `tests/test_credit_flow_refactor.py`, `tests/test_fase1_printer_styles.py`, `tests/test_fase2_loyalty_scanner.py`, `tests/test_fase2_qr_parser.py`, `tests/test_fase3_plan_cuentas.py`, `tests/test_fase_g_concurrency.py`, `tests/test_finance_remaining_fixes.py`, `tests/test_finance_sub_services.py`, `tests/test_flujo_completo.py`, `tests/test_migration_052.py`, `tests/test_migration_audit.py`, `tests/test_new_services.py`, `tests/test_phase17_uuid_schema_and_flow.py`, `tests/test_remediacion_c_born_clean_ddl.py`, `tests/test_remediacion_c_wa_uuid.py`, `tests/test_uuid_only_guard_rails.py`, `tests/test_wa_orchestrator.py`, `tests/test_wa_parser.py`, `tests/test_wa_refactor.py`.

**Sin imports faltantes y sin ningún pase (16):** `tests/test_db_bootstrap.py`, `tests/test_fase0_finanzas_syntax.py`, `tests/test_fase0_login_ui.py`, `tests/test_fase0_ui_components.py`, `tests/test_fase1_uiux_module_guards.py`, `tests/test_fase1_uiux_refresh.py`, `tests/test_fase_g_api_gateway.py`, `tests/test_loyalty_canonical_migration.py`, `tests/test_mercado_pago_pending_flow.py`, `tests/test_no_qprinter_for_thermal_tickets.py`, `tests/test_sales_operation_id_contract.py`, `tests/test_ticket_designer_raffle_layout_contract.py`, `tests/test_ticket_designer_ui_contract.py`, `tests/test_ui_does_not_publish_inventory_business_events.py`, `tests/test_wa_bridge.py`, `tests/test_wa_phase9_regression.py`.

**Sin resultado en la corrida (colección):** `tests/test_crm_40_api_auth_no_default_key.py`,
`tests/test_delivery_product_search_refactor.py`, `tests/test_notifications.py`.
