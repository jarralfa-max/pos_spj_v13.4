# Clientes y CRM — reporte de retiro de legado (CRM-43, 2026-10-09)

| Elemento anterior | Destino canónico | Acción | Consumidores restantes |
|-------------------|------------------|--------|------------------------|
| modulos/clientes.py | CustomersCrmWorkspace | DELETE (CRM-24) | 0 |
| DialogoHistorialCliente SQL | CustomerHistoryQueryService (+ `get_*` de §28 en CRM-43) | DELETE (CRM-24) | 0 |
| sqlite3 en UI | repositories infra | DELETE | 0 (guarda `test_customers_crm_ui_has_no_repositories`) |
| ClienteRepository en widget | UseCases/Queries | DELETE | 0 |
| Raíz de composición en la UI con `.execute(connection, …)` | `backend/infrastructure/desktop/customers_crm_factory.py` | MOVE (CRM-43) | 0 |
| customer básico | Customer Master + CRM | REWRITE | 0 |
| vendedor_id simple | CustomerOwnership (con historial, pantalla «Propietarios») | DELETE | 0 |
| notas libres | CRMNote con permisos (privadas) | DELETE | 0 |
| seguimiento informal | CRMActivity / CRMTask / agenda | DELETE | 0 |
| prospecto como cliente | Lead | DELETE | 0 |
| pipeline hardcodeado | CRMStageDefinition configurable (CRM-43) | DELETE | 0 |
| queja como nota | CustomerServiceCase + SLA (migr. 315) | DELETE | 0 |
| crédito simple | CustomerCreditProfile + workflow | REWRITE | 0 |
| id_cliente | customer_id | DELETE | 0 (las cotizaciones legacy se copian a `quotes` con `customer_id`, migr. 318) |
| metodo_pago | payment_method (`sale_payments.method`) | DELETE | 0 |
| IDs enteros | UUIDv7 | DELETE | 0 (guarda `test_customers_crm_has_no_integer_identity`) |
| roles hardcodeados | permisos + scopes (migr. 314, ejes BRANCH/COMPANY) | DELETE | 0 |
| tarjetas en Clientes | Fidelidad | MOVE | 0 |
| QTableWidget | StandardTable V2 | DELETE | 0 |
| tabs por índices | RouteRegistry (`route_id`) | DELETE | 0 |
| colores locales | tokens semánticos | DELETE | 0 |
| emojis | IconProvider | DELETE | 0 |
| QSS inline | QSS canónico | DELETE | 0 |
| Directorios de sólo lectura (CRM-16) | bandejas `CrmWorkbenchPage` | DELETE (CRM-43) | 0 |
| Cableado Ventas→Clientes en `core/events` | `wire_customers_sales` | MOVE (CRM-43) | 0 |
| Tabla `cotizaciones` + cascarones `use_cases/*quote*` | contexto `quotes` | REWRITE (CRM-43) | tabla: 0 lectores; cascarones: sólo una prueba de andamiaje |

Allowlist del módulo (`CUSTOMERS_CRM_MODULE_ALLOWLIST`): vacía al inicio y al final.
