# Auditoría global UI/UX de SPJ ERP/POS

Actualizada: **2026-09-12**. Estado: **IN_PROGRESS**. La infraestructura canónica existe; la adopción de todos los módulos y la aceptación visual completa siguen pendientes.

Esta medición sustituye el inventario inicial del 2026-07-17, que describía como ausentes componentes ya construidos. No se puede deducir la finalización global de que el catálogo importe correctamente o de que sus ejemplos se puedan construir.

## Alcance y evidencia

Se analizaron **601 archivos Python** del árbol de trabajo actual en `frontend/desktop/`, `modulos/` y `ui/` mediante AST. Los directorios ausentes aportan cero archivos. El inventario de módulos comprende **424 archivos en 18 módulos**, incluidos presentadores, modelos y `__init__.py`; estos números no representan una cantidad de pantallas.

- Analizador reproducible: [`tests/architecture/design_system_audit.py`](../../tests/architecture/design_system_audit.py).
- Resultado medido: [`evidence/ui_design_system_audit_20260912.json`](evidence/ui_design_system_audit_20260912.json).
- Infracciones concretas, con archivo, línea orientativa, expresión y huella: [`design_system_debt_baseline.json`](../../tests/architecture/design_system_debt_baseline.json).
- Protecciones ejecutables: [`test_design_system_guardrails.py`](../../tests/architecture/test_design_system_guardrails.py).

Entre el inventario del 10 y el del 11 de septiembre se encontraron eliminaciones ajenas a este trabajo en `ui/`, `notifications/` y `repositories/`. Se preservaron. La desaparición de deuda de esos archivos se refleja en la medición actual, pero **no se atribuye a la implementación del Design System ni demuestra que su eliminación sea segura**.

## Deuda vigente medida

| Regla AST | Ocurrencias | Archivos | Interpretación |
|---|---:|---:|---|
| `setStyleSheet` fuera de temas | 0 | 0 | La infraestructura canónica de temas es la excepción autorizada. |
| Hex visual fuera de temas/charts | 0 | 0 | Hay una excepción de contenido impreso descrita abajo. |
| `QTableWidget` fuera de componentes canónicos | 0 | 0 | Incluye construcción, herencia e imports con alias. |
| `KPICard` / `PageHeader` local | 0 | 0 | Busca definiciones de clase que duplican el contrato. |
| Subclase visual local de `QPushButton` / `QLineEdit` | 0 | 0 | Detecta estilos, fuente, paleta y `paintEvent` propios. |
| Controles con tamaño fijo literal menor a 48 px | 0 | 0 | Solo restricciones demostrables sobre controles reconocidos. |
| Diálogo con geometría literal mayor a 1280 × 720 | 0 | 0 | No sustituye comprobar la geometría real en Qt. |
| `QDialog` construido/heredado directamente | **35** | **24** | Pendiente adoptar la política de `StandardDialog`. |
| Pantalla sin composición explícita de overflow | **110** | **109** | Requiere contrato de página/viewport o composición con un host reconocido. |
| Literales Unicode potencialmente usados como iconos | **14** | **7** | Pendiente revisión y sustitución visual por `IconProvider`. |

Las 159 ocurrencias restantes están identificadas individualmente. No son 159 fallos nuevos: forman la deuda preexistente bajo control. Las infracciones nuevas medidas al cerrar esta auditoría son **0**.

La regla de overflow identifica clases `QWidget`/`QMainWindow` con nombres `Page`, `Window`, `Workspace`, `View`, `Screen`, o ubicadas en archivos de páginas/vistas. Reconoce `PageViewport`, `ContentHost`, `QScrollArea` y contratos de página/ventana canónicos. No resuelve toda la herencia entre archivos ni demuestra recorte real: una página puede recibir scroll de su padre. Cada hallazgo exige revisar y expresar ese contrato, no añadir scroll anidado indiscriminadamente.

La geometría estática no prueba alcance de acciones, mínimos calculados dinámicamente, disponibilidad del monitor, barras del sistema ni interacción táctil. El análisis Unicode omite comentarios/docstrings, pero sus hallazgos requieren distinguir iconografía visible de contenido funcional.

### Excepción precisa de contenido

El `#FFFFFF` de `_EXAMPLE_SCHEMA` en `tarjetas_fidelidad/pages/templates_page.py` describe el fondo físico de una tarjeta impresa, dentro de un `canvas` con dimensiones en milímetros serializado por `json.dumps`. No debe cambiar con el tema de la aplicación.

La excepción está restringida al archivo, asignación, clave `background_color`, valor blanco y estructura física del canvas. Las pruebas demuestran que otro literal en el mismo archivo, otro color o la misma expresión en un módulo distinto siguen siendo detectados. Los hex de HTML/charts se permiten en su infraestructura de contenido web; un `setStyleSheet` en esa infraestructura continúa prohibido.

## Adopción por módulo

La tabla cuenta **archivos con evidencia sintáctica**, no widgets visibles ni cobertura funcional. Un módulo puede heredar indirectamente componentes y no aparecer en una columna; importar componentes tampoco acredita cumplimiento completo. “Contrato estructural” comprende páginas, ventanas, diálogos canónicos y `PageViewport`.

| Módulo | Python | Importan componentes canónicos | Contrato estructural | Referencian `StandardTable` |
|---|---:|---:|---:|---:|
| assets | 13 | 6 | 0 | 2 |
| business_intelligence | 25 | 14 | 0 | 3 |
| cash_register | 23 | 16 | 2 | 13 |
| configuracion | 38 | 26 | 0 | 11 |
| customers_crm | 19 | 11 | 0 | 3 |
| fidelidad | 15 | 7 | 0 | 4 |
| finance | 50 | 30 | 1 | 6 |
| hr | 20 | 10 | 1 | 0 |
| inventory | 34 | 26 | 0 | 22 |
| losses | 19 | 9 | 1 | 1 |
| meat_processing | 15 | 4 | 0 | 1 |
| orders_delivery | 19 | 7 | 1 | 0 |
| pricing | 13 | 6 | 1 | 4 |
| products | 31 | 19 | 0 | 16 |
| purchasing | 27 | 14 | 1 | 8 |
| sales_pos | 21 | 9 | 0 | 1 |
| tarjetas_fidelidad | 12 | 3 | 0 | 0 |
| transfers | 30 | 5 | 0 | 1 |
| **Total** | **424** | **222** | **8** | **96** |

Los diálogos directos se concentran en Productos, Inventario, Finanzas, RRHH y POS. Los literales Unicode restantes aparecen en Configuración, Productos, Compras y POS. El baseline permite localizar cada caso sin eximir el resto del archivo.

## Infraestructura observada

Ya existen `themes/brand_palette.py`, `semantic_colors.py`, `tokens.py`, `qss_builder.py` y `theme_manager.py`; la paleta solicitada JUANIS y los temas deben mantenerse ahí. No corresponde crear otra fuente visual en los módulos.

También existen el catálogo/galería en `design_system/`, `components/branding.py`, `components/icons.py`, `components/standard_window.py`, `components/page_viewport.py`, `components/dialogs.py`, `components/virtual_keyboard.py`, `auth/login_window.py` y la composición de ventana, top bar, notificaciones y estado en `shell/application_shell/`.

Esta existencia se registra como infraestructura disponible. La validación de branding oficial, persistencia, colapso de navegación, tamaños, interacción, sesión y estados corresponde a las pruebas específicas del shell/componentes y a su revisión visual; la auditoría AST no aprueba esas capacidades por presencia de archivo.

## Guardrails y control de deuda

El baseline anterior de siete pruebas cubría colores de una paleta histórica, estilos de componentes y librerías de gráficas. Ahora usa la paleta solicitada y añade AST para las infracciones indicadas, con casos negativos y positivos.

La deuda se identifica mediante **ruta + regla + huella SHA-256 del AST normalizado + multiplicidad**. Añadir una segunda copia de la misma infracción, cambiar la expresión o introducirla en otro archivo produce una regresión. No se excluye ningún módulo o archivo completo por tener deuda previa.

Una prueba exige eliminar del baseline las entradas resueltas y rechaza duplicados, comodines, rutas ausentes y contadores inválidos. La ampliación del detector a vistas y ubicaciones de páginas añadió 15 hallazgos cuya existencia se verificó contra `HEAD`; no se admitieron regresiones nuevas al actualizar la cobertura. No se ofrece una opción para regenerar automáticamente el baseline y aceptar todo.

## Validación ejecutada y reproducción

El segmento ampliado de arquitectura visual, contraste, composición de ventana, apariencia, Precios y Rendimientos termina con **184 PASSED, 0 FAILED, 0 SKIPPED**. Incluye los 28 guardrails. Los resultados de las suites completas se detallan abajo; no están en verde.

Desde la raíz externa, PowerShell:

```powershell
& '.venv/Scripts/python.exe' -m pytest pos_spj_v13.4/tests/architecture/test_design_system_guardrails.py -q -p no:cacheprovider
& '.venv/Scripts/python.exe' pos_spj_v13.4/tests/architecture/design_system_audit.py
& '.venv/Scripts/python.exe' pos_spj_v13.4/tests/architecture/design_system_audit.py --json
& '.venv/Scripts/python.exe' pos_spj_v13.4/tests/architecture/design_system_audit.py --output pos_spj_v13.4/docs/refactor/evidence/ui_design_system_audit_20260912.json
```

El workflow `.github/workflows/ci-segmented.yml` ejecuta `tests/architecture`, `tests/unit`, `tests/integration` y una validación visual explícita de Compras. También referencia `scripts/ci/run_domain_tests.sh`, que no existe en el árbol inspeccionado. Para reproducir esta auditoría se debe usar el comando Python directo; esa referencia CI necesita corrección fuera de los cambios de este informe.

Se recomienda mantener los guardrails dentro del segmento de arquitectura y ejecutar los tests UI del registro, temas, shell, diálogos, viewport y teclado junto a las pruebas visuales de cada módulo migrado. El informe del trabajo del shell/componentes debe registrar sus resultados reales por separado.

## Pendientes para cierre global

1. Adoptar diálogos canónicos y contratos explícitos de overflow en las pantallas registradas, preservando captura, validaciones y señales. Disminuir el baseline después de cada migración protegida.
2. Sustituir los 14 literales Unicode identificados cuando funcionen como iconos; conservar semántica, texto accesible y estados.
3. Validar el mismo conjunto de componentes en Claro/Oscuro, Comfortable/Touch y **1280 × 720, 1366 × 768, 1440 × 900, 1600 × 900 y 1920 × 1080**.
4. Conservar evidencia de ventana principal/login, ambos estados de sidebar, grupos/flyouts/tabs, usuario/sesión, Archivo, notificaciones, Configuración, logout, tablas, formularios, dashboards, diálogos y teclado. Cubrir uso de teclado físico, escáner y operación táctil.
5. Comprobar acciones accesibles, scroll, contraste, foco visible y persistencia en las rutas reales con permisos aplicados. Una galería construida no acredita estas rutas.

No se declara ningún módulo migrado al 100 % mediante esta medición. No se modificaron reglas de negocio ni se eliminaron archivos de producto en el trabajo de auditoría y guardrails.

## Resultado de la fase de infraestructura visual — 12 septiembre 2026

La fase deja componentes canónicos integrados en el shell y evidencia ejecutable.
El cierre global sigue **IN_PROGRESS**: no se atribuye cumplimiento total a los
18 módulos. Referencia de trabajo: rama `claude/erp-financial-bounded-context-uqxz6b`,
HEAD `a12b70b09d1305fcd3029b7259c9f4dd8561c067` con cambios locales.

### Cambios y defectos corregidos

- Paleta oficial de seis colores, QSS central, Claro/Oscuro y perfiles Compacta,
  Cómoda y Táctil; restauración antes de login y actualización de controles vivos.
- SVG/QIcon real en controles, iconos que siguen el tema, catálogo ampliado y
  galería de componentes. El teclado ya no presenta el icono de archivo por
  confundir la propiedad nativa `QAction.icon` con un identificador semántico.
- Shell con Archivo, Configuración, usuario/sucursal, estado, notificaciones y
  cierre de sesión mediante revocación existente y reconstrucción tras login.
  Configuración reutiliza `PermissionEvaluator`, incluidos comodines, y maneja
  denegaciones del router desde el slot Qt.
- Sidebar global 240/64, ruta persistida y toggle; sidebar de módulo con grupos,
  flyouts y persistencia. Los permisos continúan siendo responsabilidad de la
  composición y del router/backend.
- Layouts de página, viewport y diálogos con límites de monitor. El host usa el
  mínimo de la página activa y evita que una página cacheada o el tamaño sugerido
  de un scroll interno fuerce desplazamiento exterior innecesario.
- Tabla con columnas declarativas, visibilidad/ancho persistentes, ordenación
  Decimal y UUID conservado durante recargas ordenadas. KPIs conservan sus widgets
  al redistribuirse y los combos muestran completa la selección.
- Teclado virtual con validación, selección, mayúsculas, espacio y controles de
  hardware; conserva 52 px de altura también después del polish QSS. Su ancho se
  ajusta a la cuadrícula para mostrar todas las teclas en la matriz solicitada.
- Botones primarios y destructivos presionados en Oscuro corregidos a contraste
  superior a 4.5:1. Las nuevas pruebas reprodujeron los pares anteriores fallidos.
- `YieldMonitoringPage` adopta `StandardPage` sin adelantar consultas.
  `PricingWorkspace` incorpora `PageViewport` y reemplaza marcadores de carga sin
  desplazar los índices de otras páginas. La prueba reproduce abrir secciones
  fuera de orden y regresar a páginas cacheadas.

### Archivos de la fase

La implementación se concentra en `frontend/desktop/themes/`,
`frontend/desktop/components/`, `frontend/desktop/shell/`, `frontend/desktop/auth/`,
`frontend/desktop/app.py` y el contrato/galería de `design_system/`.
Las últimas adiciones de componentes son `selection_controls.py`, `toolbar.py`
y `weight_input.py`; las bases de páginas, ventanas y branding ya se encuentran
en el árbol de trabajo junto con los cambios de sesiones de la fase.
Se modificaron también las dos pantallas de Precios y Rendimientos indicadas.

Pruebas añadidas/ampliadas: `tests/ui/conftest.py`,
`test_theme_density_icons.py`, `test_responsive_components.py`,
`test_design_system_visual_matrix.py`, `test_design_system_navigation_visuals.py`,
contratos del shell/ContentHost, `tests/unit/shell/test_desktop_logout_transition.py`,
`test_authentication_logout.py` y guardrails/contraste de arquitectura.
Guías actualizadas: `design_system/visual_guidelines.md` y `migration_guide.md`.
**Archivos de producto eliminados por esta fase: 0**. Las eliminaciones ajenas
en el árbol de trabajo permanecen identificadas por separado.

### Resultados verificables

| Ejecución | PASSED | FAILED | ERROR | SKIPPED |
|---|---:|---:|---:|---:|
| Componentes, shell, registro y transición logout | 161 | 0 | 0 | 0 |
| Arquitectura visual, contraste, integración y apariencia | 184 | 0 | 0 | 0 |
| Matriz shell/galería + navegación/login/teclado | 40 | 0 | 0 | 0 |
| Revalidación final navegación/login/teclado (incluida en matriz) | 20 | 0 | 0 | 0 |
| Revalidación responsive + revocación de sesión | 40 | 0 | 0 | 0 |
| Suite completa de arquitectura, ejecución 11 septiembre | 667 | 149 | 1 | 3 |
| Suite completa unit, colección | — | — | 13 | — |
| Suite completa integration, colección | — | — | 59 | — |

Las revalidaciones solapan casos anteriores. Hay **386 pruebas distintas
aprobadas** en los segmentos afectados, sin sumarlas dos veces. El
[manifiesto de validación](evidence/design_system_validation_20260912.json)
registra las ejecuciones, nombres de casos, fallos globales y hashes de capturas.

La suite completa de arquitectura contiene referencias a paquetes/rutas
ausentes (`core`, `modulos`, `interfaz`, repositorios retirados), contratos antiguos
y otros incumplimientos de arquitectura. El error de fixture corresponde a
permisos Windows del directorio temporal. Unit e integración se interrumpen en
colección por imports ausentes. No se arreglaron esos problemas alterando tests,
añadiendo shims ni restaurando archivos eliminados por otros cambios.

`compileall -q frontend/desktop` y `git diff --check` terminaron sin errores.
El auditor final mide **0 infracciones visuales nuevas**, **0 huellas obsoletas**
y **159 ocurrencias preexistentes**. Este resultado controla crecimiento de deuda;
no significa que la deuda sea cero.

### Evidencia visual y revisión pendiente

[Abrir el visor de las 200 capturas](evidence/design_system_ui/index.html).
Las 20 combinaciones de resolución/tema/densidad incluyen shell, sidebar global,
drawer, galería desplazada, login, sidebar/grupos de módulo, tabs/dashboard,
formulario con acción fija, Archivo/logout, flyout y teclado. Los formularios
extensos y límites de `StandardDialog` también se comprueban en pruebas Qt.

Se inspeccionaron capturas representativas de Claro/Oscuro y ambos perfiles;
esta revisión detectó los iconos incorrectos, el scroll duplicado y teclas
recortadas que se corrigieron. Las 200 capturas no han recibido aprobación
visual individual. Se cargaron fuentes reales de Windows para evitar aceptar
capturas offscreen con etiquetas vacías.

Checklist de aceptación todavía abierto:

- [ ] Incorporar y revisar los seis recursos oficiales de marca.
- [ ] Conectar `NotificationDrawer` a la fuente productiva de notificaciones.
- [ ] Conectar bloqueo/vencimiento y cambio de sucursal a sus flujos existentes;
      el menú Archivo actual ofrece Cerrar sesión y Salir.
- [ ] Migrar los 35 diálogos directos y revisar los 110 contratos de overflow
      registrados; sustituir los 14 literales cuando funcionen como iconos.
- [ ] Aprobar referencias de píxeles y validar rutas productivas con datos reales,
      permisos, DPI del puesto, lector, báscula y pantalla táctil.
- [ ] Resolver fallos globales de suites y la referencia CI ausente antes de release.

Siguiente etapa: adopción de una ruta productiva completa, con descenso medido
de la deuda y pruebas de sus operaciones, empezando por Configuración. Este
informe no declara finalizada la remediación empresarial completa.

## Continuación del orden solicitado — puntos 2 y 3

El [punto 2, Paleta JUANIS](juanis_palette_phase_2.md), verificó las seis anclas
y retiró los nombres históricos de crema/café conservando entonces los valores
semánticos y QSS. El [punto 3, Light / Dark](light_dark_phase_3.md), añadió el
selector persistente de tema de terminal en Configuración → Apariencia y corrigió
la notificación de cambios a controles abiertos, el refresco de gráficos HTML,
el contraste de ayuda/campos/foco y la flecha del desplegable.

La evidencia de este avance se conserva en un
[visor independiente de 220 capturas](evidence/light_dark_phase_3/index.html),
con su [manifiesto de pruebas y hashes](evidence/light_dark_phase_3/validation.json).
Los resultados de la base anterior y sus 200 capturas siguen siendo históricos;
no deben sumarse a las pruebas actuales sin eliminar solapamientos. Se mantienen
abiertos los pendientes globales de adopción, hardware, marca y suites completas.

Para continuar por la numeración elegida por el usuario, el siguiente punto es
**4. QSS global**.

## Continuación elegida — punto 5, IconProvider

El 2026-09-13 el usuario eligió trabajar **IconProvider**. El
[informe del punto 5](icon_provider_phase_5.md) documenta 138 identificadores
canónicos, 99 vectores, cobertura de los iconos declarados por navegación y
cabeceras, escalado vectorial y correcciones de estados/bindings/menús abiertos.
Su [visor independiente](evidence/icon_provider_phase_5/index.html) contiene
210 imágenes Qt, con resultados y hashes en el manifiesto enlazado allí.

La deuda global permanece en 159 ocurrencias, incluidas 14 referencias Unicode
por revisar en sus módulos; no se declara concluida la adopción global. La
selección de este punto tampoco declara completada una auditoría nueva del
punto 4. El siguiente punto de la numeración es **6. BrandAssetProvider**.

Al retomar el punto 5 se corrigieron nombres accesibles obsoletos y pérdida del
seguimiento de DPI al reenlazar iconos en controles visibles. La revisión agregó
6 casos y obtuvo **195 pruebas aprobadas, sin fallos, errores ni omisiones** en
los segmentos afectados. Su [manifiesto independiente](evidence/icon_provider_phase_5/followup-validation.json)
conserva los fallos reproducidos antes del cambio y el resultado final. No se
suman estos casos a los resultados históricos; la deuda permanece en 159
ocurrencias y no se generaron nuevas capturas en esta revisión.

## Corrección de iconos repetidos en módulos — 2026-09-14

Se corrigieron 17 barras laterales que omitían el icono al construir las filas
o no dibujaban los metadatos ya declarados. La comprobación del catálogo se
complementa con un guardrail que exige transmitir el icono y pruebas Qt sobre
las rutas reales. El [informe de esta corrección](module_sidebar_icons_fix.md)
conserva resultados, capturas y el fallo previo de una prueba que aún busca
`interfaz/menu_lateral.py`. Esta corrección no declara completado el refactor
global ni sustituye las evidencias históricas anteriores.
