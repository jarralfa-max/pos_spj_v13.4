# PERM-AUD — Respuesta a la auditoría global de permisos 968e0bc

**Fecha:** 2026-10-23 · **Rama:** `claude/erp-financial-bounded-context-uqxz6b` · **Migración:** 347 ·
**Pruebas:** `tests/integration/security/test_permissions_audit_968e0bc.py` (36).

Se verificó cada hallazgo contra el código ACTUAL (posterior al commit auditado) y contra una
copia de la base real (1 usuario, rol `system_owner`; 2 721 filas en `rol_permisos`; 0 en las
tablas de excepciones y del RBAC heredado).

## Resultado por hallazgo

| ID | Estado al recibirlo | Qué se hizo |
|---|---|---|
| PER-01 | Ya cerrado por HR-AUD (2026-10-14) | La política de RR. HH. falla cerrada y `hr_routes` inyecta el verificador de sesión. Se agregan pruebas de contrato: sin verificador se deniega pagar nómina; el verificador sólo responde por el usuario de la sesión. |
| PER-02 | **Confirmado y más amplio** | ~130 constructores (Inventario, Procesamiento **y Productos**) más las políticas de **Proveedores y Precios**, que sin verificador PERMITÍAN. Ahora el default es `unwired(Policy)` y falla cerrado. Los llamadores de sistema usan concesiones nominadas. |
| PER-03 | **Confirmado, también en Productos** | Los verificadores de sesión de Configuración y de Productos ignoraban el `user_id`. Ahora conceden sólo si el usuario consultado ES el de la sesión. |
| PER-04 | **Confirmado; Transferencias peor de lo descrito** | Mermas, Proveedores y Transferencias pasan a `MODULO.accion` (correspondencia 1:1 en la migración 347) y entran al catálogo. Aprobar, surtir, despachar y recibir una transferencia **se denegaban a todos, administrador incluido**. |
| PER-05 | Confirmado (riesgo latente) + 1 consumidor real | Se retiró `security/rbac.py`. El notificador interno de Pedidos leía destinatarios de `usuarios_roles` (0 filas): **ninguna alerta interna llegaba a nadie**. Ahora usa `usuarios.rol` y las sucursales asignadas. |
| PER-06 | Confirmado | Índices únicos en las dos tablas de excepciones (con limpieza previa; ante un choque gana NEGAR). La precedencia «la capa más específica gana» se mantiene como contrato y la pantalla la explica. |
| PER-07 | **Confirmado y más amplio** | Una sola regla de comodines (`is_granted`), una sola lista de acceso total (`principals.py`), roles reservados y cuentas raíz protegidas. Ver «Hallazgos que el informe no tenía». |
| PER-08 | Confirmado | Matriz de usuario con ámbito (todas las sucursales o una), columna «Efectivo» con su origen, y recarga de permisos de las sesiones abiertas. |

## Hallazgos que el informe no tenía

1. **Las entradas de stock de cada compra habrían dejado de registrarse sin aviso.** Los manejadores de
   Inventario (`PurchaseReceiptHandler`, que está vivo vía `CanonicalPurchaseStockEntryHandler`, y las
   devoluciones y reversos de Compras) tragaban `PERMISSION_DENIED` en silencio. Con sólo cambiar el
   default a fail-closed, las compras habrían dejado de entrar al inventario sin ningún error. Ahora usan
   la concesión de Compras y una denegación queda en el log como error.
2. **La venta descontaba existencia con el caso de uso sin política.** `SalesInventoryClient` recibía la
   política real para reservar, pero la salida por venta y el reingreso por devolución usaban
   `PostInventoryMovementUseCase()`. Ahora usan la concesión Inventario→Ventas, en nombre del cajero. La
   política de sesión no sirve aquí, porque exigiría al cajero el permiso de movimiento manual para vender.
3. **El alcance «todas las sucursales» nunca se concedía.** `has_global_scope` (Inventario, Mermas,
   Procesamiento) y la política de dominio de Inventario comparaban `código in permisos` sin normalizar:
   la sesión entrega MAYÚSCULAS y la constante está en minúsculas, y además no se reconocía `*`. Resultado:
   ni un permiso explícito ni un administrador tenían alcance global. Ahora usan `is_granted`.
4. **Tres listas de «administrador» distintas.** La sesión trataba a `system_owner` como administrador;
   `PermissionQueryService` (el autorizador en caliente y el control de escalamiento) no lo hacía; la
   matriz lo trataba como «sólo agregar». Por eso el dueño, como **autorizador** de una excepción, no tenía
   los permisos de los módulos nuevos (en la base real: 0/54 de Mermas, 5/71 de Inventario, 0/69 de
   Analítica, 0/83 de Activos). Ahora el dueño es acceso total en las tres.
5. **Renombrar un rol dejaba a sus usuarios sin ningún permiso.** `usuarios.rol` guarda el nombre y el
   renombrado no se propagaba. Ahora se propaga en la misma operación.
6. **El presentador de Configuración, sin política, omitía la autorización**; el de Proveedores concedía
   todo cuando la sesión no traía `permissions` (la sesión viva nunca lo trae) y nunca mostraba la cuenta
   bancaria completa a nadie. Los dos quedaron conectados a su verificador real.
7. **Alta y edición de usuarios y roles sólo se validaban en la pantalla.** Los tres casos de uso ahora
   revalidan el permiso en backend.

## Decisiones tomadas (revisar)

- **Precedencia (PER-06):** se mantiene «la capa más específica gana», también al conceder: una excepción
  de sucursal que concede **restituye** una negación general. Es la forma de expresar «sólo en esta
  sucursal». La pantalla lo marca: «Sí — excepción en la sucursal (restituye una negación general)». Si se
  prefiere que NEGAR gane siempre, el cambio es de una línea en `_apply_overrides` más una migración de
  datos (hoy 0 filas).
- **El dueño (`system_owner`) es acceso total** en la sesión, el autorizador y la matriz. Antes la sesión
  ya se lo daba; la matriz mostraba casillas sin efecto. No se le puede quitar nada.
- **Respaldo grueso (PER-04), con el mismo criterio que PROD-22:** `MERMA.ver` concede sólo las páginas de
  consulta de Mermas. `TRANSFERENCIAS.ver`/`crear` conceden lo que ya concedían más las páginas de
  consulta. En Proveedores se conserva la traducción grueso→fino que decidió el usuario el 2026-09-16.
  Nunca conceden mutaciones, costos, auditoría, banca ni alcance a otras sucursales. Ampliación efectiva
  para roles sembrados: gerente, almacén y sólo lectura (que ya tenían `MERMA.ver`) ahora VEN Mermas.
  `MERMA.crear/editar/eliminar` quedan inertes, como las gruesas de Inventario con la 179.
- **Alcance global para administradores y dueño** en Inventario, Mermas y Procesamiento. Es consecuencia
  directa del punto 3: tienen `*`.
- **Configuración no exige sucursal activa** en su verificador de sesión, aunque el informe la pedía:
  Configuración es de empresa y es donde se reparan las sucursales.
- **Cuentas raíz:** la cuenta del dueño no cambia de rol ni se desactiva. Sólo el dueño asigna el rol de
  dueño, y sólo un actor de acceso total asigna un rol de acceso total. Asignarlo queda señalado en la
  bitácora (`acceso_total=si`).
- **Roles reservados** (`admin`, `superadmin`, `administrador`, `system_owner`): no se renombran, y ningún
  otro rol puede tomar esos nombres.
- **Recarga de sesión:** cada cambio de concesión (rol, excepción, cambio de rol de un usuario,
  activar/desactivar) sube `security_grant_versions`. La sesión la consulta como mucho cada 3 s y recarga
  con la misma `PermissionQueryService` del inicio de sesión. Una cuenta desactivada revoca la sesión,
  administrador incluido. El menú lateral no se redibuja; las acciones sí se revalidan.

## Cerrado después (2026-10-23/24)

- **Tablas del RBAC heredado retiradas** por la migración **348**: borra `permisos`, `roles_permisos` y
  `usuarios_roles` si están vacías (si alguna tuviera filas, la deja y lo avisa en el log). `m000` ya no las
  crea y `UuidCutover` filtra su especificación a las tablas que existen. Probada sobre una copia de la base
  real: las tres se retiraron y la segunda corrida no hace nada.
- **Etiquetas con acentos:** `action_label` acentúa para mostrar (diccionario `_ACCENTED` y la regla
  `-cion/-sion → -ión`); el código guardado no cambia.

## Pendiente (no hecho en esta ronda)

- **Escape global por permiso en Transferencias:** `TRANSFERENCIAS.ver.todas_sucursales` ya es otorgable,
  pero el alcance lo decide `usuarios_sucursales` (decisión del usuario del 2026-09-17).

## Mapa del cambio

- Regla única y principales: `backend/security/permissions/codes.py::is_granted`,
  `backend/security/permissions/principals.py`.
- Default fail-closed: `backend/application/security/unwired_policy.py` (en pruebas lo resuelve
  `tests/conftest.py`; las de seguridad lo desactivan con la marca `unwired_fails_closed`).
- Concesiones nominadas: `backend/application/inventory/integration_grants.py` (ventas, compras, fidelidad,
  pedidos, más las ya existentes de procesamiento, calidad y transferencias).
- Permiso efectivo: `explain_permissions` en `permission_query_service.py`; matriz y diálogo con ámbito.
- Recarga de sesión: `backend/application/security/session_grant_refresh.py` +
  `LegacySessionAdapter(grant_refresher=…)` en `frontend/desktop/app.py`.
