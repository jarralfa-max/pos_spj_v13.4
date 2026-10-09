# Guías visuales — SPJ Design System (JUANIS)

## Identidad y temas

| Color oficial | Hex | Uso |
|---|---|---|
| Verde profundo | `#18372B` | Identidad y acción primaria en Claro |
| Blanco | `#FFFFFF` | Superficie clara y texto inverso |
| Dorado cálido | `#C6A15B` | Acentos de marca |
| Rojo profundo | `#9D2927` | Identidad destructiva/error en Claro |
| Carbón | `#252825` | Texto oscuro y superficie en Oscuro |
| Blanco cálido | `#F8F8F5` | Fondo claro |

`themes/brand_palette.py` contiene los seis colores. `semantic_colors.py`
define interacción, estados, texto y superficies. Oscuro utiliza variantes
accesibles. El dorado de marca no se usa como texto pequeño sobre blanco.

Las escalas derivadas se llaman `GREEN_*`, `RED_*`, `GOLD_*`, `WARM_WHITE_*` y
`CHARCOAL_*`. La identidad contiene exactamente seis anclas; crema y café no son
colores adicionales de JUANIS.

El QSS nativo se construye exclusivamente en `themes/qss_builder.py` y se aplica
desde `ThemeManager` al `QApplication`. Los módulos usan componentes canónicos,
`objectName`, `variant` y `state`. CSS corresponde al contenido web embebido.
No añadir `setStyleSheet`, paletas locales ni hex en widgets.

Las tarjetas `info`, `alert` y `danger` usan superficies y bordes semánticos;
`summary` usa la superficie elevada. Su variante prevalece sobre el estilo base
de `StandardCard`. En campos, el estado deshabilitado prevalece visualmente
sobre error, advertencia y solo lectura, conservando esas propiedades para
cuando el control vuelva a habilitarse.

El arranque restaura tema y densidad antes del login. Las preferencias visuales
de terminal usan `QSettings`; la navegación se guarda con ámbito de usuario y
terminal. Cambiar apariencia actualiza los controles ya construidos.

En **Configuración → Apariencia → Apariencia de esta terminal**, el selector
de tema ofrece **Claro** y **Oscuro**. El selector de densidad ofrece
**Compacta**, **Cómoda** y **Táctil**. La elección se aplica inmediatamente
y se conserva para la cuenta de Windows en esta terminal, también antes del
login siguiente. El catálogo administrativo de temas y preferencias por alcance
mantiene su flujo independiente; este selector no crea ni modifica esos registros.

`ThemeManager` termina de aplicar propiedades, paleta y QSS antes de notificar
el cambio. Los iconos siguen esa señal; `HtmlChartView` vuelve a generar el HTML
desde su último DTO sin consultar servicios ni cambiar el estado de la vista.
Los componentes nativos conservan valores y selección durante el cambio.

`set_theme()`, `set_density()` y `toggle()` resuelven la `QApplication` activa
si no se pasa explícitamente. El contrato y su matriz visual están documentados
en el [informe de QSS global](../../../docs/refactor/qss_global_phase_4.md).

Los campos utilizan `INPUT_BORDER` para distinguir su límite; `BORDER_DEFAULT`
queda disponible para separadores decorativos. El texto de ayuda de 11 px cumple
contraste de texto normal en las superficies comprobadas. En Claro, el foco
dorado derivado de JUANIS se distingue del botón primario verde y de su entorno.

## Densidad

| Control | Compacta | Cómoda | Táctil |
|---|---:|---:|---:|
| Input | 34 | 42 | 52 |
| Botón | 34 | 42 | 52 |
| Fila de tabla | 32 | 42 | 52 |
| Opción de sidebar | 36 | 44 | 52 |
| Pestaña | 36 | 42 | 48 |
| Botón de icono | 32 | 42 | 48 |

Medidas en píxeles lógicos Qt, centralizadas en `density_metrics()` de
`themes/tokens.py`. Son mínimos, no recortes fijos. El teclado virtual conserva
objetivos táctiles aunque el escritorio cambie a Compacta. Priorizar Táctil en
POS, recepción, inventario y producción según el puesto de trabajo.

La densidad es global para la terminal: cambiar de módulo conserva el perfil
elegido. `ThemeManager.set_density()` actualiza los controles existentes y
persiste `appearance/density` en `QSettings`. La opción histórica `NORMAL` se
normaliza a Cómoda; no constituye un cuarto perfil del escritorio.

Las opciones desplegables de `StandardComboBox` siguen la altura del perfil.
Las casillas usan toda su superficie como área clicable. El borde de selección
de pestañas y el borde de foco de campos conservan la geometría del control.
Al volver de Táctil a Compacta, el toggle del sidebar recupera su tamaño sin
invadir la primera opción. El [informe del punto 7](../../../docs/refactor/density_profiles_phase_7.md)
recoge pruebas de cambios en vivo, persistencia y las capturas de ambos temas.

## Estructura y navegación

`StandardWindow` centraliza el icono oficial, el título predeterminado JUANIS,
el mínimo nominal de 640×480 y el tamaño inicial de hasta 1440×900. Ajusta el
marco completo al área disponible del monitor actual; sigue cambios de monitor
y del área de trabajo y recupera su mínimo al volver a una pantalla mayor.
La maximización, pantalla completa y minimización pertenecen al gestor de
ventanas de Qt. Al restaurar, vuelve a comprobar los límites.

Durante un traslado entre monitores conectados, el marco puede atravesar el
borde compartido sin saltar al monitor anterior. Al mostrar, restaurar o cambiar
el área disponible se ajusta el marco completo; las ventanas demasiado grandes
o completamente fuera del escritorio recuperan una posición accesible.

Tema y densidad se heredan del `QApplication`; no se aplican estilos locales a
la ventana. `ApplicationWindow` conserva su barra de estado y contexto de sesión.
Los mensajes nativos de `statusBar()` no se borran al ajustar geometría o tema.
Consultar el [punto 8](../../../docs/refactor/standard_window_phase_8.md).

`ApplicationWindow → ContentHost → PageViewport → página actual` compone el
shell. `StandardPage` mantiene cabecera y acciones fuera del scroll del cuerpo.
Usar `WorklistPage`, `DashboardPage`, `FormPage`, `TabbedPage`,
`MasterDetailPage`, `POSPage` o `WizardPage` según la operación.

No introducir tamaños fijos para hacer caber una pantalla. Una tabla conserva
anchos legibles y ofrece scroll horizontal; sus columnas secundarias pueden
ocultarse según `ColumnSpec.hide_below`. `StandardDialog` limita su marco al área
disponible del monitor y desplaza el contenido conservando el footer.

El sidebar global ocupa 240 px expandido y 64 px colapsado, con toggle visible,
iconos y tooltips. `ModuleSidebar`/`SideNav` agrupa secciones, permite colapso
horizontal y ofrece flyouts. Los índices de navegación existentes se conservan.
Filtrar permisos antes de añadir opciones; el flyout reutiliza esos mismos hijos.
El tercer nivel corresponde a `Tabs`, nunca a otro sidebar.

## Componentes e interacción

Las cinco variantes públicas son `PrimaryButton`, `SecondaryButton`,
`GhostButton`, `DangerButton` e `IconButton`. Los nombres anteriores de factories
se dirigen a estas variantes mientras se migran sus consumidores.

Usar `IconProvider.bind()` para botones, acciones y etiquetas que deban seguir el
tema. No utilizar emoji, letras o caracteres como sustitutos de iconos. El color
de estado siempre acompaña texto o una forma distinguible.

El catálogo contiene 138 identificadores con nombre español y SVG canónico.
El QIcon se dibuja al tamaño solicitado; el estado On corresponde a selección
y Disabled prevalece sobre el estado semántico. `bind()` también cubre acciones
de menús abiertos, etiquetas deshabilitadas y cambios de DPI. Los iconos normales
de botones primarios o de peligro usan el color inverso del relleno. Consulta el
[informe de IconProvider](../../../docs/refactor/icon_provider_phase_5.md)
para contratos, validación y evidencia.

La captura usa `MoneyInput`, `IntegerInput`, `DecimalInput`, `WeightInput`,
`PhoneInput`, `EmailInput`, `PasswordInput` y `DateInput`. Las entidades requieren
búsqueda/autocomplete; `StandardComboBox` corresponde a catálogos pequeños.
Importes y cantidades parten de cero o vacío.

`KeyboardAwareInput` añade teclado a un input existente conservando su validador.
Los modos de terminal son `auto_open`, `icon_only` y `disabled`; el autoabierto
requiere interacción de puntero. Tab y escritura física no lo abren. Declarar
`hardwareInput`/`hardware_source` para escáner o báscula.

## Branding oficial

`BrandAssetProvider` resuelve desde `AppPaths.resource_root/assets/branding/` los nombres
`logo_horizontal_light`, `logo_horizontal_dark`, `isotype_light`,
`isotype_dark`, `app_icon` y `window_icon`, con extensión SVG, PNG o ICO.

Los seis recursos suministrados están en `assets/branding/` desde el 2026-09-21.
El provider los usa en login, sidebar y ventanas conservando su proporción.
Si falta una variante o no puede leerse, `BrandLabel` muestra JUANIS en texto
temporal. Ese texto no es un logo aprobado. No dibujar ni reinterpretar la marca.
En diálogos operativos basta el icono de ventana.

El proveedor dibuja SVG a la resolución física del monitor y conserva el DPR de
la imagen. PNG e ICO mantienen proporción y transparencia. El recurso de ventana
puede respaldarse con el icono de aplicación y viceversa; una variante ausente
de logo o isotipo nunca se sustituye con otra de distinto tema. En el ejecutable,
`resource_root` puede ser la carpeta de extracción de PyInstaller, distinta de
la carpeta de instalación y de los datos del usuario.

La validación de los archivos reales y sus consumidores se documenta en el
[punto 6](../../../docs/refactor/brand_asset_provider_phase_6.md).

## Accesibilidad y aceptación

Mantener foco visible, tabulación, nombres accesibles y tooltips. Explicar las
acciones destructivas y establecer Cancelar como confirmación inicial.
Se valida contraste de texto normal a 4.5:1, incluidos botones primarios y
destructivos en normal, hover y pressed.

La matriz comprende Claro/Oscuro y Cómoda/Táctil en 1280×720, 1366×768, 1440×900,
1600×900 y 1920×1080. Las pruebas de geometría y capturas Qt son evidencia
reproducible; no constituyen una comparación de píxeles contra una referencia
aprobada ni sustituyen probar el equipo táctil real.

Consultar el [informe de estado](../../../docs/refactor/global_ui_ux_design_system_audit.md)
para la deuda de adopción. La galería no acredita por sí sola todas las rutas.
