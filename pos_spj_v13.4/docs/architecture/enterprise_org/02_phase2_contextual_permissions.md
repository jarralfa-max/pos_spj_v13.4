# Fase 2 — Permisos contextuales y alcance por jerarquía (auditoría enterprise)

**Fecha:** 2026-10-25.

**Cierra:**
- **N01**: la sesión tomaba la sucursal propia del usuario y no la de la estación.
- **N02**: no se podía tener un rol sin sucursal, por ejemplo un director.
- **N03**: había un solo rol por usuario.
- **Decisión D4**: varios roles por usuario, cada uno con ámbito.

**Regla rectora:** no se creó un segundo sistema de permisos. Todo sigue saliendo de
`PermissionQueryService.permission_codes_for_user(usuario, sucursal)`; lo nuevo es que esa
función ahora sabe en qué sitios vale cada rol.

## 1. Modelo

| Rol | Dónde vale |
|---|---|
| Principal (`usuarios.rol`) | Su sucursal propia y las de `usuarios_sucursales`, como siempre. Si es de acceso total (dueño o administrador), en **toda la empresa**: `company_wide=True` explícito, nunca un NULL. |
| Adicional (`user_role_assignments`, migración 353) | `COMPANY` con el id de la empresa, o `ORG_UNIT` con una unidad. **Herencia por jerarquía**: una región cubre sus sitios y una planta sus almacenes. Sólo cuentan las unidades activas y las asignaciones vigentes hoy (desde/hasta inclusivas). Se revocan sin borrarse. |

Resolución (`backend/application/security/access_scope.py`, `AccessScopeResolver`):

- **Con sitio**: los permisos son la UNIÓN de los roles cuyo ámbito cubre el sitio. Encima se
  aplican, igual que antes, las excepciones por usuario y por sucursal. Un rol de acceso total
  en el sitio da `*`.
- **Fuera de su ámbito un rol no concede nada.** Un cajero de Centro que además es gerente de la
  región Norte es gerente en Chihuahua, **no** cajero.
- **Sin sitio**: el rol principal más los roles de toda la empresa. Es el comportamiento anterior,
  para llamadas sin sucursal (calcular lo que un actor puede otorgar).

## 2. Sitio de la sesión (N01)

`ApplicationContextBuilder`:

1. **Sitio** = el anclado a la estación (`sucursal_instalacion_id`). Sin ancla, la sucursal
   propia del usuario.
2. Si ningún rol del usuario cubre el sitio, se lanza **`SiteAccessDeniedError`**. El
   coordinador de inicio de sesión revoca la sesión recién abierta, dice por qué y vuelve a
   pedir credenciales. Antes un cajero de otra sucursal vendía aquí el inventario de la suya.
3. `permissions` y `roles` son los que valen en el sitio.
4. `assigned_branch_ids` son todos los sitios que cubren sus roles (todas las sucursales activas
   si alguno es de toda la empresa). Es el mismo campo que ya leen Inventario, Mermas, Cárnico,
   Transferencias y RR. HH., así que la herencia por jerarquía les llega sin tocarlos.
5. `site_capabilities` son las capacidades de la unidad del sitio.

`ApplicationContextService.change_branch` (aún sin uso en producción) acepta además:
- `site_access_checker`: ya no basta el permiso de cambiar de sucursal;
- los cargadores de roles y capacidades de la sucursal destino.

## 3. Capacidades del sitio en la sesión

`backend/domain/organization/site_capabilities.py` asigna una capacidad a cada módulo:

| Capacidad | Módulos |
|---|---|
| POS | POS |
| CASH | Caja |
| INVENTORY | Inventario, Transferencias, Mermas |
| PURCHASING | Compras |
| PRODUCTION | Procesamiento cárnico |
| LOGISTICS | Logística |
| SALES | Pedidos |
| FINANCE | Finanzas |
| CRM | Clientes y CRM |
| BI | BI |

Productos, Precios, Configuración, RR. HH., Activos y Fidelidad no dependen del sitio.

En un sitio sin la capacidad, con el mismo mecanismo que el perfil de instalación:
- el módulo se oculta del menú;
- el router lo rechaza (`SITE_CAPABILITY`);
- las familias de permisos **exclusivas** del módulo (las que el catálogo de instalación ya
  declara) se niegan a todos, administrador incluido.

Los módulos del núcleo (POS, Caja, Inventario y CRM) no tienen familias exclusivas, porque otros
módulos las consultan: en ellos se oculta el módulo y se rechaza la ruta.

Las sucursales existentes tienen todas las capacidades (Fase 1), así que nada cambia para ellas.

## 4. Gestión de roles por ámbito

**Servicio.** `RoleAssignmentService` es la única puerta de la pantalla:
- autoriza en la capa de aplicación: `CONFIGURACION.usuario.ver` para leer y
  `CONFIGURACION.usuario.asignaciones` para cambiar (sembrado a `system_owner` y `admin`);
- sube la versión de concesiones, así que las sesiones abiertas recargan permisos **y roles**;
- audita en `audit_logs`.

**Reglas contra el escalamiento** (las mismas que ya rigen el rol principal):
- nadie se otorga ni se revoca roles a sí mismo;
- el rol de dueño no se asigna;
- sólo quien tiene acceso total otorga o revoca uno de acceso total;
- quien no lo tiene sólo otorga roles cuyos permisos ya posee;
- un rol no se repite con el mismo ámbito;
- `COMPANY` tiene que ser esta empresa y `ORG_UNIT` una unidad activa de ella.

**Pantalla.** Configuración → Usuarios y Roles → **Roles por ámbito**:
- lista los roles vigentes y los revocados;
- «Otorgar rol…» pide rol, ámbito (empresa o cualquier unidad, con sangría por jerarquía),
  vigencia opcional y motivo;
- «Revocar» pide motivo.

## 5. Defecto de seguridad encontrado y corregido

Al recargar concesiones con la sesión abierta (PER-08) se recargaba el conjunto de permisos,
pero **no los roles**. `is_admin()` mira los roles: un administrador degradado seguía
saltándose todas las comprobaciones hasta cerrar sesión. Ahora `SessionGrantRefresher.load_roles`
y `LegacySessionAdapter` recargan los dos. Lo cubre
`test_an_open_session_drops_a_revoked_admin_role`.

## 6. Lo que no cambia

- `usuarios.rol` y `usuarios_sucursales` siguen siendo la fuente del rol principal: no hay dos
  copias del mismo dato.
- La base real tiene un solo usuario, el dueño. Su sucursal propia es también la anclada, así
  que ninguna sesión real queda fuera.
- Los nombres de los roles de acceso total siguen reservados (PER-07). Ahora además valen sólo
  donde llega su ámbito: un administrador asignado a una sucursal es administrador **en esa
  sucursal**.

## 7. Evidencia

| Prueba | Resultado |
|---|---|
| `tests/integration/security/test_contextual_permissions.py` | 14 pasan |
| `tests/unit/organization/test_access_scope.py` | 6 pasan |
| Coordinador de inicio de sesión (`tests/ui/test_authentication_coordinator.py`) | pasa |
| `change_branch` (`tests/unit/bootstrap/test_application_context_service.py`) | pasa |

`test_contextual_permissions.py` cubre:
- el ámbito del rol;
- la herencia por región;
- la empresa explícita;
- la vigencia y la revocación;
- el sitio inactivo;
- el sitio de la sesión;
- la sesión rechazada;
- el dueño en toda la empresa;
- las capacidades de una planta;
- el administrador degradado con la sesión abierta;
- otorgar y revocar;
- el escalamiento;
- la autorización;
- la siembra.

`tests/integration/security/test_permissions_audit_968e0bc.py` cambió una línea. Su cajero no
tenía sucursal y operaba «b1»; ahora se le da esa sucursal, porque un rol sin ámbito sobre el
sitio ya no concede nada.

En la copia de la base real:
- la migración va a 353;
- la sesión del dueño queda en Corregidora con acceso total, 11 capacidades y 2 sucursales de
  alcance;
- el arranque completo pasa.
