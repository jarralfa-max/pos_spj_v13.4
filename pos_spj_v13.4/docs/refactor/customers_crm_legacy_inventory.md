# Clientes y CRM — inventario de legado (CRM-43, 2026-10-09)

Estado al iniciar la re-auditoría. El módulo monolítico `modulos/clientes.py`, sus
diálogos con SQL (`DialogoHistorialCliente`) y `core/services/cliente_service.py` ya se
habían retirado en CRM-24/CRM-34 (ver esos documentos); la carpeta `core/` y la API
`api/routers/` ya no existen.

| Elemento | Dónde | Situación encontrada | Acción CRM-43 |
|----------|-------|----------------------|---------------|
| Códigos gruesos `CLIENTES.eliminar` | `rol_permisos` | Sin uso en el catálogo | Borrado (migr. 314) |
| Directorios de sólo lectura | `pages/leads_directory_page.py`, `opportunities_directory_page.py`, `service_cases_directory_page.py`, `_directory_base.py` | Sustituidos por bandejas operativas | Borrados |
| Métodos de directorio del presentador | `customers_crm_presenter.py` | Sin consumidores tras lo anterior | Borrados |
| Raíz de composición en la UI | `frontend/.../customers_crm/composition.py` | Ejecutaba casos de uso desde la UI | Movida a `backend/infrastructure/desktop/customers_crm_factory.py` |
| Cableado Ventas→Clientes | `core/events/wiring.py` (borrado antes) | Manejadores huérfanos | Recableado en el bus canónico |
| Pruebas de código borrado | `test_crm_21_legacy_identity_bridge.py` (parte), `test_crm_21_read_path_wiring.py` (parte), `test_crm_27_finance_credit_cutover.py` (parte), `test_credit_sale_requires_valid_customer.py`, `test_credit_sale_creates_cxc_and_updates_balance.py`, `TestModuloClientesCrmShim` | Importaban `core/`, `application/`, `modulos/`, `api/` | Retiradas (lo vigente quedó probado) |
| Tabla `clientes` / `ventas.cliente_id` / `cotizaciones.cliente_id` | esquema | Identidad legacy; `clientes` tiene 0 filas en la base real | Se conserva el puente `customers.legacy_customer_id` para cotizaciones legacy (BLOCKED hasta que Cotizaciones migre) |
| `QTableWidget`, QSS en línea, colores locales, emojis | módulo | Guardas CRM-1 en verde | Sin cambios (guardas pasan) |
