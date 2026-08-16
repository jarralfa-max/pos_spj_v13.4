# CRM-0 — Auditoría de Clientes (Customer Master / CRM)

Fecha: 2026-08-08
Alcance: todo el código que toca `clientes` / `customer` en `pos_spj_v13.4` (legacy `modulos/`, `core/`, `repositories/`, `api/`, y la arquitectura nueva `backend/`) más `whatsapp_service/`.

Este documento es el inventario base exigido por CRM-0 antes de tocar nada. No se modificó código en esta pasada.

---

## 1. Funciones (lógica de negocio encontrada)

### `modulos/clientes.py` (UI, 1394 líneas) — `ModuloClientes`
- `cargar_clientes` / `buscar_clientes` / `_mostrar_clientes` — listado y búsqueda con filtro activos/inactivos/todos.
- `nuevo_cliente` / `editar_cliente` — abren `DialogoCliente`.
- `eliminar_cliente` — **soft-delete** (marca `activo=0`), no elimina físicamente; escribe `audit_write(modulo="CLIENTES", accion="MODIFICAR_CLIENTE")`.
- `ver_historial_cliente` — abre `DialogoHistorialCliente` (compras/puntos/créditos).
- `asignar_tarjeta_cliente` / `ver_tarjetas_cliente` — integra `CardBatchEngine` (fidelidad) directamente desde Clientes.
- `_abrir_rfm` — abre `_DialogoRFM`, segmentación RFM (Recency/Frequency/Monetary) con 6 segmentos hardcodeados (Champions, Leales, Potenciales, Nuevos, En riesgo, Casi perdidos) y exportación CSV/XLSX.
- `conectar_eventos` / `on_venta_realizada` / `on_datos_actualizados` — suscripción a bus de eventos legacy (`main_window.registrar_evento`, no el `EventBus` canónico) para refrescar UI en `venta_realizada`, `producto_actualizado`, `gasto_creado`.
- `registrar_actualizacion` — logger propio a archivo plano `logs/clientes_actualizaciones.log` (paralelo a `audit_write`; duplica auditoría).
- KPIs propios (`_crear_stats_clientes`): total, activos, con tarjeta, puntos totales — vía `ClienteService.get_stats()`.

### `DialogoCliente` (mismo archivo)
- Captura-only (ya remediado: no ejecuta SQL/commit). Arma DTO y delega en `ClienteService.guardar_formulario()`.
- Valida: nombre obligatorio, teléfono 10 dígitos locales (México, vía `PhoneWidget` E.164).
- Campos de alta: nombre, apellido, teléfono, **ID tarjeta** (parseo de prefijos `TF-/TAR-/CARD-/CLT-`), puntos, nivel fidelidad (Bronce/Plata/Oro/Platino, editable libre), descuento %, saldo crédito, límite de crédito, activo.
- Confirmación de duplicado (`_confirm_duplicate`) antes de crear si ya existe cliente con mismo nombre+apellido+teléfono.

### `DialogoHistorialCliente`
- 3 tabs: Compras, Puntos, Créditos — consume `CustomerHistoryQueryService` (ya migrado a `backend/application/queries/`, **no** SQL en el diálogo).

### `_DialogoAsignarTarjetaCliente` / `_DialogoTarjetasCliente`
- Asignar tarjeta libre, buscar por número, bloquear/liberar tarjeta, ver score de fidelidad — todo vía `ClienteQueryService` + `CardBatchEngine`.

### `core/services/cliente_service.py` — `ClienteService`
- Fachada de consultas (`get_stats`, `get_filtered`, `search`, `get_by_id`, `get_historial`, `get_movimientos_puntos`) y mutaciones (`crear`, `actualizar`, `dar_de_baja`, `actualizar_puntos`) delegando en `ClienteRepository`.
- `guardar_formulario()` (Remediación D): **doble ruta** — intenta `uc_cliente` (Use Case) primero; si lanza excepción, **cae a SQL directo embebido en el service** (INSERT/UPDATE `clientes` + `tarjetas_fidelidad`, `db.commit()/rollback()` manual). Es decir: el UC no es la única fuente de verdad, es un intento con fallback silencioso.
- `parse_tarjeta()` / `existe_similar()` — lógica de dedupe simple (nombre+apellido+teléfono exactos).

### `core/use_cases/cliente.py` — `GestionarClienteUC` (legacy, español)
- `crear_cliente`: crea en `ClienteRepository`, abre asiento contable `1301/3101` si `allows_credit and credit_limit>0` (vía `finance_service.registrar_asiento`, cumple regla 11 del CLAUDE.md), inicializa ledger de fidelidad (soft-fail), publica `CLIENTE_CREADO`.
- `actualizar_cliente` / `dar_de_baja` — publican `CLIENTE_ACTUALIZADO`.
- Comentario propio en el archivo admite la brecha: *"ClienteRepository.crear() y actualizar() son usados directamente desde 34+ módulos de UI sin pasar por la capa UC"*.

### `backend/application/use_cases/create_customer_use_case.py` — `CreateCustomerUseCase` (nuevo, inglés)
- **Segunda ruta de creación de cliente**, independiente de `GestionarClienteUC`. Usada para alta rápida desde Ventas (quick-create). Tiene su propio `CreateCustomerCommand` DTO, su propia dedupe por `loyalty_code` (no por nombre/teléfono), y su propio SQL fallback si no se inyecta repositorio.
- `backend/application/commands/customer_commands.py` define `UpdateCustomerCommand` (inglés) — **tercer** contrato de actualización, distinto de los `campos: dict` de `GestionarClienteUC.actualizar_cliente`.

### `repositories/cliente_repository.py` — `ClienteRepository`
- CRUD con SQL embebido (parametrizado, sin concatenación insegura). Detecta columnas opcionales en runtime (`_get_clientes_columns`, compat `codigo_fidelidad`).
- `crear()` ya genera `UUIDv7` vía `backend/shared/ids.new_uuid()` (cumple Regla Cero).
- `actualizar()` sólo permite `{nombre, telefono, email, direccion, notas, activo}` — **no permite actualizar puntos/nivel/crédito por esta vía** (esos campos se tocan por SQL directo en `ClienteService.guardar_formulario` o por otros servicios).

### `api/routers/clientes.py` (FastAPI)
- `GET /clientes` búsqueda, `GET /clientes/{id}` detalle + últimas ventas + saldo puntos, `POST /clientes` alta, `GET /clientes/{id}/puntos` historial de puntos.
- **SQL directo en el router** (no pasa por `ClienteRepository`/UC). Genera su propio `codigo_qr` con `uuid4()[:12]` en el alta — inconsistente con el flujo de UI que usa `codigo_qr = tarjeta_id` (formato distinto).

### `application/services/customer_credit_service.py` — `CustomerCreditService`
- Validación de cliente y crédito (CxC) en checkout de ventas — cuarta pieza de "lógica de cliente", vive fuera de `core/` y `backend/`, en `application/` a nivel raíz del legacy.

---

## 2. Pantallas (UI)

| Pantalla | Clase | Notas |
|---|---|---|
| Listado/CRUD de clientes | `ModuloClientes` | Tabla, KPIs, filtros, búsqueda |
| Alta/edición | `DialogoCliente` | Captura-only, delega en service |
| Historial 360 parcial | `DialogoHistorialCliente` | Compras/Puntos/Créditos (3 tabs) |
| Asignar tarjeta | `_DialogoAsignarTarjetaCliente` | Fidelidad, no Clientes |
| Tarjetas + historial + score | `_DialogoTarjetasCliente` | Fidelidad, no Clientes |
| Segmentación RFM | `_DialogoRFM` | Analítica/BI embebida en Clientes |

No existen pantallas de: Leads, Oportunidades/Pipeline, Actividades/Agenda, Casos de atención/SLA, Crédito como workflow (solo campos planos), Consentimientos/Privacidad, Segmentos/Tags/Territorios/Carteras, Detección de duplicados/Merge, Importación/Exportación masiva. Todo el CRM-4 a CRM-11 es funcionalidad **nueva**, no una migración de algo existente.

---

## 3. SQL embebido detectado (fuera de repositories)

| Archivo | Función | Problema |
|---|---|---|
| `core/services/cliente_service.py::guardar_formulario` | INSERT/UPDATE `clientes`, INSERT `tarjetas_fidelidad`, `db.commit()/rollback()` | Service ejecuta SQL directo como fallback del UC — viola regla 13 (SQL seguro sólo en repos) en espíritu, aunque parametrizado |
| `core/services/cliente_query_service.py` | 6 métodos `db.execute(...)` | Es un QueryService "canónico" pero para UI legacy; correcto en intención, pero coexiste con `ClienteRepository` (duplica capa de lectura) |
| `api/routers/clientes.py` | 4 endpoints, SQL directo | API FastAPI no usa `ClienteRepository` ni ningún Use Case — ruta totalmente paralela |
| `backend/application/use_cases/create_customer_use_case.py` | INSERT `clientes` + `tarjetas_fidelidad` (fallback si no hay repo inyectado) | Mismo patrón de "SQL de emergencia" duplicado en la nueva arquitectura |

No se encontró SQL de clientes dentro de `modulos/clientes.py` (ya remediado — Remediación D según comentarios del propio archivo).

---

## 4. Tablas (schema actual, `migrations/m000_base_schema.py`)

| Tabla | PK | FKs relevantes | Notas |
|---|---|---|---|
| `clientes` | `id TEXT` (UUID) | — | Mezcla identidad + fidelidad + crédito + segmentación en una sola tabla: `puntos`, `nivel`, `nivel_fidelidad` (dos columnas de nivel distintas), `allows_credit`, `credit_limit`, `credit_balance`, `saldo`\*, `limite_credito`\*, `codigo_qr`, `sucursal_id`. (\*columnas usadas por la UI pero no declaradas todas en el `CREATE TABLE` base — ver `_get_clientes_columns()` compat runtime, indicio de migraciones incrementales fuera de este archivo) |
| `historico_puntos` | `id TEXT` | `cliente_id` | Historial de puntos — coexiste con `loyalty_ledger` (fuente canónica según comentario en `CustomerHistoryQueryService`) |
| `puntos_fidelidad` | — | `cliente_id` | Usada por `ClienteRepository.get_movimientos_puntos`, **tabla distinta** de `historico_puntos` para lo mismo |
| `loyalty_ledger` | — | `cliente_id` | Fuente canónica de puntos según comentarios de código nuevo |
| `loyalty_scores` | `cliente_id TEXT` (PK) | — | Score de fidelidad (RFM-like) |
| `tarjetas_fidelidad` | `id TEXT` | `id_cliente` | **Nomenclatura invertida**: `id_cliente`, no `cliente_id` |
| `card_assignment_history` | `id TEXT` | `cliente_id_prev`, `cliente_id_nuevo`, `tarjeta_id` | |
| `referidos` | `id TEXT` | (no confirmado) | Programa de referidos, tocado por Clientes/Fidelidad |
| `clientes_diarios` | `id TEXT` | `sucursal_id` | Agregado BI diario |
| `clientes_lista_precio` | `cliente_id TEXT` (PK) | — | Precios especiales por cliente (pricing) |
| `movimientos_credito` | — | `cliente_id` | Historial de crédito; **tabla opcional** (código verifica existencia antes de usar) |
| `cuentas_por_cobrar` | — | `cliente_id` | CxC — fuente canónica alterna de crédito cuando no existe `movimientos_credito` |

**Inconsistencia de columnas confirmada**: `tarjetas_fidelidad`/`card_assignment_history` usan `id_cliente`/`cliente_id_prev`/`cliente_id_nuevo`; `ventas`, `historico_puntos`, `movimientos_credito`, `loyalty_ledger`, `clientes_lista_precio`, `cuentas_por_cobrar` usan `cliente_id`. Ambos patrones activos simultáneamente.

**Identidad**: `clientes.id` ya es `TEXT` (UUID), cumple Regla Cero. No se encontraron `INTEGER PRIMARY KEY AUTOINCREMENT` para clientes. `api/routers/clientes.py` sí genera un `codigo_qr` con `uuid4()[:12]` (identificador secundario, no de negocio-crítico, pero es una segunda fuente de generación de identificador fuera de `backend/shared/ids.py`).

---

## 5. Repositorios

| Repositorio | Ubicación | Consumidores |
|---|---|---|
| `ClienteRepository` | `repositories/cliente_repository.py` | `ClienteService`, `GestionarClienteUC` (vía `container.cliente_repo`), `CreateCustomerUseCase` (opcional) |
| Ninguno en `backend/infrastructure/db/repositories/` | — | La nueva arquitectura (`backend/`) **no tiene** repositorio de cliente propio; `CreateCustomerUseCase` recibe uno opcional o hace SQL directo |

No existe todavía un `CustomerRepository` (inglés) en `backend/infrastructure/`, pese a que ya existen `use_cases`, `commands` y `queries` de "customer" en `backend/application/`. La capa de persistencia nueva es la pieza que falta.

---

## 6. Servicios

| Servicio | Rol | Observación |
|---|---|---|
| `ClienteService` (`core/services/`) | Fachada UI legacy | Contiene fallback SQL (ver §3) |
| `ClienteQueryService` (`core/services/`) | Lecturas para diálogos (tarjetas, RFM, historial legacy) | Coexiste con `CustomerHistoryQueryService` (backend) para el mismo propósito de historial |
| `CustomerHistoryQueryService` (`backend/application/queries/`) | Lectura canónica de historial (compras/puntos/créditos) | Ya usado por `DialogoHistorialCliente` — único QueryService "en inglés" en producción activa |
| `GestionarClienteUC` (`core/use_cases/cliente.py`) | UC legacy español | Orquesta crédito + fidelidad + evento |
| `CreateCustomerUseCase` (`backend/application/use_cases/`) | UC nuevo inglés, alta rápida | No integrado con `GestionarClienteUC`; ruta paralela para "alta rápida desde Ventas" |
| `CustomerCreditService` (`application/services/`) | Validación de crédito en checkout | Vive en un tercer namespace (`application/` raíz, ni `core/` ni `backend/`) |
| `CardBatchEngine` (`core/services/`) | Fidelidad — asignar/bloquear/liberar tarjetas | Invocado directamente desde la UI de Clientes (acoplamiento cruzado Clientes↔Fidelidad, contraviene la regla final "Clientes administra identidad… Fidelidad administra tarjetas") |

---

## 7. Permisos

Catálogo canónico (`core/security/permission_catalog.py`):

```python
"CLIENTES": ["ver", "crear", "editar", "credito"],
```

Comparado con módulos ya refactorizados a bounded context (CAJA, INVENTARIO, COMPRAS, FINANZAS), que tienen decenas de permisos granulares con sufijos `.ver`, `.autorizar`, `.reversar`, `.sucursal_propia`, etc., **CLIENTES sigue en el modelo plano original**: 4 permisos totales, sin verbos de dominio CRM (no hay `lead.asignar`, `oportunidad.transicionar`, `caso.escalar`, `credito.aprobar`, `privacidad.procesar`, `duplicado.fusionar`, `exportar`, etc.).

`TARJETAS_FIDELIDAD: ["ver"]` — también mínimo, un solo permiso para todo el dominio de fidelidad.

`INTELIGENCIA_BI` sí tiene `ver_clientes` como permiso de solo-lectura para BI — es el único punto donde "clientes" aparece con granularidad fuera de su propio módulo.

Persistencia de roles: tablas `roles`, `permisos`, `roles_permisos`, `usuarios_roles` (RBAC por base de datos, no hardcodeado por nombre de rol) — el mecanismo correcto ya existe a nivel de infraestructura; lo que falta es la **definición** de permisos CRM sobre ese mecanismo.

---

## 8. Roles

No se encontró una lista de roles de negocio (vendedor, supervisor, gerente de sucursal, account manager, analista de crédito, oficial de privacidad, auditor) codificada en `core/security/`. Los roles viven como filas en la tabla `roles` (seed/datos), no en código — no hay archivo canónico que enumere los roles CRM objetivo (`test_sales_rep_sees_only_own_leads.py` y demás tests de la sección 96 del pipeline no existen todavía).

**Conclusión**: no hay roles legacy específicos de "Clientes" que migrar; los roles CRM (sales rep, supervisor, branch manager, account manager, auditor, credit analyst, privacy officer, crm admin) son de creación nueva.

---

## 9. Scopes

No existe ningún resolver de scope (`OWN/TEAM/BRANCH/TERRITORY/PORTFOLIO/COMPANY`) para clientes. El único patrón de "scope" existente en el repo es el sufijo de permiso por sucursal ya usado en CAJA/INVENTARIO/COMPRAS:

```
ver.sucursal_propia | ver.sucursales_asignadas | ver.todas_sucursales
```

Eso cubre solo el eje BRANCH y sólo para lectura; no hay equivalente para OWN (cartera propia de un vendedor) ni TEAM ni TERRITORY ni PORTFOLIO. `clientes.sucursal_id` existe en el schema pero no se usa para filtrar en ningún query service auditado (`ClienteRepository.get_filtered/buscar_por_termino` no filtran por sucursal). Esto es una brecha de aislamiento de datos: cualquier usuario con `CLIENTES.ver` ve la cartera completa sin importar sucursal/propiedad.

---

## 10. Integraciones activas encontradas

| Integración | Punto de contacto | Dirección |
|---|---|---|
| **Ventas** | `ventas.cliente_id`, `customer_lookup_service.py`, `sale_loyalty_policy.py`, `sales_application_service.py` | Ventas lee/escribe cliente en cada venta (puntos, crédito) |
| **Fidelidad** | `CardBatchEngine`, `loyalty_service.py`, `loyalty_repository.py`, `loyalty_ledger`, `loyalty_scores`, `tarjetas_fidelidad` | Fuertemente acoplada — UI de Clientes abre diálogos de tarjetas directamente |
| **Finanzas / CxC** | `finance_service.registrar_asiento` (asiento 1301/3101 al abrir crédito), `receivable_repository.py`, `commercial_obligation_repository.py`, `customer_credit_service.py`, `credit_validation_service.py`, `accounts_receivable_service.py` | Cumple regla 11 CLAUDE.md (asiento doble entrada) en `GestionarClienteUC`, pero **no** en `ClienteService.guardar_formulario` fallback SQL (el fallback no abre asiento aunque se edite `limite_credito`) |
| **WhatsApp** | `whatsapp_service/erp/bridge.py`, `business_orchestrator.py`, `pos_notifier.py`, flujos `registro_flow.py`, `pedido_flow.py`, `cotizacion_flow.py` | Bridge externo consulta/crea clientes vía ERP Bridge (no confirmado si usa `ClienteRepository` o su propio acceso — pendiente de profundizar en CRM-13) |
| **BI** | `bi_sales_query_service.py`, `bi_inventory_query_service.py`, `INTELIGENCIA_BI.ver_clientes` | Lectura agregada, permiso propio |
| **Pricing** | `clientes_lista_precio`, `pricing_repository.py`, `product_price_query_service.py` | Precios especiales por cliente |
| **Cotizaciones / Pedidos** | `api/routers/cotizaciones.py`, `api/routers/pedidos.py` | Referencian `cliente_id` |
| **Delivery** | (no confirmado directo; pendiente CRM-13) | — |

---

## 11. Legacy y duplicación detectados (hallazgo principal de CRM-0)

Este es el problema central que CRM-1..CRM-23 debe resolver: **hay 3 arquitecturas de "cliente" coexistiendo activamente**, no una sola con shims claros:

1. **Legacy español, capa `core/`** — `ClienteRepository` → `ClienteService`/`ClienteQueryService` → `GestionarClienteUC` → `modulos/clientes.py`. Es la ruta que sirve la UI de escritorio hoy. Ya tiene UUIDv7 y ya sacó el SQL de la UI (Remediación D), pero el *service* todavía tiene un fallback SQL propio.
2. **Nuevo inglés, capa `backend/application/`** — `CreateCustomerUseCase`, `UpdateCustomerCommand`, `CustomerHistoryQueryService`. Sigue la convención objetivo (`backend/domain|application|infrastructure`) pero **no tiene repositorio propio** ni domain entity `Customer`; su UC de creación hace su propio INSERT si no le inyectan repo.
3. **API REST, `api/routers/clientes.py`** — SQL 100% directo, no usa ninguna de las dos capas anteriores. Genera su propio formato de `codigo_qr`.

Ninguna de las tres es la "única fuente de verdad" que exige la Regla Final del pipeline CRM. `guardar_formulario()` intenta ser el punto de unificación (UC con fallback), pero el fallback reintroduce SQL directo y omite el asiento contable de apertura de crédito.

**Otras duplicaciones encontradas:**
- Dos columnas de nivel de fidelidad en `clientes`: `nivel` y `nivel_fidelidad`.
- Dos tablas de historial de puntos: `historico_puntos` y `puntos_fidelidad` (leídas por métodos distintos: `ClienteQueryService.historial_puntos` vs `ClienteRepository.get_movimientos_puntos`), más `loyalty_ledger` como "fuente canónica" según comentarios recientes — tres fuentes para el mismo dato.
- Dos formas de guardar crédito: `movimientos_credito` (si existe) vs `cuentas_por_cobrar` (fallback), resuelto en `CustomerHistoryQueryService` con `_table_exists`, no con una migración que consolide.
- Doble log de auditoría: `audit_write()` (canónico) + `registrar_actualizacion()` (archivo plano `logs/clientes_actualizaciones.log`, sólo en `ModuloClientes`, no en los demás módulos).
- Tarjetas/fidelidad gestionadas *desde* la pantalla de Clientes (`asignar_tarjeta_cliente`, `ver_tarjetas_cliente`, `_abrir_rfm`) — mezcla que el punto final del pipeline ("Clientes y Fidelidad están separados") pide deshacer.

**No se encontró código muerto evidente** (sin referencias) en los archivos auditados — todo lo listado tiene al menos un consumidor activo, incluida la ruta API REST.

---

## 12. Tests existentes relacionados

```
tests/test_cliente_repository_schema_compat.py
tests/test_uc_cliente.py
tests/test_sales_customer_loyalty.py
tests/integration/test_credit_sale_requires_valid_customer.py
tests/integration/test_customer_history_query_service.py
tests/integration/test_customer_points_history_from_ledger.py
```

Ninguno de los tests de seguridad/permisos exigidos por la sección 96 del pipeline (`test_sales_rep_sees_only_own_leads.py`, `test_supervisor_sees_team_leads.py`, etc.) ni los guardrails de arquitectura de la sección 98 (`tests/architecture/test_customers_crm_*.py`) existen todavía.

---

## 13. Resumen ejecutivo (para Reporte Final / tabla de preservación)

| Elemento anterior | Estado | Acción sugerida en fases futuras |
|---|---|---|
| `modulos/clientes.py` (UI) | Activo, ya sin SQL propio | CRM-14/16/17: reemplazar por CustomersCRMView + Design System |
| `ClienteRepository` (`repositories/`) | Activo, único repo real | CRM-3: base para `CustomerRepository` en `backend/infrastructure/` |
| `ClienteService.guardar_formulario` fallback SQL | Activo, riesgo (sin asiento contable) | CRM-1/CRM-3: eliminar fallback, UC única fuente |
| `GestionarClienteUC` (español) | Activo | CRM-3: fusionar con `CreateCustomerUseCase` (inglés) en un único UC |
| `CreateCustomerUseCase` (inglés) | Activo, parcial (sin repo propio) | CRM-3: dotar de `CustomerRepository`, eliminar SQL fallback |
| `api/routers/clientes.py` (SQL directo) | Activo, aislado | CRM-3/CRM-13: reescribir sobre UseCases/QueryServices |
| `nivel` vs `nivel_fidelidad` | Duplicado | CRM-3: consolidar en un solo campo, Fidelidad es dueña del nivel |
| `historico_puntos` / `puntos_fidelidad` / `loyalty_ledger` | Triplicado | CRM-21: `loyalty_ledger` como única fuente, resto DEPRECATE |
| `movimientos_credito` / `cuentas_por_cobrar` | Duplicado | CRM-8: CxC en Finanzas es la única fuente |
| `id_cliente` (tarjetas/card_history) vs `cliente_id` (resto) | Inconsistente | CRM-22: unificar a `customer_id` en todo el schema nuevo |
| `CLIENTES: [ver, crear, editar, credito]` | Insuficiente | CRM-2: permisos granulares + scopes |
| Sin scope resolver OWN/TEAM/BRANCH/... | Ausente | CRM-2/CRM-10: nuevo, siguiendo patrón `ver.sucursal_propia` ya usado en CAJA/INVENTARIO |
| Asignar/ver tarjetas y RFM desde Clientes | Acoplado a Fidelidad/BI | CRM-22: mover a Fidelidad/BI, Clientes referencia por evento |
| `registrar_actualizacion` (log a archivo) | Duplica `audit_write` | CRM-22: eliminar, dejar sólo `audit_write` |

---

## 14. Riesgos pendientes identificados

1. Editar `limite_credito` vía el fallback SQL de `ClienteService.guardar_formulario` **no genera asiento contable** — viola la regla 11 del CLAUDE.md si ese camino se ejecuta (se ejecuta cada vez que `uc_cliente` lanza excepción, lo cual ocurre silenciosamente — `except Exception: logger.debug(...)`).
2. Sin scope por sucursal/cartera en lectura de clientes: cualquier rol con `CLIENTES.ver` ve todos los clientes de todas las sucursales.
3. Tres fuentes de verdad para "cliente" (español legacy, inglés backend, API REST) sin contrato compartido — alto riesgo de que un alta por API no dispare lo mismo que un alta por UI (p. ej. sin asiento de crédito, sin evento `CLIENTE_CREADO`).
4. `api/routers/clientes.py` no valida ni usa `PhoneWidget`/E.164 — puede insertar teléfonos en formato distinto al que exige la UI.
5. Ninguna de las tres rutas de creación implementa lo pedido por CRM-1 (UUIDv7 ya sí, pero no idempotencia por `operation_id`, ni outbox).

---

## 15. REFRESH — Re-auditoría post CRM-24 (2026-08-14)

El pipeline CRM-0..CRM-24 ya se ejecutó casi en su totalidad (CRM-19/20 fueron
saltadas por decisión explícita del usuario). Esta sección documenta el
estado REAL del código hoy, verificado por agente de exploración +
`pytest`, no reconstruido de memoria — no reemplaza las secciones 1-14
(que documentan el punto de partida), las complementa.

### 15.1 Lo que YA NO es una brecha (estaba en §13/§14, ahora existe)

Casi todo lo listado como "ausente"/"nuevo" en la auditoría original ya
tiene código de dominio + aplicación + tests reales, no solo el master
prompt aspiracional:

| Brecha original (§13/§14) | Estado hoy | Dónde |
|---|---|---|
| Sin Leads/Oportunidades/Pipeline | ✅ Construido | `backend/domain/crm/entities/{lead,opportunity,...}.py`, `application/crm/use_cases/{lead,opportunity,convert_lead,create_opportunity_from_lead}.py` (CRM-4/5) |
| Sin Actividades/Agenda/Tareas | ✅ Construido | `crm_activity.py`/`crm_task.py`/`crm_note.py`/`crm_reminder.py` + use cases (CRM-6) |
| Sin Casos de atención/SLA | ✅ Construido | `backend/application/customer_service/` completo, `SLAInstance`/`ServiceLevelPolicy` (CRM-7) |
| Crédito solo como campos planos | ✅ Workflow completo | `backend/application/customer_credit/use_cases/customer_credit_use_cases.py`: `RequestCustomerCreditUseCase`, `ReviewCustomerCreditUseCase`, `ApproveCustomerCreditUseCase`, `RejectCustomerCreditUseCase`, `UpdateCustomerCreditLimitUseCase`, `SuspendCustomerCreditUseCase`, `BlockCustomerCreditUseCase`, `ReopenCustomerCreditUseCase`, `CloseCustomerCreditUseCase` (CRM-8) |
| Sin Consentimientos/Privacidad | ✅ Construido | `backend/domain/customer_privacy/` + `application/customer_privacy/use_cases/{consent,privacy_request,anonymize_customer,retention_policy}.py` (CRM-9) |
| Sin Segmentos/Tags/Territorios/Carteras | ✅ Construido | `backend/domain/crm/entities/{customer_segment,customer_tag,sales_territory,customer_portfolio,customer_ownership}.py` (CRM-10) |
| Sin detección de duplicados/Merge | ✅ Construido | `customer_duplicate_candidate.py`, `application/customers/use_cases/merge_use_cases.py` (`ProposeCustomerMergeUseCase`/`ExecuteCustomerMergeUseCase`/`RejectCustomerMergeUseCase` — nombres distintos al `MergeCustomersUseCase` literal del master prompt, mismo patrón "nombre real difs del prompt" ya documentado en cada fase) (CRM-11) |
| Sin importación/exportación masiva | ✅ Import construido | `customer_import_batch.py`, `application/customers/use_cases/import_use_cases.py` (CRM-11). Exportación masiva (`ExportCustomersQuery` etc., §48) sigue sin encontrarse como caso de uso dedicado — no confirmado en este refresh, pendiente verificar en fase futura si se necesita. |
| Catálogo de permisos plano (4 códigos) | ✅ 166 códigos reales | `CustomerPermissions` = 83, `CRMPermissions` = 83 (`backend/application/{customers,crm}/permissions.py`) — códigos reales tipo `"CLIENTES.credito.aprobar"`, no aspiracionales (CRM-2) |
| Sin scope resolver OWN/TEAM/BRANCH/... | ✅ Construido, 6 ejes | `CustomerDataScopeResolver`/`CRMDataScopeResolver` (CRM-2), consumidos por casi todos los query services desde CRM-3 en adelante |
| Sin pantalla real (todo el CRM era solo campos en `modulos/clientes.py`) | ✅ Módulo completo wireado | `frontend/desktop/modules/customers_crm/` (CRM-14-18), único punto de entrada real (`modulos/clientes_crm.py` → `"CLIENTES_CRM"` en menú), `modulos/clientes.py` **eliminado** (CRM-24) |

### 15.2 Brecha real confirmada, no cerrada

- **`CRMAutomationRule`/`CRMAutomationExecution` (§56, automatizaciones
  declarativas por trigger)** — grep de `"automation"` en todo `backend/`
  no arrojó ningún resultado. Ningún trigger (`LEAD_IDLE`,
  `OPPORTUNITY_OVERDUE`, `SLA_AT_RISK`, etc.) tiene mecanismo de reglas
  declarativas ni ejecutor. Es la única sección grande del master prompt
  sin ningún código, ni parcial.

### 15.3 Lo que §11 llamaba "3 arquitecturas coexistiendo" — estado hoy

El hallazgo central de CRM-0 (tres rutas paralelas de "cliente": legacy
español `core/`, nuevo inglés `backend/application/`, API REST SQL
directo) **se redujo pero no se cerró del todo**, por decisión explícita
documentada en CRM-21/CRM-24 (no un olvido):

- **Ruta 1 (legacy español, `modulos/clientes.py` + sus 4 diálogos)**:
  eliminada por completo en CRM-24. Ya no existe.
- **Ruta 2 (`backend/application/`, ahora `backend/domain/customers` +
  `application/customers`)**: es la única ruta real que sirve la UI activa
  hoy (`frontend/desktop/modules/customers_crm/`).
- **Ruta 3 (API REST `api/routers/clientes.py`, SQL directo) y las piezas
  legacy que todavía la alimentan** (`core/use_cases/cliente.py`
  `GestionarClienteUC`, `repositories/cliente_repository.py`
  `ClienteRepository`, `application/services/customer_credit_service.py`,
  `core/services/card_batch_engine.py`) — **siguen vivas y activas**,
  consumidas por Ventas (`modulos/ventas.py:1010,1055,2884-2885`, checkout)
  y WhatsApp. Documentadas explícitamente en `CUSTOMERS_CRM_LEGACY_CONSUMERS`
  (`tests/architecture/allowlists.py`) como burn-down pendiente — no se
  tocan hasta que Ventas/WhatsApp migren sus propias llamadas al Customer
  Master nuevo, un trabajo de fases futuras aún no numeradas.

Es decir: **para la UI de escritorio ya hay una sola fuente de verdad**;
para Ventas/WhatsApp/API REST todavía hay una segunda, legacy, que no ha
sido unificada. §11 sigue siendo parcialmente cierto, ya no en la UI.

### 15.4 Números de verificación (agente + pytest, 2026-08-14)

- `tests/unit/customers/ tests/unit/crm/ tests/integration/customers/ tests/integration/crm/ tests/architecture/test_customers_crm_*.py`: **586 passed**.
- Incluyendo también `customer_credit`/`customer_privacy`/`customer_service` (unit+integration): **808 passed, 0 failed**.
- Menú: confirmado un solo punto de entrada real (`"CLIENTES_CRM"` →
  `modulos.clientes_crm.ModuloClientesCrm`); cero referencias reales a
  `ModuloClientes` (solo comentarios/docstrings históricos).
- `core/ui/module_loader.py["clientes"]` apunta a `ModuloClientesCrm`.

### 15.5 Nombres de clase que difieren del master prompt (no son brechas, son nomenclatura)

Confirmado por el agente, consistente con el patrón ya documentado en cada
fase (CRM-2, CRM-9, CRM-12, CRM-14... "el prompt nombra un concepto, la
clase real tiene otro nombre"):

- Merge: `ProposeCustomerMergeUseCase`/`ExecuteCustomerMergeUseCase`/`RejectCustomerMergeUseCase`, no `MergeCustomersUseCase`.
- Consentimiento: `CaptureConsentUseCase`/`RequestConsentUseCase`/`ConfirmConsentUseCase`/`WithdrawConsentUseCase`/`MarkConsentNotRequiredUseCase`, no `GrantCustomerConsentUseCase`/`WithdrawCustomerConsentUseCase`.

No se recomienda renombrar solo para calzar con el prompt — el prompt es
la brújula, no el contrato literal (regla ya establecida desde CRM-2).

### 15.6 Conclusión de este refresh

## 16. CUSTOMER MASTER CUT-OVER / LEGACY PURGE (2026-08-16)

Sesión de cut-over completo (CRM-27 a CRM-34) ejecutada tras §15.3/§15.6
identificar la segunda ruta legacy viva como el riesgo principal
restante. Reporte completo, con las 12 secciones que pide la Fase 16 del
prompt maestro (resumen, archivos, tablas, integraciones, seguridad,
frontend, tests, deuda restante, grep final):
**`docs/refactor/CRM-35_cutover_session_report.md`**.

Resumen de una línea por fase — cada una con su propio doc en
`docs/refactor/`:

- **CRM-27**: el gate de crédito real de Ventas ahora prefiere
  `customer_credit_profiles` (workflow CRM-8) cuando existe, en vez de
  leer `clientes.allows_credit` directo — el workflow moderno de crédito
  finalmente tiene efecto en el POS.
- **CRM-28**: eliminado el fallback de contraseña en texto plano/SHA-256
  en las tres rutas de auth — fail-fast si bcrypt no está instalado.
- **CRM-29**: wildcard de módulo (`"CLIENTES.*"`) agregado al evaluador
  de permisos real.
- **CRM-30**: Delivery/Loyalty investigados — su lado de lectura ya
  estaba correctamente wireado desde CRM-13, no era una brecha real.
- **CRM-31**: el dominio de consentimiento de CRM-9 ahora gatea envíos
  reales de WhatsApp (honra un WITHDRAWN explícito, nunca bloquea por
  ausencia de registro).
- **CRM-32**: `NavigationIntent` — Customer 360 puede saltar a Ventas con
  el cliente preseleccionado, mecanismo listo para crecer a más destinos.
- **CRM-33**: la Timeline del cliente ahora incluye eventos de venta.
- **CRM-34**: `core/services/cliente_service.py` eliminado (cero
  consumidores de producción).

Actualiza §15.3: la ruta legacy de Ventas/WhatsApp sigue viva por diseño
(decisión ya tomada en CRM-25, "safe subset now, credit gate later") —
esta sesión cerró la parte de "credit gate later" que quedaba pendiente,
sin migrar la selección de cliente de Ventas fuera de la identidad
legacy (deuda real, documentada en la sección 11 del reporte CRM-35).

El bounded context Customer Master/CRM está, en profundidad de dominio y
aplicación, sustancialmente completo contra el master prompt (10 de 11
áreas grandes construidas con tests reales; automatizaciones es la única
ausente por completo). El riesgo real que queda no es "falta construir
X" sino "todavía hay una segunda ruta legacy viva para Ventas/WhatsApp/API
REST" (§15.3) — coherente con lo que CRM-21/24 ya documentaron como
pendiente, no un hallazgo nuevo. Cualquier fase futura debería priorizarse
entre: (a) cerrar §15.3 (migrar Ventas/WhatsApp a los Use Cases nuevos),
o (b) construir §15.2 (automatizaciones) — ambas son decisiones del
usuario, no algo para asumir.
