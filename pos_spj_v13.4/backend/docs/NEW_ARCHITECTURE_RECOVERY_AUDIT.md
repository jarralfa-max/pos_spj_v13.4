# NEW ARCHITECTURE RECOVERY AUDIT — PASS 1 (inventario)

**HEAD:** `a35b8bab` · rama `claude/erp-financial-bounded-context-uqxz6b`
**Fecha:** 2026-09-10
**Alcance:** sólo lectura. Este pass no modifica código.

Ubicado en `backend/docs/` y no en `docs/` porque §1 sólo admite `frontend/` y
`backend/` como raíces válidas.

---

## 0. Estado del árbol

`a35b8bab` ("Commit despues de refacturacion ERP") consolidó la eliminación de
los paquetes legacy. Fuera de `frontend/` y `backend/` sobreviven en disco
`database/`, `integrations/`, `notifications/`, `repositories/`, `security/`,
`services/`, `sync/`, `tools/`, `ui/`, `utils/`, más `migrations/`, `scripts/`,
`tests/` y ficheros sueltos de raíz. Todos ellos son namespaces prohibidos por
§1 salvo `tests/`.

| | archivos `.py` |
|---|---|
| `frontend/` | 587 |
| `backend/` | 2209 |
| **total escaneado** | **2796** |

---

## 1. Imports rotos internos

**0.**

Ningún archivo bajo `frontend/` o `backend/` importa un módulo inexistente
*dentro de esas dos raíces*. La arquitectura nueva es internamente consistente:
lo que falta viene siempre de fuera.

**Archivos no parseables: 0.** No hay daño sintáctico por la eliminación.

---

## 2. Imports legacy (§1, §15)

**80 imports prohibidos, en 62 archivos, hacia 28 módulos distintos.**

| namespace raíz | ocurrencias |
|---|---|
| `core` | 48 |
| `modulos` | 18 |
| `repositories` | 10 |
| `migrations` | 2 |
| `scripts` | 1 |
| `application` | 1 |

### Por módulo (los 28)

| n | módulo prohibido |
|---|---|
| 17 | `modulos.ui_components` |
| 12 | `core.security.permission_catalog` |
| 8 | `core.services.configuration_settings_service` |
| 7 | `repositories.config_repository` |
| 5 | `core.services.loyalty_service` |
| 4 | `core.services.auto_audit` |
| 3 | `core.services.printer_service` |
| 2 | `core.events.event_bus` |
| 2 | `repositories.feature_flag_repository` |
| 2 | `migrations` |
| 1 | `application.services.customer_credit_service` |
| 1 | `core.engines.template_engine` |
| 1 | `core.events.catalog_events` |
| 1 | `core.integrations.whatsapp_client` |
| 1 | `core.permissions` |
| 1 | `core.repositories.hardware_config_repository` |
| 1 | `core.services.feature_flag_service` |
| 1 | `core.services.hardware_service` |
| 1 | `core.services.inventory.canonical_stock_read_adapter` |
| 1 | `core.services.production_query_service` |
| 1 | `core.services.recipes.recipe_resolver` |
| 1 | `core.services.stock_reservation_service` |
| 1 | `core.services.whatsapp_service` |
| 1 | `core.ticket_escpos_renderer` |
| 1 | `core.use_cases.venta` |
| 1 | `modulos.spj_phone_widget` |
| 1 | `repositories.cliente_repository` |
| 1 | `scripts.verify_tables` |

### Por zona del árbol nuevo

| ocurrencias | zona |
|---|---|
| 33 | `frontend/desktop/modules` |
| 13 | `backend/infrastructure/integrations` |
| 11 | `backend/application/queries` |
| 6 | `backend/bootstrap` |
| 3 | `backend/application/services` |
| 3 | `backend/infrastructure/hardware` |
| 2 | `frontend/desktop/components` |
| 6 | resto de `backend/application/*` (1 c/u) |

---

## 3. Matriz de responsabilidades perdidas (§17)

Lo que hay que **recrear por responsabilidad**, no por namespace. La columna de
destino es propuesta, alineada con §5–§7 y con la estructura que el backend ya
usa para otros bounded contexts.

### 3.1 Camino de arranque — bloquea todo lo demás

| archivo nuevo | import roto | responsabilidad | destino propuesto |
|---|---|---|---|
| `backend/bootstrap/application_context_builder.py:21` | `core.services.configuration_settings_service` | lectura de configuración | `backend/application/configuracion/configuration_query_service.py` |
| `…:22` | `core.services.feature_flag_service` | evaluación de feature flags | `backend/application/features/feature_flag_service.py` |
| `…:23` | `repositories.config_repository` | persistencia de configuración | `backend/infrastructure/persistence/repositories/config_repository.py` |
| `…:24` | `repositories.feature_flag_repository` | persistencia de flags | `backend/infrastructure/persistence/repositories/feature_flag_repository.py` |
| `backend/bootstrap/permission_evaluator.py:13` | `core.security.permission_catalog` | vocabulario y normalización de permisos | `backend/security/permission_catalog.py` |
| `backend/bootstrap/steps/database_migration_step.py:27` | `migrations` | runner de migraciones | `backend/infrastructure/persistence/migrations/` (§31) |
| `backend/bootstrap/steps/schema_validation_step.py:91` | `scripts.verify_tables` | validación de esquema | `backend/infrastructure/persistence/schema/validator.py` |

**Además (§12):** `application_context_builder.py:33` ejecuta SQL directo
(`SELECT nombre FROM sucursales WHERE id = ?`). Debe delegarse a un
`BranchRepository`/query en infraestructura.

### 3.2 Capa de aplicación

| import roto | usos | responsabilidad | destino propuesto |
|---|---|---|---|
| `core.services.configuration_settings_service` | 4 en `application/queries` | configuración | igual que arriba |
| `repositories.config_repository` | 4 en `application/queries` | configuración | igual que arriba |
| `core.services.inventory.canonical_stock_read_adapter` | 1 | lectura de stock | `backend/application/inventory/queries/` (§26) |
| `core.services.production_query_service` | 1 | consultas de producción | `backend/application/meat_processing/queries/` (§23) |
| `core.services.loyalty_service` | 5 | fidelidad | `backend/application/loyalty/` (ya existe el contexto) |
| `core.services.auto_audit` | 4 | sumidero de auditoría | `backend/application/shared/audit.py` o port en `backend/security/` |
| `core.use_cases.venta` | 1 | caso de uso de venta | ya existe `backend/application/sales/use_cases/` (§49) |
| `application.services.customer_credit_service` | 1 | crédito de cliente | ya existe `backend/application/customer_credit/` |
| `repositories.cliente_repository` | 1 | clientes | ya existe `backend/application/customers/` (§28) |
| `core.services.stock_reservation_service` | 1 | reservas de stock | `backend/application/inventory/` (§26) |
| `core.services.recipes.recipe_resolver` | 1 | recetas | `backend/application/meat_processing/` (§23) |

### 3.3 Infraestructura

| import roto | usos | responsabilidad | destino propuesto |
|---|---|---|---|
| `core.services.printer_service` | 3 | impresión | `backend/infrastructure/hardware/printer/` (§35) |
| `core.services.hardware_service` | 1 | hardware genérico | `backend/infrastructure/hardware/` |
| `core.repositories.hardware_config_repository` | 1 | config de hardware | `backend/infrastructure/persistence/repositories/` |
| `core.ticket_escpos_renderer` | 1 | render ESC/POS | `backend/infrastructure/hardware/printer/escpos/` |
| `core.engines.template_engine` | 1 | plantillas de ticket | `backend/infrastructure/hardware/printer/templates.py` |
| `core.integrations.whatsapp_client` | 1 | cliente WhatsApp | `backend/infrastructure/integrations/whatsapp/` (§67) |
| `core.services.whatsapp_service` | 1 | WhatsApp | idem |
| `core.events.event_bus` | 2 | bus de eventos | **ya existe** `backend/shared/events/` → repunte, no creación (§33) |
| `core.events.catalog_events` | 1 | nombres de evento | `backend/shared/events/event_names.py` |

### 3.4 Frontend

| import roto | usos | responsabilidad | destino propuesto |
|---|---|---|---|
| `modulos.ui_components` | 17 | widgets compartidos | `frontend/desktop/components/` (§54: **no** crear otro design system) |
| `modulos.spj_phone_widget` | 1 | input de teléfono | `frontend/desktop/components/` |
| `core.permissions` | 1 | consulta de permisos en UI | `backend/security/` vía presenter (§29) |

`modulos.ui_components` es el import legacy más repetido de todo el árbol y
está **enteramente en el frontend**: es el primer trabajo de UI del PASS 3.

---

## 4. Entrypoint y arranque (§2, §13, §37)

| comprobación | estado |
|---|---|
| `frontend/desktop/app.py` | **no existe** — hay que crearlo |
| `main.py` como launcher mínimo | **no** — importa `core.logging_setup`, `core.app_container`, `interfaz.main_window`, `version` |
| `python main.py` | **falla**: `ModuleNotFoundError: No module named 'core'` |

`main.py` debe quedar reducido al launcher de §0.

---

## 5. Bootstrap y contenedor (§10)

**Un solo contenedor.** `backend/bootstrap/service_container.py` es la única
clase `*Container` del árbol nuevo. No hay `AppContainer`, `ContainerV2` ni
equivalentes compitiendo: §10 ya se cumple estructuralmente y sólo falta que el
contenedor deje de depender de namespaces prohibidos.

---

## 6. Módulos y rutas (§19, §20)

18 módulos bajo `frontend/desktop/modules/`. **16 tienen
`shell_registration.py`**; faltan dos:

- `assets` — sin registro
- `pricing` — sin registro

Los 16 registrados: `business_intelligence`, `cash_register`, `configuracion`,
`customers_crm`, `fidelidad`, `finance`, `hr`, `inventory`, `losses`,
`meat_processing`, `orders_delivery`, `products`, `purchasing`, `sales_pos`,
`tarjetas_fidelidad`, `transfers`.

**Routing — cuatro paquetes conviven** y §19 exige auditar si duplican
responsabilidad:

- `frontend/desktop/navigation/`
- `frontend/desktop/shell/router/`
- `frontend/desktop/shell/routing/`
- `frontend/desktop/shell/sidebar/`

Pendiente de PASS 2: determinar si son capas de un único mecanismo
(`ModuleRegistry → RouteRegistry → ModuleRoute → PageFactory`) o dos routers
compitiendo.

---

## 7. Placeholders (§21)

| token | archivos |
|---|---|
| `Placeholder` | 33 |
| `NotImplementedError` | 26 |
| `mock` | 8 |
| `TODO` | 2 |

Sin clasificar todavía: `NotImplementedError` en un port abstracto es legítimo;
en una ruta activa, no. `Placeholder` en 33 archivos incluye los módulos que
§22/§23/§24 nombran explícitamente (`losses`, `meat_processing`,
`orders_delivery`). La clasificación es trabajo del PASS 4.

---

## 8. Deuda que yo mismo introduje, y que este prompt prohíbe

`backend/infrastructure/db/connection.py` (commit `98a57e7e`) **se obtuvo con
`git show` del archivo eliminado `core/db/connection.py`**. §18 prohíbe
exactamente eso.

No lo restauro ni lo justifico: queda anotado como pieza a **rediseñar** contra
el modelo actual y a consolidar en `backend/infrastructure/persistence/`
(§30), junto a `connection_factory`, `unit_of_work` y `migration_runner`. Hoy
tiene 40 importadores, así que su reemplazo es trabajo del PASS 2 y no se
puede simplemente borrar.

---

## 9. Objetivo del PASS 2

Por dependencia, no por volumen:

1. `core.security.permission_catalog` → `backend/security/` (12 usos, y lo
   necesita `permission_evaluator` del bootstrap).
2. Configuración y feature flags → `backend/application/…` +
   `backend/infrastructure/persistence/repositories/` (24 usos combinados,
   bloquean `ApplicationContextBuilder`).
3. Migration runner y validador de esquema → `backend/infrastructure/persistence/`.
4. Quitar el SQL directo de `ApplicationContextBuilder`.
5. Crear `frontend/desktop/app.py` y reducir `main.py` al launcher.

Meta del PASS 2: `python main.py` llega a mostrar login sin ningún
`ModuleNotFoundError`.

---

## Cifras del PASS 1

```
HEAD:                       a35b8bab
PASS:                       1 (inventario)
Archivos modificados:       0
Archivos creados:           1 (este documento)
Archivos eliminados:        0
Imports legacy antes:       80
Imports legacy después:     80   (este pass no modifica código)
Imports rotos antes:        0 internos
Imports rotos después:      0 internos
Placeholders antes:         33 archivos con `Placeholder`
Placeholders después:       33
Tests:                      no ejecutados en este pass
Startup:                    FALLA — ModuleNotFoundError: 'core' desde main.py
```
