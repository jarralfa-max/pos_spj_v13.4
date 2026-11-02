# SDLC-UI-021 — Teclado virtual: el modo por terminal nunca se aplica y la protección contra escáner/báscula está muerta

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §40 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-31, Alfred)
- **Depende de:** —

## Problema
`KeyboardAwareInput` define los tipos (texto, entero, decimal, dinero, peso, teléfono, email) y los modos auto_open, icon_only y disabled. Pero `attach_virtual_keyboard_action` nunca pasa `terminal_key`, así que el modo se guarda siempre como `default`. Ninguna pantalla permite fijarlo y nada fija `hardware_source`, así que la lógica que evita abrir el teclado con lector de códigos o báscula nunca se ejecuta.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/components/virtual_keyboard.py:18-19,160,258-259,274,328`
- Sin usos directos de `KeyboardAwareInput` en módulos; uso indirecto en POS (`sales_pos/.../catalog_panel.py:38`, diálogos de cobro) e Inventario (7 archivos)
- `tests/ui/test_responsive_components.py:179-226`; `test_keyboard_density_target.py`

## Impacto
POS y básculas táctiles: no se puede configurar el teclado por caja; el teclado puede abrirse sobre una lectura de escáner si se activa auto_open.

## Objetivo
- El modo se resuelve por terminal (id de estación) y se configura desde una pantalla existente de Configuración
- Escáner y báscula marcan su entrada como hardware y el teclado no se abre
- Pruebas de los tres modos y del caso escáner

## Alcance
- **Incluye:** `virtual_keyboard.py`, adaptadores de escáner y báscula del frontend, ajuste en Configuración.
- **No incluye:** Drivers de hardware.

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T1: spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada.

## Trabajo previo relacionado
Identidad de terminal fragmentada: SDLC-ARQ-TERM-001.

## Preguntas abiertas
- ¿Desde dónde se configura el modo del teclado por terminal (Configuración → Dispositivos u otra sección)? Dispositivos

## Nota 

Quiero que al presionar el ícono del teclado en la barra de texto, el teclado virtual se despliegue hacia abajo como un menú colapsable (Toggle).
• Para ingresar datos cómodamente sin que el teclado tape el contenido superior, viendo un diseño adaptado al tipo de información que debo escribir.

1. Comportamiento de la Interfaz (UI Behavior)

• Gesto/Acción: Tap/Click en el ícono del teclado (ubicado en la barra de texto).
• Animación de Apertura: Despliegue vertical hacia abajo (Slide-down / Dropdown animation) tomando como punto de anclaje la base de la barra de texto.
• Comportamiento Toggle:
	• Si el teclado está oculto: al presionar el ícono, se despliega.
	• Si el teclado está visible: al presionar el ícono (o hacer tap fuera), se contrae hacia arriba (Slide-up) ocultándose detrás o debajo de la barra.

2. Matriz de Variaciones según el Tipo de Entrada (Input Type)

El teclado virtual debe renderizar dinámicamente una de las siguientes variantes según la propiedad inputType del campo activo:

Tipo de Entrada	Variación del Teclado (Layout)	Teclas Específicas / Comportamiento
Texto	Alfanumérico estándar (QWERTY)	Primera letra en mayúscula por defecto, barra de espacio amplia.
Entero	Teclado Numérico puro	Solo números del 0 al 9. Sin punto decimal. Tecla "Borrar".
Correo	Alfanumérico optimizado	Incluye accesos directos visibles para @ y .com en la pantalla principal.
Decimal	Teclado Numérico con punto	Números del 0 al 9 y la tecla de punto (.) o coma ( , ) según la región.
Dinero	Numérico financiero	Incluye el símbolo de moneda local ($), el punto decimal y opción de doble cero (00).
Peso	Numérico con unidad de medida	Teclado numérico decimal que incluye un sufijo o tecla rápida para la unidad (ej. kg, g, lbs).


3. Criterios de Aceptación 

1. Anclaje: El teclado virtual no debe flotar; su borde superior debe coincidir exactamente con el borde inferior de la barra de texto.
2. Dinámico: El cambio de layout del teclado debe ocurrir antes de que termine la animación de apertura (basado en el foco del input).
3. Persistencia: Si el usuario cambia de un campo "Texto" a uno "Dinero" con el teclado abierto, este no debe cerrarse; debe hacer una transición fluida al nuevo layout.
¿
