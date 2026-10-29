Actúa como un Arquitecto de Software Senior especializado en PyQt5, UX/UI empresarial, Design Systems, accesibilidad, POS táctil y aplicaciones ERP.

Tu objetivo es auditar, corregir y estandarizar completamente la interfaz gráfica de SPJ POS / ERP, trabajando sobre la arquitectura actual del frontend y evitando crear soluciones aisladas o componentes duplicados.

La aplicación debe evolucionar hacia una interfaz empresarial profesional, consistente, escalable, táctil, responsive y alineada con la identidad visual de JUANIS.

⸻

1. OBJETIVO PRINCIPAL

Establecer un Design System único y obligatorio para toda la aplicación.

Debe cubrir como mínimo:

* QSS global.
* CSS únicamente donde corresponda a contenido web embebido.
* Layouts estándar.
* Componentes estándar.
* Ventanas estándar.
* Diálogos estándar.
* Navegación primaria.
* Navegación secundaria.
* Tabs internos.
* Tablas.
* KPIs.
* Formularios.
* Inputs.
* Botones.
* Iconografía.
* Branding JUANIS.
* Light Mode.
* Dark Mode.
* Densidades de interfaz.
* Touch.
* Responsive.
* Scroll y overflow.
* Estado de usuario y sesión.
* Notificaciones.
* Configuración.
* Logout.
* Accesibilidad.

No se debe rediseñar módulo por módulo de forma independiente.

Primero se debe consolidar la infraestructura UI global y después migrar cada módulo al estándar.

⸻

2. TECNOLOGÍA VISUAL: QSS VS CSS

La aplicación principal utiliza PyQt5.

Por tanto, el sistema visual principal debe utilizar:

QSS — Qt Style Sheets

No debe llamarse CSS al estilo nativo de PyQt.

QSS

Debe existir una única arquitectura centralizada:

Design Tokens
      ↓
Semantic Tokens
      ↓
Theme
      ↓
QSS Builder
      ↓
Widgets

Los widgets no deben definir colores visuales directamente.

Está prohibido introducir en widgets:

setStyleSheet("...")

salvo excepciones documentadas dentro de la infraestructura del Design System.

También deben evitarse valores visuales inline como:

#18372B
#FFFFFF
#C6A15B

Los componentes deben consumir tokens semánticos.

Ejemplo:

BACKGROUND
SURFACE
SURFACE_ELEVATED
PRIMARY
ACCENT
TEXT_PRIMARY
TEXT_SECONDARY
BORDER
SUCCESS
WARNING
DANGER
INFO

⸻

3. USO DE CSS

CSS solamente debe utilizarse cuando exista contenido web embebido, por ejemplo:

QtWebEngine
ECharts
HTML reports
Web views

Debe quedar completamente separado:

PyQt native UI
    → QSS
Web content
    → CSS

No mezclar ambas tecnologías ni mantener dos sistemas visuales independientes.

⸻

4. PALETA JUANIS

La identidad visual debe construirse sobre la paleta definida para JUANIS:

Verde profundo
#18372B
Blanco
#FFFFFF
Dorado cálido
#C6A15B
Rojo profundo
#9D2927
Carbón
#252825
Blanco cálido
#F8F8F5

Estos colores deben transformarse en escalas y tokens semánticos para Light y Dark Mode.

No deben utilizarse directamente en cada pantalla.

⸻

5. LIGHT MODE Y DARK MODE

Deben existir exactamente dos temas oficiales:

Claro
Oscuro

Ambos deben utilizar la misma estructura de componentes.

No deben existir versiones de widgets separadas para cada tema.

La arquitectura debe ser:

Component
      ↓
Semantic Token
      ↓
Light Theme / Dark Theme

El tema seleccionado debe persistirse por usuario o terminal.

Debe restaurarse antes de crear las ventanas principales.

⸻

6. COMPONENTES ESTÁNDAR

Debe existir una única colección canónica de componentes.

No crear versiones locales dentro de cada módulo.

Como mínimo:

ApplicationWindow
StandardWindow
StandardDialog
PageViewport
StandardPage
ScrollablePage
DashboardPage
WorklistPage
FormPage
MasterDetailPage
SplitPage
TabbedPage
WizardPage
POSPage
PageHeader
Breadcrumbs
ContextBar
KPIBar
KPICard
StandardCard
ChartCard
DashboardGrid
FilterBar
Toolbar
StandardTable
ColumnSpec
PrimaryButton
SecondaryButton
GhostButton
DangerButton
IconButton
StandardLineEdit
SearchInput
PasswordInput
MoneyInput
DecimalInput
IntegerInput
WeightInput
PhoneInput
EmailInput
DateInput
StandardComboBox
StandardCheckBox
StandardRadioButton
StatusBadge
StateWidget
Toast
LoadingState
EmptyState
ErrorState
Tabs
TabBar
AppSidebar
ModuleSidebar
NavGroup
NavItem
NotificationDrawer
StatusBar
VirtualKeyboard

Cada módulo debe reutilizar estos componentes.

⸻

7. LAYOUT SYSTEM

Debe existir un sistema de layouts explícito.

No permitir que cada pantalla construya arbitrariamente su estructura.

StandardPage

PageHeader
Content

WorklistPage

PageHeader
KPIBar
FilterBar / Toolbar
Table

DashboardPage

PageHeader
ContextBar
KPIBar
DashboardGrid

FormPage

PageHeader
ScrollableForm
StickyActions

TabbedPage

PageHeader
Tabs
CurrentTab

MasterDetailPage

PageHeader
Master
Detail

POSPage

Optimizado específicamente para touch y operación rápida.

⸻

8. PAGE VIEWPORT Y OVERFLOW

Debe existir:

ApplicationWindow
        ↓
ContentHost
        ↓
PageViewport
        ↓
CurrentPage

PageViewport debe controlar:

* scroll vertical;
* scroll horizontal;
* viewport disponible;
* tamaño mínimo;
* overflow;
* contenido expandible;
* sticky header cuando aplique;
* sticky actions cuando aplique.

Ningún módulo debe depender de tamaños fijos para que la interfaz “quepa”.

Evitar:

setFixedWidth(...)
setFixedHeight(...)

cuando se utilicen como solución de layout.

⸻

9. RESPONSIVE

Validar obligatoriamente:

1280 × 720
1366 × 768
1440 × 900
1600 × 900
1920 × 1080

En ninguna resolución puede ocurrir:

* botones críticos fuera de pantalla;
* formularios cortados;
* footer inaccesible;
* pestañas ocultas;
* diálogos más grandes que el viewport;
* tablas ilegibles;
* acciones imposibles de alcanzar.

⸻

10. DENSIDADES DE INTERFAZ

Implementar tres perfiles globales:

COMPACT
COMFORTABLE
TOUCH

Referencia:

Control	Compact	Comfortable	Touch
Input	32–36 px	40–44 px	48–52 px
Button	32–36 px	40–44 px	48–52 px
Table row	32 px	40–44 px	52 px
Sidebar item	36 px	44 px	52 px
Tab	36 px	42 px	48 px
IconButton	32 px	40–44 px	48 px

POS, Inventario, Recepción, Producción y operaciones táctiles deben priorizar TOUCH.

⸻

11. ICONOGRAFÍA

Eliminar como estándar:

* emojis;
* caracteres Unicode utilizados como iconos;
* letras simulando iconos.

Utilizar:

SVG
QIcon
IconProvider

Debe existir un proveedor canónico de iconos.

Cada icono debe disponer de comportamiento correcto para:

Light
Dark
Hover
Selected
Disabled
Danger
Success
Warning

⸻

12. MENÚ LATERAL PRIMARIO

El menú principal debe convertirse en un componente estándar:

AppSidebar

Debe colapsarse horizontalmente mediante un toggle visible.

No debe desaparecer verticalmente ni convertirse en otro tipo de navegación.

Estado expandido

Ancho recomendado:

240 px

Debe mostrar:

[LOGO JUANIS]
[Buscar módulo]
Inicio
Ventas
Clientes
Productos
Compras
Inventario
Transferencias
Producción
Merma
Finanzas
Reportes
Configuración
...

Cada opción debe mostrar:

icono + texto

⸻

13. MENÚ LATERAL COLAPSADO

Ancho recomendado:

60–64 px

Debe mostrar:

[ISOTIPO JUANIS]
[iconos]

Solo iconos.

Al pasar el mouse debe mostrarse tooltip.

En touch, la selección debe seguir siendo clara.

El botón toggle debe permanecer accesible en ambos estados.

Ejemplo:

EXPANDIDO
┌────────────────────────┐
│ JUANIS              ‹ │
│                        │
│ 🔎 Buscar              │
│                        │
│ ◻ Inicio               │
│ ◻ Ventas               │
│ ◻ Clientes             │
│ ◻ Inventario           │
│ ◻ Finanzas             │
└────────────────────────┘
COLAPSADO
┌──────┐
│ LOGO │
│   ›  │
│  ⌂   │
│  $   │
│  👤  │
│  ▦   │
└──────┘

Los símbolos anteriores son solamente diagramas.

La implementación real debe usar iconos SVG/QIcon.

⸻

14. ESTADO DEL SIDEBAR

Debe persistirse:

expanded / collapsed

por usuario o terminal.

También debe preservar:

módulo activo

y restaurarlo correctamente.

⸻

15. SIDEBAR SECUNDARIO

Los módulos grandes deben tener:

ModuleSidebar

Ejemplo en Finanzas:

Finanzas
▾ Contabilidad
    Plan de cuentas
    Asientos
    Libro mayor
    Periodos
▸ Cobranza
▸ Pagos
▸ Tesorería
▸ Planeación financiera
▸ Activos

⸻

16. GRUPOS COLAPSABLES

Los encabezados deben ser interactivos.

Cada grupo debe soportar:

expand
collapse
chevron
icono
badge
permission
persistencia
deep-link

No deben ser simples textos decorativos.

⸻

17. SIDEBAR SECUNDARIO COLAPSADO

También debe poder reducirse horizontalmente.

Estado reducido:

[Contabilidad icon]
[Cobranza icon]
[Pagos icon]
[Tesorería icon]

Al activar un grupo debe abrirse un flyout/popover con sus hijos.

Ejemplo:

Tesorería
------------------------
Cuentas y transferencias
Conciliación bancaria

No crear un tercer sidebar.

⸻

18. NIVELES DE NAVEGACIÓN

La navegación máxima debe ser:

NIVEL 1
AppSidebar
NIVEL 2
ModuleSidebar
NIVEL 3
Tabs horizontales

Está prohibido diseñar:

Sidebar
+
Sidebar
+
Sidebar

⸻

19. TABS INTERNOS

Utilizar tabs para vistas relacionadas dentro de la misma función.

Ejemplo:

Estados financieros
[Balanza]
[Balance general]
[Resultados]
[Flujo de efectivo]

Los tabs deben ser componentes estándar.

Debe existir un TabBar canónico.

⸻

20. VENTANA PRINCIPAL

La ventana principal debe tener una estructura clara de aplicación empresarial.

Debe existir:

ApplicationWindow

con al menos:

TopBar
AppSidebar
ContentHost
NotificationDrawer
StatusBar

⸻

21. TOP BAR DE LA APLICACIÓN

Actualmente faltan elementos esenciales.

La barra superior debe contener como mínimo:

Archivo
Notificaciones
Configuración
Usuario actual
Estado de sesión
Cerrar sesión

Ejemplo conceptual:

┌────────────────────────────────────────────────────────────┐
│ Archivo       Página actual             🔔  ⚙  Juan Pérez │
│                                            ● Conectado     │
└────────────────────────────────────────────────────────────┘

⸻

22. MENÚ ARCHIVO

Debe existir una entrada:

Archivo

Su contenido deberá definirse de forma consistente con las funciones del ERP.

Como mínimo puede contener:

Cambiar sucursal
Bloquear sesión
Cerrar sesión
Salir

No duplicar funciones si ya existen en otras partes.

⸻

23. NOTIFICACIONES

Debe existir un icono de notificación visible:

NotificationButton

Debe mostrar badge cuando existan pendientes.

Ejemplo:

🔔 3

pero utilizando un icono real.

Debe abrir:

NotificationDrawer

o panel equivalente.

⸻

24. CONFIGURACIÓN

Debe existir un botón/icono de:

Configuración

Debe usar icono estándar.

Debe navegar a la configuración general o abrir un menú contextual según corresponda.

⸻

25. USUARIO ACTUAL

La ventana principal debe mostrar claramente el usuario autenticado.

Ejemplo:

Juan Pérez
Administrador

o:

Juan Pérez
Sucursal San Bartolo

No debe existir una sesión autenticada sin ninguna representación visible del usuario.

⸻

26. ESTADO DE LA SESIÓN

Debe indicarse al menos:

Conectado
Sin conexión
Sesión bloqueada
Sesión próxima a vencer

según la arquitectura final.

No utilizar únicamente color.

Ejemplo:

● Conectado

Debe existir icono/texto accesible.

⸻

27. CERRAR SESIÓN

Debe existir una acción visible y consistente:

Cerrar sesión

Puede estar disponible desde:

menú de usuario
y/o
Archivo

Debe solicitar confirmación cuando corresponda.

No debe depender de cerrar toda la aplicación.

⸻

28. BLOQUE DE USUARIO

El bloque de usuario puede estar en TopBar o parte inferior del AppSidebar.

Ejemplo expandido:

┌────────────────────────┐
│ JP  Juan Pérez         │
│     Administrador      │
│     ● Conectado        │
└────────────────────────┘

Al pulsarlo:

Mi perfil
Cambiar sucursal
Bloquear sesión
Cerrar sesión

⸻

29. BRANDING JUANIS

Debe existir un componente:

BrandAssetProvider

que centralice los recursos oficiales.

No recrear ni reinterpretar los logos.

Debe manejar como mínimo:

logo_horizontal_light
logo_horizontal_dark
isotype_light
isotype_dark
app_icon
window_icon

⸻

30. LOGO EN MENÚ LATERAL

Sidebar expandido

Mostrar logo oficial JUANIS.

Sidebar colapsado

Mostrar solamente isotipo oficial.

No deformar, recortar ni reinterpretar el logo.

⸻

31. LOGO EN LOGIN

El login debe utilizar claramente la identidad de JUANIS.

Estructura recomendada:

[LOGO JUANIS]
SPJ ERP / POS
Sucursal / empresa
Usuario
Contraseña
[Iniciar sesión]

El logo debe aparecer arriba.

⸻

32. LOGO EN VENTANAS

Las ventanas principales deben utilizar:

window icon

oficial.

No es necesario colocar el logo grande dentro del contenido de todas las ventanas.

Debe usarse principalmente:

barra de título / icono de aplicación
sidebar
login
pantallas institucionales

⸻

33. LOGO EN DIÁLOGOS

Los diálogos deben seguir una política uniforme.

No repetir el logo horizontal grande en cada popup.

Para diálogos normales:

window icon / isotipo

Para diálogos institucionales o de autenticación:

logo completo cuando tenga sentido

Ejemplos:

Login
Cambio de sucursal
Acerca de JUANIS
Bloqueo de sesión

⸻

34. STANDARD WINDOW

Crear contrato canónico:

StandardWindow

Debe administrar:

window icon
minimum size
initial geometry
theme
responsive behavior
branding
status

Ningún módulo debe configurar esto por su cuenta.

⸻

35. STANDARD DIALOG

Todos los diálogos deben utilizar:

StandardDialog

Debe incluir:

window icon
header
content
footer
button order
Escape behavior
default action
max viewport height
automatic scroll
touch sizing

Nunca un diálogo debe quedar fuera de la pantalla.

⸻

36. TABLAS

StandardTable debe convertirse en la única tabla operativa estándar.

Debe soportar:

ColumnSpec
min_width
preferred_width
stretch
priority
hide_below
alignment
column visibility
saved widths
horizontal scroll
density
touch
actions
sorting
filtering
empty state
loading state

⸻

37. KPIs

KPICard debe admitir:

icono
título
valor
subtitle
trend
status
freshness
tooltip

No convertir cada tarjeta en un bloque de color saturado.

Usar color semántico como acento.

⸻

38. BOTONES

Deben existir únicamente variantes oficiales:

Primary
Secondary
Ghost
Danger
Icon

No diseñar botones nuevos en cada módulo.

Cada variante debe tener:

normal
hover
pressed
disabled
focus
Light
Dark
Touch

⸻

39. INPUTS

Todos los inputs deben compartir:

altura
radius
border
focus state
error state
disabled state
placeholder
label
helper text

Inputs especializados:

Money
Integer
Decimal
Weight
Phone
Email
Password
Search
Date

⸻

40. TECLADO VIRTUAL

Crear:

KeyboardAwareInput

Debe soportar:

text
integer
decimal
money
weight
phone
email

y modos:

auto_open
icon_only
disabled

Por terminal.

Debe evitar interferencias con:

barcode scanner
scale
hardware keyboard

⸻

41. ACCESIBILIDAD

Todos los componentes deben contemplar:

keyboard navigation
focus visible
tooltips
accessible names
contrast
state not represented only by color
touch target

⸻

42. GUARDRAILS

Agregar pruebas automáticas que fallen si un nuevo módulo introduce:

setStyleSheet inline
brand hex hardcoded
QPushButton personalizado visualmente
QLineEdit personalizado visualmente
QTableWidget fuera del StandardTable
KPICard local
PageHeader local
emoji como icono
control touch menor al mínimo
diálogo mayor al viewport
pantalla sin política de overflow

⸻

43. PRUEBAS VISUALES

Validar:

LIGHT
DARK

en:

1280×720
1366×768
1440×900
1600×900
1920×1080

y al menos:

Comfortable
Touch

⸻

44. COMPONENTES A PROBAR VISUALMENTE

Como mínimo:

ApplicationWindow
LoginWindow
AppSidebar expanded
AppSidebar collapsed
ModuleSidebar expanded
ModuleSidebar collapsed
NavGroup expanded
NavGroup collapsed
User block
Notification button
NotificationDrawer
File menu
Settings button
Logout menu
PageHeader
Tabs
KPICard
StandardTable
FormPage
DashboardPage
Dialog
VirtualKeyboard

⸻

45. CRITERIO DE TERMINADO

La estandarización UI/UX no puede considerarse terminada hasta que:

1. exista un único QSS central;
2. CSS quede limitado a contenido web;
3. Light y Dark utilicen los mismos componentes;
4. el tema se persista;
5. exista Layout System;
6. exista PageViewport;
7. no haya contenido cortado;
8. existan perfiles Compact/Comfortable/Touch;
9. el AppSidebar colapse horizontalmente con toggle;
10. el AppSidebar tenga iconos;
11. el AppSidebar muestre logo e isotipo correctamente;
12. exista ModuleSidebar colapsable;
13. existan grupos expandibles;
14. existan tabs estándar;
15. exista icono de notificaciones;
16. exista menú Archivo;
17. exista acceso a Configuración;
18. se muestre usuario actual;
19. se muestre estado de sesión;
20. exista Cerrar sesión;
21. se utilice branding JUANIS en sidebar, login, ventanas y diálogos según el estándar;
22. las tablas sean responsive;
23. los inputs sean touch-ready;
24. los diálogos nunca excedan el viewport;
25. las pruebas visuales estén pasando;
26. los módulos nuevos solo utilicen componentes canónicos.

⸻

46. ORDEN DE IMPLEMENTACIÓN

Ejecutar en este orden:

1. Design tokens
2. Paleta JUANIS
3. Light / Dark
4. QSS global
5. IconProvider
6. BrandAssetProvider
7. Density profiles
8. StandardWindow
9. StandardDialog
10. PageViewport
11. Layout system
12. AppSidebar
13. User/session controls
14. Notification system UI
15. File menu
16. Settings control
17. ModuleSidebar
18. Tabs
19. StandardTable V2
20. KeyboardAwareInput
21. Login branding
22. Shell branding
23. Migración de módulos
24. Guardrails
25. Visual regression

⸻

47. REGLA FINAL

No crear componentes visuales adicionales sin comprobar primero si existe un componente estándar equivalente.

La dirección arquitectónica debe ser:

Design System
      ↓
Application Shell
      ↓
Layouts
      ↓
Standard Components
      ↓
Modules

y nunca:

Module
      ↓
Custom Widget
      ↓
Custom QSS
      ↓
Custom layout

El resultado debe sentirse como un solo sistema ERP/POS profesional de JUANIS, no como una colección de módulos desarrollados de manera independiente.