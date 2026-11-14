# Lote 7 — Permisos, sesiones y seguridad

- **Rama:** `fix/lote-7`, sale de `sdlc/sdlc-arq-perm-001` (`abfd87e1`) por decisión del responsable.
- **Rama base de comparación:** `claude/erp-financial-bounded-context-uqxz6b`.
- **Saltado:** SDLC-ARQ-AUD-001, construido en `sdlc/sdlc-ui-003-auto`; no se trajo aquí.

## Resumen por ítem

| Ítem | Estado | Commit |
|---|---|---|
| SDLC-ARQ-PERM-001 | LISTO (construido en `sdlc/sdlc-arq-perm-001`, verificado aquí) | `a0b5c80b`…`abfd87e1` |
| SDLC-ARQ-SESS-003 | LISTO | `8e0e8851` |
| SDLC-ARQ-PERM-003 | LISTO | `c9978d67` |
| SDLC-ARQ-PERM-002 | LISTO | `89ea53a0` |
| SDLC-ARQ-PERM-004 | LISTO: la política queda fijada; sin migración de roles, por decisión del responsable | `bdf2f999` |

Ningún ítem quedó BLOQUEADO, en ESPERA ni DESCARTADO.

## Detalle

### SDLC-ARQ-PERM-001 — solo verificación

- **Pruebas:** 142 pasan (`tests/architecture/test_configuracion_use_cases_are_authorized.py`,
  `tests/unit/configuracion/test_configuracion_action_authorizer.py`,
  `tests/unit/configuracion/test_configuracion_use_cases_backend_authorization.py`,
  `tests/integration/configuracion/test_configuracion_backend_authorization.py`).
- **Revisión del diff, sin defectos:**
  - Ningún caso de uso se construye sin `authorization` fuera de `configuracion_routes.py`, salvo
    `PreviewLogoUseCase`, que no escribe (recorrido AST de `backend`, `frontend`, `scripts`, `main.py`).
  - El actor declarado por el presentador siempre es `session.user_id`, incluido `user_name=actor`.
  - El atajo de actor confiado solo se activa desde `permissive_for_tests()`.

### SDLC-ARQ-SESS-003 — venta suspendida ajena

- **Problema confirmado:** el caso de uso dejaba reanudar a cualquiera y `cashier_user_id` no cambiaba.
- **Defecto adicional:** `SaleRepository.save` no incluía `cashier_user_id` en el `ON CONFLICT`, así que
  aunque el dominio reasignara, el cambio no llegaba a la base.
- **Cambio:**
  - Por defecto solo reanuda el cajero original. La comparación es contra `cashier_user_id`; antes un
    `suspended_by_user_id` vacío dejaba pasar a cualquiera.
  - Permiso nuevo `POS.venta.reanudar_ajena`. Con él, el supervisor toma la venta directamente; sin él, otro
    cajero necesita la autorización en caliente de quien lo tenga (usuario, clave y motivo).
  - El caso de uso ya no acepta `allow_cross_user_resume`: lo decide el permiso, no el llamador.
  - El responsable pasa a ser quien reanuda y se suelta `cash_session_id`. Queda
    `SALE_RESUME_TRANSFERRED` en `audit_logs` y el traspaso en el evento `SALE_RESUMED`, en la misma
    transacción.
  - La pantalla pide la autorización **antes** de apartar la venta en curso. Si el backend rechaza después de
    apartarla, abre una venta nueva; la apartada queda en la lista de suspendidas.
- **Pruebas:** `tests/integration/sales/test_sales_foreign_resume.py`,
  `tests/integration/sales/test_sales_pos_screen_flows.py`. Se actualizaron `tests/unit/test_sales_use_cases.py`
  y `tests/unit/test_sales_domain.py`: fijaban la bandera y el nombre de parámetro anteriores.
- **Sin cambio, a revisar:** `allow_cross_workstation_resume` sigue en `True`. El objetivo solo pide
  restringir por usuario, así que el mismo cajero puede reanudar en otra estación. El intent lo menciona en
  el problema, pero no está decidido.

### SDLC-ARQ-PERM-003 — un solo resolvedor de alcance

- **Problema confirmado:** ver `tests/integration/security/test_scope_single_resolver.py`; 12 de 19 fallaban
  antes del arreglo.
- **Cambio:**
  - `BranchScopeQueryService.allowed_branch_ids` resuelve con `AccessScopeResolver`, el mismo de la sesión.
  - `TransferSessionScopeChecker` niega sin sucursal, salvo alcance global.
  - `TransferAuthorizationPolicy.require` solo comprueba las patas que la operación declara. Imprimir,
    generar sugerencias y validar al autorizador no recaen sobre una sucursal y siguen funcionando; una pata
    declarada vacía se niega.
- **Cambios de comportamiento que el responsable debe conocer:**
  - La asignación ahora se **suma** a la sucursal propia; antes la sustituía en este servicio y se sumaba en
    la sesión. Se reescribió `test_la_asignacion_gana_sobre_la_sucursal_propia`.
  - Un rol de toda la empresa alcanza todas las sucursales sin permiso inyectado. Antes un administrador se
    quedaba en la suya en Compras, Precios y Transferencias, aunque el docstring decía lo contrario. Se
    reescribió `test_sin_permiso_inyectado_no_hay_escape_global`, ahora con `gerente`, y se agregó la prueba
    del administrador.
  - Un usuario con `usuarios.rol` vacío ya no alcanza su sucursal propia; de todas formas no tiene permisos.
  - El objetivo y las decisiones aprobadas de PERM-004 respaldan estos cambios, pero sustituyen la decisión
    anterior «asignación con respaldo» del buscador.
- **Fixtures:** 8 archivos de prueba montaban `usuarios` sin `rol` o sin la tabla. Se les dio la forma real
  (`test_pricing_branch_selector`, 6 de `tests/integration/procurement`, `test_create_transfer_request_e2e`).
- **Sin verificar:** transferencias existentes con nodo sin `branch_id` en una base real. No se probó sobre
  una copia real; a partir de ahora se negarían salvo alcance global.

### SDLC-ARQ-PERM-002 — escalada por alcance

- **Problema confirmado:** 9 de 16 pruebas fallaban antes del arreglo.
- **Cambio:** `GrantScope` (`backend/application/security/grant_scope.py`), apoyado en `AccessScopeResolver`.
  - Una unidad se cubre entera: quien tiene una sucursal de la región no otorga en la región.
  - `COMPANY` exige alcance de toda la empresa.
  - El usuario destino debe operar en algún sitio del actor.
  - Una excepción sin sucursal exige cubrir todo lo que el usuario alcanza.
- **Aplica en** `RoleAssignmentService.assign`/`revoke` y `SaveUserPermissionsUseCase`, también para DENY e
  INHERIT.
- **Rechazos auditados con motivo:** `ROLE_ASSIGNMENT_DENIED` en `audit_logs` y
  `ACTUALIZAR_PERMISOS_DENEGADO` en `configuracion_audit_log`.
- **Prueba:** `tests/integration/security/test_grant_scope_escalation.py`.
- **Fuera de alcance, para seguimiento:** cambiar el rol principal o las sucursales de un usuario
  (`SaveUser`) y editar permisos de un rol (`SaveRolePermissions`) siguen sin esta guarda; el intent no los
  incluye.

### SDLC-ARQ-PERM-004 — roles reservados y operación global

- **Decisiones del responsable (BACKLOG, 2026-11-02):** `system_owner` y las cuentas COMPANY operan el POS de
  cualquier sucursal sin asignación operativa, y los roles se mantienen **reservados**. Estas decisiones dejan
  sin efecto dos objetivos del intent: separar consulta y operación, y la migración que convertía nombres en
  asignaciones. Por eso no hay migración.
- **Cambio:**
  - La política queda escrita en `principals.py` y fijada en
    `tests/integration/security/test_company_wide_operation_policy.py`.
  - Se retira `LegacySessionAdapter.es_gerente`, sin lectores en `backend/` ni `frontend/`.
- **Prueba que falla antes del arreglo:** solo la de `es_gerente` (la propiedad existía). No se ejecutó sobre
  el código anterior: se dedujo de leerlo. Las demás fijan una política que ya era el comportamiento.
- **`test_the_owner_is_company_wide_and_reaches_every_site` se conserva:** coincide con la política aprobada.

## Migraciones

| Número | Archivo | Qué hace |
|---|---|---|
| 368 | `migrations/standalone/368_pos_foreign_resume_permission.py` | Siembra `POS.venta.reanudar_ajena` para `system_owner`, `admin`, `gerente` y `supervisor` si existe. Solo agrega, con `INSERT OR IGNORE`. |

Registrada en `migrations/engine.py` y documentada en `migrations/MIGRATION_LOG.md`. Se ejecutó dentro de la
cadena completa `migrations.engine.up` sobre una base temporal (fixture de
`test_branch_scope_query_service.py`). No se probó sobre una copia de la base real.

## Pruebas finales (commit `bdf2f999`)

| Corrida | Resultado |
|---|---|
| `python -m compileall -q .` | rc=0 |
| Unit e integración de áreas tocadas (seguridad, ventas, configuración, compras, precios, organización, bootstrap) | **7 failed, 2055 passed** (53 min) |
| `tests/integration/transfers` | **62 passed** (15 min; cada prueba de páginas tarda unos 25 s en su fixture) |
| `tests/architecture` completo | **22 failed, 883 passed, 1 skipped, 2 xfailed** (42 min; sin deseleccionadas) |

### Fallos preexistentes

Las 7 fallas también ocurren en `abfd87e1`, antes de este lote (7 failed, 50 passed, sobre una exportación de
ese commit en un directorio temporal):

- `tests/unit/bootstrap/test_steps.py::test_application_paths_step_creates_directories`
- `tests/unit/test_transfers_ui_workspace.py::test_sidebar_filters_permissions_and_dialogs_use_accessible_standard_inputs`
  (también en `docs/sdlc/baseline/2026-10-28.md`)
- `tests/integration/pricing/test_pricing_write_layer.py`: `test_el_autorizador_se_valida_contra_rol_permisos`,
  `test_un_autorizador_sin_el_permiso_de_excepcion_no_autoriza`, `test_el_comodin_de_modulo_autoriza`
- `tests/integration/test_sales_checkout_settles_everything.py`:
  `test_con_autorizacion_y_motivo_se_cobra_y_queda_negativo_y_auditado`,
  `test_la_autorizacion_sin_existencia_se_valida[sin_permiso]`

Las de Precios y Ventas se deben a `no such column: sucursal_id` en fixtures reducidos, la causa que la línea
base agrupa como «fixtures sin `usuarios.sucursal_id`».

### Corrida completa de arquitectura

Las 22 fallas son del mismo conjunto de la línea base (22 failed, 879 passed): todas están en archivos que
`docs/sdlc/baseline/2026-10-28.md` ya nombra, y ninguna apunta a un archivo tocado por este lote. Las 4 pasadas
de más son la guardia de PERM-001. La comparación es por archivo de prueba, no por el detalle de cada fallo.

Esta corrida se lanzó como guardias del área, con `-k "sales or pos or ..."`, pero `pos` coincide con la carpeta
`pos_spj_v13.4` y seleccionó toda la suite. Por eso cuenta como corrida completa y no se repitió.

Una corrida anterior no sirvió: su log, `arch.log`, estaba en un directorio temporal compartido y lote-3 lo
sobrescribió. Las cifras de ese archivo (22 failed, 879 passed) son de lote-3 y no se usaron.
