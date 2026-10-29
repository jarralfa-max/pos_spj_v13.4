# Backlog SDLC

Fuente única del trabajo pendiente. `/sdlc-plan triage` y `/sdlc-maintain` agregan filas; cada comando de etapa actualiza la columna **Etapa**. Ordena por prioridad (P0 primero).

Etapas válidas: `intent-borrador` · `intent-aprobado` · `spec-borrador` · `spec-aprobado` · `plan-borrador` · `plan-aprobado` · `en-build` · `en-test` · `listo-deploy` · `liberado` · `descartado`.

> **Triage 2026-10-28** (commit `16eb1d8e`): 74 ítems — P0 8 · P1 30 · P2 26 · P3 10; T0 43 · T1 28 · T2 3. Línea base en `baseline/2026-10-28.md`. Fuentes: barrido por bounded context (5 grupos), auditoría `docs/audits/auditoria_integral_produccion_recepcion_transferencias_productos_precios_2026-10-26.md` (sus P0 siguen abiertos: `git diff 9f7d9f61 HEAD` no toca esos archivos), `docs/refactor/*_validacion_final*` y `work_queue.json` (pipeline CONFIGURACION: 5 DONE, `CONFIGURACION-06-DOMAIN_RULES` IN_PROGRESS, 11 PENDING — referenciado por SDLC-SET-002/003, no duplicado). La columna **Evidencia** lleva la primera ruta; la lista completa está en cada `intent.md`.

| ID | Prioridad | Nivel | Título | Evidencia (ruta:línea o prueba) | Etapa | Rama | Depende de |
|---|---|---|---|---|---|---|---|
| [SDLC-INST-001](items/SDLC-INST-001/intent.md) | P0 | T0 | El actualizador confía en update_job.json escribible por cualquier usuario local | `backend/shared/app_paths.py:230-231` | intent-borrador | — | — |
| [SDLC-INV-001](items/SDLC-INV-001/intent.md) | P0 | T0 | Ajustes, diferencias de conteo y disposición de cuarentena sin asiento contable | `backend/application/finance/wiring.py:22` | intent-borrador | — | — |
| [SDLC-LOSS-001](items/SDLC-LOSS-001/intent.md) | P0 | T0 | Mermas: ningún caso puede aprobarse, y al habilitarlo una revaluación asentaría doble | `backend/domain/losses/entities/loss_case.py:70` | intent-borrador | — | — |
| [SDLC-SALES-001](items/SDLC-SALES-001/intent.md) | P0 | T0 | Falla del motor de precios cobra en silencio el precio de catálogo | `backend/application/sales/pricing_resolution.py:25-28` | intent-borrador | — | — |
| [SDLC-SYNC-001](items/SDLC-SYNC-001/intent.md) | P0 | T0 | Servidor central no aplica p006: toda petición de sync revienta en BD nueva | `migrations/engine.py:475-481` | intent-borrador | — | — |
| [SDLC-SYNC-002](items/SDLC-SYNC-002/intent.md) | P0 | T0 | Hecho en CONFLICTO reenviado se marca SYNCED y nunca se proyecta | `backend/application/sync/central_ingestion.py:166-176,192-194` | intent-borrador | — | SDLC-SYNC-001 |
| [SDLC-WA-001](items/SDLC-WA-001/intent.md) | P0 | T1 | Webhook de MercadoPago puede confirmar el pedido equivocado y pierde aprobaciones | `whatsapp_service/webhook/mercadopago.py:65` | intent-borrador | — | SDLC-WA-002 |
| [SDLC-WA-002](items/SDLC-WA-002/intent.md) | P0 | T1 | Webhooks de WhatsApp y pagos aceptan peticiones sin firma si falta APP_ENV | `whatsapp_service/config/settings.py:166` | intent-borrador | — | — |
| [SDLC-BI-001](items/SDLC-BI-001/intent.md) | P1 | T0 | BI ignora el alcance por sucursal y usa un verificador de permisos que permite todo | `frontend/desktop/modules/business_intelligence/business_intelligence_routes.py:98-100,108-183` | intent-borrador | — | — |
| [SDLC-CASH-001](items/SDLC-CASH-001/intent.md) | P1 | T0 | Reversa de venta registra la salida de efectivo en el turno original, aunque esté cerrado | `backend/application/sales/use_cases/return_use_cases.py:190-268` (vs ~185 para devolución parcial) | intent-borrador | — | — |
| [SDLC-CORE-001](items/SDLC-CORE-001/intent.md) | P1 | T0 | Falla en el cableado de eventos al arrancar deja la app sin integración contable, en silencio | `backend/bootstrap/wiring/event_wiring.py:62-88,93-126,224-255` | intent-borrador | — | — |
| [SDLC-CORE-007](items/SDLC-CORE-007/intent.md) | P1 | T0 | El segmento de integración de CI no colecta: las pruebas de integración nunca corren | `docs/sdlc/baseline/2026-10-28.md` | intent-borrador | — | — |
| [SDLC-CRED-001](items/SDLC-CRED-001/intent.md) | P1 | T0 | Exposición de crédito suma la tabla legacy cuentas_por_cobrar que ya nadie escribe | `backend/application/customer_credit/queries/customer_accounts_receivable_summary_query.py:97-114,157` (docstring línea 100) | intent-borrador | — | — |
| [SDLC-CRM-001](items/SDLC-CRM-001/intent.md) | P1 | T0 | Fusión de clientes escribe crédito directo, cierra crédito con saldo y deja puntos huérfanos | `backend/application/customers/use_cases/merge_use_cases.py:54,126-137` (docstring 22-26) | intent-borrador | — | — |
| [SDLC-CRM-002](items/SDLC-CRM-002/intent.md) | P1 | T1 | Anonimización de cliente deja nombre y teléfono en claro fuera del maestro | `backend/application/customer_privacy/use_cases/anonymize_customer_use_case.py:46-47` | intent-borrador | — | — |
| [SDLC-HR-001](items/SDLC-HR-001/intent.md) | P1 | T0 | Nómina asienta faltas y retardos como retenciones por enterar e ignora la cuota patronal | `backend/application/event_handlers/finance/payroll_paid_handler.py:37-38,63-66` | intent-borrador | — | — |
| [SDLC-HR-002](items/SDLC-HR-002/intent.md) | P1 | T0 | Asiento de nómina sin reintento periódico; la UI dice 'pagada' aunque Finanzas falle | `frontend/desktop/modules/hr/hr_presenter.py:505-514` | intent-borrador | — | — |
| [SDLC-INST-002](items/SDLC-INST-002/intent.md) | P1 | T0 | Llavero de releases vacío: ninguna actualización puede aplicarse | `backend/infrastructure/updater/trusted_keys.py:30-33` | intent-borrador | — | SDLC-INST-001 |
| [SDLC-INV-002](items/SDLC-INV-002/intent.md) | P1 | T0 | Captura de peso suma el peso completo al stock y el signo del peso puede invertirse | `backend/application/inventory/use_cases/catch_weight_use_cases.py:79-84` | intent-borrador | — | — |
| [SDLC-INV-003](items/SDLC-INV-003/intent.md) | P1 | T0 | Cada flujo pone stock en una 'ubicación' distinta (sucursal, almacén o técnica) | `backend/application/event_handlers/inventory/purchase_stock_entry_bridge.py:52-57`; `backend/application/procurement/integrations/downstream_translators.py:84-97` | intent-borrador | — | SDLC-INV-001 |
| [SDLC-ORD-001](items/SDLC-ORD-001/intent.md) | P1 | T0 | Dinero de Pedidos: efecto de caja tragado y cobros/liquidaciones de repartidor sin asiento | `backend/application/sales/use_cases/checkout_use_cases.py:172-185`; llamado desde `backend/infrastructure/integrations/orders_delivery_sales_client.py:136-137` | intent-borrador | — | — |
| [SDLC-PROC-001](items/SDLC-PROC-001/intent.md) | P1 | T0 | Lo recibido no llega al despiece: falta orquestación recepción → transformación | `backend/application/meat_processing/queries/direct_transformation_query_service.py` (`lots`) | intent-borrador | — | SDLC-INV-003, SDLC-TRF-001 |
| [SDLC-PROC-002](items/SDLC-PROC-002/intent.md) | P1 | T1 | Disponibilidad para producción suma piezas como kg y con REAL | `backend/application/meat_processing/queries/direct_transformation_query_service.py:132` | intent-borrador | — | — |
| [SDLC-PUR-001](items/SDLC-PUR-001/intent.md) | P1 | T0 | Recepción de compra rechazada por Inventario se descarta, pero la CxP sí se crea | `backend/application/event_handlers/inventory/purchase_receipt_handler.py:64-67,89-92` | intent-borrador | — | — |
| [SDLC-SALES-002](items/SDLC-SALES-002/intent.md) | P1 | T0 | Totales de venta nunca se redondean a centavos | `backend/domain/sales/services/sale_totals_service.py:32-41` | intent-borrador | — | — |
| [SDLC-SALES-003](items/SDLC-SALES-003/intent.md) | P1 | T0 | Outbox de ventas sin contador de intentos ni dead-letter: un evento envenenado se reintenta para siempre | `backend/application/sales/integrations/wiring.py:88-123` | intent-borrador | — | — |
| [SDLC-SEC-001](items/SDLC-SEC-001/intent.md) | P1 | T0 | Contraseñas de usuario se hashean en la UI y saltan la política de contraseñas | `frontend/desktop/modules/configuracion/configuracion_presenter.py:1007-1009,1038-1040` | intent-borrador | — | — |
| [SDLC-SEC-002](items/SDLC-SEC-002/intent.md) | P1 | T0 | Autorización de dos personas confía en IDs enviados por la UI; usuarios inactivos siguen autorizando | `backend/infrastructure/desktop/cash_register_factory.py:614,628,642,1269-1278` | intent-borrador | — | — |
| [SDLC-SET-001](items/SDLC-SET-001/intent.md) | P1 | T0 | Anclar la sucursal de la instalación no cambia la sesión en curso | `frontend/desktop/modules/configuracion/pages/empresa_page.py:408-412` | intent-borrador | — | — |
| [SDLC-SYNC-003](items/SDLC-SYNC-003/intent.md) | P1 | T0 | Proyección central: errores permanentes, eventos fuera de orden y última-escritura-gana en crédito/lealtad | `backend/infrastructure/central/projection_repository.py:35-37,76-78,117-120,177-207` (comparar `:223` `upsert_org_unit` con guardia) | intent-borrador | — | SDLC-SYNC-001 |
| [SDLC-SYNC-004](items/SDLC-SYNC-004/intent.md) | P1 | T0 | Huecos en la secuencia de estación bloquean la recuperación de dispositivo | `backend/application/sync/replication_outbox.py:148,163-171` | intent-borrador | — | SDLC-SYNC-001 |
| [SDLC-SYNC-005](items/SDLC-SYNC-005/intent.md) | P1 | T0 | Ninguna estación replica al central: transporte nunca configurado y sin planificador | `backend/infrastructure/desktop/cash_register_factory.py:492-496,1238-1254` | intent-borrador | — | SDLC-SYNC-002, SDLC-SYNC-003, SDLC-SYNC-004 |
| [SDLC-TRF-001](items/SDLC-TRF-001/intent.md) | P1 | T0 | Recepción de transferencias no captura peso, piezas, lote ni temperatura | `backend/application/transfers/cycle_service.py:124-131` | intent-borrador | — | — |
| [SDLC-TRF-002](items/SDLC-TRF-002/intent.md) | P1 | T0 | Ciclo de transferencia termina en la recepción: faltantes desaparecen sin merma ni asiento | `backend/application/transfers/composition.py:148-164` | intent-borrador | — | SDLC-TRF-001, SDLC-LOSS-001 |
| [SDLC-WA-003](items/SDLC-WA-003/intent.md) | P1 | T1 | Pedidos, cotizaciones y anticipos por WhatsApp no pueden crearse en producción | `backend/api/main.py:23-25`, `backend/api/central_app.py:152-153` | intent-borrador | — | SDLC-WA-002 |
| [SDLC-WA-004](items/SDLC-WA-004/intent.md) | P1 | T0 | Anticipos por WhatsApp sin asiento y regla de monto que nunca casa | `whatsapp_service/erp/gateways/payment_gateway.py:24-55`; `migrations/m000_base_schema.py:689-692` | intent-borrador | — | SDLC-WA-003 |
| [SDLC-WA-005](items/SDLC-WA-005/intent.md) | P1 | T1 | Microservicio WhatsApp importa el paquete core.* eliminado y la bandeja del POS nunca recibe avisos | `whatsapp_service/erp/adjustment_approval.py:15-17`; `whatsapp_service/router/message_router.py:217-234` | intent-borrador | — | — |
| [SDLC-WA-006](items/SDLC-WA-006/intent.md) | P1 | T1 | Trabajadores del microservicio WhatsApp nunca corren y el webhook responde 200 aunque falle | `whatsapp_service/bootstrap/composition_root.py:218,243` | intent-borrador | — | — |
| [SDLC-ASSET-001](items/SDLC-ASSET-001/intent.md) | P2 | T2 | Módulo Activos visible en el menú sin persistencia: 31 de 36 rutas en construcción | `frontend/desktop/modules/assets/shell_registration.py:70-87` | intent-borrador | — | — |
| [SDLC-BI-002](items/SDLC-BI-002/intent.md) | P2 | T2 | BI: ajustes y estado de alertas sólo en memoria; errores SQL se muestran como $0 | `backend/application/analytics/services/bi_settings_service.py:38-39` | intent-borrador | — | SDLC-BI-001 |
| [SDLC-BI-003](items/SDLC-BI-003/intent.md) | P2 | T2 | Dos motores de pronóstico dan números distintos para lo mismo | `backend/application/analytics/queries/bi_forecast_query_service.py:1-5,34-40` | intent-borrador | — | — |
| [SDLC-CASH-002](items/SDLC-CASH-002/intent.md) | P2 | T0 | Depósito de caja confirmado nunca se asienta al banco | `backend/application/event_handlers/finance/cash_finance_router.py:21` | intent-borrador | — | — |
| [SDLC-CORE-002](items/SDLC-CORE-002/intent.md) | P2 | T0 | operation_id compuesto por concatenación de cadenas en rutas de dinero e inventario | `backend/application/use_cases/finance/register_sale_credit_charge_use_case.py:31,52,74-75` | intent-borrador | — | — |
| [SDLC-CORE-003](items/SDLC-CORE-003/intent.md) | P2 | T1 | La UI crea esquema y repositorios SQLite (22 archivos de frontend importan infraestructura) | `frontend/desktop/modules/hr/hr_routes.py:90,98` | intent-borrador | — | — |
| [SDLC-CORE-008](items/SDLC-CORE-008/intent.md) | P2 | T0 | Guardias de arquitectura en rojo por DDL fuera de migraciones, conexiones crudas y ratchet UUID | `docs/sdlc/baseline/2026-10-28.md` | intent-borrador | — | — |
| [SDLC-CORE-010](items/SDLC-CORE-010/intent.md) | P2 | T1 | 4 fallas en tests/unit: permiso de aprobar flags, diálogo de cobro y barra lateral de Transferencias | `docs/sdlc/baseline/2026-10-28.md` | intent-borrador | — | — |
| [SDLC-CORE-011](items/SDLC-CORE-011/intent.md) | P2 | T1 | 74 fallas y 32 errores en tests/integration, en su mayoría fixtures desactualizados | `docs/sdlc/baseline/2026-10-28.md` | intent-borrador | — | SDLC-CORE-007 |
| [SDLC-CRM-003](items/SDLC-CRM-003/intent.md) | P2 | T1 | Dos maestros de clientes vivos (clientes y customers) con puente bidireccional | `backend/application/customers/use_cases/legacy_customer_bridge_use_cases.py:3-9,22,114-118` | intent-borrador | — | SDLC-WA-003 |
| [SDLC-FIN-001](items/SDLC-FIN-001/intent.md) | P2 | T0 | 16 handlers de Finanzas muertos duplican las reglas del puente de Lealtad | `backend/application/event_handlers/finance/{coupon_*,gift_card_*,voucher_*,stored_value_adjusted,loyalty_points_*,loyalty_reward_granted,loyalty_transaction_reversed,purchase_received}_handler.py` | intent-borrador | — | — |
| [SDLC-INST-003](items/SDLC-INST-003/intent.md) | P2 | T0 | Carpeta de datos con permiso de modificación para todos los usuarios de Windows | `installer/windows/spj_setup.iss:119` | intent-borrador | — | — |
| [SDLC-INV-004](items/SDLC-INV-004/intent.md) | P2 | T0 | Cableado muerto de inventario (cutover canónico, puentes huérfanos, wire_logistics) | `backend/bootstrap/wiring/event_wiring.py:180-197` | intent-borrador | — | — |
| [SDLC-INV-005](items/SDLC-INV-005/intent.md) | P2 | T0 | Almacén de stock legacy (inventory_stock) se sigue creando y BI lo lee | `migrations/standalone/098_canonical_inventory.py:18`; `108_sync_inventory_stock.py:46` | intent-borrador | — | — |
| [SDLC-LOG-001](items/SDLC-LOG-001/intent.md) | P2 | T1 | Logística ejecuta SQL contra tablas de Compras y Productos | `backend/application/logistics/service.py:185-208` | intent-borrador | — | — |
| [SDLC-ORD-002](items/SDLC-ORD-002/intent.md) | P2 | T1 | Outbox de Pedidos, CRM, clientes, cotizaciones, tarjetas, sorteos y privacidad nunca se drenan | `backend/application/orders_delivery/integrations/orders_delivery_outbox_dispatcher.py:32` | intent-borrador | — | — |
| [SDLC-ORD-003](items/SDLC-ORD-003/intent.md) | P2 | T1 | Tres pipelines de pedidos paralelos sin fuente de verdad decidida | `backend/infrastructure/db/schema/whatsapp_schema.py:38-47` | intent-borrador | — | — |
| [SDLC-PROC-003](items/SDLC-PROC-003/intent.md) | P2 | T1 | Asiento de costo de producción fallido espera a la siguiente orden | `backend/infrastructure/desktop/meat_processing_factory.py:74-80` | intent-borrador | — | — |
| [SDLC-SALES-004](items/SDLC-SALES-004/intent.md) | P2 | T0 | Expiración de ventas suspendidas sin llamador e insegura si se cablea | `backend/application/sales/use_cases/suspension_sweep_use_cases.py:46-69` | intent-borrador | — | — |
| [SDLC-SALES-005](items/SDLC-SALES-005/intent.md) | P2 | T1 | Modelo de ventas legacy (ventas/detalles_venta) sigue vivo como fuente de lectura | `backend/infrastructure/db/sales_read_source.py:1-52` | intent-borrador | — | — |
| [SDLC-SALES-006](items/SDLC-SALES-006/intent.md) | P2 | T1 | 'Guardar PDF' del ticket ignora el diseñador de Configuración | `backend/infrastructure/hardware/sales_ticket_printer.py:64-73` | intent-borrador | — | — |
| [SDLC-SEC-003](items/SDLC-SEC-003/intent.md) | P2 | T0 | Alcance de seguridad abierto: central acepta cualquier actor y algunos checkers omiten sucursal | `backend/application/sync/central_ingestion.py:88-94,109` | intent-borrador | — | — |
| [SDLC-SEC-004](items/SDLC-SEC-004/intent.md) | P2 | T0 | Código de autenticación duplicado y muerto (security/auth.py, listas de admin divergentes) | `security/auth.py` | intent-borrador | — | — |
| [SDLC-SET-002](items/SDLC-SET-002/intent.md) | P2 | T1 | Tablas de configuración legacy (configuraciones, feature_flags, hardware_config) siguen vivas | `backend/infrastructure/db/schema/settings_schema.py:70`; `migrations/m000_base_schema.py:121,130,149` | intent-borrador | — | SDLC-WA-007 |
| [SDLC-SET-003](items/SDLC-SET-003/intent.md) | P2 | T1 | Secciones de Configuración que guardan datos que nada lee | `frontend/desktop/modules/configuracion/pages/apariencia_page.py:1-11`; `frontend/desktop/themes/theme_manager.py:66-80` | intent-borrador | — | — |
| [SDLC-WA-007](items/SDLC-WA-007/intent.md) | P2 | T1 | Microservicio WhatsApp viola REGLA CERO y escribe configuración/migraciones del ERP | `whatsapp_service/erp/bridge.py:66-69` | intent-borrador | — | SDLC-WA-003 |
| [SDLC-CORE-004](items/SDLC-CORE-004/intent.md) | P3 | T0 | Archivos de migración SQLite sin registrar y números duplicados | `migrations/engine.py:179-180` | intent-borrador | — | — |
| [SDLC-CORE-005](items/SDLC-CORE-005/intent.md) | P3 | T1 | Código muerto y cascarones de casos de uso (ventas, delivery, RRHH, BI) | `backend/application/use_cases/cancel_sale_use_case.py:9`; `execute_monthly_closing_use_case.py:24-28` | intent-borrador | — | — |
| [SDLC-CORE-006](items/SDLC-CORE-006/intent.md) | P3 | T1 | Float residual en dinero y cantidades (lealtad, recibos, analítica, proveedores, depreciación) | `backend/infrastructure/integrations/sales_loyalty_client.py:25-26,118-127`; `sales_receipt_client.py:133-147` | intent-borrador | — | — |
| [SDLC-CORE-009](items/SDLC-CORE-009/intent.md) | P3 | T1 | Resto de guardias de arquitectura en rojo (UI, deuda visual, herramientas de refactor) | `docs/sdlc/baseline/2026-10-28.md` | intent-borrador | — | — |
| [SDLC-INV-006](items/SDLC-INV-006/intent.md) | P3 | T1 | Folios de ajuste, conteo y peso se repiten (new_uuid()[:8]) | `frontend/desktop/modules/inventory/presenter.py:1215,1362,1468` | intent-borrador | — | — |
| [SDLC-INV-007](items/SDLC-INV-007/intent.md) | P3 | T1 | Báscula simulada (StubScaleGateway) cableada en la composición de Inventario; doble mecanismo de retención de calidad | `frontend/desktop/modules/inventory/composition.py:102-109` | intent-borrador | — | — |
| [SDLC-LOY-001](items/SDLC-LOY-001/intent.md) | P3 | T1 | Cupones nunca expiran (ExpireCouponsUseCase sólo en pruebas) | `backend/application/commercial_instruments/use_cases/coupon_use_cases.py:265` | intent-borrador | — | — |
| [SDLC-PUR-002](items/SDLC-PUR-002/intent.md) | P3 | T1 | Falla al leer días de crédito vuelve la factura de proveedor exigible hoy | `backend/application/procurement/use_cases/supplier_invoice_use_cases.py:144-146` | intent-borrador | — | — |
| [SDLC-SALES-007](items/SDLC-SALES-007/intent.md) | P3 | T1 | POS reporta cualquier OperationalError como 'no hay turno abierto'; folio de CxC = id de venta | `frontend/desktop/modules/sales_pos/composition.py:134-138` | intent-borrador | — | — |
| [SDLC-SEC-005](items/SDLC-SEC-005/intent.md) | P3 | T0 | Endurecimiento menor: rate limit por cabecera no autenticada, nonce por proceso, respaldo de secretos en claro | `backend/api/routers/sync.py:76-79` | intent-borrador | — | — |

## Decisiones aprobadas

_(fecha · ID · decisión · quién aprobó)_

## Preguntas abiertas para el responsable

_(ID · pregunta · por qué bloquea)_

- SDLC-TRF-001 / SDLC-PROC-001 / SDLC-PROC-002 · La auditoría 2026-10-26 los clasificó P0; el triage los deja en P1 (flujo roto, sin pérdida directa de dinero) según la tabla del comando. · Si se quieren P0, cambia el orden de trabajo.
- SDLC-CORE-002 · Posible contradicción entre fuentes: la REGLA CERO exige UUIDv7 en toda operación, pero la idempotencia necesita `operation_id` derivados deterministas. · Registrada aquí en vez de elegir en silencio (regla del README).
- SDLC-INST-001 · ¿Nombre/huella del certificado de firma de código que se usará? · bloquea `/sdlc-design SDLC-INST-001`
- SDLC-INV-001 · ¿Las bajas por caducidad son merma (Mermas valúa y asienta) o ajuste de inventario directo? · bloquea `/sdlc-design SDLC-INV-001`
- SDLC-INV-001 · ¿Qué cuentas usa un ajuste positivo (sobrante)? · bloquea `/sdlc-design SDLC-INV-001`
- SDLC-LOSS-001 · ¿Umbral de monto a partir del cual la aprobación requiere gerente? · bloquea `/sdlc-design SDLC-LOSS-001`
- SDLC-LOSS-001 · Revaluación: ¿ajuste por diferencia o reversa total + asiento nuevo? · bloquea `/sdlc-design SDLC-LOSS-001`
- SDLC-SALES-001 · Ante falla del motor: ¿bloquear la línea o permitir catálogo con autorización de gerente? · bloquea `/sdlc-design SDLC-SALES-001`
- SDLC-SYNC-001 · ¿`354_device_enrollment` es parte del mismo slice que p006 o es un remanente a borrar? · bloquea `/sdlc-design SDLC-SYNC-001`
- SDLC-SYNC-002 · ¿Quién resuelve un conflicto (central, estación, humano) y con qué pantalla? · bloquea `/sdlc-design SDLC-SYNC-002`
- SDLC-WA-001 · ¿Se usa MercadoPago en producción hoy, o el flujo está apagado? · bloquea `/sdlc-design SDLC-WA-001`
- SDLC-WA-002 · ¿Hay hoy algún despliegue del microservicio sin `APP_ENV=production`? · bloquea `/sdlc-design SDLC-WA-002`
- SDLC-CORE-007 · ¿Se mantiene la lista curada como gate o se vuelve a exigir el segmento completo verde? · bloquea `/sdlc-design SDLC-CORE-007`
- SDLC-CRED-001 · ¿Hay saldos vivos en `cuentas_por_cobrar` en la BD real? (se medirá sobre copia) · bloquea `/sdlc-design SDLC-CRED-001`
- SDLC-CRM-002 · ¿Qué datos deben conservarse por obligación fiscal en ventas? · bloquea `/sdlc-design SDLC-CRM-002`
- SDLC-HR-001 · ¿Cálculo de cuota patronal IMSS: lo hace el sistema o se captura? · bloquea `/sdlc-design SDLC-HR-001`
- SDLC-INST-002 · ¿Dónde se genera y custodia la llave privada de release? (el humano la crea; Claude no la ve) · bloquea `/sdlc-design SDLC-INST-002`
- SDLC-INV-003 · Probablemente requiera dividirse en Design (resolver + migración por flujo). · bloquea `/sdlc-design SDLC-INV-003`
- SDLC-ORD-001 · ¿Cuenta contable para 'efectivo en poder de repartidores'? · bloquea `/sdlc-design SDLC-ORD-001`
- SDLC-PROC-001 · ¿Política por producto/sucursal/almacén de qué dispara la transformación? · bloquea `/sdlc-design SDLC-PROC-001`
- SDLC-SALES-002 · ¿Regla de redondeo: por línea o sobre el total? ¿HALF_UP o bancario? · bloquea `/sdlc-design SDLC-SALES-002`
- SDLC-SET-001 · ¿Cambio en caliente o reinicio obligatorio? · bloquea `/sdlc-design SDLC-SET-001`
- SDLC-SYNC-005 · ¿Ya hay un servidor central (Oracle Always Free) listo para recibir tráfico real? · bloquea `/sdlc-design SDLC-SYNC-005`
- SDLC-TRF-001 · La auditoría lo clasificó P0; aquí P1 (flujo roto, sin pérdida de dinero). ¿De acuerdo? · bloquea `/sdlc-design SDLC-TRF-001`
- SDLC-WA-003 · ¿El destino es la API REST del ERP (aún inexistente) o los casos de uso canónicos `customer_orders`/`quotes`? · bloquea `/sdlc-design SDLC-WA-003`
- SDLC-WA-003 · ¿El canal WhatsApp está en uso hoy en alguna sucursal? · bloquea `/sdlc-design SDLC-WA-003`
- SDLC-WA-004 · ¿Cuenta contable de anticipos de clientes? · bloquea `/sdlc-design SDLC-WA-004`
- SDLC-ASSET-001 · ¿Ocultar Activos del menú hasta construirlo? · bloquea `/sdlc-design SDLC-ASSET-001`
- SDLC-CASH-002 · ¿Quién confirma el depósito (cajero, tesorería) y con qué evidencia? · bloquea `/sdlc-design SDLC-CASH-002`
- SDLC-CORE-002 · Los ids derivados necesitan ser deterministas para idempotencia: ¿se acepta UUIDv5/v8 derivado del UUIDv7 padre, o se exige UUIDv7 persistido? (posible contradicción con la REGLA CERO) · bloquea `/sdlc-design SDLC-CORE-002`
- SDLC-INST-003 · ¿Varios usuarios de Windows por PC de sucursal, o uno solo? · bloquea `/sdlc-design SDLC-INST-003`
- SDLC-ORD-003 · ¿Cuál pipeline de pedidos es el autoritativo? · bloquea `/sdlc-design SDLC-ORD-003`
- SDLC-SALES-004 · ¿Vigencia de una venta suspendida? · bloquea `/sdlc-design SDLC-SALES-004`
- SDLC-SET-002 · ¿Se ejecuta dentro del pipeline CONFIGURACION (lotes 07/14) o como ítem SDLC independiente? · bloquea `/sdlc-design SDLC-SET-002`
- SDLC-SET-003 · ¿Qué secciones conectar y cuáles ocultar? · bloquea `/sdlc-design SDLC-SET-003`
- SDLC-CORE-009 · ¿Las herramientas de `tools/refactor_control` y el orquestador Codex siguen en uso? · bloquea `/sdlc-design SDLC-CORE-009`
- SDLC-LOY-001 · ¿Se reconoce breakage contablemente? · bloquea `/sdlc-design SDLC-LOY-001`
