# Fase 0 — Auditoría correctiva enterprise (organización, finanzas multiunidad, permisos, dispositivos)

Fecha: 2026-10-25. Rama `claude/erp-financial-bounded-context-uqxz6b`, HEAD `64bffd34`. Árbol limpio y sin
divergencia con el remoto.

**Alcance.** Se verificó cada hallazgo preliminar sobre HEAD y se amplió la inspección a sesión,
autorización, organización, Finanzas, instalación y almacenamiento. Las líneas citadas son de HEAD.
Medición de datos: copia de la base real del 2026-10-25.

**Relación con trabajo previo.** Esta auditoría continúa la arquitectura híbrida, sin reemplazarla.

- `docs/architecture/hybrid_postgresql/00..15`: Slices 0–6 hechos y probados contra PostgreSQL 16 en el CI.
- `docs/refactor/PERM-AUD_auditoria_968e0bc.md`: regla única de concesión, `unwired()` y alcance por
  sucursal.

## 1. Hallazgos preliminares (H01–H07)

| ID | Veredicto | Evidencia en HEAD |
|---|---|---|
| H01 PostgreSQL incompleto | **DESCARTADO, ya resuelto** | `backend/infrastructure/db/database.py:97` `_postgresql_factory` (psycopg 3, transacción explícita, límites, DSN del entorno). Slice 3; probado en el CI (`central-postgres`, ejecuciones 40199145410 y siguientes). La revisión remota leyó un commit anterior |
| H02 Finanzas filtra por sucursal | **CONFIRMADO, sin uso en la UI** | `financial_statement_query_service.py:54-145` acepta `branch_id`. La pantalla nunca lo pasa (H07) |
| H03 Centros de costo y utilidad | **CONFIRMADO, sin modelo organizacional** | `cost_centers(id, code, name, parent_id, branch_id, active)`, `profit_centers(id, code, name, branch_id, active)` y `budgets(..., branch_id)` existen (0 filas en la base real). Cuelgan de `branch_id`; no hay unidad organizacional |
| H04 Autenticación ligada a sucursal | **CONFIRMADO, en dos sentidos** | (a) `security/auth.py:119-175` es legacy (detalle abajo). (b) El login **canónico** también liga la sesión a la sucursal de origen: N01 |
| H05 Esquema financiero delicado | **CONFIRMADO Y AGRAVADO** | N05: la migración 345 manda borrar la base completa |
| H06 Contrato de arquitectura | **CONFIRMADO, vigente** | `docs/architecture/DATABASE_COMPATIBILITY.md` (47 líneas): propiedad del esquema, sin SQL en la UI, reglas de transacción y compatibilidad SQL. Se adopta como contrato base |
| H07 Ámbito contable limitado | **CONFIRMADO, más amplio** | N04. Las **lecturas** de Finanzas no tienen autorización en la capa de aplicación, y la UI no envía ámbito |

**Detalle de H04 (a).** `security/auth.py` usa ids enteros (`uid: int`, línea 245) y la tabla
`usuario_modulos`. Su único importador es `database/conexion.py:25` (`verificar_password`), que **nadie
llama**. Es código muerto. El login canónico es `backend/security/authentication/authenticate_user_use_case.py`.

## 2. Hallazgos nuevos

| ID | Severidad | Hallazgo | Evidencia |
|---|---|---|---|
| **N05** | **P0 operativo** | La 345 (contrato «nacido limpio» de Finanzas) **detiene el arranque** ante un esquema financiero anterior y ordena *«respalde y elimine data/spj_pos_database.db»*: la base COMPLETA, con ventas, clientes e inventario. `drop_legacy_finance_tables` borra «sin rescate» | `finance_schema.py:1000-1012`, `:970-975`. **En la copia real el motor se detiene en la 345: la próxima actualización no abriría la base real** (39 tablas difieren, todas vacías hoy) |
| **N01** | Alta | La sucursal activa de la sesión es la **de origen del usuario**, no la del equipo. La sucursal de instalación (`sucursal_instalacion_id`) se guarda, pero nadie la lee: su lector (`core/app_container.py`, `branch_resolution.py`) se borró. **Regresión**: la terminal ya no está anclada a su sucursal | `authenticate_user_use_case.py:110`, `application_context_builder.py:60-78`, `set_installation_branch_use_case.py:2-6` |
| **N02** | Alta | Sin sucursal, la sesión **se niega** (cierra seguro, bien), pero eso hace que **todo rol dependa de una sucursal** | `cash_register/session_authorization.py:26-28`, igual en `customers`, `inventory`, `loyalty`, `orders_delivery` |
| **N04** | Alta | Finanzas: las **lecturas** no pasan por autorización de aplicación (sólo se oculta la ruta en la UI) y la UI llama sin ámbito | `finance_routes.py:197-221` (servicios de consulta sin política); `finance_presenter.py:137-140` (`can` sólo para comandos); `:1010-1018` y `:344` (sin `branch_id`) |
| **N03** | Media | Un solo rol por usuario | `user_credentials.py:22` `role: str`; `application_context_builder.py:86` `roles=(credentials.role,)` |
| **N06** | Media | No existen organización, entidad legal ni planta. La empresa es `installation.company_id` + `sucursales.rfc_empresa`; la única ubicación es `sucursales` | Tablas de la base real (sección 3) |
| **N07** | Media, decisión | Cada equipo tiene **su propia SQLite**; no hay base compartida ni servidor de sucursal | `app_paths.py:140`, `frontend/desktop/app.py:79` |
| **N08** | Media | Las transferencias no generan asientos. Al consolidar no hay doble conteo, pero el inventario contable **por sucursal** queda desfasado tras transferir | `event_handlers/finance/`: sólo `inventory_adjustment_handler.py`; ninguno de transferencias |
| **N09** | Baja | `security/auth.py` es legacy muerto | H04 (a) |
| **N10** | Media | Aprovisionamiento parcial (detalle abajo) | `provision_installation_use_case.py`; tablas `installation`, `workstations`, `devices`; `backend/application/sync/station_admin.py` |
| **N11** | Info | La sesión offline siempre funciona contra la SQLite local. No hay permisos firmados desde el servidor (todavía no existe servidor central) | Sesión: `legacy_session_adapter.py`, `security_grant_versions` (PERM-AUD) |

**Consecuencias de N07.** Dos cajas de la misma sucursal llevan existencias, turnos y folios
independientes. El servidor central (Slices 4–6) consolida después, pero **no coordina en línea**.

**Detalle de N10.** Lo que existe:

- primer arranque con empresa, sucursal, dueño y estación (`provision_installation_use_case.py`);
- tablas `installation`, `workstations` y `devices` en la base local;
- alta de estación en el servidor central con secreto de 256 bits (Slice 4, `station_admin.py`).

Lo que falta: invitación de un solo uso, llave generada en el equipo, revocación que llegue a la estación,
y reemplazo o recuperación con historial.

### Lo que ya está bien y se conserva

- **Una sesión sin sucursal nunca equivale a acceso global** (N02). El prompt pide justo esto.
- **Alcance por sucursal resuelto en el servidor** (`branch_scope_query_service.py:1-40`): permiso global
  inyectado por el módulo consumidor, después `usuarios_sucursales`, después la sucursal propia, y si no,
  ninguna.
- **Regla única de concesión** `is_granted` y `unwired()`, que cierra seguro (PERM-AUD).
- **Capacidades** a nivel de almacén (`warehouses.allow_sales_allocation/purchase_receipt/production`) y de
  instalación (`InstallProfile`, `software_updates/installation.py:36`).
- **Jerarquía de ámbitos de Configuración** (`ScopeType`: GLOBAL, COMPANY, BRANCH, WAREHOUSE, LOCATION,
  WORKSTATION, PLANT, WORK_CENTER, PRODUCTION_AREA…) con herencia (`configuration_inheritance_policy.py`).
- **Tipos de transferencia que ya hablan de planta** (`transfers/enums.py:19-28`: PLANT_TO_WAREHOUSE,
  WAREHOUSE_TO_PLANT; ámbito PLANT).
- **Persistencia híbrida, sincronización, ingesta y proyecciones** centrales (Slices 0–6).

## 3. Organización: actual frente a objetivo

| Concepto | Hoy | Propuesta (extender, no duplicar) |
|---|---|---|
| Organization | `installation.company_id` (texto) | Tabla `organizations` (una fila por instalación central). `company_id` pasa a ser su id |
| LegalEntity | `sucursales.rfc_empresa` (texto por sucursal) | `legal_entities` (RFC, razón social) **sólo si hay más de un RFC** (decisión D2) |
| OrganizationalUnit | — | `org_units` con `unit_type` y `parent_id`: una sola jerarquía para sucursal, planta, centro de distribución y oficina corporativa |
| OperatingSite / Branch / Plant | `sucursales` = todo | `sucursales` **se conserva** (conserva los ids; 772 tablas la referencian vía `branch_id`). Cada sucursal es una `org_unit` de su tipo. Una planta es una `org_unit` PRODUCTION_PLANT con su propio id, sin fingir ser sucursal |
| Warehouse | `warehouses.branch_id` + capacidades | Se conserva; agrega `org_unit_id` (la planta o el centro de distribución donde está) |
| Department | `hr_departments.branch_id` | Agrega `org_unit_id` (opcional) |
| CostCenter / ProfitCenter | `branch_id`, `parent_id` | Agregan `org_unit_id`; **no se recrean** |
| Workstation / Device | `workstations`, `devices` (`branch_id`) | Agregan `org_unit_id`; el equipo define el **sitio de operación** de la sesión (N01) |
| Capacidades | Almacén + instalación | `org_unit_capabilities` (SALES, POS, CASH, INVENTORY, PURCHASING, RECEIVING, PRODUCTION, LOGISTICS, FINANCE, CRM, BI) con excepciones autorizadas. **No se deducen del tipo** |
| RoleAssignment | `usuarios.rol` + `usuarios_sucursales` | `user_role_assignments(user, role, scope_type, scope_id)`: varios roles con ámbito (N03). `usuarios.rol` queda como rol por omisión, por compatibilidad |

**Por qué `branch_id` no se renombra.** Lo usan cientos de tablas y todos los contextos. La compatibilidad
se logra así: cada `branch_id` existente es el id de una `org_unit`, y una sucursal sigue siendo una
sucursal. Lo nuevo (plantas, oficinas, centros de distribución) son `org_units` de otro tipo, y las tablas
que deban colgar de ellas lo harán mediante `org_unit_id`.

## 4. Matriz de reutilización

| Componente existente | Decisión |
|---|---|
| `is_granted`, `PermissionQueryService`, catálogo de permisos, `unwired()` | **Reutilizar**. Los ámbitos se suman como contexto de evaluación, sin un segundo RBAC |
| `BranchScopeQueryService`, `session_branch_scope.py` | **Extender** de sucursal a `org_unit` con jerarquía |
| `ApplicationContextBuilder`, `AuthenticateUserUseCase`, `LegacySessionAdapter` | **Corregir** (N01): el sitio de operación viene del equipo y se valida contra los ámbitos del usuario |
| `SetInstallationBranchUseCase`, `sucursal_instalacion_id` | **Reconectar** como sitio del equipo |
| Servicios de consulta financieros (`financial_statement`, `general_ledger`…) | **Extender** con un filtro de ámbito componible + una política de lectura en aplicación (N04) |
| `cost_centers`, `profit_centers`, `budgets`, `hr_departments` | **Extender** con `org_unit_id` |
| `ScopeType` y herencia de Configuración | **Reutilizar** como vocabulario de ámbitos |
| `ProvisionInstallationUseCase`, `workstations`, `devices`, `station_admin` (Slice 4) | **Extender** con invitación, llave de equipo, revocación y reemplazo |
| Motor de replicación, ingesta, proyecciones, carril `pg` (Slices 0–6) | **Reutilizar** para propagar organización, asignaciones y revocaciones |
| Migración 345 / `finance_schema` | **Corregir** (N05) sin perder la regla «nacido limpio» para bases vacías |
| `security/auth.py` | **Retirar** (N09) |

## 5. Estrategia y orden propuesto (ajustado por dependencias)

1. **P0 — N05.** La 345 nunca debe ordenar borrar la base:
   - si las tablas financieras que difieren están vacías, se reconstruyen solas;
   - si tienen datos, se detiene con una conversión guiada y respaldo.

   Va primero porque hoy **bloquea la actualización de la base real**.
2. **Fase 1 — Modelo organizacional.** `organizations`, `org_units` (con jerarquía y tipos), capacidades por
   unidad, y `org_unit_id` en almacenes, centros de costo y utilidad, departamentos y equipos. Migración
   expandir/migrar: cada sucursal existente se convierte en unidad RETAIL_BRANCH con el **mismo id**.
3. **Fase 2 — Permisos contextuales.**
   - `user_role_assignments` con ámbito;
   - el sitio de operación de la sesión sale del equipo (N01) y se valida contra los ámbitos del usuario;
   - los roles corporativos no necesitan sucursal (N02), sin convertir NULL en global;
   - ámbitos heredados por jerarquía.
4. **Fase 3 — Finanzas multiunidad.**
   - filtro de ámbito componible (organización, sucursal, planta, centro de costo o utilidad, periodo,
     cuenta, moneda) validado contra permisos;
   - política de lectura en aplicación (N04) y selector de ámbitos autorizados en la UI;
   - consolidación sin doble conteo y reclasificación de inventario entre unidades (N08).
5. **Fase 4 — Aprovisionamiento.**
   - invitación de un solo uso (sólo se guarda su huella) y llave generada en el equipo;
   - registro con UUIDv7, revocación, suspensión, reemplazo y recuperación;
   - pantalla de equipos.
6. **Fases 5–6** (PostgreSQL y sincronización): ya avanzadas en los Slices 3–6. Aquí se agrega la
   propagación de organización, asignaciones y revocaciones hacia las estaciones (lo que estaba previsto
   como Slice 7).
7. **Fases 7–9:** web, instalador e integración, en ese orden.

Regla de toda la implementación: cambios incrementales, sin migraciones destructivas, cada fase con
pruebas ejecutadas, documento y commit.

## 6. Decisiones que necesito del usuario

| # | Decisión | Opciones | Recomendación |
|---|---|---|---|
| D1 | Varias cajas en una sucursal (N07) | (a) cada caja autónoma con su SQLite y conciliación central; (b) un equipo de la sucursal como servidor local en la red y las demás cajas como clientes; (c) configurable por sucursal | **(a)** hoy, con alertas de sobreventa entre cajas. (b) crea un punto único de falla dentro de la sucursal y rompe «sin Internet sí vende» si ese equipo se apaga |
| D2 | ¿Un RFC o varios? | Una entidad legal, o varias con relaciones intercompañía | Si hoy es **un solo RFC**, `legal_entities` no se crea todavía (el modelo queda listo para agregarla) |
| D3 | Identidad del equipo | (a) llave Ed25519 generada en el equipo y protegida con DPAPI de Windows, con firma en cada solicitud; (b) el secreto por estación del Slice 4 | **(a)**: la llave privada nunca sale del equipo. El secreto del Slice 4 queda como respaldo durante la transición |
| D4 | Varios roles por usuario | Sí (`user_role_assignments` con ámbito) / no | **Sí**: lo exigen los ejemplos del prompt, como el comprador corporativo |

## 7. Avance: P0 N05 resuelto (2026-10-25)

La 345 aplica el contrato sin convertir y **sin pedir nunca borrar la base**:

- crea las tablas ausentes;
- vuelve a crear las de un contrato anterior que estén vacías;
- si alguna tiene datos, se detiene sin tocar nada y nombra las tablas.

Se retiró `assert_finance_schema_contract`, cuyo mensaje mandaba borrar la base.

**Evidencia:**

- `tests/integration/finance/test_finance_born_clean_345.py`: 4 pasan.
- `test_installer_updater_guardrails` **pasa**. Fallaba desde antes justo por ese mensaje
  (`finance_schema.py:1010`).
- Sobre una copia de la base real:
  - el motor migra completo, 332 → 350 (recrea 16 tablas vacías y crea 23; ningún dato tocado);
  - el **arranque completo de la app** pasa sus seis etapas, con llaves foráneas activas.

