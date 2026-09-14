# Punto 3 — Light / Dark

Estado: **IMPLEMENTADO; validación automática completada**. La aceptación en
hardware operativo y el render WebEngine permanecen pendientes al final del informe.

Alcance: selección y persistencia del tema de terminal, actualización de vistas
abiertas y contraste de los controles compartidos. Fecha: 2026-09-12.

## Comportamiento implementado

**Configuración → Apariencia → Apariencia de esta terminal** permite elegir
**Claro** u **Oscuro**. El cambio se aplica al momento sobre los mismos widgets,
conserva los datos en captura y se restaura antes del siguiente login.
La preferencia usa `QSettings` de la cuenta de Windows en la terminal.

`ThemeManager` normaliza la preferencia a los dos temas oficiales. Un valor
desconocido vuelve a Claro. Aplica propiedades de aplicación, paleta y QSS antes
de emitir señales; los observadores reciben un estado coherente incluso cuando
cambian tema y densidad juntos. Restaurar preferencias actualiza también los
iconos ya construidos. Reaplicar el mismo tema no duplica la notificación.

El selector sigue los cambios externos sin emitir otro cambio recursivo.
El catálogo administrativo de temas y las preferencias por alcance conservan
su ruta de aplicación; elegir el tema de terminal no crea ni modifica registros
de ese catálogo.

`HtmlChartView` conserva el último DTO y vuelve a generar el HTML cuando cambia
el tema. No vuelve a consultar datos. Los estados de carga, error, sin conexión
y vacío se conservan; la tabla nativa mantiene su selección.

## Contraste y paleta

Las seis anclas aprobadas en el [punto 2](juanis_palette_phase_2.md) se conservan.
Esta fase ajusta su aplicación semántica:

- El texto de ayuda de 11 px en Claro cumple 4.5:1 sobre las superficies probadas.
- `INPUT_BORDER` usa el borde fuerte en ambos temas para identificar los campos
  con al menos 3:1 respecto al interior y al fondo comprobados.
- El foco del botón primario en Claro usa dorado derivado, visible contra
  su relleno verde y contra el entorno, también en hover y pressed.
- Se retiró la regla parcial de `QComboBox::drop-down` que ocultaba su flecha.
  El indicador nativo vuelve a mostrarse en ambos temas y las tres densidades,
  conservando apertura por clic y selección por teclado.

Las pruebas examinan ratios y píxeles de controles Qt reales. No constituyen
una certificación de accesibilidad de todos los módulos.

## Archivos de esta fase

Modificados:

- `frontend/desktop/themes/theme_manager.py`
- `frontend/desktop/themes/semantic_colors.py`
- `frontend/desktop/themes/qss_builder.py`
- `frontend/desktop/components/chart_view.py`
- `frontend/desktop/modules/configuracion/pages/apariencia_page.py`
- `frontend/desktop/design_system/visual_guidelines.md`
- `tests/architecture/test_theme_contrast.py`
- `tests/ui/test_charts.py`
- `docs/refactor/global_ui_ux_design_system_audit.md`

Creados:

- `tests/ui/test_theme_manager_runtime.py`
- `tests/ui/test_theme_contrast_rendering.py`
- `tests/ui/test_combo_dropdown_rendering.py`
- `tests/ui/test_appearance_theme_visuals.py`
- Este informe y la evidencia en `docs/refactor/evidence/light_dark_phase_3/`.

Archivos eliminados por esta fase: ninguno. No se modificaron lógica de negocio,
identidades, esquema, SQL ni servicios de aplicación.

## Validación

**333 PASSED distintos, 0 FAILED, 0 ERRORS, 0 SKIPPED** en los segmentos de esta fase.

| Segmento | Aprobados |
|---|---:|
| Runtime, iconos/densidad, componentes, gráficos y páginas de Configuración | 145 |
| Contraste semántico y render Qt | 65 |
| Integración de Apariencia y protecciones de arquitectura | 67 |
| Matriz visual definitiva | 50 |
| Desplegable y revalidación de runtime/densidad (22 casos solapados) | 28 |

El total elimina esos 22 solapamientos. El auditor mide **0 infracciones nuevas**,
**0 huellas obsoletas** y **159 ocurrencias preexistentes**. `compileall` del
frontend y `git diff --check` también finalizaron sin errores.

Los resultados definitivos y nombres de cada caso están en el
[manifiesto de validación](evidence/light_dark_phase_3/validation.json).
Las regresiones de notificación/restauración se reprodujeron antes de corregirse:
6 fallos y 1 aprobado en el nuevo segmento de runtime. Después pasan sus 7 casos.
La prueba nueva de gráficos también reprodujo el HTML que no cambiaba de tema.

Se probaron el flujo de Apariencia con servicios y SQLite en memoria, sus
repositorios y casos de uso, las restricciones de SQL/transacciones en frontend,
las protecciones del Design System y los controles de tema/densidad.

[Visor de 220 capturas Qt](evidence/light_dark_phase_3/index.html): cinco
resoluciones (1280×720, 1366×768, 1440×900, 1600×900, 1920×1080), Claro/Oscuro y
Cómoda/Táctil. Incluye las diez escenas anteriores y el selector productivo de
Apariencia dentro del shell, con datos de ejemplo. El cambio Claro → Oscuro se
ejecuta sobre la misma página, comprobando que el selector queda visible y el
texto capturado se conserva. Las capturas de la fase anterior se conservan en
su directorio original.

Se inspeccionaron Apariencia en Claro/Oscuro a 1280×720 Táctil y el formulario
en Oscuro/Cómoda con acción fija visible. No hay comparación automática de
píxeles contra una referencia visual aprobada. WebEngine/ECharts no está
disponible en este entorno: el refresco HTML se comprueba con el template y el
bridge reales usando un receptor de HTML de prueba; la tabla nativa sí usa Qt.

Las suites completas tienen fallos preexistentes documentados en la
[auditoría general](global_ui_ux_design_system_audit.md). Esta validación por
segmentos no declara verde la suite global ni cerrada toda la estandarización.

## Aceptación en terminal

- [x] Dos temas oficiales, selector sincronizado y persistencia comprobada con INI aislado.
- [x] Cambio sobre widgets existentes, conservación de datos y densidad.
- [x] Contraste probado en campos, ayuda y foco primario de Claro.
- [x] Matriz de geometría e interacción en las resoluciones solicitadas.
- [ ] Revisión humana en el equipo operativo con su DPI y pantalla táctil.
- [ ] Render de gráficos con QtWebEngine y el recurso ECharts instalado.

Siguiente punto del orden solicitado: **4. QSS global**.
