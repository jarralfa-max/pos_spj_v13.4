# SALES-1 — Contrato visual (POS-1 del master prompt)

Fecha: 2026-08-16
Fase anterior: `SALES-0_auditoria.md`.

## Alcance ejecutado

Master prompt §67, fase POS-1: "Documentar layout. Crear screenshots. Crear medidas. Crear
tests visuales. Bloquear cambios estructurales." Los 5 puntos se ejecutaron contra el widget
**real** (`modulos.ventas.ModuloVentas`), no una maqueta — construido headless
(`QT_QPA_PLATFORM=offscreen`) sobre un esquema SQLite completamente bootstrapeado, siguiendo
el mismo patron ya establecido en `tests/ui/test_purchasing_visual_closure.py`.

## Entregables

1. **`docs/refactor/sales_pos_layout_inventory.md`** — arbol de widgets completo (orden real
   de construccion, objectNames, medidas literales del codigo) + tabla de medidas/proporciones
   + hallazgos de fidelidad (que bindings son reales vs. decorativos) + estados verificados
   contra el widget real.
2. **`docs/refactor/sales_pos_visual_contract.md`** — el contrato en si: jerarquia obligatoria,
   tabla "zonas que no pueden cambiar" (cada fila enlazada a su test), zonas que si pueden
   cambiar, y 4 hallazgos honestos documentados (no corregidos en esta fase).
3. **`tests/visual/golden/sales_pos/`** — 18 tests, todos verdes contra el widget real (no
   mockeado):
   - `test_pos_layout_matches_golden_master.py` (4 casos: carrito vacio / con items / cliente
     identificado / ambos combinados)
   - `test_pos_preserves_two_panel_layout.py`
   - `test_pos_cashier_bar_position.py`
   - `test_pos_catalog_panel_remains_left.py`
   - `test_pos_checkout_panel_remains_right.py`
   - `test_pos_customer_panel_position.py`
   - `test_pos_cart_position.py`
   - `test_pos_totals_position.py`
   - `test_pos_checkout_actions_position.py`
   - `test_pos_primary_charge_button_is_dominant.py`
   - `test_pos_shortcut_buttons_are_visible.py`
   - `test_pos_layout_at_1366x768.py`
   - `test_pos_layout_at_1920x1080.py`
   - `test_pos_dark_theme_layout.py`
   - `test_pos_light_theme_layout.py`
   - `conftest.py` (fixture compartido: `build_pos_widget`, `add_fake_cart_item`,
     `set_fake_customer`, `maybe_save_artifact`)

   PNG opcionales via `SALES_POS_VISUAL_ARTIFACTS=<dir>` (mismo mecanismo que
   `PURCHASING_VISUAL_ARTIFACTS`); no se commitean por defecto.

## Como se construyo el widget real headless

`ModuloVentas.__init__` ya degrada de forma segura cuando faltan servicios opcionales del
container (`getattr(container, name, None)` en cada punto), asi que el fixture usa un
`_FakeContainer` minimo (`db` + `sucursal_id`/`sucursal_nombre`, todo lo demas resuelve a
`None` via `__getattr__`) contra una base de datos SQLite bootstrapeada con
`scripts/bootstrap_db.py::bootstrap_database` (el mismo helper que ya usa
`tests/test_db_bootstrap.py`). No se necesito mockear ningun metodo de `ModuloVentas` — es
la clase real, sin parchear.

3 migraciones fallan de forma pre-existente contra una DB vacia (024 `venta_id`, 029
`movimientos_caja`, 080 `cierres_caja`) — no relacionado con esta fase, el bootstrap continua
y deja suficiente esquema para construir el widget; no se investigo mas a fondo por estar
fuera de alcance de POS-1 (fase de solo-documentacion/tests visuales).

## Hallazgos nuevos de esta fase (mas alla de lo que SALES-0 ya cubria)

Los 4 hallazgos de `sales_pos_visual_contract.md` §4 no estaban en SALES-0 (que audito logica
de negocio, SQL, hardware — no el detalle fino de bindings visuales):

1. **F6-F12 son decorativos** — no existe NINGUN `QShortcut`/manejo de tecla-F en todo el
   repositorio para estas 7 teclas. `keyPressEvent` de `ModuloVentas` solo atiende scanner
   HID/Enter/Tab.
2. **El tema claro/oscuro no esta cableado en produccion** — `GestorTemas` real de `config.py`
   no existe (el archivo no la define), el `ImportError` siempre cae al stub local
   (hardcodeado a "Oscuro", `aplicar_tema` es no-op). Busqueda repo-wide de
   `setStyleSheet(TEMAS` no encontro ningun punto de aplicacion real.
3. Confirmacion adicional (ya apuntada en SALES-0) de que el boton "Terminal" es cosmetico —
   ahora con las lineas exactas del re-proposito (`set_sucursal`/`on_branches_changed`).
4. El badge "● Abierto" es texto estatico, nunca reasignado tras `init_ui`.

Ninguno de estos 4 se corrigio — POS-1 es documentar y bloquear estructura, no reparar
funcionalidad. Quedan como items abiertos para una fase SALES-N posterior (probablemente
junto con el trabajo de permisos/hardware ya identificado en SALES-0).

## Que NO se hizo en esta fase (honesto, no fabricado)

- No se generaron capturas con render de fuentes reales (requiere una maquina con pantalla,
  Windows real) — las capturas headless muestran geometria correcta pero no tipografia fiel.
- No se cubrieron los estados "bascula activa" (lectura serial en vivo) ni "dialogo de pago
  abierto" — quedan pendientes, no fabricados como probados.
- No se corrigio ninguno de los 4 hallazgos de la seccion anterior — son observaciones, no
  cambios de codigo (POS-1 es una fase de solo lectura/tests, igual que SALES-0).

## Siguiente fase

`SALES-0_auditoria.md`/`sales_pos_enterprise_transformation.md` proponian SALES-2 (permisos
granulares) y SALES-3 (dominio) despues de esta fase — confirmar orden con el usuario antes de
continuar, no asumir.
