# Grafo inicial PK/FK UUIDv7

## Estado

```text
IN_PROGRESS
```

## Resumen

- Archivos de schema escaneados: 106
- Archivos con señales de schema/identidad: 78
- Tablas detectadas: 382
- FKs declaradas detectadas: 53
- Columnas `id`/`*_id` detectadas: 792
- Archivos con `INTEGER PRIMARY KEY AUTOINCREMENT`: 55

## Archivos con AUTOINCREMENT

```text
migrations/093_create_delivery_core.sql
migrations/094_add_delivery_outbox.sql
migrations/engine.py
migrations/m000_base_schema.py
migrations/m050_hardware_config_canonical.py
migrations/standalone/016_concurrency_events.py
migrations/standalone/023_enterprise_upgrade.py
migrations/standalone/024_enterprise_blocks_5_8.py
migrations/standalone/025_sync_batch_log.py
migrations/standalone/026_final_structural_hardening.py
migrations/standalone/027_inventory_hardening.py
migrations/standalone/028_sales_transaction_hardening.py
migrations/standalone/029_reversals_hardening.py
migrations/standalone/030_recetas_industriales.py
migrations/standalone/031_inventory_engine.py
migrations/standalone/032_bi_tables.py
migrations/standalone/032_meat_production.py
migrations/standalone/033_demand_forecast.py
migrations/standalone/035_finance_erp.py
migrations/standalone/036_whatsapp_rasa.py
migrations/standalone/038_transfer_suggestions.py
migrations/standalone/040_qr_reception.py
migrations/standalone/041_notification_inbox.py
migrations/standalone/042_whatsapp_multicanal.py
migrations/standalone/043_price_history.py
migrations/standalone/044_cotizaciones.py
migrations/standalone/046_comisiones_happy_hour.py
migrations/standalone/047_v13_schema.py
migrations/standalone/049_v134_intelligent_erp.py
migrations/standalone/050_wa_integration.py
migrations/standalone/051_fix_kpi_snapshots.py
migrations/standalone/052_financial_event_log.py
migrations/standalone/053_meat_production_tables.py
migrations/standalone/056_print_job_log.py
migrations/standalone/057_loyalty_ledger_unificado.py
migrations/standalone/058_scan_event_log.py
migrations/standalone/059_plan_cuentas.py
migrations/standalone/060_depreciacion_acumulada.py
migrations/standalone/062_bi_analytics_tables.py
migrations/standalone/063_audit_log_table.py
migrations/standalone/066_erp_financial_model.py
migrations/standalone/067_meat_erp_improvements.py
migrations/standalone/070_delivery_enterprise_lifecycle.py
migrations/standalone/073_temp_purchase_drafts.py
migrations/standalone/075_plantillas_compra.py
migrations/standalone/076_purchase_requests.py
migrations/standalone/077_purchase_requests.py
migrations/standalone/082_treasury_tables.py
migrations/standalone/083_financial_traceability_tables.py
migrations/standalone/084_capital_movements.py
migrations/standalone/091_scheduled_demand_events.py
migrations/standalone/092_loyalty_ledger_canonicalization.py
migrations/standalone/094_rrhh_delivery_cleanup_schema.py
migrations/standalone/096_configuration_services_schema.py
migrations/standalone/098_canonical_inventory.py
```

## Entradas por archivo

Consultar `UUIDV7_SCHEMA_GRAPH.json` para el inventario completo generado por archivo.

## Próxima acción

Completar clasificación de cada tabla como entidad funcional UUID, tabla técnica o deuda legacy antes de diseñar la migración atómica.
