# SPJ_BUGFIX_AUDIT_CORRECTION_SKILL.md

## Propósito

Este skill define el flujo obligatorio para corregir bugs, regresiones y hallazgos detectados en auditorías funcionales del proyecto `pos_spj_v13.4`, sin romper la arquitectura definida por:

* `pos_spj_v13.4/docs/skills/SPJ_REFACTOR_SKILL.md`
* `pos_spj_v13.4/docs/skills/SPJ_UI_UX_ARCHITECTURE_SKILL.md`
* `AGENTS.md`
* `docs/architecture/REFACTOR_RULES.md`

Este skill no reemplaza `SPJ_REFACTOR_SKILL.md`; lo complementa.

Toda corrección debe respetar la regla central del proyecto:

> Corregir código fuente, schema canónico y tests. No rescatar legacy. No parchar DB viva. No ocultar problemas con fallbacks silenciosos.

---

## Contexto del proyecto

La app SPJ POS / ERP v13.4 está en desarrollo activo.

Por lo tanto:

* No se deben conservar datos legacy.
* No se deben crear scripts temporales de rescate.
* No se deben crear migraciones nuevas para compatibilidad legacy.
* No se debe hacer lectura dual.
* No se debe hacer escritura dual.
* No debe existir fallback UUID → entero.
* No debe existir `legacy_id`.
* No debe existir migración tipo “200” para rescatar datos viejos.
* Se debe corregir el código fuente y el schema base/canónico.
* La DB local de desarrollo debe resetearse si está contaminada.

---

## Reglas obligatorias

### Identidad

Está prohibido:

* `int(..._id)` para identidades funcionales.
* IDs enteros funcionales.
* `lastrowid`.
* `AUTOINCREMENT`.
* `INTEGER PRIMARY KEY AUTOINCREMENT`.
* `MAX(id)+1`.
* `randomblob()` como identidad de dominio.
* Usar folios, tickets, SKU o códigos de barras como PK.
* Usar `sucursal_id = 1` como fallback.
* Usar `branch_id = 1` como fallback.

Obligatorio:

* Usar `backend.shared.ids.new_uuid()` para identidades persistentes.
* Usar UUIDv7 como única identidad persistente.
* En SQLite usar `id TEXT PRIMARY KEY`.
* FKs funcionales deben ser `TEXT`.

---

### UI / PyQt

PyQt no debe:

* Ejecutar SQL.
* Crear schema.
* Alterar schema.
* Hacer `commit()`.
* Hacer `rollback()`.
* Decidir reglas de negocio.
* Registrar operaciones financieras directamente.
* Convertir UUID a entero.
* Usar defaults arbitrarios funcionales.
* Ocultar errores críticos con `except Exception: pass`.

La UI solo debe:

* Renderizar widgets.
* Leer campos.
* Validar formato superficial.
* Mostrar errores.
* Llamar Query Services.
* Llamar Application Services / Use Cases.
* Mostrar resultados.

---

### Servicios

Los servicios no deben:

* Crear tablas.
* Alterar tablas.
* Usar schema-healing.
* Hacer compatibilidad legacy.
* Tragar errores críticos silenciosamente.

Los servicios sí deben:

* Validar reglas de negocio.
* Recibir DTOs / Commands.
* Usar repositories.
* Usar UnitOfWork.
* Emitir eventos con `operation_id`.
* Fallar claramente cuando una dependencia crítica no está disponible.

---

### Migraciones

Solo `migrations/` puede modificar schema.

No crear:

* `fix_db.py`
* `repair_db.py`
* `patch_db.py`
* migraciones de rescate
* scripts para adaptar DB contaminada

Se debe corregir:

* `migrations/m000_base_schema.py`
* migraciones fuente existentes cuando aplique

---

## Flujo obligatorio de corrección

Para cada bug:

1. Leer primero los skills y reglas del repo.
2. Identificar el flujo funcional roto.
3. Identificar archivos afectados.
4. Crear o actualizar tests que reproduzcan el bug.
5. Confirmar que el test falla.
6. Corregir en la ruta canónica.
7. Eliminar legacy relacionado.
8. Ejecutar tests.
9. Reportar archivos modificados, tests y riesgos.

No corregir a ciegas.

No reescribir módulos completos sin protección de tests.

---

# FASE 0 — Auditoría inicial obligatoria

Antes de modificar, buscar y reportar los siguientes archivos y patrones.

## Archivos clave a revisar

```text
pos_spj_v13.4/modulos/compras_pro.py
pos_spj_v13.4/modulos/clientes.py
pos_spj_v13.4/modulos/caja.py
pos_spj_v13.4/modulos/productos.py
pos_spj_v13.4/modulos/planeacion_compras.py
pos_spj_v13.4/modulos/ticket_designer.py
pos_spj_v13.4/modulos/finanzas_unificadas.py
pos_spj_v13.4/interfaz/main_window.py
pos_spj_v13.4/core/session_context.py
pos_spj_v13.4/core/permissions.py
pos_spj_v13.4/security/rbac.py
pos_spj_v13.4/repositories/config_repository.py
pos_spj_v13.4/repositories/security_repository.py
pos_spj_v13.4/repositories/proveedor_repository.py
pos_spj_v13.4/backend/infrastructure/db/repositories/finance_read_repository.py
pos_spj_v13.4/core/services/auth_service.py
pos_spj_v13.4/core/services/configuration_settings_service.py
pos_spj_v13.4/core/services/sales_service.py
pos_spj_v13.4/core/services/payment_normalization.py
pos_spj_v13.4/core/services/forecast_service.py
pos_spj_v13.4/core/services/recipes/recipe_service.py
pos_spj_v13.4/application/services/customer_credit_service.py
pos_spj_v13.4/application/services/accounts_receivable_service.py
pos_spj_v13.4/core/events/handlers/finance_handler.py
pos_spj_v13.4/core/events/handlers/purchase_handler.py
pos_spj_v13.4/core/events/wiring.py
pos_spj_v13.4/core/services/purchase_service.py
pos_spj_v13.4/core/services/lote_service.py
pos_spj_v13.4/core/use_cases/compra.py
pos_spj_v13.4/application/purchases/traditional_purchase_uc.py
pos_spj_v13.4/core/services/enterprise/finance_service.py
pos_spj_v13.4/core/services/finance/accounts_payable_service.py
pos_spj_v13.4/core/services/finance/accounts_receivable_service.py
pos_spj_v13.4/core/services/finance/treasury_service.py
pos_spj_v13.4/core/services/finance/general_ledger_service.py
pos_spj_v13.4/core/services/finance/journal_entry_service.py
pos_spj_v13.4/application/services/caja_application_service.py
pos_spj_v13.4/core/services/printer_service.py
pos_spj_v13.4/core/services/hardware_service.py
pos_spj_v13.4/core/services/microservice_launcher.py
pos_spj_v13.4/core/engines/template_engine.py
pos_spj_v13.4/migrations/m000_base_schema.py
```

## Patrones obligatorios de búsqueda

Buscar:

```text
int(user_id)
int(usuario_id)
int(role_id)
int(rol_id)
int(branch_id)
int(sucursal_id)
int(cliente_id)
int(compra_id)
int(lote_id)
int(venta_id)
int(producto_id)
lastrowid
AUTOINCREMENT
CREATE TABLE
ALTER TABLE
INSERT INTO movimientos_caja
escpos.printer.Usb
ticket_template_html
metodo_pago
id_cliente
loyalty_snapshots
ultimo_evento_id
lotes
_prov_repo
permission_codes_for_user
usuario_permisos
usuario_sucursal_permisos
rol_permisos
intentos_fallidos
bloqueado_hasta
desbloquear
unlock
forecast_service
generar_plan_compras
ExponentialSmoothing
financial_documents
financial_event_log
journal_entries
capital_movements
_tbl_den
_den_sub_labels
DialogoReceta
product_recipes
recipe_components
combo
compuesto
```

## Reporte obligatorio de auditoría

Antes de corregir, reportar:

* Archivos infractores.
* Bug asociado.
* Riesgo por módulo.
* Ruta legacy usada actualmente.
* Ruta canónica esperada.
* Tests necesarios.
* Orden recomendado de corrección.

---

# FASE 1 — Tests de arquitectura

Crear o actualizar:

```text
tests/architecture/test_no_int_id_casts.py
tests/architecture/test_no_lastrowid_entity_identity.py
tests/architecture/test_no_schema_changes_outside_migrations.py
tests/architecture/test_no_sql_in_pyqt_modules.py
tests/architecture/test_no_commit_rollback_in_pyqt.py
tests/architecture/test_no_purchase_writes_to_movimientos_caja.py
tests/architecture/test_no_direct_escpos_usb_default.py
tests/architecture/test_no_forecast_sql_in_pyqt.py
tests/architecture/test_no_finance_kpi_reads_unknown_tables_without_guard.py
```

Estos tests deben fallar si encuentran:

* Casts `int(..._id)`.
* `lastrowid`.
* `CREATE TABLE` fuera de `migrations/`.
* `ALTER TABLE` fuera de `migrations/`.
* SQL directo en `modulos/`.
* `commit()` o `rollback()` en `modulos/`.
* Compras escribiendo directamente en `movimientos_caja`.
* Uso directo de `escpos.printer.Usb` como default.
* Forecast con SQL directo desde PyQt.
* KPIs financieros leyendo tablas inciertas sin guard o sin fuente canónica.

---

# FASE 2 — Schema base limpio

Revisar y corregir:

```text
pos_spj_v13.4/migrations/m000_base_schema.py
```

No crear migración nueva de rescate.

## Tablas mínimas a validar

### usuarios

```sql
id TEXT PRIMARY KEY
usuario TEXT UNIQUE
password_hash TEXT
rol TEXT
sucursal_id TEXT
activo INTEGER DEFAULT 1
intentos_fallidos INTEGER DEFAULT 0
bloqueado_hasta TEXT NULL
locked_reason TEXT NULL
updated_at DATETIME NULL
```

### roles

```sql
id TEXT PRIMARY KEY
nombre TEXT UNIQUE NOT NULL
descripcion TEXT
```

### rol_permisos

```sql
id TEXT PRIMARY KEY
rol_id TEXT NOT NULL
modulo TEXT NOT NULL
accion TEXT NOT NULL
permitido INTEGER DEFAULT 1
```

### usuario_permisos

```sql
id TEXT PRIMARY KEY
usuario_id TEXT NOT NULL
modulo TEXT NOT NULL
accion TEXT NOT NULL
permitido INTEGER DEFAULT 1
```

### usuario_sucursal_permisos

```sql
id TEXT PRIMARY KEY
usuario_id TEXT NOT NULL
sucursal_id TEXT NOT NULL
modulo TEXT NOT NULL
accion TEXT NOT NULL
permitido INTEGER DEFAULT 1
```

### clientes

```sql
id TEXT PRIMARY KEY
allows_credit INTEGER DEFAULT 0
credit_limit REAL DEFAULT 0
credit_balance REAL DEFAULT 0
activo INTEGER DEFAULT 1
```

### cuentas_por_cobrar

```sql
id TEXT PRIMARY KEY
cliente_id TEXT NOT NULL
venta_id TEXT NOT NULL
folio TEXT NOT NULL
monto_original REAL NOT NULL
saldo_pendiente REAL NOT NULL
sucursal_id TEXT NOT NULL
estado TEXT DEFAULT 'pendiente'
```

Debe existir índice único por `venta_id` o por `folio + cliente_id`.

### loyalty_snapshots

```sql
id TEXT PRIMARY KEY
cliente_id TEXT NOT NULL UNIQUE
puntos_actuales INTEGER NOT NULL DEFAULT 0
nivel TEXT NOT NULL DEFAULT 'Bronce'
visitas INTEGER NOT NULL DEFAULT 0
importe_total REAL NOT NULL DEFAULT 0
ultimo_evento_id TEXT
fecha_snapshot DATETIME DEFAULT (datetime('now'))
```

### lotes

```sql
id TEXT PRIMARY KEY
uuid TEXT NOT NULL UNIQUE
producto_id TEXT NOT NULL
numero_lote TEXT NOT NULL
proveedor_id TEXT
peso_inicial_kg REAL DEFAULT 0
peso_actual_kg REAL DEFAULT 0
costo_kg REAL DEFAULT 0
fecha_caducidad DATE
sucursal_id TEXT NOT NULL
estado TEXT DEFAULT 'activo'
```

Si `uuid` se conserva, no debe ser identidad funcional separada de `id`.

### movimientos_lote

```sql
id TEXT PRIMARY KEY
lote_id TEXT NOT NULL
tipo TEXT NOT NULL
cantidad_kg REAL NOT NULL
referencia TEXT
usuario TEXT
fecha DATETIME DEFAULT (datetime('now'))
```

### recetas / combos

Validar o crear canónicamente:

```text
product_recipes
recipe_components
combo_definitions
combo_components
```

Regla preferida:

* Combo = producto compuesto con receta/componentes.
* No duplicar modelo si `product_recipes` cubre combos.
* Si el combo necesita precio paquete o descuento, agregar campos canónicos al producto o tabla de pricing.
* No duplicar inventario.

---

# FASE 3 — Usuarios / desbloqueo por intentos fallidos

## Bug

Existe bloqueo por intentos fallidos, pero no hay flujo administrativo claro para desbloquear usuario.

## Archivos

```text
core/services/auth_service.py
repositories/config_repository.py
core/services/configuration_settings_service.py
modulos/configuracion.py
core/security/permission_catalog.py
migrations/m000_base_schema.py
```

## Corrección

Crear servicio o caso de uso:

```python
UserSecurityService.unlock_user(user_id: str, operation_id: str, actor_id: str)
```

Debe resetear:

```text
intentos_fallidos = 0
bloqueado_hasta = NULL
locked_reason = NULL
```

Debe auditar:

```text
accion = USER_UNLOCKED
modulo = CONFIG_SEGURIDAD
actor
usuario_desbloqueado
fecha
operation_id
```

Debe exigir permiso:

```text
CONFIG_SEGURIDAD.editar
```

o:

```text
USUARIOS.desbloquear
```

## UI

En Configuración / Seguridad / Usuarios agregar:

```text
Desbloquear usuario
```

Mostrar:

```text
intentos_fallidos
bloqueado_hasta
```

El botón solo debe estar activo si el usuario está bloqueado o tiene intentos fallidos.

## Tests

```text
tests/integration/test_admin_unlocks_locked_user.py
tests/integration/test_unlock_user_requires_permission.py
tests/integration/test_login_lockout_and_unlock_flow.py
```

---

# FASE 4 — Compras: `_prov_repo` y sucursales

## Bug

`ModuloComprasPro` usa:

```python
self._prov_repo.get_sucursales_activas()
```

sin inicializar `_prov_repo`.

## Corrección mínima

Inicializar:

```python
self._prov_repo = ProveedorRepository(self.container.db)
```

## Corrección preferida

Crear:

```text
BranchQueryService
```

y usar:

```python
branch_query_service.list_active_branches()
```

## Validación

* Abrir Compras.
* Entrar a QR / etiquetas / asignar.
* Debe cargar sucursales sin `AttributeError`.

---

# FASE 5 — Compras: método y forma de pago duplicados

## Bug

En Compras están repetidos los datos de método/forma de pago en pantalla central y derecha.

## Archivos

```text
modulos/compras_pro.py
application/purchases/traditional_purchase_uc.py
backend/application/commands/purchase_commands.py
backend/infrastructure/db/repositories/compras_write_repository.py
```

## Regla

Debe haber una sola fuente de verdad para la condición financiera de compra.

Conceptos canónicos:

```text
Condición de compra: CREDITO, CONTADO, PARCIAL
Origen de fondos: CAPITAL_OPERATIVO, BANCO, TESORERIA, CAJA_POS_EXPLICITA
Método de pago: TRANSFERENCIA, EFECTIVO_CAPITAL, CHEQUE, TERMINAL, OTRO
```

Caja POS no debe ser default.

## UI esperada

Panel central editable:

```text
Condición de compra
Origen de fondos
Método de pago
Monto pagado
Saldo / CxP calculada
```

Panel derecho solo lectura:

```text
Totales
Resumen financiero
Pagado desde: Capital/Banco/CxP
```

## Tests

```text
tests/ui/test_purchase_payment_fields_single_source.py
tests/integration/test_purchase_command_payment_payload.py
```

---

# FASE 6 — Compras / lotes

## Archivos

```text
core/services/purchase_service.py
core/services/lote_service.py
migrations/m000_base_schema.py
```

## Reglas

* Todo lote debe tener `id` UUIDv7.
* Si existe `uuid`, debe ser igual a `id` o no debe ser identidad funcional separada.
* No usar `lower(hex(randomblob(16)))`.
* No usar `lastrowid`.
* `movimientos_lote.id` debe generarse con `new_uuid()`.
* `LoteService` no debe crear schema.

## Test

```text
tests/integration/test_purchase_lot_schema_flow.py
```

Debe validar:

* Compra crea lote con `id`, `uuid`, `producto_id`, `numero_lote`, `sucursal_id`.
* Compra crea `movimientos_lote` con `id`.
* No falla por `lotes.uuid`.

---

# FASE 7 — Fidelidad / Scheduler

## Bug

```text
no such column: ls.ultimo_evento_id
```

## Archivos

```text
core/services/scheduler_service.py
migrations/m000_base_schema.py
```

## Reglas

* `SchedulerService` no debe crear ni alterar schema.
* `cliente_id` y `ultimo_evento_id` son `TEXT` UUID.
* No comparar UUID contra `0`.
* No usar `int(ultimo_evento_id)`.
* Usar `new_uuid()` para insertar `loyalty_snapshots.id`.

## Test

```text
tests/integration/test_loyalty_snapshot_scheduler_schema.py
```

---

# FASE 8 — Ventas / crédito cliente

## Archivos

```text
core/services/sales_service.py
application/services/customer_credit_service.py
core/services/payment_normalization.py
```

## Regla

Venta a crédito debe fallar si:

* No hay `client_id`.
* El cliente no existe.
* El cliente está inactivo.
* `allows_credit != 1`.
* `credit_limit <= 0`.
* `credit_balance + total > credit_limit`.
* `customer_service` no está disponible.

## Mensajes esperados

```text
Para vender a crédito debe seleccionar un cliente con crédito autorizado.
El cliente no tiene crédito autorizado.
El cliente no tiene límite de crédito configurado.
Crédito insuficiente: disponible $X, requerido $Y.
```

## Test

```text
tests/integration/test_credit_sale_requires_valid_customer.py
```

Casos:

* Crédito sin cliente falla.
* Cliente inexistente falla.
* Cliente sin crédito falla.
* Cliente con límite 0 falla.
* Cliente con límite insuficiente falla.
* Cliente válido pasa.

---

# FASE 9 — CxC en Finanzas

## Archivos

```text
core/events/handlers/finance_handler.py
application/services/accounts_receivable_service.py
core/services/sales_service.py
```

## Reglas

* Venta a crédito válida debe crear CxC.
* CxC debe crearse dentro del flujo crítico/transaccional de venta.
* Si falla CxC, debe fallar la venta.
* No omitir CxC silenciosamente.
* Debe ser idempotente por `venta_id` o `folio`.
* No duplicar CxC al reintentar evento.
* Actualizar `clientes.credit_balance`.
* Usar `AccountsReceivableService` como ruta canónica.

## Test

```text
tests/integration/test_credit_sale_creates_cxc_and_updates_balance.py
```

---

# FASE 10 — Clientes / historial

## Bug

```text
name 'sqlite3' is not defined
```

## Archivo

```text
modulos/clientes.py
```

## Parche inmediato permitido

Agregar `import sqlite3` para estabilizar.

## Corrección real

Crear:

```text
backend/application/queries/customer_history_query_service.py
```

Métodos:

```python
get_purchase_history(customer_id: str) -> list[dict]
get_points_history(customer_id: str) -> list[dict]
get_credit_history(customer_id: str) -> list[dict]
```

## Reglas

* Usar `cliente_id`, no `id_cliente`.
* Usar `forma_pago`, no `metodo_pago`.
* No SQL directo desde PyQt.
* No `commit()` ni `rollback()` en `modulos/clientes.py`.
* Si falta tabla opcional, devolver lista vacía con warning controlado.

## Tests

```text
tests/integration/test_customer_history_query_service.py
tests/architecture/test_no_sql_in_clientes_ui.py
tests/architecture/test_no_commit_rollback_in_clientes_ui.py
```

---

# FASE 11 — Roles y permisos UUID

## Bug

```text
invalid literal for int() with base 10: '<UUID>'
```

## Archivos

```text
repositories/config_repository.py
core/session_context.py
security/rbac.py
repositories/security_repository.py
core/security/permission_catalog.py
interfaz/main_window.py
```

## Corrección principal

En `ConfigRepository.permission_codes_for_user()`:

* Eliminar `int(row[0])`.
* Usar `user_uuid = str(row[0]).strip().lower()`.
* Pasar `user_uuid` a overrides y restricciones por sucursal.

Cambiar firmas:

```python
_apply_user_permission_overrides(self, user_id: str, permissions: set[str])
_apply_branch_permission_restrictions(self, user_id: str, branch_id: str | None, permissions: set[str])
```

## Reglas

* `usuario_permisos.usuario_id` compara contra UUID.
* `usuario_sucursal_permisos.usuario_id` compara contra UUID.
* `usuario_sucursal_permisos.sucursal_id` compara contra UUID.
* `SessionContext.user_id` y `SessionContext.sucursal_id` son `str`.
* Eliminar comentarios “legacy integer”.
* No usar `sucursal_id=1`.
* No usar `ur.sucursal_id=0`.

## Permisos mínimos por rol

### cajero

```text
DASHBOARD.ver
POS.ver
POS.crear
CAJA.ver
CLIENTES.ver
```

### compras

```text
COMPRAS.ver
COMPRAS.crear
COMPRAS.recibir
```

### finanzas

```text
FINANZAS_UNIFICADAS.ver
CAJA.ver
```

### inventario

```text
INVENTARIO.ver
PRODUCTOS.ver
TRANSFERENCIAS.ver
```

### admin

```text
todos
```

## Tests

```text
tests/integration/test_permissions_uuid_user.py
tests/integration/test_session_permissions_uuid.py
tests/architecture/test_no_int_id_casts_permissions.py
```

---

# FASE 12 — Compras no deben afectar Caja

## Bug contable

Las compras se registran como salida de Caja, pero deben salir de Capital, Tesorería, Bancos o quedar como CxP.

## Regla

Caja/POS solo representa dinero físico operativo de sucursal.

Caja registra:

* Ventas en efectivo.
* Ingresos directos del módulo Caja.
* Egresos directos del módulo Caja.
* Retiros.
* Ajustes.
* Fondo.
* Corte Z.

Caja no registra:

* Compras de inventario.
* Pagos a proveedores desde banco/tesorería.
* CAPEX.
* Activos fijos.
* Nómina bancaria.

## Archivos

```text
core/use_cases/compra.py
application/purchases/traditional_purchase_uc.py
core/events/handlers/purchase_handler.py
core/services/finance/treasury_service.py
application/services/caja_application_service.py
```

## Asientos esperados

Compra a crédito:

```text
Debe: inventario_almacen
Haber: cuentas_por_pagar
```

Compra pagada desde capital:

```text
Debe: inventario_almacen
Haber: capital_operativo / banco / tesoreria
```

Compra parcial:

```text
Debe: inventario_almacen por total
Haber: capital_operativo por pagado
Haber: cuentas_por_pagar por saldo
```

## Guarda en Caja

Rechazar movimientos con:

```text
modulo == "compras"
referencia_tipo == "compra"
```

Mensaje:

```text
Las compras no se registran desde Caja. Use Tesorería/Capital o CxP.
```

## Tests

```text
tests/integration/test_purchase_does_not_touch_cash_register.py
tests/integration/test_cash_module_direct_movements_only.py
tests/architecture/test_no_purchase_writes_to_movimientos_caja.py
```

---

# FASE 13 — Finanzas / KPIs vacíos

## Bug

Finanzas no registra o no muestra datos en KPIs.

## Archivos

```text
modulos/finanzas_unificadas.py
backend/infrastructure/db/repositories/finance_read_repository.py
core/services/enterprise/finance_service.py
core/services/finance/general_ledger_service.py
core/services/finance/journal_entry_service.py
core/services/finance/treasury_service.py
core/events/handlers/finance_handler.py
core/events/handlers/purchase_handler.py
core/events/wiring.py
migrations/m000_base_schema.py
```

## Fuentes canónicas preferidas

```text
journal_entries
financial_event_log
accounts_payable
accounts_receivable
treasury_ledger
ventas
compras
cierres_caja
```

## Reglas

* Definir fuente canónica de KPIs.
* No leer de tablas vacías si el sistema escribe en otras.
* Verificar existencia de tablas antes de consultar.
* No romper si falta tabla opcional.
* No declarar Finanzas resuelto si KPIs siguen en cero con datos reales.

## Cada operación crítica debe registrar

```text
source_module
event_type
amount
branch_id
operation_id
source_folio / referencia
```

## Tests

```text
tests/integration/test_finance_kpis_populate_from_sales_purchase_cash.py
tests/integration/test_finance_read_repository_uses_canonical_sources.py
tests/integration/test_finance_kpis_do_not_crash_when_optional_tables_missing.py
```

---

# FASE 14 — Productos / recetas / combos

## Bug

Productos no maneja combos de forma completa y no tiene CRUD claro para recetas.

## Archivos

```text
modulos/productos.py
modulos/dialogs/receta_dialog.py
core/services/recipes/recipe_service.py
backend/application/services/product_catalog_service.py
backend/application/queries/product_query_service.py
backend/domain/services/product_type_policy.py
migrations/m000_base_schema.py
```

## Reglas de tipos

```text
SIMPLE: no usa receta.
SERVICIO: no usa inventario ni receta.
COMPUESTO / COMBO: descuenta componentes al vender.
PROCESABLE: genera subproductos con rendimiento/merma.
PRODUCIDO: consume insumos para producir.
```

## UI esperada en Productos

Pestañas:

```text
Catálogo
Crear / Editar producto
Recetas y combos
Precios por sucursal
Historial / movimientos
```

En “Recetas y combos”:

```text
Selector de producto base
Tipo de receta
Tabla de componentes
Nueva receta
Editar receta
Guardar cambios
Desactivar receta
Agregar componente
Quitar componente
Simular
Costo estimado
Margen sugerido
Stock virtual
Componente limitante
Rendimiento / merma
```

## Tests

```text
tests/integration/test_product_combo_recipe_crud.py
tests/integration/test_combo_sale_deducts_components.py
tests/integration/test_recipe_crud_no_sql_in_pyqt.py
tests/integration/test_virtual_stock_for_combo.py
```

---

# FASE 15 — Caja / Corte Z / arqueo

## Bug

`DialogoCorteZCiego._recalcular_arqueo` usa:

```python
self._tbl_den.item(row, 2)
```

pero la UI creó:

```python
self._den_spins
self._den_sub_labels
```

## Archivo

```text
modulos/caja.py
```

## Corrección conceptual

Usar los labels existentes:

```python
for _, valor in self.DENOMINACIONES:
    spin = self._den_spins.get(valor)
    sub = float(valor) * (spin.value() if spin else 0)
    total += sub
    lbl = self._den_sub_labels.get(valor)
    if lbl:
        lbl.setText(f"${sub:,.2f}")

self.total_contado = round(total, 2)
self.lbl_total_arq.setText(f"${self.total_contado:,.2f}")
```

## Reglas

* No tronar al cambiar denominaciones.
* No permitir corte si no hay turno abierto.
* No registrar compras como egresos de caja.
* Corte debe usar `GenerateZCutUseCase`.
* Diferencia debe calcularse con efectivo esperado.
* Pagos con tarjeta, transferencia y crédito no deben compararse contra efectivo contado.

## Tests

```text
tests/unit/test_cash_cut_denomination_recalculation.py
tests/integration/test_cash_z_cut_blind_count_flow.py
tests/integration/test_cash_z_cut_expected_cash_excludes_card_transfer_credit.py
```

---

# FASE 16 — Planeación de Compras / Forecast

## Bug

Planeación de compras no ejecuta forecast correctamente.

## Archivos

```text
modulos/planeacion_compras.py
core/services/forecast_service.py
backend/application/queries/purchase_planning_query_service.py
core/events/event_bus.py
core/events/wiring.py
application/purchases/traditional_purchase_uc.py
```

## Reglas

* No SQL directo en PyQt.
* `producto_id` y `sucursal_id` deben ser `str` UUID.
* `ForecastService` debe aceptar UUID strings.
* Si falta `statsmodels`, mostrar mensaje claro.
* Si no hay historial suficiente, mostrar mensaje claro.
* Forecast debe publicar `FORECAST_GENERADO`.
* No buscar módulos de Compras por atributos sueltos del container.

## Crear

```text
backend/application/queries/purchase_planning_query_service.py
```

Métodos:

```python
list_forecastable_products(branch_id: str) -> list[dict]
last_purchase_cost(product_id: str, branch_id: str) -> float
sales_history(product_id: str, branch_id: str, days: int) -> list[dict]
current_stock(product_id: str, branch_id: str) -> float
```

## Resultado esperado de forecast

```text
historial_fechas
historial_valores
pronostico_fechas
pronostico_valores
metricas.stock_actual
metricas.venta_proyectada
metricas.compra_recomendada
```

## Tests

```text
tests/integration/test_purchase_planning_forecast_executes_with_uuid_ids.py
tests/integration/test_purchase_planning_no_sql_in_pyqt.py
tests/integration/test_forecast_handles_missing_statsmodels.py
tests/integration/test_forecast_generated_event_published.py
tests/integration/test_forecast_to_purchase_suggestion_flow.py
```

---

# FASE 17 — Impresión canónica POS / ESC

## Bugs

* Compras y Caja no imprimen correctamente.
* ESC/POS USB falla en Windows por dependencia USB.

## Archivos

```text
core/services/printer_service.py
core/services/hardware_service.py
application/services/caja_application_service.py
```

## Regla

Todo debe imprimir por una sola ruta:

```text
ReceiptPrintingService
→ PrinterService
→ transporte
```

No usar `escpos.printer.Usb` como default en Windows.

Transportes soportados:

```text
USB_WIN32
NETWORK
SERIAL
FILE
```

## Crear si no existe

```text
backend/application/services/receipt_printing_service.py
```

Tipos:

```text
SALE_TICKET
PURCHASE_RECEIPT
CASH_MOVEMENT_RECEIPT
CASH_CUT_Z
RAFFLE_TICKET
LABEL
```

## Regla crítica

Fallo de impresión no cancela operación de negocio ya registrada.

## Test

```text
tests/integration/test_purchase_cash_ticket_printing.py
```

---

# FASE 18 — Ticket template configurado

## Bug

```text
ticket_template_html not configured
```

## Archivos

```text
core/services/sales_service.py
core/engines/template_engine.py
migrations/m000_base_schema.py
```

## Reglas

* Ticket HTML no debe fallar si falta configuración.
* Preferir seed/default en schema/configuración.
* Si hay fallback, encapsular en método privado.
* No bloquear venta por error de template.
* Loggear warning y devolver payload.

## Test

```text
tests/integration/test_sale_ticket_default_template.py
```

---

# FASE 19 — Ticket con datos de sucursal

## Archivos

```text
core/services/sales_service.py
core/engines/template_engine.py
modulos/ticket_designer.py
repositories/config_repository.py
```

## Crear/agregar

```python
_ticket_header_data(branch_id: str) -> dict
```

Debe devolver:

```text
nombre_empresa
rfc_emisor
regimen_fiscal
web_empresa
whatsapp_empresa
sucursal_id
sucursal_nombre
sucursal_direccion
sucursal_telefono
```

## Reglas

* No hardcodear “San Bartolo”.
* No usar sucursal default `1`.
* No convertir `branch_id` a int.
* Si falta teléfono o dirección, dejar vacío.
* No fallar venta.

## Variables en TicketTemplateEngine

```text
sucursal_id
sucursal_nombre
sucursal_direccion
sucursal_telefono
whatsapp_empresa
rfc_emisor
regimen_fiscal
web_empresa
```

## Template default mínimo

```html
<div style="text-align:center;">
  <strong>{{nombre_empresa}}</strong><br>
  Sucursal: {{sucursal_nombre}}<br>
  {{sucursal_direccion}}<br>
  Tel: {{sucursal_telefono}}<br>
  WhatsApp: {{whatsapp_empresa}}<br>
  RFC: {{rfc_emisor}}<br>
  Régimen: {{regimen_fiscal}}<br>
  <hr>
  Ticket: {{folio}}<br>
  Fecha: {{fecha}}<br>
  Cajero: {{cajero}}<br>
</div>
```

## Test

```text
tests/integration/test_ticket_contains_branch_header.py
```

---

# FASE 20 — Microservicio WhatsApp Launcher

## Bug

```text
Microservicio no respondió en 10 segundos
```

## Archivo

```text
core/services/microservice_launcher.py
```

## Reglas

Usar:

```python
[sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

No depender de `uvicorn` en PATH global.

Guardar logs en:

```text
logs/whatsapp_service.log
```

Usar espera de 30 segundos o backoff.

Si no responde, reportar ruta del log.

No bloquear arranque del POS si WhatsApp falla.

## Test

```text
tests/integration/test_microservice_launcher_uses_current_python.py
```

---

# FASE 21 — Validación final

Ejecutar:

```bash
python -m pytest tests/architecture
python -m pytest tests/integration/test_admin_unlocks_locked_user.py
python -m pytest tests/integration/test_unlock_user_requires_permission.py
python -m pytest tests/integration/test_login_lockout_and_unlock_flow.py
python -m pytest tests/integration/test_purchase_lot_schema_flow.py
python -m pytest tests/integration/test_loyalty_snapshot_scheduler_schema.py
python -m pytest tests/integration/test_credit_sale_requires_valid_customer.py
python -m pytest tests/integration/test_credit_sale_creates_cxc_and_updates_balance.py
python -m pytest tests/integration/test_customer_history_query_service.py
python -m pytest tests/integration/test_permissions_uuid_user.py
python -m pytest tests/integration/test_session_permissions_uuid.py
python -m pytest tests/integration/test_purchase_does_not_touch_cash_register.py
python -m pytest tests/integration/test_cash_module_direct_movements_only.py
python -m pytest tests/integration/test_finance_kpis_populate_from_sales_purchase_cash.py
python -m pytest tests/integration/test_finance_read_repository_uses_canonical_sources.py
python -m pytest tests/integration/test_product_combo_recipe_crud.py
python -m pytest tests/integration/test_combo_sale_deducts_components.py
python -m pytest tests/unit/test_cash_cut_denomination_recalculation.py
python -m pytest tests/integration/test_cash_z_cut_blind_count_flow.py
python -m pytest tests/integration/test_purchase_planning_forecast_executes_with_uuid_ids.py
python -m pytest tests/integration/test_forecast_generated_event_published.py
python -m pytest tests/integration/test_purchase_cash_ticket_printing.py
python -m pytest tests/integration/test_sale_ticket_default_template.py
python -m pytest tests/integration/test_ticket_contains_branch_header.py
python -m compileall pos_spj_v13.4
```

---

# Validación manual obligatoria

Después de tests automáticos:

1. Resetear DB local de desarrollo.
2. Arrancar app.
3. Fallar login 5 veces con usuario de prueba.
4. Confirmar bloqueo.
5. Entrar con admin.
6. Desbloquear usuario desde Configuración / Seguridad.
7. Confirmar login exitoso.
8. Login con usuario cajero Ana.
9. Confirmar permisos sin error `int(UUID)`.
10. Confirmar que Ana puede abrir Dashboard si tiene `DASHBOARD.ver`.
11. Abrir Clientes → Historial.
12. Confirmar que no aparece `sqlite3 not defined`.
13. Crear cliente sin crédito.
14. Intentar venta a crédito; debe fallar.
15. Crear cliente con crédito autorizado.
16. Hacer venta a crédito.
17. Confirmar CxC en Finanzas.
18. Confirmar `credit_balance` actualizado.
19. Registrar compra a crédito.
20. Confirmar que no afecta Caja.
21. Confirmar que crea CxP.
22. Registrar compra pagada desde capital.
23. Confirmar que no afecta Caja.
24. Confirmar asiento financiero contra capital/tesorería/banco.
25. Confirmar que Compras no muestra controles duplicados de pago.
26. Registrar egreso manual desde Caja.
27. Confirmar que sí aparece en Caja.
28. Hacer Corte Z.
29. Capturar denominaciones.
30. Confirmar subtotales y total contado sin error.
31. Confirmar que la diferencia compara solo efectivo esperado.
32. Registrar venta, compra, CxC y CxP.
33. Abrir Finanzas y confirmar KPIs con datos reales.
34. Crear combo/receta desde Productos.
35. Vender combo y confirmar descuento de componentes.
36. Abrir Planeación de Compras.
37. Generar forecast de producto con historial.
38. Confirmar recomendación de compra.
39. Enviar sugerencia a Compras.
40. Imprimir ticket de venta.
41. Confirmar datos de sucursal, dirección, teléfono, cajero, folio y total.
42. Imprimir ticket/recibo de compra y caja por PrinterService.
43. Confirmar que falla de impresora no cancela venta/compra/caja.
44. Arrancar WhatsApp launcher.
45. Confirmar que usa `sys.executable -m uvicorn` y deja log.

---

# Entrega final obligatoria

Reportar:

* Archivos modificados.
* Archivos creados.
* Archivos eliminados.
* Tests agregados.
* Tests ejecutados.
* Resultado de cada test.
* Bugs corregidos.
* Observaciones convertidas en requerimientos.
* Reglas cumplidas de `SPJ_REFACTOR_SKILL.md`.
* Reglas cumplidas de `SPJ_UI_UX_ARCHITECTURE_SKILL.md`.
* Reglas cumplidas de este skill.
* Riesgos restantes.
* Siguiente fase recomendada.

---

# NO HACER

* No crear `fix_db.py`.
* No crear migración nueva de rescate.
* No arreglar solo la DB viva.
* No usar `ALTER TABLE` en servicios.
* No meter SQL en PyQt.
* No convertir UUID a int.
* No usar `lastrowid`.
* No usar `AUTOINCREMENT`.
* No usar `randomblob()` como identidad.
* No usar `sucursal_id=1` como fallback.
* No registrar compras en Caja.
* No duplicar controles de pago en Compras.
* No omitir CxC silenciosamente.
* No permitir venta a crédito sin cliente válido.
* No usar `escpos.printer.Usb` como ruta default Windows.
* No hardcodear datos de sucursal en tickets.
* No dejar usuario bloqueado sin flujo administrativo de desbloqueo.
* No calcular Corte Z comparando ventas totales contra efectivo si hay pagos mixtos.
* No dejar forecast dependiendo de SQL directo en PyQt.
* No declarar Finanzas resuelto si los KPIs siguen leyendo tablas vacías.
* No declarar Productos resuelto si combos/recetas no tienen CRUD y efecto real en inventario.
