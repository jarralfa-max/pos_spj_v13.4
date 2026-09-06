# Fases 5 y 6: por qué el cutover de CompositionRoot y shell NO se puede cerrar todavía

Fecha de validación: 2026-09-06. Rama: `claude/erp-financial-bounded-context-uqxz6b`.
Parte de: `ad155c2f`.

## Lo que se pidió y lo que la evidencia permite

La instrucción es clara: todo dentro de la arquitectura nueva, sin conservar la antigua y
sin duplicar. Las fases 5 y 6 del plan lo concretan: `main.py` debe usar
`CompositionRoot` y `ApplicationShellWindow`, y `AppContainer` + `MainWindow` deben
desaparecer.

Medí el terreno antes de tocar `main.py`, y el resultado impide ejecutar ese corte ahora.
Lo escribo con números porque la conclusión no es de opinión.

## Medición

| Shell | Módulos | ¿Lo usa producción? |
| --- | ---: | --- |
| `interfaz/main_window.py` (legacy) | **26** (`_conectar(...)`) | **Sí** — `main.py` lo construye |
| `frontend/desktop/shell/desktop_shell_window_composition.py` (canónico) | **9** | **No** — `build_application_window()` sólo lo llaman pruebas |

`main.py` no contiene ninguna referencia a `CompositionRoot`,
`DesktopApplicationBootstrapper` ni `ApplicationWindow`. El shell canónico existe,
funciona y está probado de extremo a extremo… y está **dormido**.

Los 9 módulos canónicos (sales_pos, customers_crm, finance, hr, inventory, products,
purchasing, transfers, cash_register) tienen **todos** contraparte viva en MainWindow. Esos
dominios están compuestos dos veces.

Matiz que importa para no exagerar el hallazgo: **no son dos rutas vivas simultáneas**. La
canónica no arranca, así que el usuario ve una sola. Pero sigue siendo el estado que §49
declara abierto — "CompositionRoot existe pero main usa AppContainer" — y no se cierra
solo.

## Por qué cambiar `main.py` hoy sería un retroceso

Quedan **17 módulos sólo-legacy**, sin contraparte canónica:

    ACTIVOS · CONFIGURACION · CONFIG_HARDWARE · CONFIG_MODULOS · CONFIG_SEGURIDAD
    COTIZACIONES · DASHBOARD · DELIVERY · ETIQUETAS · GROWTH_ENGINE · INTELIGENCIA_BI
    MERMAS · PLANEACION_COMPRAS · PRODUCCION · PROVEEDORES · TARJETAS_FIDELIDAD · WHATSAPP

Apuntar `main.py` al shell canónico dejaría al usuario sin Configuración, sin Producción,
sin Delivery, sin BI, sin Mermas y sin WhatsApp, entre otros. §2 lo prohíbe de forma
explícita: *"NO eliminar funcionalidad operativa sin migración completa"*.

La alternativa —arrancar los dos shells a la vez— sería exactamente la arquitectura
paralela **viva** que §49 prohíbe, y sería peor que el estado actual: hoy la duplicación es
latente; así sería real.

Así que el corte no está bloqueado por falta de trabajo en `main.py`. Está bloqueado por
**17 migraciones de módulo** que nadie ha hecho todavía. Escribir un `main.py` nuevo sin
ellas no sería avanzar la fase 5: sería romper el producto y llamarlo arquitectura.

## Lo que sí se hizo: congelar la divergencia

`tests/architecture/test_shell_cutover_ratchet.py` convierte el corte en inevitable en vez
de perpetuo. Cinco garantías, todas leídas del código fuente, no declaradas a mano:

1. **El shell legacy no puede ganar módulos.** Cualquier `_conectar("NUEVO", …)` falla: los
   módulos nuevos nacen en el canónico.
2. **El registro canónico no puede encoger.** El cutover no retrocede.
3. **El avance debe registrarse.** Si un módulo sale del legacy o entra en el canónico y
   este archivo no se actualiza, la prueba falla — es lo que evita que estos conjuntos
   acaben como las allowlists obsoletas de `05_IDENTITY_GUARDRAILS.md`.
4. **La duplicación queda explícita**, con el mapa canónico → slot legacy de los 9 pares.
5. **La brecha (17) es un número comprobado**, no una estimación en prosa.

Verificado insertando un `_conectar("MODULO_NUEVO_LEGACY", …)` real en `main_window.py`:
**fallan dos pruebas** (la de crecimiento y la de brecha), y vuelven a pasar al revertir.
`main_window.py` quedó intacto, comprobado con `git status`.

## Estado honesto

Las fases 5 y 6 siguen **abiertas y sin avance funcional en esta fase**. No se retiró
`AppContainer` del arranque ni se sustituyó `MainWindow`. Lo único que cambia es que la
brecha está medida, congelada y no puede crecer en silencio.

`main.py` sigue haciendo `AppContainer(db_path=DB_PATH)` y `MainWindow(container)`.

## El trabajo real que queda

El orden es forzoso y no admite atajos:

1. Migrar los 17 módulos sólo-legacy al registro canónico (`shell_registration.py` propio,
   descriptor, ruta y activator por módulo, como los 9 ya migrados).
2. Sólo entonces, apuntar `main.py` a `DesktopApplicationBootstrapper` + `CompositionRoot`
   + `build_application_window()`.
3. Sólo entonces, eliminar `interfaz/main_window.py` y `core/app_container.py`, lo que a su
   vez desbloquea los 4 consumidores restantes del `SalesService` legacy
   (ver `08_SALES_CUTOVER.md`).

Cada módulo migrado debe reducir `_LEGACY_MODULES` y ampliar `_CANONICAL_MODULE_IDS` en el
ratchet, de modo que el progreso sea siempre visible y verificable.
