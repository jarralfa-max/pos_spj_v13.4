# CRM-24 — Retiro del módulo legacy `modulos/clientes.py`

Fecha: 2026-08-14. El usuario aclaró que la app está en desarrollo, no en
producción ("La app no esta en produccion, esta en desarollo. puedes
eliminar directamente") — la fase anterior (CRM-23) había construido
deliberadamente solo los prerrequisitos (menú real + edición) sin borrar
nada, precisamente por el riesgo de romper producción. Con esa aclaración,
esta fase ejecuta el retiro real que se había dejado pendiente.

## Qué se eliminó

- `modulos/clientes.py` (`ModuloClientes`).
- `modulos/dialogs/cliente_dialog.py` (`DialogoCliente`).
- `modulos/dialogs/cliente_historial_dialog.py` (`DialogoHistorialCliente`).
- `modulos/dialogs/cliente_tarjetas_dialog.py`
  (`_DialogoAsignarTarjetaCliente`, `_DialogoTarjetasCliente`).
- `modulos/dialogs/cliente_rfm_dialog.py` (`_DialogoRFM`).
- `core/services/cliente_query_service.py` (`ClienteQueryService`) — huérfano
  tras el borrado de arriba: verificado que sus únicos consumidores reales
  eran esos mismos diálogos (grep de todo el repo antes de borrar,
  no asumido).
- `tests/ui/test_modulo_clientes_legacy_smoke.py` (CRM-22) y
  `tests/integration/test_customer_history_query_service.py`'s
  `test_dialog_assigns_history_qs_in_init_not_property` — su sujeto ya no
  existe.
- La entrada de menú `"CLIENTES"` (`_conectar`/`_crear_boton`) en
  `interfaz/main_window.py`/`interfaz/menu_lateral.py` — `"CLIENTES_CRM"`
  (CRM-23) es ahora la única entrada de Clientes.

Los 5 archivos borrados quedaron respaldados (fuera del repo, en el
scratchpad de esta sesión) antes de borrarlos — el índice de git de este
repositorio no rastrea ninguno de estos archivos (confirmado con `git
status`: todos aparecían como `??`), así que no había red de seguridad de
git para revertir el borrado.

## Qué NO se eliminó (deliberadamente, verificado antes de decidir)

`modulos/clientes.py` usaba varios servicios COMPARTIDOS que otros módulos
reales siguen necesitando — borrarlos habría roto Ventas/WhatsApp, no solo
la pantalla de Clientes:

- `repositories/cliente_repository.py` / `core/services/cliente_service.py`
  — `modulos/ventas.py:1010,1055` instancia `ClienteRepository`
  directamente para el checkout.
- `core/services/card_batch_engine.py` — `modulos/ventas.py:2884-2885`
  también lo usa (escaneo de tarjeta durante el cobro).
- `api/routers/clientes.py`, `core/use_cases/cliente.py`,
  `application/services/customer_credit_service.py` — consumidos por la
  API REST/WhatsApp (ver `docs/refactor/CRM-21_migracion_consumidores.md`).

Estos siguen en el burn-down list `CUSTOMERS_CRM_LEGACY_CONSUMERS`
(`tests/architecture/allowlists.py`) — no se tocan hasta que sus propios
llamadores (Ventas, WhatsApp) migren a los casos de uso nuevos, un trabajo
de fases futuras (mismo alcance ya documentado en CRM-21/23).

## Pérdida de funcionalidad real, sin reemplazo todavía

Tarjetas de fidelidad (asignar/bloquear/liberar/ver score) y segmentación
RFM (con exportación CSV/Excel) **ya no son accesibles desde ninguna
pantalla** — no porque se hayan migrado, sino porque no le pertenecen
arquitectónicamente al Customer Master (guardrail
`tests/architecture/test_customers_crm_does_not_own_loyalty.py`, ver
CRM-23) y ninguna fase construyó todavía una UI de Fidelidad/BI que las
absorba. Esto es una pérdida real de capacidad de usuario, aceptada
explícitamente por el usuario al pedir la eliminación directa en un entorno
de desarrollo — documentado aquí para que no se pierda de vista, no para
cuestionar la decisión.

## Rutas actualizadas para apuntar al módulo nuevo

Además del menú (`interfaz/main_window.py`/`menu_lateral.py`, ya cableado
en CRM-23), se encontraron y actualizaron dos rutas adicionales que
todavía apuntaban a `modulos.clientes`:

- `core/ui/module_loader.py::MODULE_REGISTRY["clientes"]` — un registro de
  carga dinámica de módulos separado de `main_window.py`'s `_conectar`,
  mismo patrón que `"gastos"` ya usa para apuntar a `modulos.finanzas`.
  Actualizado a `("ModuloClientesCrm", "modulos.clientes_crm", [])`.
- `interfaz/diagnostico.py` — pantalla de diagnóstico que intenta importar
  módulos "críticos" para verificar salud de la instalación. Actualizado.
- `interfaz/main_window.py`'s búsqueda global (`buscar_clientes` → navega a
  `"CLIENTES"`) y el mapeo `_DASH_NAV` del dashboard (`"clientes" ->
  "CLIENTES"`) — ambos actualizados a `"CLIENTES_CRM"` para que buscar un
  cliente o hacer clic en la tarjeta del dashboard sigan funcionando.

## Limpieza de tests dependientes

Cada archivo de test/guardrail que asumía la existencia de estos 5 archivos
se actualizó o retiró explícitamente (no se dejó fallando):

- `tests/architecture/test_no_sql_in_pyqt_modules.py`'s
  `test_clientes_history_dialog_has_no_sql` — retirado, con comentario.
- `tests/architecture/test_fase_a_identity_clean_modules.py` —
  `"modulos/clientes.py"` removido de `BRANCH_CLEAN_MODULES`.
- `tests/architecture/test_clean_birth_guardrails.py`'s
  `test_clientes_table_is_born_clean_uuid_identity` — se retiró solo la
  aserción que leía `modulos/clientes.py`; el resto del test (esquema de la
  tabla `clientes`, `api/routers/clientes.py`, `pos_adapter.py`) sigue
  intacto, esos archivos no se tocaron.
- `tests/architecture/customers_crm_guardrails.py::LEGACY_CUSTOMER_FILES` —
  las dos entradas retiradas.
- `tests/architecture/allowlists.py`:
  `HARDCODED_RELATIVE_PATHS_ALLOWLIST['...modulos/clientes.py']` y las
  cinco entradas correspondientes en `CUSTOMERS_CRM_LEGACY_CONSUMERS`
  eliminadas por completo (no solo bajadas de número — esa lista documenta
  su propia regla de que una entrada debe desaparecer, no decrecer, cuando
  el archivo se borra).

## Verificación

```bash
python -m pytest tests/architecture/test_customers_crm_*.py \
  tests/unit/test_customers_crm_*.py tests/unit/customers/ \
  tests/integration/customers/ tests/integration/crm/ tests/integration/finance/ -q
```

- 659 pruebas de la suite dirigida customers/crm/finance pasando, cero
  regresión.
- `core/ui/module_loader.py::MODULE_REGISTRY["clientes"]` verificado por
  importación real (no solo lectura de texto): resuelve a
  `modulos.clientes_crm.ModuloClientesCrm`.
- Sintaxis limpia en todo el repositorio.
- 10 fallas preexistentes en `tests/test_core_services.py::TestClienteRepository`
  reconfirmadas sin relación (mismo hallazgo ya documentado en CRM-21: el
  fixture de ese test crea una tabla `clientes` sin columna `codigo_qr`,
  algo que predata esta sesión — no se tocó `ClienteRepository.crear()` en
  ningún momento de esta fase).
- Se corrió también `tests/architecture/` completo (84+ archivos) en
  segundo plano para confirmar que ningún otro guardrail reaccionaba a
  este borrado más allá de los ya corregidos arriba.

## Pendiente (fases futuras)

- Igual que CRM-23: migrar las rutas de escritura legacy que SÍ siguen
  vivas (`repositories/cliente_repository.py`, `core/services/
  cliente_service.py`, `api/routers/clientes.py`, altas de WhatsApp) a los
  casos de uso del Customer Master.
- Decidir el destino de tarjetas/fidelidad y RFM — sin dueño de UI hoy.
- Límite/saldo de crédito — sin caso de uso en el Customer Master todavía.
