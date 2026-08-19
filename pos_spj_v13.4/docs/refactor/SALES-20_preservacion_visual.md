# SALES-20 — Preservación visual (POS-20 del master prompt)

Fecha: 2026-08-18
Fase anterior: `SALES-19_ui_decomposition.md`.

## Alcance ejecutado

Master prompt §67, fase POS-20: "Comparar golden master. Corregir proporciones. Validar 1366×768.
Validar 1920×1080. Validar claro/oscuro. Validar teclado. Validar scanner."

## Decisión de alcance: preservar visualmente QUÉ, dado que SALES-19 no tocó el legacy

SALES-19 construyó `frontend/desktop/modules/sales_pos/` como módulo nuevo y paralelo, **sin
tocar** `modulos/ventas.py` — decisión explícita del usuario ("Parallel new module, not wired
in"). Eso deja una pregunta abierta al llegar a "Preservación visual": ¿preservar visualmente qué,
si el árbol legacy no cambió?

Interpretación aplicada, coherente con el resto del pipeline: darle al módulo NUEVO el mismo rigor
de validación visual que `tests/visual/golden/sales_pos/` ya aplica al árbol LEGACY —
construcción real de widgets, offscreen, en ambas resoluciones objetivo, ambos temas, más
interacción real de teclado/scanner (no solo geometría estática). El árbol legacy no se toca; sus
18 pruebas golden-master se re-corren sin cambios como parte de la regresión de esta fase, igual
que en cada fase anterior.

## Entregables

### Corrección real de proporciones (bug encontrado, no hipotético)

`CheckoutPanel` no tenía restricciones de ancho — el `QSplitter` sin `setStretchFactor` divide
aproximadamente 50/50 entre los dos paneles. Medido empíricamente antes de la corrección: a
1920×1080 el panel de cobro quedaba en ~900-1000px de ancho. El contrato legacy documentado en
`docs/refactor/sales_pos_layout_inventory.md` §1 (`panel_derecho`) fija ese panel como una barra
lateral acotada: `minimumWidth=380`, `maximumWidth=600`.

Corrección aplicada:
- `components/checkout_panel.py`: `self.setMinimumWidth(380)` / `self.setMaximumWidth(600)` en
  `__init__`, reproduciendo el mismo contrato legacy.
- `sales_pos_workspace.py`: `self._splitter.setStretchFactor(0, 1)` (catálogo absorbe todo el
  ancho extra) / `setStretchFactor(1, 0)` (cobro permanece en su ancho propio).

Verificado empíricamente con un script desechable antes/después del fix: sin el fix, ancho de
cobro sin límites (minW=0, maxW=16777215) y split ~50/50; con el fix, ancho de cobro fijo en 600px
tanto a 1366×768 como a 1920×1080, y el catálogo absorbe todo el ancho extra (713→1267px).

### Validar 1366×768 / 1920×1080

`TestResolutionValidation` (nuevo, en `tests/unit/test_sales_pos_visual_validation.py`): construye
el workspace real a ambas resoluciones objetivo y verifica que el catálogo siempre recibe la
mayoría del ancho, que ningún panel colapsa a cero, y que el ancho del panel de cobro es
IDÉNTICO en ambas resoluciones (es una barra lateral acotada, no proporcional — no debe crecer
solo porque la ventana creció).

### Validar claro/oscuro

`TestThemeValidation`: construye el workspace real bajo cada tema de `config.TEMAS` ("Oscuro",
"Claro") y confirma que la estructura (un splitter, dos paneles) sobrevive el cambio de hoja de
estilo — el QSS nunca reparenta/remueve widgets, solo los reestiliza. Además, una prueba de
arquitectura nueva confirma que ningún componente de `sales_pos/` llama `.setStyleSheet(...)`
directamente — el look debe venir exclusivamente del QSS del tema, igual que exige el propio
docstring de `frontend/desktop/components/cards.py`.

### Validar teclado — funcionalidad real, no decorativa

A diferencia del panel legacy (confirmado en SALES-1: insignias F6-F12 puramente decorativas, sin
ningún `QShortcut` real detrás — `sales_pos_visual_contract.md` §4.1), este módulo nuevo no tiene
esa deuda heredada que preservar. Se agregaron `QShortcut` reales en `SalesPosWorkspace`, cada uno
disparando exactamente el mismo manejador que su botón correspondiente ya dispara (nunca una
segunda ruta de código divergente):

| Tecla | Acción |
|-------|--------|
| F6 | Suspender |
| F7 | Reanudar |
| F8 | Cancelar |
| F9 | Cobrar |
| F10 | Devolución |
| F11 | Factura |
| F12 | Reimpresión |

`TestKeyboardValidation` verifica los siete bindings registrados y que un evento real de tecla F9
(`QTest.keyClick`) dispara el mismo manejador que el botón Cobrar.

**Hallazgo real durante esta prueba** (no un bug de producción — un defecto de la prueba misma,
dos veces): (1) `QShortcut` solo se dispara si la ventana realmente tiene foco activo — las
plataformas Qt offscreen no lo otorgan automáticamente como sí lo hace un gestor de ventanas real;
corregido forzando `activateWindow()` / `QApplication.setActiveWindow()` / `setFocus()` /
`processEvents()` antes del `QTest.keyClick`. (2) La primera corrección de (1) volvió a re-llamar
`workspace._wire_shortcuts()` después de aplicar el `monkeypatch`, lo cual creó un SEGUNDO juego de
`QShortcut` con las mismas siete teclas — Qt mantiene vivos a los hijos parentados en C++
independientemente de las referencias de Python, así que el primer juego (sin parchear) seguía
activo. Dos `QShortcut` con la misma combinación hacen que Qt trate la tecla como AMBIGUA y no
dispare ninguno. Corregido parcheando `_on_checkout_requested` en la CLASE antes de construir el
workspace, para que `_wire_shortcuts()` (llamado una sola vez, dentro de `__init__`, igual que en
producción) capture directamente el método ya parcheado — sin re-cableo.

### Validar scanner

Un lector de código de barras es, eléctricamente, un tecleo muy rápido seguido de Enter —
distinguible de la navegación en vivo por texto. `CatalogPanel` gana una señal nueva
`code_scanned`, emitida por `_on_search_submitted` (conectada a `SearchInput.search_submitted`,
que dispara con Return — distinta de `search_changed`, que dispara con debounce mientras se
escribe). `SalesPosWorkspace._on_code_scanned` enruta esa señal a través de
`SalesPosPresenter.scan_code(sale_id, code, context="AUTO")` — el consumidor real, previamente sin
usar en ninguna capa de UI, de `ScanCodeRouter` (SALES-12). `context="AUTO"` replica el
comportamiento real del propio router: intenta primero un match de producto, y si falla recurre a
una tarjeta de lealtad/cliente. Un código no resuelto muestra el mensaje real de
`ScanCodeNotResolvedError`, nunca un no-op silencioso.

`TestScannerValidation` cubre: Enter en el buscador emite `code_scanned` (no filtra en vivo), un
código escaneado sin venta activa es un no-op seguro, y un código no resuelto muestra advertencia
en vez de fallar en silencio.

Adicionalmente se conectaron dos señales que SALES-19 había dejado sin usar:
`checkout.reprint_requested` → `_on_reprint_requested` (llama a
`SalesPosPresenter.reprint_receipt`, SALES-17) y `checkout.invoice_requested` →
`_on_invoice_requested` (llama a `SalesPosPresenter.request_invoice`, SALES-18).
`return_requested` se dejó deliberadamente sin conectar — una devolución real necesita un diálogo
completo de selección de línea/cantidad/motivo/autorizador, fuera del alcance de esta fase.

### Comparar golden master

No existe un "golden master" de este árbol nuevo contra el cual comparar píxel a píxel (SALES-19
no persiguió fidelidad de píxel exacta con el legacy — módulo paralelo, no descomposición en el
lugar). La comparación aplicada es estructural: el mismo invariante que
`test_pos_preserves_two_panel_layout.py` protege en el legacy (`TestGoldenMasterComparison`, exacto
un splitter de dos paneles) y el mismo número real (380-600px) que el inventario de layout legacy
documenta para el panel de cobro — no contra el árbol legacy en sí (widget distinto), sino contra
los mismos números reales que ese inventario documenta.

### Tests

Nuevo archivo `tests/unit/test_sales_pos_visual_validation.py`, 15 pruebas en 5 clases
(`TestGoldenMasterComparison`, `TestResolutionValidation`, `TestThemeValidation`,
`TestKeyboardValidation`, `TestScannerValidation`) — las 15 en verde.

Regresión completa re-corrida: `tests/unit/test_sales_*.py`, `tests/architecture/test_sales_*.py`,
`tests/visual/golden/sales_pos/` (18 pruebas golden-master legacy, sigue en verde — confirma que
`modulos/ventas.py` sigue exactamente intacto), `tests/test_ventas_devolucion_authorization_regression.py`,
`tests/test_fase5_stock_reservations.py` — **401 passed, 1 failed**. El único fallo es el mismo
conocido y preexistente de fases anteriores
(`test_ui_pasa_reserva_id_al_uc_antes_de_aplicar_resultado`, no relacionado con Ventas/POS ni con
esta fase).

## Lo que esta fase NO hizo (honesto, no fabricado)

- **No se tocó `modulos/ventas.py`** ni ningún archivo del árbol legacy — cero cambios, coherente
  con la decisión de alcance de SALES-19.
- **No se comparó píxel a píxel contra el árbol legacy** — es un widget distinto y paralelo; la
  validación es estructural y contra los mismos números reales que el inventario de layout legacy
  documenta, no una superposición de capturas de pantalla.
- **No se conectó `return_requested`** (F10 / botón Devolución) a un manejador real — necesita un
  diálogo completo de selección de línea/cantidad/motivo/autorizador que no existe aún en este
  árbol nuevo; queda pendiente para una fase futura o para cuando se decida conectar el módulo a
  `interfaz/main_window.py`.
- **No se conectó `frontend/desktop/modules/sales_pos/` a `interfaz/main_window.py`** — sigue sin
  cablear, igual que al cierre de SALES-19.
- **No se agregó soporte de hardware real de escáner** (driver/evento de sistema) — el manejo
  cubierto aquí es a nivel de aplicación (Enter tras tecleo rápido), que es como los lectores de
  código de barras USB en modo HID ya se comportan con cualquier campo de texto enfocado.

## Siguiente fase

El master prompt continúa con POS-21 (Offline) según la lista de fases §67 — no solicitada aún;
según la disciplina establecida en cada fase anterior, no se avanza sin que el usuario la nombre
explícitamente.
