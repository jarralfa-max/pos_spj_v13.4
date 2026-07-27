# SPJ ERP/POS Refactor Skill for Codex

> Archivo guía para ejecutar la reestructuración completa del ERP/POS SPJ con Codex de forma controlada, por fases y módulos, sin perder lógica de negocio funcional.

---

# REGLA CERO — UUIDv7 COMO ÚNICA IDENTIDAD

Esta regla es obligatoria y tiene prioridad sobre cualquier instrucción posterior de este skill.

## Decisión no negociable

Toda entidad persistente, relación funcional, evento, comando, DTO, caso de uso, repositorio, API y operación sincronizable debe utilizar **UUIDv7 como única identidad**.

Queda prohibido conservar dentro del runtime:

- IDs enteros funcionales.
- `INTEGER PRIMARY KEY AUTOINCREMENT`.
- `legacy_id`.
- escritura dual.
- lectura dual.
- fallback de UUID a entero.
- tablas paralelas de compatibilidad.
- contratos `int | str`.
- conversiones `int(product_id)`, `int(sale_id)`, `int(branch_id)` o equivalentes.
- `lastrowid` como identidad de dominio.
- `MAX(id) + 1`.
- folios, SKU, códigos de barras o números de ticket como clave primaria.

## Generador obligatorio

Debe existir una sola fuente de generación:

```text
backend/shared/ids.py
```

Contrato:

```python
def new_uuid() -> str:
    """Return a canonical lowercase UUIDv7 string."""
```

Ningún widget PyQt, repositorio o motor de base de datos puede generar una identidad distinta para la misma entidad.

## Persistencia

SQLite:

```sql
id TEXT PRIMARY KEY
```

PostgreSQL:

```sql
id UUID PRIMARY KEY
```

Todas las claves foráneas funcionales deben almacenar UUID:

```sql
product_id TEXT NOT NULL
branch_id TEXT NOT NULL
sale_id TEXT NOT NULL
customer_id TEXT
reservation_id TEXT
```

## Migración obligatoria

La migración a UUID debe ejecutarse como un **corte total, global y atómico**:

1. cerrar la aplicación;
2. crear backup completo;
3. bloquear otras instancias;
4. abrir transacción exclusiva;
5. crear tablas nuevas con UUIDv7;
6. usar mapas temporales `old_id → uuid` solo durante la migración;
7. copiar y reescribir todas las PK y FK;
8. validar conteos y referencias;
9. eliminar tablas antiguas;
10. renombrar tablas nuevas;
11. ejecutar `PRAGMA foreign_key_check`;
12. confirmar la transacción;
13. eliminar mapas temporales;
14. iniciar únicamente con el esquema UUID.

Si algo falla:

- rollback;
- restaurar backup;
- bloquear el inicio normal;
- registrar el error.

No se permite dejar una migración parcial.

## Criterio de terminado

Un módulo no puede declararse migrado al 100% mientras:

- use IDs enteros;
- tenga PK o FK funcionales enteras;
- use `AUTOINCREMENT`;
- use `lastrowid`;
- convierta IDs con `int(...)`;
- exponga IDs enteros en UI, eventos o API;
- mantenga compatibilidad legacy;
- carezca de tests de integridad UUIDv7.

---

# REGLA DE DESARROLLO — SIN CONSERVACIÓN DE DATOS LEGACY

SPJ ERP/POS está en fase de desarrollo activo.

Durante esta fase no se requiere ni se requerirá conservar datos legacy. Por lo
tanto, queda prohibido invertir esfuerzo en migraciones de rescate,
compatibilidad temporal o reparación tabla por tabla de bases contaminadas,
híbridas o parcialmente migradas.

La estrategia obligatoria durante desarrollo es:

1. Eliminar código muerto, viejo, duplicado o contradictorio.
2. Atacar la causa raíz directamente en código fuente.
3. Corregir el schema fuente para que nazca UUIDv7 desde cero.
4. Resetear o eliminar la base local de desarrollo cuando esté contaminada.
5. Crear una base nueva limpia.
6. Validar con tests y auditorías arquitectónicas.

La migración 200 o cualquier migración de identidad legacy queda reservada
únicamente para escenarios excepcionales donde explícitamente se necesite
conservar datos. Ese no es el caso durante desarrollo, y **no debe ser el flujo
normal de arranque**: una base nueva debe nacer ya UUIDv7 sin ejecutar la
migración 200.

En desarrollo está prohibido:

- conservar compatibilidad con IDs enteros;
- crear lectura dual `int | str`;
- crear escritura dual;
- crear fallback de UUID a entero;
- conservar columnas `legacy_id`;
- reparar datos viejos en lugar de corregir código;
- crear migraciones para salvar bases locales descartables;
- mantener `INTEGER PRIMARY KEY AUTOINCREMENT`;
- usar `lastrowid` como identidad de dominio;
- usar `DEFAULT 1` en claves foráneas funcionales;
- convertir IDs de dominio con `int(...)`.

Si una base local falla por estar en estado híbrido o contaminado, debe
respaldarse si se desea y eliminarse. El sistema debe poder crear una base nueva
limpia con UUIDv7 nativo sin ejecutar migraciones de rescate.

**Criterio obligatorio:** el éxito del refactor no es "salvar la base vieja"; el
éxito es que el código actual cree y use correctamente una base limpia,
coherente y UUIDv7 desde el inicio.

### Reset limpio de la base de desarrollo

PowerShell (Windows):

```powershell
cd "C:\Users\Diego Rodriguez\Downloads\pos_spj_v13.4\pos_spj_v13.4"
Copy-Item ".\data\spj_pos_database.db" ".\data\spj_pos_database_backup_dev_reset.db" -ErrorAction SilentlyContinue
Remove-Item ".\data\spj_pos_database.db" -ErrorAction SilentlyContinue
python main.py
```

Bash (Linux/macOS):

```bash
cd pos_spj_v13.4
cp ./data/spj_pos_database.db ./data/spj_pos_database_backup_dev_reset.db 2>/dev/null || true
rm -f ./data/spj_pos_database.db
python main.py
```

El sistema debe arrancar creando una DB limpia, born-UUIDv7, sin migrar datos
viejos y sin requerir la migración 200.

---

## 0. Propósito

Este archivo debe usarse como instrucción permanente para Codex durante la migración/refactor del repositorio.

El objetivo es transformar el proyecto en una arquitectura limpia, mantenible, preparada para:

- Desktop PyQt instalable como `.exe`
- Actualizaciones de versión
- SQLite actual
- PostgreSQL futuro
- API FastAPI futura
- Webapp futura
- Backend en inglés
- Frontend visible al usuario en español
- Cero SQL en UI
- Cero lógica de negocio en UI
- Cero rutas duplicadas para operaciones críticas
- Componentes UI estándar
- Módulos interconectados por Application Services + EventBus

---

## 1. Reglas maestras obligatorias

Estas reglas son no negociables.

**Prioridad absoluta:** la REGLA CERO de UUIDv7 prevalece sobre cualquier contrato, tabla o implementación existente.

1. Backend en inglés.
2. Frontend visible al usuario en español.
3. La app está en desarrollo: código muerto, duplicado o legacy inútil debe eliminarse.
4. No modificar lógica de negocio funcional sin pruebas de protección.
5. No romper flujos existentes.
6. No introducir regresiones.
7. SQLite actual, PostgreSQL futuro.
8. PyQt no debe ejecutar SQL.
9. PyQt no debe hacer `commit()` ni `rollback()`.
10. Servicios no deben crear ni alterar schema.
11. Solo `migrations/` puede modificar schema.
12. Toda operación crítica debe pasar por Use Case / Application Service.
13. Toda lectura para UI debe pasar por QueryService.
14. PyQt y futura API FastAPI deben usar los mismos Use Cases.
15. No pasar `AppContainer` completo a servicios.
16. Toda dependencia debe inyectarse explícitamente.
17. Toda mutación crítica debe emitir evento de dominio con `operation_id`.
18. Toda la app debe estar interconectada: ventas, inventario, caja, finanzas, fidelidad, delivery, WhatsApp, BI, compras, producción, merma, transferencias, tickets y notificaciones.
19. Todo teléfono debe usar estándar WhatsApp/E.164.
20. Donde se seleccione producto, cliente, proveedor, empleado, receta, activo, sucursal o repartidor debe usarse barra de búsqueda/autocomplete, no listas largas.
21. Donde se capture dirección debe usarse componente con API de mapas/autocomplete y fallback manual.
22. Todo campo numérico de captura debe iniciar en cero absoluto o vacío.
23. Prohibido usar defaults arbitrarios en UI como `1`, `7`, `10`, `30`, `50`, `100`.
24. Si un default funcional es necesario, debe venir desde `SystemSettingsService` o `ModuleSettingsService`.
25. El `.exe` debe permitir actualización de versiones.
26. Antes de actualizar versión debe hacerse backup automático de SQLite.
27. No usar rutas relativas sueltas; usar `AppPaths`.
28. No usar SQL exclusivo de SQLite en código nuevo si puede afectar PostgreSQL futuro.
29. No duplicar rutas para la misma operación.
30. Cada módulo refactorizado debe quedar cubierto por tests unitarios, integración, arquitectura y checklist manual.
31. Toda nueva carpeta del refactor (`backend/`, `frontend/`, `tests/`, `docs/`, etc.) debe crearse dentro de `pos_spj_v13.4/pos_spj_v13.4/`; está prohibido crear duplicados en la raíz externa del repositorio.

32. Toda entidad persistente y toda relación funcional debe usar UUIDv7 como única identidad.
33. SQLite almacena UUID como `TEXT`; PostgreSQL debe usar el tipo nativo `UUID`.
34. Está prohibido crear nuevas PK funcionales `INTEGER PRIMARY KEY AUTOINCREMENT`.
35. Está prohibido mantener `legacy_id`, escritura dual, lectura dual, fallback de UUID a entero o tablas paralelas de compatibilidad.
36. Está prohibido usar `lastrowid`, `MAX(id) + 1` o secuencias locales como identidad de dominio.
37. Está prohibido convertir identificadores de dominio con `int(product_id)`, `int(sale_id)`, `int(branch_id)` o equivalentes.
38. Folios, SKU, códigos de barras, números de ticket y códigos visibles no sustituyen al UUID.
39. Toda migración de identidad debe ser directa, global, atómica, respaldada y validada antes de iniciar la aplicación.
40. Toda entidad, Command, DTO, Use Case, QueryService, Repository, evento, outbox y futura API debe transportar UUID.
41. `operation_id`, `event_id` y `entity_id` son UUID distintos y no deben reutilizarse entre sí.
42. Un módulo no puede considerarse migrado mientras use IDs enteros o referencias funcionales enteras.


---

## 2. Arquitectura objetivo

```text
SPJ ERP
│
├── frontend/
│   └── desktop/
│       ├── modules/
│       ├── components/
│       ├── i18n/
│       └── themes/
│
├── backend/
│   ├── domain/
│   ├── application/
│   │   ├── use_cases/
│   │   ├── commands/
│   │   ├── dto/
│   │   ├── queries/
│   │   └── event_handlers/
│   ├── infrastructure/
│   │   ├── db/
│   │   ├── hardware/
│   │   ├── maps/
│   │   ├── printers/
│   │   ├── whatsapp/
│   │   └── updater/
│   ├── api/
│   └── shared/
│       ├── events/
│       ├── errors/
│       ├── result.py
│       ├── app_paths.py
│       └── ids.py
│
├── migrations/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── architecture/
│   └── e2e/
│
├── installer/
│   └── windows/
│
└── docs/
    └── architecture/
```

---

## 3. Principio central

```text
Una sola operación.
Una sola ruta canónica.
Una sola fuente de verdad.
```

Ejemplos:

- Registrar merma → `RegisterWasteUseCase`
- Crear venta → `CreateSaleUseCase`
- Ejecutar producción cárnica → `ExecuteMeatProductionUseCase`
- Despachar transferencia → `DispatchTransferUseCase`
- Recibir transferencia → `ReceiveTransferUseCase`
- Crear pedido delivery → `CreateDeliveryOrderUseCase`
- Generar corte Z → `GenerateZCutUseCase`
- Crear producto → `CreateProductUseCase`
- Convertir cotización a venta → `ConvertQuoteToSaleUseCase`
- Generar plan de compras → `GeneratePurchasePlanUseCase`

### 3.1 Política obligatoria de identidad UUID

```text
Una entidad.
Un UUID.
Una sola identidad.
```

#### Decisión no negociable

Todas las entidades persistentes del ERP deben usar UUIDv7 como única identidad.

No se permite conservar dentro del runtime:

- ID entero junto con UUID.
- `legacy_id`.
- escritura dual.
- lectura dual.
- fallback de UUID a entero.
- adaptadores permanentes de compatibilidad.
- tablas paralelas.
- contratos `int | str` para el mismo identificador.

La aplicación está en desarrollo. La migración se ejecutará como corte total para evitar múltiples fuentes de verdad.

#### Generador único

Debe existir:

```text
backend/shared/ids.py
```

Contrato:

```python
def new_uuid() -> str:
    """Return a canonical lowercase UUIDv7 string."""
```

Reglas:

1. El UUID se genera una sola vez en dominio o aplicación.
2. PyQt no genera IDs.
3. Los repositorios no reemplazan un UUID recibido.
4. SQLite y PostgreSQL no generan la identidad de dominio.
5. Está prohibido dispersar `uuid.uuid4()` u otros generadores por el repositorio.
6. Toda validación de UUID debe usar una utilidad compartida.

#### Representación por motor

SQLite:

```sql
id TEXT PRIMARY KEY
```

PostgreSQL:

```sql
id UUID PRIMARY KEY
```

Las claves foráneas conservan nombres como `product_id`, `sale_id` o `branch_id`, pero su tipo de dominio siempre es UUID/string.

#### Prohibiciones de código

Queda prohibido en código migrado:

```python
product_id: int
sale_id: int
branch_id: int
customer_id: int
user_id: int
reservation_id: int
```

Queda prohibido:

```python
int(product_id)
int(sale_id)
int(branch_id)
int(customer_id)
int(reservation_id)
```

Queda prohibido usar:

```text
lastrowid
MAX(id) + 1
INTEGER PRIMARY KEY AUTOINCREMENT
```

para entidades funcionales.

#### Folios y códigos visibles

UUID no sustituye:

- folio de venta.
- SKU.
- código de barras.
- número de ticket.
- número de empleado.
- número de cliente.
- número de orden.
- código de tarjeta.

Estos campos son referencias comerciales y nunca la clave primaria de dominio.

#### Alcance obligatorio

Deben usar UUID como identidad única:

- sucursales.
- usuarios.
- roles.
- permisos asignados.
- productos.
- categorías.
- clientes.
- proveedores.
- ventas.
- detalles de venta.
- pagos.
- cajas.
- cortes.
- inventario por sucursal.
- movimientos de inventario.
- reservas de stock.
- detalles de reserva.
- mermas.
- recetas.
- componentes de recetas.
- producciones.
- lotes.
- compras.
- órdenes de compra.
- recepciones.
- transferencias.
- detalles de transferencia.
- cotizaciones.
- pedidos.
- delivery.
- direcciones.
- activos.
- mantenimientos.
- empleados.
- nómina.
- fidelidad.
- promociones.
- notificaciones.
- outbox.
- auditorías.
- trabajos de impresión.
- tablas puente y relaciones entre entidades.

#### Contratos y eventos

Todo Command, DTO, Use Case, QueryService, Repository y evento debe aceptar UUID.

Todo evento crítico debe incluir, cuando corresponda:

```text
event_id
operation_id
entity_id
branch_id
user_id
timestamp
source_module
payload
```

`event_id`, `operation_id` y `entity_id` deben ser UUID independientes.

#### Corte total de migración

No se permite una fase de convivencia dentro del runtime.

La migración debe:

1. cerrar la aplicación;
2. bloquear otra instancia;
3. crear backup completo de SQLite;
4. registrar checksum y versión del esquema;
5. abrir una transacción exclusiva;
6. crear tablas nuevas con PK/FK UUID;
7. crear mapas temporales `old_integer_id → new_uuid` únicamente dentro de la migración;
8. copiar y transformar todos los datos;
9. validar conteos y relaciones;
10. eliminar tablas antiguas;
11. renombrar las tablas nuevas;
12. recrear índices, constraints y triggers;
13. ejecutar `PRAGMA foreign_key_check`;
14. ejecutar pruebas de integridad;
15. confirmar la transacción;
16. eliminar mapas temporales;
17. arrancar únicamente con el esquema UUID.

Si cualquier validación falla:

1. rollback;
2. cerrar conexión;
3. restaurar backup;
4. registrar el error;
5. impedir inicio normal.

La aplicación nunca debe operar con una migración UUID incompleta.

---

## 4. Flujo obligatorio de trabajo para Codex

Codex debe trabajar en ciclos pequeños.

### 4.1 Ciclo de cada fase

1. Leer este archivo completo.
2. Leer `docs/architecture/*` si existen.
3. Identificar archivos afectados.
4. Crear o actualizar tests de protección antes de tocar lógica crítica.
5. Extraer lecturas a QueryService.
6. Extraer mutaciones a Use Case / Application Service.
7. Conservar lógica de negocio funcional.
8. Eliminar código legacy solo cuando la ruta nueva esté cubierta por tests.
9. Ejecutar pruebas.
10. Reportar:
   - archivos creados
   - archivos modificados
   - archivos eliminados
   - tests agregados
   - riesgos cubiertos
   - regresiones detectadas
   - siguiente paso recomendado

### 4.2 Prohibido

Codex no debe:

- Reescribir todo un módulo a ciegas.
- Cambiar reglas de negocio sin test.
- Crear tablas desde UI o servicios.
- Agregar SQL directo en PyQt.
- Pasar `AppContainer` completo a servicios nuevos.
- Agregar defaults numéricos arbitrarios.
- Usar listas largas para seleccionar entidades.
- Usar `QLineEdit` simple para teléfonos.
- Agregar rutas relativas nuevas.
- Mantener código muerto “por si acaso”.

---

## 5. Fases del refactor

### FASE 0 — Documentación base

Crear o actualizar:

```text
docs/architecture/ARCHITECTURE.md
docs/architecture/BACKEND_FRONTEND_LANGUAGE_RULES.md
docs/architecture/DATABASE_COMPATIBILITY.md
docs/architecture/UI_COMPONENT_RULES.md
docs/architecture/EVENT_CATALOG.md
docs/architecture/INSTALLER_AND_UPDATER.md
docs/architecture/REFACTOR_RULES.md
docs/architecture/MODULE_MAP.md
docs/architecture/DELETE_LEGACY_POLICY.md
```

Resultado:

- Reglas claras.
- Mapa de módulos.
- Criterios de eliminación.
- Contratos de eventos.
- Lineamientos SQLite/PostgreSQL.
- Lineamientos UI.

---

### FASE 1 — Tests de arquitectura

Crear:

```text
tests/architecture/test_no_sql_in_frontend.py
tests/architecture/test_no_commit_rollback_in_frontend.py
tests/architecture/test_no_schema_changes_outside_migrations.py
tests/architecture/test_backend_names_are_english.py
tests/architecture/test_no_container_passed_to_services.py
tests/architecture/test_no_hardcoded_numeric_defaults_in_ui.py
tests/architecture/test_no_plain_phone_inputs.py
tests/architecture/test_no_entity_combo_mass_loading.py
tests/architecture/test_no_hardcoded_paths.py
tests/architecture/test_no_deprecated_services_with_business_logic.py
tests/architecture/test_event_payload_contracts.py
tests/architecture/test_all_entity_ids_are_uuid.py
tests/architecture/test_no_integer_primary_keys.py
tests/architecture/test_no_autoincrement_entities.py
tests/architecture/test_no_int_id_casts.py
tests/architecture/test_no_lastrowid_entity_identity.py
tests/architecture/test_events_use_uuid_ids.py
tests/architecture/test_api_uses_uuid_ids.py
tests/architecture/test_no_legacy_identity_paths.py
```

Los tests pueden iniciar con allowlist temporal, pero deben:

- Listar archivos infractores.
- Fallar para nuevas infracciones.
- Documentar deuda técnica existente.
- Reducir la allowlist en cada fase.

---

### FASE 2 — Infraestructura base

Crear:

```text
backend/shared/app_paths.py
backend/infrastructure/updater/version_checker.py
backend/infrastructure/updater/update_manifest.py
backend/infrastructure/updater/update_downloader.py
backend/infrastructure/updater/update_installer.py
backend/infrastructure/db/database.py
backend/infrastructure/db/dialect.py
backend/infrastructure/db/unit_of_work.py
backend/infrastructure/db/transaction.py
backend/infrastructure/db/repositories/base_repository.py
backend/api/main.py
backend/api/dependencies.py
backend/api/routers/
backend/api/schemas/
```

Debe soportar:

- SQLite ahora.
- PostgreSQL futuro.
- `.exe` actualizable.
- Backup automático previo a actualización.
- AppData para datos persistentes.
- API futura sin duplicar lógica.

---

### FASE 2.5 — Corte total de identidad a UUID

Esta fase es obligatoria antes de continuar con refactors funcionales.

Crear:

```text
backend/shared/ids.py
migrations/standalone/200_uuid_only_schema_cutover.py
tests/integration/test_uuid_schema_migration.py
tests/integration/test_uuid_foreign_key_integrity.py
tests/integration/test_uuid_offline_collision_resistance.py
tests/integration/test_uuid_sales_inventory_flow.py
tests/integration/test_uuid_reservation_flow.py
tests/integration/test_uuid_product_recipe_flow.py
```

Tareas obligatorias:

1. Auditar todas las PK, FK, columnas `*_id`, DTO, comandos, eventos y contratos.
2. Construir un grafo completo de dependencias.
3. Crear backup automático previo al corte.
4. Reconstruir todas las tablas funcionales con PK/FK UUID.
5. Usar mapas temporales de migración solo dentro de la transacción.
6. Eliminar tablas y columnas enteras anteriores.
7. Eliminar `AUTOINCREMENT`, `lastrowid` e `int(..._id)`.
8. Actualizar dominio, aplicación, infraestructura, PyQt, API, eventos, outbox, fixtures, seeds y tests.
9. Ejecutar `PRAGMA foreign_key_check`.
10. Bloquear el arranque si la migración no queda completa.
11. No dejar compatibilidad legacy.
12. No dejar escritura o lectura dual.

Criterios de aceptación:

```text
[ ] Cero PK funcionales enteras.
[ ] Cero FK funcionales enteras.
[ ] Cero `INTEGER PRIMARY KEY AUTOINCREMENT` en tablas funcionales.
[ ] Cero `lastrowid` como identidad.
[ ] Cero casts `int(..._id)`.
[ ] Cero `legacy_id`.
[ ] Cero contratos `int | str`.
[ ] Cero tablas paralelas.
[ ] Todos los eventos usan UUID.
[ ] Todos los tests UUID pasan.
```

---

### FASE 3 — Componentes UI estándar

Crear:

```text
frontend/desktop/components/numeric_input.py
frontend/desktop/components/money_input.py
frontend/desktop/components/quantity_input.py
frontend/desktop/components/percent_input.py
frontend/desktop/components/integer_input.py
frontend/desktop/components/phone_input.py
frontend/desktop/components/search_selector.py
frontend/desktop/components/address_input.py
frontend/desktop/components/product_search_box.py
frontend/desktop/components/customer_search_box.py
frontend/desktop/components/supplier_search_box.py
frontend/desktop/components/employee_search_box.py
frontend/desktop/components/branch_search_box.py
frontend/desktop/components/driver_search_box.py
frontend/desktop/components/asset_search_box.py
frontend/desktop/components/status_badge.py
frontend/desktop/components/date_range_filter.py
```

Reglas:

- Números en 0 o vacío.
- Teléfono E.164.
- Entidades con búsqueda.
- Direcciones con mapa + fallback.
- UI en español.
- Nada de listas masivas.

---

### FASE 4 — Event Catalog y contratos

Crear:

```text
backend/shared/events/event_bus.py
backend/shared/events/event_contracts.py
backend/shared/events/event_names.py
backend/shared/events/event_dispatcher.py
```

Todo evento crítico debe incluir:

```text
event_id
event_name
operation_id
entity_id
branch_id
user_id o user_name
timestamp
source_module
payload
```

Eventos mínimos:

```text
SALE_COMPLETED
SALE_CANCELLED
SALE_REFUNDED
CUSTOMER_CREATED
CUSTOMER_UPDATED
CUSTOMER_CREDIT_LIMIT_CHANGED
PRODUCT_CREATED
PRODUCT_UPDATED
PRODUCT_PRICE_CHANGED
INVENTORY_MOVEMENT_RECORDED
INVENTORY_STOCK_LOW
INVENTORY_RESERVED
INVENTORY_RELEASED
WASTE_REGISTERED
WASTE_HIGH_VALUE_REGISTERED
MEAT_PRODUCTION_COMPLETED
MEAT_YIELD_VARIANCE_DETECTED
TRANSFER_DISPATCHED
TRANSFER_RECEIVED
TRANSFER_DIFFERENCE_DETECTED
DELIVERY_ORDER_CREATED
DELIVERY_DRIVER_ASSIGNED
DELIVERY_WEIGHT_ADJUSTED
DELIVERY_ORDER_DELIVERED
QUOTE_CREATED
QUOTE_APPROVED
QUOTE_CONVERTED_TO_SALE
LOYALTY_POINTS_EARNED
LOYALTY_POINTS_REDEEMED
LOYALTY_CARD_ASSIGNED
PURCHASE_PLAN_GENERATED
PURCHASE_ORDER_CREATED
PURCHASE_RECEIVED
CASH_SHIFT_OPENED
CASH_MOVEMENT_RECORDED
CASH_Z_CUT_GENERATED
CASH_DIFFERENCE_DETECTED
ASSET_CREATED
MAINTENANCE_SCHEDULED
MAINTENANCE_COMPLETED
NOTIFICATION_REQUESTED
TICKET_PRINT_REQUESTED
```

---

### FASE 5 — Query Services base

Crear:

```text
backend/application/queries/customer_query_service.py
backend/application/queries/product_query_service.py
backend/application/queries/supplier_query_service.py
backend/application/queries/employee_query_service.py
backend/application/queries/branch_query_service.py
backend/application/queries/driver_query_service.py
backend/application/queries/asset_query_service.py
backend/application/queries/delivery_query_service.py
backend/application/queries/transfer_query_service.py
backend/application/queries/waste_query_service.py
backend/application/queries/production_query_service.py
backend/application/queries/quote_query_service.py
backend/application/queries/loyalty_query_service.py
backend/application/queries/cash_register_query_service.py
backend/application/queries/purchase_planning_query_service.py
backend/application/queries/business_intelligence_query_service.py
```

Estos servicios alimentan:

- SearchSelector.
- KPIs.
- Tablas.
- Filtros.
- Autocompletados.
- Dashboards.

---

### FASE 6 — Use Cases / Application Services

Crear:

```text
backend/application/use_cases/
```

Use cases prioritarios:

```text
RegisterWasteUseCase
CreateSaleUseCase
CancelSaleUseCase
ExecuteMeatProductionUseCase
DispatchTransferUseCase
ReceiveTransferUseCase
CreateDeliveryOrderUseCase
AssignDeliveryDriverUseCase
AdjustDeliveryWeightUseCase
CreateProductUseCase
UpdateProductUseCase
CreateQuoteUseCase
ApproveQuoteUseCase
ConvertQuoteToSaleUseCase
OpenCashShiftUseCase
RegisterCashMovementUseCase
GenerateZCutUseCase
CreateCustomerUseCase
UpdateCustomerUseCase
AssignLoyaltyCardUseCase
RedeemLoyaltyPointsUseCase
GeneratePurchasePlanUseCase
CreatePurchaseOrderUseCase
ReceivePurchaseUseCase
CreateAssetUseCase
ScheduleMaintenanceUseCase
CompleteMaintenanceUseCase
```

---

### FASE 7 — Refactor por módulos

Orden obligatorio recomendado:

1. Configuración / configuración módulo
2. Merma
3. Productos
4. Procesamiento cárnico
5. Transferencias
6. Delivery
7. Caja
8. BI / Dashboard
9. Planeación de compras
10. Cotizaciones
11. Fidelidad / tarjetas
12. Activos
13. Clientes
14. Tickets / etiquetas
15. Hardware
16. Notificaciones
17. WhatsApp pedidos
18. Finanzas
19. RRHH
20. Compras
21. Ventas

Cada módulo debe cumplir checklist de aceptación.

---

## 6. Checklist obligatorio por módulo

Un módulo no se considera terminado si no cumple:

```text
[ ] Backend en inglés.
[ ] UI en español.
[ ] Sin SQL en UI.
[ ] Sin commit/rollback en UI.
[ ] Sin schema changes fuera de migrations.
[ ] Sin AppContainer completo en servicios.
[ ] Sin listas largas para entidades.
[ ] Usa SearchSelector donde aplica.
[ ] Usa PhoneInput donde aplica.
[ ] Usa AddressInput donde aplica.
[ ] Campos numéricos en 0 o vacío.
[ ] Sin defaults arbitrarios hardcodeados.
[ ] Usa QueryService para lecturas.
[ ] Usa UseCase/ApplicationService para mutaciones.
[ ] Emite eventos con operation_id.
[ ] Compatible con SQLite/PostgreSQL.
[ ] Preparado para API futura.
[ ] Tests unitarios.
[ ] Tests de integración.
[ ] Tests de arquitectura.
[ ] Validación manual documentada.
[ ] Código legacy eliminado.
[ ] Todas las entidades usan UUIDv7 como única identidad.
[ ] Todas las FK funcionales usan UUID.
[ ] Sin PK `INTEGER AUTOINCREMENT`.
[ ] Sin `lastrowid` para identidad.
[ ] Sin casts `int(..._id)`.
[ ] Sin `legacy_id`, escritura dual o fallback.
[ ] Eventos, DTO, Commands, UseCases y API usan UUID.
[ ] Migración UUID validada con integridad referencial.
```

---

## 7. Guía por módulo

### 7.1 Configuración

Crear:

```text
SystemSettingsService
ModuleSettingsService
CompanyProfileService
PaymentProviderSettingsService
CommissionSettingsService
ClosingPeriodService
```

Eliminar:

- `CREATE TABLE` desde UI.
- `INSERT defaults` desde UI.
- SQL directo.
- Defaults numéricos hardcodeados.

---

### 7.2 Merma

Crear:

```text
WasteApplicationService
RegisterWasteUseCase
WasteQueryService
WasteRepository
WasteFinanceHandler
WasteInventoryHandler
```

Eliminar:

- `ALTER TABLE` desde UI.
- SQL directo en UI.
- Fallback `UPDATE productos`.
- Evento genérico cuando debe ser `WASTE_REGISTERED`.

---

### 7.3 Productos

Crear:

```text
ProductCatalogService
ProductTypePolicy
ProductPricingService
ProductImageService
ProductBarcodeService
ProductRecipeConfigService
ProductQueryService
```

Reglas:

- `products.id` es UUIDv7.
- Toda referencia a producto usa `product_id` UUID.
- No existe ID entero alterno ni `legacy_id`.
- Inventario, ventas, compras, recetas, producción, merma, transferencias, etiquetas, pedidos y cotizaciones usan el mismo UUID.
- Tipos de producto en backend.
- Receta configurada por servicio.
- Precios/costos por servicio.
- UI solo captura.

---

### 7.4 Procesamiento cárnico

Crear:

```text
MeatProductionApplicationService
ExecuteMeatProductionUseCase
YieldCalculator
ProductionCostService
ProductionInventoryHandler
ProductionWasteHandler
```

Debe conservar:

- SUBPRODUCTO.
- COMBINACION.
- PRODUCCION.
- Rendimiento.
- Merma.
- Inventario.
- Costos.

---

### 7.5 Transferencias

Crear:

```text
TransferApplicationService
DispatchTransferUseCase
ReceiveTransferUseCase
CancelTransferUseCase
TransferQueryService
TransferRepository
```

Eliminar:

- SQL en KPIs UI.
- Código muerto.
- Estados duplicados.
- Mutaciones fuera del servicio.

---

### 7.6 Delivery

Crear:

```text
DeliveryApplicationService
CreateDeliveryOrderUseCase
AssignDriverUseCase
AdjustDeliveryWeightUseCase
MarkDeliveredUseCase
DeliveryQueryService
MapAddressService
```

UI obligatoria:

- CustomerSearchBox.
- ProductSearchBox.
- DriverSearchBox.
- AddressInput.
- PhoneInput.
- MoneyInput.
- QuantityInput.

---

### 7.7 Caja

Crear:

```text
CashRegisterApplicationService
OpenCashShiftUseCase
RegisterCashMovementUseCase
GenerateZCutUseCase
CashRegisterQueryService
```

Eventos:

```text
CASH_SHIFT_OPENED
CASH_MOVEMENT_RECORDED
CASH_Z_CUT_GENERATED
CASH_DIFFERENCE_DETECTED
```

---

### 7.8 BI / Dashboard

Crear:

```text
BusinessIntelligenceQueryService
SalesMetricsService
MarginMetricsService
CustomerMetricsService
InventoryMetricsService
ExecutiveDashboardService
```

Eliminar:

- SQL directo en dashboard.
- KPIs calculados en UI.
- Duplicidad de métricas.

---

### 7.9 Planeación de compras

Crear:

```text
PurchasePlanningService
GeneratePurchasePlanUseCase
PurchasePlanningQueryService
PurchaseSuggestionService
```

Debe considerar:

- Ventas históricas.
- Stock actual.
- Stock mínimo.
- Pedidos programados.
- Cotizaciones aprobadas.
- Merma.
- Lead time proveedor.
- Compras pendientes.
- Transferencias pendientes.

---

### 7.10 Cotizaciones

Crear:

```text
QuoteApplicationService
CreateQuoteUseCase
ApproveQuoteUseCase
RejectQuoteUseCase
ExpireQuoteUseCase
ConvertQuoteToSaleUseCase
QuoteQueryService
```

Eliminar:

- Servicio recibiendo `container` completo.
- Conversión a venta acoplada.

---

### 7.11 Fidelidad / tarjetas

Crear:

```text
LoyaltyApplicationService
LoyaltyLedgerService
LoyaltyCardService
ReferralProgramService
BirthdayRewardService
RetentionService
RaffleService
LoyaltyFinanceService
```

Debe conservar:

- Puntos.
- Canje.
- Tarjetas.
- Referidos.
- Cumpleaños.
- Rifas.
- Retención.
- Pasivo financiero.

---

### 7.12 Activos

Crear:

```text
AssetApplicationService
CreateAssetUseCase
UpdateAssetUseCase
ScheduleMaintenanceUseCase
CompleteMaintenanceUseCase
DepreciationService
AssetFinanceHandler
AssetQueryService
```

Eliminar:

- SQL directo en UI.
- PDF generado dentro del módulo si corresponde a report service.

---

### 7.13 Tickets / etiquetas

Crear:

```text
TicketTemplateService
TicketRenderContext
HtmlTicketRenderer
EscPosTicketRenderer
PdfTicketRenderer
LabelTemplateService
BarcodeService
QrCodeService
```

Regla:

- Preview HTML y ESC/POS real deben compartir contrato de layout.

---

### 7.14 Hardware

Crear:

```text
ScaleService
PrinterService
CashDrawerService
HardwareDiagnosticService
TorreyScaleDriver
RhinoScaleDriver
UsbEscPosPrinter
NetworkEscPosPrinter
SerialCashDrawer
```

---

### 7.15 Notificaciones

Crear:

```text
NotificationRouter
NotificationTemplateService
RecipientResolver
WhatsAppNotificationSender
PosInboxNotificationSender
```

---

### 7.16 WhatsApp pedidos

Crear:

```text
WhatsAppOrderApplicationService
ParseWhatsAppOrderUseCase
CreateOrderFromWhatsAppUseCase
WhatsAppMessageService
WhatsAppTemplateService
```

Debe conectar con:

- Delivery.
- Sales.
- Inventory reservation.
- Payments.
- Notifications.
- Customer.
- Loyalty.

---

### 7.17 Inventario

Crear o consolidar:

```text
InventoryApplicationService
InventoryQueryService
InventoryAvailabilityQueryService
InventoryRepository
StockReservationApplicationService
```

Reglas:

- `inventory_stock` usa PK compuesta `(branch_id, product_id)` con UUID.
- `inventory_movements.id`, `operation_id`, `product_id` y `branch_id` son UUID.
- Reservas y detalles de reserva usan UUID.
- `inventory_stock` es la única fuente de stock físico.
- La disponibilidad es `físico - reservado`.
- No usar `productos.existencia`, `branch_inventory` ni tablas legacy.
- No crear schema desde servicios.

---

### 7.18 Ventas

Crear o consolidar:

```text
CreateSaleUseCase
CancelSaleUseCase
SaleApplicationService
SaleQueryService
SaleInventoryHandler
SaleFinanceHandler
```

Reglas:

- `sales.id`, `sale_items.id`, `product_id`, `branch_id`, `customer_id`, `user_id` y `operation_id` son UUID.
- Folio es un campo comercial independiente.
- La venta usa disponibilidad canónica de inventario.
- La reserva propia se excluye durante la validación y se confirma atómicamente.
- Venta, inventario, caja y finanzas comparten una sola UnitOfWork.
- No usar `lastrowid` para identificar la venta.
- No aceptar IDs enteros.

---

## 8. Validación continua

Después de cada fase o módulo, Codex debe ejecutar:

```bash
python -m pytest tests/architecture
python -m pytest tests/unit
python -m pytest tests/integration
```

Si hay CI segmentado, ejecutar el segmento afectado.

Codex debe reportar:

```text
PASSED
FAILED
SKIPPED
New violations
Existing allowlist violations
Files changed
Files deleted
Next module
```

---

## 9. Política de eliminación de legacy

La política general es eliminar toda ruta legacy tan pronto exista una ruta canónica protegida por tests.

Para identidad UUID la regla es más estricta:

- No se permite compatibilidad permanente.
- No se permite escritura dual.
- No se permite lectura dual.
- No se permite `legacy_id`.
- No se permite fallback de UUID a entero.
- No se permiten tablas paralelas.
- Los mapas `old_id → UUID` solo pueden existir dentro de la migración atómica y deben eliminarse antes del commit.

Se elimina código legacy cuando:

1. Existe ruta nueva.
2. La ruta nueva tiene tests.
3. El flujo manual sigue funcionando.
4. Ya no hay imports.
5. No hay referencias dinámicas.
6. La eliminación no rompe CI.

No se conserva código por miedo.

---

## 10. Prompt de arranque para Codex

Usar este prompt al iniciar el refactor:

```text
Lee el archivo SPJ_REFACTOR_SKILL.md completo y úsalo como regla obligatoria.

Vamos a iniciar el refactor maestro del ERP/POS SPJ.

Primera tarea:
Ejecutar FASE 0 y FASE 1.

Debes:
1. Crear documentación base en docs/architecture/.
2. Crear tests de arquitectura.
3. Los tests pueden usar allowlist temporal para infracciones existentes.
4. Deben fallar para nuevas infracciones.
5. No modificar lógica de negocio.
6. No romper la app.
7. Reportar deuda técnica detectada.
8. Indicar siguiente fase recomendada.

No hagas refactor funcional todavía. Primero instala las reglas y las protecciones.
```

---

## 11. Prompt para continuar después de cada fase

```text
Lee SPJ_REFACTOR_SKILL.md.

Continúa con la siguiente fase pendiente según el reporte anterior.

Reglas:
- No romper lógica funcional.
- Proteger con tests antes de eliminar legacy.
- Backend en inglés.
- UI en español.
- Cero SQL en UI.
- Cero schema changes fuera de migrations.
- Componentes estándar para teléfono, búsqueda, dirección y números.
- Eventos con `event_id`, `operation_id` y `entity_id` UUID.
- Cero IDs enteros funcionales.
- Cero `legacy_id`, escritura dual o fallback.
- Reporte final obligatorio.

Ejecuta solo una fase o un módulo por vez.
```

---

## 12. Prompt para módulo específico

```text
Lee SPJ_REFACTOR_SKILL.md.

Refactoriza el módulo: [MODULO].

Sigue el checklist obligatorio del skill.

Debes:
1. Diagnosticar el módulo.
2. Crear tests de protección.
3. Extraer lecturas a QueryService.
4. Extraer mutaciones a UseCase/ApplicationService.
5. Reemplazar controles UI por componentes estándar.
6. Eliminar SQL en UI.
7. Eliminar commit/rollback en UI.
8. Eliminar schema changes fuera de migrations.
9. Emitir eventos con operation_id.
10. Mantener lógica de negocio funcional.
11. Eliminar legacy muerto.
12. Ejecutar pruebas.
13. Migrar toda identidad y relación del módulo a UUIDv7.
14. Eliminar PK/FK enteras, casts `int(..._id)`, `lastrowid` y compatibilidad legacy.
15. Reportar cambios, riesgos y validación manual.
```

---

## 13. Estado final esperado

El proyecto queda con:

```text
PyQt Desktop en español
  ↓
Componentes UI estándar
  ↓
Use Cases backend en inglés
  ↓
Domain Services
  ↓
Repositories
  ↓
SQLite / PostgreSQL
  ↓
EventBus
  ↓
Inventario, caja, finanzas, fidelidad, delivery, WhatsApp, BI, compras, producción, tickets
  ↓
API FastAPI futura
  ↓
.exe instalable y actualizable
```

---

## 14. Frase de control

```text
No parchar.
No duplicar.
No ocultar legacy.
Un UUID por entidad.
Cero identidad dual.
Proteger, extraer, probar, eliminar.
```
