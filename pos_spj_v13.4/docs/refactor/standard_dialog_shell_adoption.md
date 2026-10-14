# StandardDialog en los módulos del shell

Cierre: **13 de octubre de 2026**. Continuación del
[punto 9 — StandardDialog](standard_dialog_phase_9.md), ampliada por solicitud
del usuario a los módulos restantes del shell.

La auditoría de los 679 archivos Python de `frontend/desktop` no encuentra
herencia o construcción directa de `QDialog` fuera de su base canónica, ni
capturas mediante `QInputDialog`. Tampoco detecta layouts que sustituyan el
contenedor de las subclases directas de `StandardDialog`/`FormDialog`.
Los 17 módulos registrados en el shell están incluidos en esa auditoría.

**398 pruebas distintas aprobadas, 2 fallos globales preexistentes,
0 errores finales y 0 omitidas.** Hay **123 capturas** de esta continuación.
El conteo consolida cada caso por su última ejecución y no suma repeticiones.

## Adopción realizada

| Alcance | Clases migradas | Archivos |
|---|---:|---:|
| Productos: formularios, variantes, atributos, combos, recetas, cortes y rendimientos | 22 | 14 |
| Inventario: zonas, detalle de movimiento, lote e historial de peso | 4 | 1 |
| POS: descuento, cobro y alta rápida de cliente | 3 | 3 |
| Finanzas/Proveedores: perfiles contables, asientos, base de formularios y ficha | 4 | 4 |
| **Total en módulos** | **33** | **22** |

La base de proveedores alcanza ocho formularios derivados; junto con los tres
diálogos restantes, la prueba de Finanzas cubre 11 variantes concretas.
`NumericKeypadDialog`, compartido por la captura de cantidades e importes,
también hereda `StandardDialog`. Conserva `get_value`, `valor`, rango, precisión,
entrada física, aceptación de cero y el contrato de `QuantityInputDialog`.

Se sustituyeron además **10 llamadas de captura en ocho páginas** por
`FormDialog.get_text()` / `get_item()`: surtidos/canales de Productos, cancelación
de factura en Compras, baja de empleado, inspección de calidad, planificación de
producción, conciliación bancaria, resumen de cliente y rechazo de campaña.
Los helpers devuelven `(texto, aceptado)`, conservan la validación en el llamador
y liberan el diálogo después de obtener su resultado.

Los módulos que ya usaban componentes canónicos mantienen su ruta. Los
selectores nativos de archivos y los avisos `QMessageBox` conservan sus APIs Qt;
el guardrail distingue esas APIs de los diálogos personalizados y de captura.

## Estructura y comportamiento

- El contenido utiliza `content_layout()` o `self.form`, dentro de `PageViewport`.
  Título, icono oficial y límites del monitor pertenecen a la base canónica.
- `add_footer_widget(widget)` permite adoptar una botonera existente sin
  reconectar sus señales. Mantiene acciones fuera del scroll, aplica densidad y
  conserva foco/default y nombres accesibles personalizados.
- Guardar, aceptar, cerrar y cancelar mantienen sus resultados y callbacks.
  La validación fallida conserva captura y diálogo abierto; el cobro conserva
  su orden de operaciones y evita duplicar pagos al reintentar.
- El detalle de lote distribuye sus cinco acciones en dos filas. En Cobrar,
  método, importe, referencia y Agregar pago se distribuyen en una cuadrícula
  de dos filas, con ancho preferido de 640 px. La revisión visual detectó y
  corrigió que el ancho predeterminado dejaba Agregar pago fuera del área visible.
- El teclado numérico mantiene sus botones de aceptar/cancelar visibles al
  desplegar, ocultar o desplazar el teclado.

Los métodos operativos fuera de los constructores de Productos, Inventario,
POS y las cuatro bases de Finanzas se comprobaron por AST. En Inventario/POS,
los 19 métodos de las siete clases migradas permanecen idénticos; la comparación
de los cuatro archivos completos conserva 96 métodos. En Finanzas/Proveedores
se comprobaron 46 métodos. Las páginas de capturas breves conservan argumentos,
normalización, UUID, condiciones de cancelación y llamadas al presentador.

No se modificaron reglas de negocio, servicios, persistencia ni schema como
parte de esta entrega. El árbol contiene cambios concurrentes de otros trabajos;
los diffs completos de algunas páginas incluyen esas modificaciones previas.

## Pruebas y evidencia

| Segmento, sin duplicar casos | Passed | Failed |
|---|---:|---:|
| Base, pie, teclado numérico, geometría, matriz visual y componentes responsive | 100 | 0 |
| Contratos previos de captura numérica y controlador del teclado virtual | 8 | 0 |
| Finanzas/Proveedores | 64 | 0 |
| Productos | 60 | 0 |
| Inventario/POS y regresión adicional | 78 | 0 |
| Helpers de captura, páginas y prueba de integración de calidad | 34 | 0 |
| Propiedad del diálogo y detección de aliases/layouts | 28 | 0 |
| Guardrails visuales generales | 26 | 2 |
| **Total distinto consolidado** | **398** | **2** |

La regresión adicional de operaciones contiene tres casos Escape ya incluidos
en los 72 de adopción. Después de corregir visualmente Cobrar se repitieron los
12 casos afectados, todos aprobados; los otros 60 conservaban la misma fuente.

Las protecciones se ejecutaron antes de las migraciones. La falta de adopción
produjo inicialmente 28 fallos en Productos, 33 en Finanzas, 7 en operaciones y
6 en geometría del teclado numérico. La prueba de la API de pie falló en sus
nueve casos antes de incorporarla. Las 26 pruebas de los prompts de páginas
pasaban también con el proveedor anterior, protegiendo el comportamiento.

Una ejecución conjunta inicial no resolvió `qt_font_resources`/`ui_tmp_path` en
53 casos. Al ejecutar el segmento UI con sus fixtures, los 100 casos pasaron.
Esos errores iniciales se conservan en la evidencia y quedan reemplazados por
las ejecuciones posteriores en el conteo final. También se corrigió el doble
de configuración de Productos para que `settings.defaults()` devolviera un
diccionario, conforme a la API existente.

- [Resultados por ejecución, casos, hashes y auditoría](evidence/standard_dialog_phase_9/shell_adoption_20261010/validation.json).
- [Galería de 123 capturas](evidence/standard_dialog_phase_9/shell_adoption_20261010/index.html).
- [Preservación de métodos de Inventario/POS](evidence/standard_dialog_phase_9/shell_adoption_20261010/shell-dialog-operations-preservation.json).

Las capturas se reparten en 30 de la base (cinco resoluciones, ambos temas y
tres densidades), 33 de Finanzas, 42 de Inventario/POS, 12 del teclado numérico
desplegado/colapsado y 6 de Productos. Las suites de formularios ejercitan
captura, último campo accesible, scroll, pie, cambio de densidad y cancelación.
Se inspeccionaron muestras, incluidas las versiones corregidas de Cobrar.

Qt se ejecutó en modo offscreen con fuentes reales y áreas disponibles
simuladas, incluidas pantallas de 640×480. Estas capturas no certifican arrastre
nativo entre monitores con distinto DPI ni interacción con hardware físico;
esa comprobación permanece como validación manual en equipo real.

## Auditoría y fallos globales existentes

La deuda visual medida baja de **136 a 103 hallazgos**: desaparecen las 33
declaraciones de diálogos no canónicos. Se retiran exactamente **32 entradas**
resueltas de la allowlist; `PurchaseUnitsDialog` era el hallazgo restante fuera
de ella. No hay hallazgos nuevos frente a la instantánea inicial ni se amplió
la allowlist.

Persisten dos fallos del guardrail general:

1. Doce hallazgos previos fuera de la allowlist: nueve páginas CRM sin política
   explícita de overflow, una tabla de sugerencias de Producción y las páginas
   de configuración de Producción y Pricing.
2. Entradas obsoletas de otros alcances, incluida la referencia a
   `customers_crm/pages/_directory_base.py`, ya eliminada antes de esta entrega.

Los XML registran estos fallos. La suite completa del repositorio no se declara
verde. El nuevo guardrail específico de diálogos sí aprueba sus 28 casos y
prohíbe reintroducir `QDialog` o `QInputDialog` mediante imports o aliases.

## Archivos y reproducción

Producción: `components/dialogs.py`, `components/numeric_keypad_dialog.py`,
los 22 archivos de módulos enumerados en el manifiesto y las ocho páginas de
captura. Los cuatro archivos de Finanzas y la API de pie ya estaban incorporados
en `cebf67a7` durante esta continuación; el informe conserva su validación.

Pruebas nuevas: `test_standard_dialog_footer.py`,
`test_numeric_keypad_standard_dialog.py`, `test_finance_remaining_standard_dialogs.py`,
`test_products_standard_dialog_adoption.py`, `test_operations_standard_dialogs.py`,
`test_standard_dialog_prompts.py`, `test_shell_prompt_adoption.py` y
`test_standard_dialog_ownership.py`. La prueba de integración de calidad ahora
parchea el proveedor canónico, conservando sus expectativas.

Actualizados la allowlist, la guía de adopción y el enlace del informe inicial.
Creado este informe y su evidencia. **Archivos eliminados por esta fase: ninguno.**
Las fuentes Python del alcance compilan y los hashes verifican los archivos
recogidos en el manifiesto.

Desde el paquete interno:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
..\.venv\Scripts\python.exe -m pytest tests/ui/test_standard_dialog_footer.py tests/ui/test_numeric_keypad_standard_dialog.py tests/ui/test_standard_dialog_geometry.py tests/ui/test_standard_dialog_visuals.py tests/ui/test_responsive_components.py -q -p no:cacheprovider
..\.venv\Scripts\python.exe -m pytest tests/ui/test_products_standard_dialog_adoption.py tests/ui/test_finance_remaining_standard_dialogs.py tests/ui/test_operations_standard_dialogs.py tests/ui/test_standard_dialog_prompts.py tests/ui/test_shell_prompt_adoption.py -q -p no:cacheprovider
..\.venv\Scripts\python.exe -m pytest tests/architecture/test_standard_dialog_ownership.py -q -p no:cacheprovider
..\.venv\Scripts\python.exe -m pytest tests/architecture/test_design_system_guardrails.py -q -p no:cacheprovider
```

El último comando reproduce los dos fallos generales documentados. Para guardar
capturas, usar `SPJ_DIALOG_VISUAL_ARTIFACTS`; la matriz de Productos utiliza
`SPJ_SHELL_DIALOG_ARTIFACTS`. No iniciar otra fase antes de cerrar este alcance.
El siguiente punto del orden original es **10. PageViewport**.
