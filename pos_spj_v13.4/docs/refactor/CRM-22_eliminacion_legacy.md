# CRM-22 — Eliminación de legacy: SQL UI, módulo monolítico, IDs, campos inconsistentes, componentes, imports, allowlist

Fecha: 2026-08-14. Limpieza en sitio de `modulos/clientes.py` y sus
servicios legacy (`core/services/cliente_query_service.py`,
`repositories/cliente_repository.py`), guiada por el §94 del prompt maestro
(marcado "INCOMPLETA" en `docs/refactor/customers_crm_master_prompt.md`) y
confirmada explícitamente con el usuario antes de tocar código: **limpiar
los anti-patrones EN SITIO, sin retirar capacidad operativa** —
`modulos/clientes.py` sigue siendo la ruta de escritura real de Clientes en
producción durante y después de esta fase. Ninguna de las tres opciones que
se le presentaron al usuario (limpieza en sitio / retiro completo / solo el
módulo CRM nuevo) fue elegida sin preguntar; se preguntó explícitamente
porque el §94 original terminaba a media frase y el retiro completo
requeriría una migración de escrituras que CRM-21 deliberadamente no hizo.

## El hallazgo que cambió el alcance esperado

La auditoría inicial encontró que `modulos/clientes.py` ya estaba bastante
limpio en el eje SQL: **cero SQL crudo real** (confirmado por
`tests/architecture/allowlists.py`'s `SQL_IN_UI_ALLOWLIST` con comentario
"0 SQL real" desde antes de esta fase) y **cero `ClienteRepository`
instanciado desde un widget** — ambos ejes que el propio §94 nombra ya
estaban resueltos por remediaciones previas ("Remediación D"). El trabajo
real resultó ser: un archivo de 1393 líneas/6 clases (el cargo real de
"monolítico"), dos métodos muertos y rotos, dos bugs reales de `NameError`
nunca detectados por falta de cobertura de tests, un uso crudo de
`QTableWidget`, y una entrada de allowlist obsoleta.

## 1. Módulo monolítico → dividido, sin cambio de comportamiento

`modulos/clientes.py` (1393 líneas: `ModuloClientes` + 5 diálogos) se
dividió en:

- `modulos/clientes.py` — solo `ModuloClientes` ahora (541 líneas).
- `modulos/dialogs/cliente_dialog.py` — `DialogoCliente`.
- `modulos/dialogs/cliente_historial_dialog.py` — `DialogoHistorialCliente`.
- `modulos/dialogs/cliente_tarjetas_dialog.py` — `_DialogoAsignarTarjetaCliente`
  + `_DialogoTarjetasCliente`.
- `modulos/dialogs/cliente_rfm_dialog.py` — `_DialogoRFM`.

`modulos/clientes.py` reexporta las cuatro clases movidas (`from
modulos.dialogs.cliente_dialog import DialogoCliente`, etc.) para que
cualquier `from modulos.clientes import DialogoCliente` siga funcionando
igual. Verificado que era seguro antes de tocar nada: **un solo consumidor
externo real** en todo el repositorio, `from modulos.clientes import
ModuloClientes` en `interfaz/main_window.py` — ningún otro archivo importa
los diálogos directamente (son clases internas, tres de ellas ya con
guion bajo).

### Por qué se auditó primero en vez de dividir directamente (CLAUDE.md regla 1)

Cero tests en todo el repositorio instanciaban `ModuloClientes` ni ninguno
de los 5 diálogos antes de esta fase (solo guardrails de texto estático).
Se escribió `tests/ui/test_modulo_clientes_legacy_smoke.py` (9 pruebas)
**contra el archivo original, sin dividir**, confirmando que pasaban, y
solo después se hizo la división física, reejecutando la misma suite sin
cambiarla — mismo comportamiento probado antes y después.

## 2. Dos bugs reales de `NameError`, nunca detectados

Al mover el código se encontró que `QInputDialog` (usado en
`_bloquear_tarjeta`) y `QFileDialog` (usado en `_exportar` del diálogo RFM)
**nunca estuvieron importados en ningún lado del archivo original** — un
comentario `# [spj-dedup] from PyQt5.QtWidgets import QInputDialog,
QMessageBox` muestra que una pasada automática de deduplicación de imports
eliminó el import local asumiendo, incorrectamente, que ya existía a nivel
de módulo. Presionar "🔒 Bloquear" en tarjetas o "📥 Exportar Excel" en RFM
lanzaba `NameError` en producción. Se agregaron los imports correctos en
los archivos nuevos, y dos pruebas de regresión
(`test_bloquear_tarjeta_uses_qinputdialog_without_nameerror`,
`test_exportar_rfm_uses_qfiledialog_without_nameerror`) — verificadas
directamente: se removió el import, se confirmó que la prueba fallaba con
el `NameError` real, se restauró el import, se confirmó que volvía a pasar.

## 3. Código muerto y roto eliminado

- **`ClienteQueryService.historial_compras/historial_puntos/
  historial_creditos`** (`core/services/cliente_query_service.py`):
  eliminados. Cero llamadores en todo el repositorio (`DialogoHistorialCliente`
  usa `CustomerHistoryQueryService`, no este servicio) y además **roto**:
  `historial_compras` seleccionaba `ventas.metodo_pago`, columna que no
  existe (la canónica, usada en todo el resto del código, es
  `ventas.forma_pago`) — habría lanzado `sqlite3.OperationalError` si
  alguna vez se hubiera invocado. Esta era la pieza concreta de "campos
  inconsistentes" que el usuario nombró.
- Un método `_abrir_rfm` duplicado y huérfano, mal indentado dentro de
  `_DialogoTarjetasCliente` (nunca conectado a ningún botón — la única
  conexión real es `ModuloClientes._abrir_rfm`), no se copió al dividir el
  archivo. Prueba de regresión: `test_abrir_rfm_button_opens_only_one_real_dialog`.
- Un `self._svc = ClienteQueryService(conexion)` sin uso alguno dentro de
  `DialogoHistorialCliente.__init__` (esa clase solo usa
  `self._history_qs`) no se copió al archivo nuevo.
- `import sqlite3` a nivel de módulo en `modulos/clientes.py`, sin ningún
  uso real (`sqlite3.` no aparece en todo el archivo) — eliminado.

## 4. IDs / componentes

- **IDs**: no había ningún `lastrowid` ni identidad entera real (`clientes.id`
  ya es UUIDv7 TEXT desde antes de esta fase). Sí había type hints
  engañosos (`cliente_id: int`) y un bug real de logging: cuatro llamadas
  `logger.warning/info("...%d...", cliente_id, ...)` en
  `repositories/cliente_repository.py` formateando un UUID string con `%d`
  — no rompe la app (el módulo `logging` atrapa errores de formato al
  emitir y solo ensucia stderr), pero pierde el mensaje de log real.
  Corregido: 9 type hints `cliente_id: int` → `cliente_id: str`, 4
  `%d` → `%s`.
- **Componentes**: un solo uso real de `QTableWidget()` crudo en todo
  `modulos/clientes.py` — la tabla principal de `_DialogoRFM`. El resto del
  archivo ya usaba consistentemente `create_table_with_columns`/
  `create_standard_tabs`. `create_table_with_columns` no sirve aquí sin
  cambiar comportamiento visual (fuerza `Stretch` en las 10 columnas; esta
  tabla necesita columna 0 en `Stretch` y las demás en `ResizeToContents`),
  así que se usa el factory de nivel más bajo, `create_table` (mismas
  banderas `NoEditTriggers`/`SelectRows`/alternating colors que el código
  manual ya aplicaba), preservando el resize mode por columna
  explícitamente.

## 5. Allowlist

`tests/architecture/allowlists.py::COMMIT_ROLLBACK_IN_UI_ALLOWLIST['pos_spj_v13.4/
modulos/clientes.py'] = 5` estaba obsoleta — el conteo real de
`.commit(`/`.rollback(` en el archivo, verificado antes Y después de la
división, es 0 (solo existía una mención en un docstring). Entrada
eliminada. `CUSTOMERS_CRM_LEGACY_CONSUMERS` (el burn-down list que el
usuario nombró explícitamente como "allowlist" — documentación, sin
enforcement automático) se actualizó para reflejar la nueva estructura de
archivos: la entrada de `modulos/clientes.py` ahora describe solo
`ModuloClientes`, y se agregaron cuatro entradas nuevas para
`modulos/dialogs/cliente_*.py`, cada una apuntando a su reemplazo futuro en
`frontend/desktop/modules/customers_crm/`.

## No tocado (fuera del alcance elegido por el usuario)

- **SQL UI / `ClienteRepository` desde widgets**: ya estaba limpio antes de
  esta fase (0 casos en `modulos/clientes.py`). `modulos/ventas.py:1010,1055`
  sí instancia `ClienteRepository` directamente desde un widget — un caso
  real de este anti-patrón, pero en un módulo distinto (Ventas, no
  Clientes), no tocado aquí.
- **Retiro completo de `modulos/clientes.py`**: explícitamente descartado
  por el usuario — el módulo sigue siendo la ruta de escritura real de
  Clientes en producción; su eliminación requiere el corte completo de
  rutas de escritura que CRM-21 dejó fuera de alcance (deferido a CRM-23+
  o equivalente).
- **Imports no usados restantes** en `modulos/clientes.py` (p. ej.
  `PhoneWidget`, `QFormLayout`, `QSpinBox`, ya no usados por `ModuloClientes`
  tras la división, solo por los diálogos movidos): se dejó el bloque de
  imports original intacto para no arriesgar una omisión bajo presión de
  tiempo — una poda exhaustiva símbolo por símbolo es trabajo de bajo riesgo
  y baja prioridad para una fase futura.

## Verificación

```bash
python -m pytest tests/ui/test_modulo_clientes_legacy_smoke.py \
  tests/architecture/test_customers_crm_*.py \
  tests/architecture/test_no_sql_in_pyqt_modules.py \
  tests/architecture/test_no_commit_rollback_in_frontend.py \
  tests/architecture/test_no_commit_rollback_in_pyqt.py \
  tests/architecture/test_fase_a_identity_clean_modules.py \
  tests/integration/test_customer_history_query_service.py \
  tests/integration/customers/ tests/integration/crm/ tests/integration/finance/ -q
```

- 457 pruebas pasando (9 nuevas de smoke/regresión + toda la suite
  customers/crm/finance existente), cero regresión.
- Dos guardrails de arquitectura tuvieron que actualizarse para apuntar a
  la nueva ubicación de archivo (no reflejan una regresión, sino la
  división intencional):
  `test_no_sql_in_pyqt_modules.py::test_clientes_history_dialog_has_no_sql`
  y `tests/integration/test_customer_history_query_service.py::
  test_dialog_assigns_history_qs_in_init_not_property`, ambos localizaban
  `class DialogoHistorialCliente` dentro de `modulos/clientes.py` por texto
  — actualizados a `modulos/dialogs/cliente_historial_dialog.py`.
- `import ModuloClientes, DialogoCliente, DialogoHistorialCliente,
  _DialogoAsignarTarjetaCliente, _DialogoTarjetasCliente, _DialogoRFM from
  modulos.clientes` verificado end-to-end: todas las clases resuelven
  correctamente vía reexport.
- Sintaxis limpia en todo el repositorio.
- `git status` confirma que este trabajo, igual que CRM-21, aterriza en
  archivos sin rastrear por el índice de git desactualizado ya documentado
  en `docs/refactor/CRM-21_migracion_consumidores.md` — mismo hallazgo, no
  repetido aquí en detalle.

## Pendiente (futuras fases)

- Retiro completo de `modulos/clientes.py`/servicios legacy — requiere el
  corte de escrituras que CRM-21 dejó fuera de alcance.
- `modulos/ventas.py:1010,1055` — mismo anti-patrón `ClienteRepository`
  desde widget, en un módulo distinto.
- Poda de imports no usados restantes en `modulos/clientes.py`.
- Formularios de edición equivalentes en `frontend/desktop/modules/
  customers_crm/` para reemplazar `DialogoCliente`/diálogos de tarjetas/RFM
  (CRM-18 solo construyó alta rápida, no edición).
