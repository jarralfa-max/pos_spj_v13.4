# Punto 4 — QSS global

Fecha: 2026-09-21. Estado: **correcciones implementadas y verificadas**.
Alcance: apariencia nativa compartida y su validación.
La corrección previa de iconos de 17 sidebars está documentada por separado en
[module_sidebar_icons_fix.md](module_sidebar_icons_fix.md).

## Arquitectura y correcciones

Se mantiene una sola cadena: `tokens → colores semánticos → tema → build_qss →
QApplication → widgets`. El inventario AST encuentra un único escritor de QSS
y paleta, `ThemeManager.apply()`, y un único `build_qss`. El guardrail nuevo
incluye los módulos de temas: no exime toda esa carpeta. Distingue código
ejecutable de ejemplos en documentación y de HTML/JavaScript embebidos.
No se introdujeron hojas `.qss` paralelas ni estilos locales en widgets.
CSS corresponde a vistas web, gráficos y reportes HTML.

Se corrigieron defectos observados en controles Qt reales:

- `#standardCard` ocultaba las superficies semánticas de `info`, `alert`,
  `danger` y, en Oscuro, `summary`. Los selectores de variante ahora prevalecen
  sobre la tarjeta base, conservando el contrato genérico `cardVariant`.
- Error, advertencia y solo lectura podían sobreescribir la apariencia de un
  campo deshabilitado. Esos selectores ahora se limitan a controles habilitados.
  La validación sigue presente y vuelve a verse al habilitar el campo.
- `set_theme()`, `set_density()` y `toggle()` sin argumento `app` podían
  cambiar iconos/observadores sin aplicar el nuevo QSS. Ahora resuelven la
  `QApplication` existente y actualizan propiedades, paleta y QSS antes de las
  señales. Antes del arranque GUI se mantiene el almacenamiento del estado,
  sin crear una aplicación implícita.
- Las flechas de `QSpinBox`/`QDoubleSpinBox` desaparecían al combinar borde y
  padding personalizados. Sus subcontroles se dibujan ahora con geometría QSS
  y colores semánticos, sin archivos de imagen ni estilos locales. Se mantiene
  el editor separado de los botones; se verifican forma direccional, contraste,
  incremento/decremento, límites, solo lectura y deshabilitado en tres densidades.
  Los subcontroles de fecha/hora y el desplegable de calendario se conservan.

## Protección y resultados

**504 PASSED distintos, 1 FAILED, 0 ERRORS, 0 SKIPPED**. El único fallo es el
guardrail de overflow de las dos páginas ajenas descritas abajo. Los segmentos
se deduplican por nombre de caso en el manifiesto. Compilación de los archivos
afectados y `git diff --check` del alcance terminan sin errores.

Los nuevos casos de tarjetas, estados y observadores reprodujeron **22 fallos
y 7 aprobados antes del cambio**. Tras la corrección pasan los 29 casos.
Las flechas numéricas reprodujeron 24 fallos antes del cambio; sus 24 casos
pasan con la solución final y la comprobación de dirección del indicador.
Los resultados finales por segmento, nombres de casos y hashes se conservan
en el [manifiesto de validación](evidence/qss_global_phase_4/validation.json),
junto a XML JUnit y logs. La validación incluye unitarias e integración de
Apariencia, render Qt, iconos, shell, contraste, densidad y geometría responsive.

Existe **un fallo previo** en
`test_design_system_guardrails.py::test_desktop_visual_debt_does_not_grow`:
`frontend/desktop/modules/pricing/pages/settings_page.py:33` no declara una
frontera de overflow. Se reprodujo antes de editar el QSS, en
`qss-existing-before.xml`. No se atribuye a esta fase ni se oculta ampliando
el baseline. Al retomar el 21 de septiembre también aparece el mismo tipo de
infracción en `meat_processing/pages/meat_processing_settings_page.py:20`,
archivo ajeno a esta fase. El test global falla por ambas rutas. Los cambios
funcionales ajenos en el árbol de trabajo se conservaron.

El inventario final mide 622 archivos Python, 161 ocurrencias:
35 diálogos directos, 112 contratos de overflow y 14 literales Unicode por
revisar. Hay 159 ocurrencias permitidas por el baseline y las dos infracciones
descritas arriba fuera de él; 0 huellas obsoletas y 0 infracciones
introducidas por este trabajo. No equivale a una suite global verde ni a
haber terminado la adopción de todos los módulos.

## Evidencia visual

[Visor de 220 capturas Qt](evidence/qss_global_phase_4/index.html):
Claro/Oscuro × Cómoda/Táctil × 1280×720, 1366×768, 1440×900, 1600×900 y
1920×1080. Incluye shell, login, navegación, flyouts, teclado, formularios y
galería, además de 20 capturas de tarjetas y estados de captura.

Las pruebas verifican píxeles semánticos y geometría. Se inspeccionaron las
vistas Claro/Oscuro táctiles a 1280×720, con fuentes reales de Windows.
`QComboBox` no ofrece un estado de solo lectura nativo: esas celdas de la
galería se identifican como «No aplica».

Las capturas no son referencias visuales aprobadas ni prueban hardware real.
Los cuerpos de demostración no ejecutan operaciones de negocio. Las escenas
de login y shell incorporan los originales de marca entregados al retomar el
punto 6; queda pendiente la revisión operativa de cada ruta.

## Archivos de la fase

Modificados: `frontend/desktop/themes/qss_builder.py`,
`frontend/desktop/themes/theme_manager.py`, las guías de adopción y visuales,
y `docs/refactor/global_ui_ux_design_system_audit.md`.

Creados: `tests/ui/test_global_qss_runtime.py`,
`tests/ui/test_global_qss_visuals.py`,
`tests/ui/test_spin_controls_rendering.py`,
`tests/architecture/test_global_qss_ownership.py`, este informe y su evidencia.
Ningún archivo eliminado. No se modificaron lógica de negocio, SQL, schema,
identidades ni datos.

Para reproducir desde el paquete interno, con la venv de la raíz externa:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
..\.venv\Scripts\python.exe -m pytest tests/ui/test_global_qss_runtime.py tests/architecture/test_global_qss_ownership.py -q -p no:cacheprovider
$env:SPJ_UI_VISUAL_ARTIFACTS = Join-Path (Get-Location) 'docs/refactor/evidence/qss_global_phase_4'
..\.venv\Scripts\python.exe -m pytest tests/ui/test_design_system_visual_matrix.py tests/ui/test_design_system_navigation_visuals.py tests/ui/test_global_qss_visuals.py -q -p no:cacheprovider
```

El usuario eligió continuar con [6. BrandAssetProvider](brand_asset_provider_phase_6.md).
