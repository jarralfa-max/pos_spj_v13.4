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

---

## Corrección — mi diagnóstico inicial estaba mal planteado

Escribí arriba "17 módulos sólo-legacy" y lo presenté como si faltara construirlos. **Eso
era incorrecto y conviene decirlo con claridad**: medí el *cableado del shell*, no la
existencia de los módulos. `frontend/desktop/modules/` contiene **18 paquetes canónicos**.

El cuadro real, verificado paquete por paquete:

| Situación | Módulos | Trabajo pendiente |
| --- | --- | --- |
| Cableados en el shell canónico | 10 | ninguno |
| Existen, **sin contrato de shell** | `assets`, `business_intelligence`, `fidelidad`, `losses`, `meat_processing`, `orders_delivery`, `pricing`, `tarjetas_fidelidad` | escribir `shell_registration.py` |
| Sin módulo canónico | `DASHBOARD`, `COTIZACIONES` | construir el módulo |

Ninguno de esos 8 declara `ModuleDescriptor`, `RouteDefinition` ni `ModuleActivator`
(comprobado con `git grep` sobre cada paquete): tienen vistas, páginas y presenters, pero
no la superficie que el shell necesita para registrarlos. No hay que construirlos de cero
— hay que darles el contrato.

## Primer módulo cableado: `configuracion`

`configuracion` ya tenía `shell_registration.py` **completo** (`CONFIGURACION_MODULE_ID`,
`build_configuracion_module_descriptor`, `build_configuracion_route_definition`,
`ConfiguracionModuleActivator`) y sólo faltaba añadirlo a `_MIGRATED_MODULE_WIRINGS` y al
sidebar. Estaba construido y sin conectar.

Se verificó antes de cablearlo que su activator acepta exactamente la firma que
`_standard_activator_factory` entrega (`connection`, `view_factory_registry`,
`session_context`), igual que los otros nueve — no hizo falta una factory especial como la
de `products`.

Etiqueta del sidebar: "Configuración", tomada de `menu_lateral.py` sin el emoji ni el
sufijo "(Nuevo)", siguiendo la convención que el propio archivo de navegación documenta.

**Brecha: 17 → 16.**

### Una prueba que pasaba por accidente

`test_migrated_modules_sidebar.py` mantiene su propia lista `_MODULE_BUILDERS`. Al añadir
el item de navegación de `configuracion` sin añadirlo a esa lista, la prueba **seguía
pasando**: `SidebarResolver` descarta en silencio los items cuyo módulo no está registrado,
así que resolvía 9 de 10 y su `assert len(resolved) == 9` seguía verde mientras
sub-verificaba.

Se añadió `configuracion` también a esa lista y se subieron los conteos a 10. Las tres
pruebas que fijaban 9 se **endurecen**, no se relajan.

### Evidencia

```text
python -m pytest tests/integration/shell/ -q -p no:cacheprovider
```
Resultado: **60 passed** (antes 58 passed + 2 failed por el conteo de 9).

```text
python -m pytest tests/architecture/test_shell_cutover_ratchet.py -q
```
El ratchet **falló primero** exigiendo registrar el avance
(`CONFIGURACION_MODULE_ID` ya está en el shell canónico), y pasó tras actualizarlo:
**5 passed**. Funcionó exactamente como se diseñó.

## Estado tras esta corrección

`main.py` sigue sin cambiar. La brecha es de **16 slots legacy**, de los cuales 14 tienen
módulo canónico esperando contrato de shell y 2 no tienen módulo. El corte sigue bloqueado,
pero el trabajo restante es bastante menor de lo que este documento afirmaba antes.

---

## Segunda corrección: "existe el módulo" no equivale a "reemplaza al legacy"

Al abrir los 8 paquetes para darles contrato de shell apareció algo que ni mi medición
anterior ni la premisa de partida recogían: **varios son cascarones de UI con páginas
placeholder**, no reemplazos funcionales.

Medido leyendo `_REAL_ROUTE_BUILDERS` de cada módulo, no por inspección visual:

| Módulo | Rutas | Con página real | Placeholder |
| --- | ---: | ---: | ---: |
| `business_intelligence` | 13 | **10** | 3 |
| `orders_delivery` | 23 | **3** | 20 |
| `losses` | todas | **0** | todas |
| `meat_processing` | todas | **0** | todas |

`losses_routes.build_page()` y `meat_processing_routes.build_page()` devuelven
`LossesPlaceholderPage` / `MeatProcessingPlaceholderPage` **en todos los casos**, sin
ninguna rama alternativa.

Consecuencia directa: **cablear `losses` o `meat_processing` al shell canónico sería
registrar pantallas vacías**. Si después `main.py` corta, MERMAS y PRODUCCIÓN se
convertirían en pantallas de relleno. Eso es exactamente lo que §2 prohíbe, y el hecho de
que el módulo "exista en la arquitectura nueva" no lo evita.

Por eso este lote cablea **uno** de los ocho, no los ocho.

## Módulo cableado: `business_intelligence` (brecha 16 → 15)

Es el único del lote que reemplaza funcionalidad real: 10 de sus 13 rutas construyen
páginas con presenter y conexión (ejecutivo, ventas, inventario, compras, finanzas,
forecast, recomendaciones, escenarios, alertas, reportes); las 3 restantes caen a un
placeholder explícito y acotado.

`BusinessIntelligenceView` ya acepta `connection`/`branch_id`/`actor_user_id` y arma su
propio `page_builder`, así que el activator **no reimplementa** esa composición: le entrega
los tres valores que la vista ya sabe usar. Sin duplicar lógica.

Dos decisiones que conviene dejar por escrito:

- **`_has_permission` niega por defecto sin sesión.** El `SidebarResolver` ya filtra la
  entrada del módulo por `required_permission`; este callback gobierna el sidebar *interno*.
  Negar sin contexto es lo correcto: lo contrario mostraría secciones que la persona quizá
  no puede ver.
- **`Icons.ANALYTICS` es nuevo en el catálogo central**, con su nombre accesible
  ("Inteligencia de Negocios"). §20 exige que los iconos salgan de un catálogo; añadirlo
  ahí es lo correcto, y no se usó un icono ajeno para evitar el trámite.

## Estado del lote de 8

| Módulo | Estado | Qué falta |
| --- | --- | --- |
| `business_intelligence` | **cableado** | — |
| `orders_delivery` | bloqueado | 20 de 23 rutas son placeholder |
| `losses` | bloqueado | todas sus rutas son placeholder |
| `meat_processing` | bloqueado | todas sus rutas son placeholder |
| `fidelidad` / `tarjetas_fidelidad` | por evaluar | tienen páginas placeholder; falta medir la proporción |
| `assets` | por evaluar | `assets_routes.py` sólo define metadatos de ruta, no construye páginas |
| `pricing` | no aplica como reemplazo | 5 páginas reales, pero **no tiene slot legacy**: es módulo nuevo, no sustituye nada |

El trabajo pendiente de esos 7 **no es escribir `shell_registration.py`** — eso es la parte
trivial. Es construir las páginas reales que hoy son placeholder. Presentarlo como
"cablear 8 módulos" subestimaría el esfuerzo por un orden de magnitud.

---

## Tercer lote: cableado de 5 módulos por decisión explícita (brecha 15 → 10)

El usuario, tras leer el hallazgo de los placeholders, indicó: *"cablealos, en otra sesión
se corregirán los módulos"*. Es su decisión y se ejecuta completa.

Módulos cableados en este lote:

| Módulo | Slot legacy | Permiso | Contenido real |
| --- | --- | --- | --- |
| `losses` | MERMAS | `LOSSES_VIEW` | **0 rutas reales** |
| `meat_processing` | PRODUCCION | `PRODUCCION.ver` | **0 rutas reales** |
| `orders_delivery` | DELIVERY | `DELIVERY.acceso` | 3 de 23 |
| `fidelidad` | GROWTH_ENGINE | `GROWTH_ENGINE.ver` | parcial |
| `tarjetas_fidelidad` | TARJETAS_FIDELIDAD | `TARJETAS_FIDELIDAD.ver` | parcial |

Los cinco `shell_registration.py` se generaron con una plantilla parametrizada desde el
patrón de `transfers`, no copiando el archivo cinco veces: descriptor, route definition y
activator con dependencias explícitas, sin `AppContainer`.

`fidelidad` y `tarjetas_fidelidad` ya tenían `create_*_view(connection, session_context)` en
su `composition.py`; sus activators **llaman a esa función**, no reimplementan la
composición. `losses` y `meat_processing` reciben su propio `build_page` como
`page_builder`. `orders_delivery` recibe `connection`/`branch_id`/`actor_user_id`, que su
vista ya sabe usar.

Permisos: todos salen del `permissions.py` de cada bounded context
(`LossPermissions.VIEW`, `MeatProcessingPermissions.VIEW`,
`OrdersDeliveryPermissions.ACCESS`, `LoyaltyPermissions.VIEW`,
`LoyaltyCardsPermissions.VIEW`) — ninguno inventado para esta migración.

## El pestillo que hace segura esta decisión

Cablear placeholders es inocuo **mientras el shell siga dormido**, y peligroso en el
instante en que `main.py` corte: Mermas, Producción y Delivery se convertirían en pantallas
de relleno para el usuario final.

`test_main_is_not_cut_over_while_placeholder_modules_are_wired` cierra esa puerta. Mientras
`_PLACEHOLDER_BACKED` no esté vacío, `main.py` no puede referenciar
`build_application_window`, `ApplicationWindow` ni `CompositionRoot` sin que la prueba
falle, nombrando qué módulo falta rellenar y por qué.

Verificado añadiendo un import real de `build_application_window` a `main.py`: la prueba
**falla** y lista los cinco pendientes; al revertir, vuelve a pasar. `main.py` quedó
intacto (`git status` limpio).

El orden queda así forzado y no depende de que alguien recuerde esta conversación:
**primero se rellenan las páginas, después corta `main.py`**. Cuando un módulo deje de ser
placeholder, se retira de `_PLACEHOLDER_BACKED`; cuando la lista quede vacía, el pestillo
se abre solo.

## Los 2 que NO se cablearon, y por qué

| Módulo | Motivo |
| --- | --- |
| `assets` | No existe función de composición. `assets_routes.py` sólo define metadatos (`AssetRoute`, `visible_routes`, `grouped_routes`); `AssetsWorkspace` exige un `presenter` y un `page_factories` que nadie construye todavía. Cablearlo exige **escribir** esa composición, no conectarla. |
| `pricing` | `PricingPresenter` necesita un `read_service_factory` que ningún módulo provee, y sobre todo **no tiene slot legacy**: no sustituye nada del menú actual. Es un módulo nuevo, no un reemplazo, así que no reduce la brecha del cutover. |

## Estado

**Brecha: 15 → 10.** Slots legacy sin contraparte canónica: ACTIVOS, CONFIG_HARDWARE,
CONFIG_MODULOS, CONFIG_SEGURIDAD, COTIZACIONES, DASHBOARD, ETIQUETAS, PLANEACION_COMPRAS,
PROVEEDORES, WHATSAPP.

`main.py` sigue sin cambiar. El shell canónico monta 16 módulos y sigue dormido.
