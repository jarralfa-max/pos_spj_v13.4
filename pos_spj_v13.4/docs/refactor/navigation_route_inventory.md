# SHELL-0 — Inventario de navegación (`menu_lateral.py` ↔ `main_window.py`)

Fuente: lectura íntegra de `interfaz/menu_lateral.py` (624 líneas) y
`interfaz/main_window.py` (1559 líneas). Cada entrada del sidebar
(`self._crear_boton(label, codigo)`) se contrasta contra su
`self._conectar(codigo, ClaseWidget, fallback)` correspondiente en
`_construir_todas_las_pantallas()`.

## 1. Superficie de navegación actual — completa

| Sección sidebar | Código de ruta | Label sidebar | Clase UI real (`main_window.py`) | Import module | ¿Registrado en sidebar? |
|---|---|---|---|---|---|
| *(no listado en sidebar — solo alcanzable si `ui.dashboard` importa bien)* | `DASHBOARD` | — | `DashboardWidget` | `ui.dashboard` | **NO** — construido condicionalmente en `_construir_todas_las_pantallas` pero sin botón propio en `menu_lateral.py`. Solo se llega a él por navegación programática (`abrir_modulo` del propio dashboard, atajos). |
| Operaciones | `POS` | 🛒 Punto de Venta | `ModuloVentasPos` (alias `ModuloVentas`) | `modulos.ventas_pos` | Sí |
| Operaciones | `CAJA` | 💰 Caja / Cortes Z | `CashRegisterModuleHost` | `backend.infrastructure.desktop.cash_register_factory` | Sí |
| Operaciones | `INVENTARIO` | 📦 Inventario | `ModuloInventarioEnterprise` (alias `ModuloInventarioLocal`) | `modulos.inventario_enterprise` | Sí |
| Operaciones | `TRANSFERENCIAS` | 🔄 Transferencias | `TransfersModuleHost` | `backend.infrastructure.desktop.transfers_factory` | Sí |
| Operaciones | `PRODUCTOS` | 🏷️ Productos | `ModuloProductosEnterprise` (alias `ModuloProductos`) | `modulos.productos_enterprise` | Sí |
| Operaciones | `CLIENTES_CRM` | 👥 Clientes y CRM | `ModuloClientesCrm` | `modulos.clientes_crm` | Sí |
| Operaciones | `MERMAS` | Mermas | `LossesModuleHost` | `backend.infrastructure.desktop.losses_factory` | Sí |
| Comercial | `DELIVERY` | 🛵 Delivery | `ModuloDelivery` | `modulos.delivery` | Sí |
| Comercial | `COMPRAS` | 🛒 Compras | `ModuloComprasEnterprise` (alias `ModuloCompras`) | `modulos.compras_enterprise` | Sí |
| Comercial | `COTIZACIONES` | 📋 Cotizaciones | `ModuloCotizaciones` | `modulos.cotizaciones` | Sí |
| *(eliminado)* | `PROVEEDORES` | — | `ModuloProveedores = None` (hardcoded) | — | Eliminado intencionalmente — integrado en `FINANZAS_UNIFICADAS` (comentado en ambos archivos) |
| Producción | `PRODUCCION` | 🔪 Procesamiento Cárnico | `ModuloProduccion` | `modulos.produccion` | Sí |
| Producción | `ETIQUETAS` | 🏷️ Etiquetas | `ModuloEtiquetas` | `modulos.etiquetas` | Sí |
| Producción | `PLANEACION_COMPRAS` | 📈 Planeación de Compras | `ModuloPlaneacionCompras` | `modulos.planeacion_compras` | Sí |
| Administración | `FINANZAS_UNIFICADAS` | 💰 Finanzas | `ModuloFinanzas` | `modulos.finanzas` | Sí |
| *(eliminado)* | `TESORERIA` | — | `ModuloTesoreria = None` (hardcoded) | — | Eliminado — integrado en `FINANZAS_UNIFICADAS` |
| Administración | `ACTIVOS` | 🏗️ Activos | `ModuloActivos` | `modulos.activos` | Sí |
| Administración | `RRHH` | 👔 Recursos Humanos | `ModuloRRHH` | `modulos.rrhh` | Sí |
| Administración | `GROWTH_ENGINE` | ⭐ Fidelización | `ModuloFidelidadConfig` | `modulos.fidelidad_config` | Sí (nota: código de ruta `GROWTH_ENGINE` mapea a la clase `Fidelidad*Config*`, no a `ModuloGrowthEngine` — ver §3) |
| Administración | `TARJETAS_FIDELIDAD` | 💳 Tarjetas Fidelidad | `ModuloTarjetas` | `modulos.tarjetas` | Sí |
| Administración | `INTELIGENCIA_BI` | 📈 Inteligencia de Negocios | `ModuloReportesBIv2` | `modulos.reportes_bi_v2` | Sí |
| Administración | `WHATSAPP` | 📱 Pedidos WhatsApp | `ModuloWhatsApp` | `modulos.whatsapp_module` | Sí |
| Sistema | `DISEÑADOR_TICKETS` | 🎨 Diseñador Tickets | `ModuloTicketDesigner` | `modulos.ticket_designer` | Sí |
| Sistema | `CONFIG_HARDWARE` | 🖨️ Hardware | `ModuloConfigHardware` | `modulos.config_hardware` | Sí (también alcanzable desde el menú superior "🖨️ Hardware → ⚙️ Configurar Dispositivos") |
| Sistema | `CONFIG_MODULOS` | 🔌 Configuración Módulos | `ModuloConfigModulos` | `modulos.config_modules` | Sí |
| Sistema | `CONFIG_SEGURIDAD` | 🛡️ Configuración | `ModuloConfiguracion` | `modulos.configuracion` | Sí |
| Zona inferior | `LOGOUT` | 🚪 Cerrar Sesión | *(no es pantalla — dispara `manejar_navegacion("LOGOUT")`)* | — | Sí, caso especial manejado aparte en `manejar_navegacion()` |

**Total de rutas reales con pantalla propia:** 25 (24 módulos + `DASHBOARD` sin
botón) + 1 pseudo-ruta (`LOGOUT`, no navega a un widget).
**Total de botones en el sidebar:** 24 módulos + `LOGOUT` = 25 botones.
**Módulos importados por `main_window.py` que YA NO tienen ruta activa
(`= None` hardcodeado, código muerto intencional documentado):** 2
(`ModuloProveedores`, `ModuloTesoreria`).

## 2. Rutas adicionales fuera del sidebar/stack (menú superior, no en `QStackedWidget`)

Estas navegan directo sin pasar por `manejar_navegacion()`/el stack:

| Origen | Acción |
|---|---|
| Menú "📁 Archivo → 🚪 Cerrar sesión" | Llama `manejar_navegacion("LOGOUT")` — sí pasa por el router |
| Menú "📁 Archivo → ❌ Salir" | `self.close()` directo |
| Menú "🎨 Interfaz → 🌙 Modo Oscuro" | `self._aplicar_tema(...)` directo, no navegación |
| Menú "🖨️ Hardware → ⚙️ Configurar Dispositivos" | `manejar_navegacion("CONFIG_HARDWARE")` — ruta duplicada de acceso (mismo código que el botón del sidebar, dos puntos de entrada a la misma pantalla — no es ambigüedad de identidad, es UX redundante intencional) |
| Menú "❓ Ayuda → 🔧 Diagnóstico del Sistema" | `self._mostrar_diagnostico()` — abre `interfaz.diagnostico.mostrar_diagnostico(self)`, **no** es una pantalla del stack |
| Menú "❓ Ayuda → ℹ️ Acerca de" | `QMessageBox.information` directo |
| Menú superior "📦 Pedidos (N)" | `self._abrir_panel_pedidos()` → `manejar_navegacion("DELIVERY")` |

## 3. Ambigüedades / inconsistencias de identidad de ruta detectadas

1. **`DASHBOARD` sin botón de sidebar.** Es una pantalla real (`ui.dashboard.
   DashboardWidget`), registrada en el stack, pero **no** tiene entrada en
   `menu_lateral.py`. Solo se llega por navegación programática: el propio
   dashboard emite `abrir_modulo` con claves como `"ventas"`, `"inventario"`,
   `"caja"`, etc. (traducidas por el diccionario `_DASH_NAV` en
   `main_window._conectar()`), o por el atajo de búsqueda global. Un usuario
   que cierra sesión y no tiene otra forma de "volver al dashboard" desde el
   sidebar. Para el catálogo objetivo ("Inicio, Punto de Venta, ...") esto
   probablemente debería mapear a la entrada **"Inicio"**, que hoy no existe
   como concepto de sidebar explícito — la pantalla `BIENVENIDA` (bienvenida
   estática) cumple ese rol parcialmente pero no es la misma clase que
   `DASHBOARD`.

2. **`_DASH_NAV` usa claves en minúsculas inglesas/español mezcladas
   (`"ventas"`, `"inventario"`, `"caja"`, `"clientes"`,
   `"pedidos_whatsapp"`, `"delivery"`, `"reportes"`, `"finanzas"`, `"rrhh"`,
   `"productos"`, `"compras"`) que NO coinciden 1:1 con los códigos de ruta
   reales en mayúsculas (`POS`, `INVENTARIO`, `CAJA`, `CLIENTES_CRM`,
   `WHATSAPP`, `DELIVERY`, `INTELIGENCIA_BI`, `FINANZAS_UNIFICADAS`, `RRHH`,
   `PRODUCTOS`, `COMPRAS`).** Es un diccionario de traducción manual
   mantenido en paralelo al `RouteRegistry` implícito — cualquier ruta nueva
   agregada al sidebar que el dashboard también quiera enlazar debe
   actualizarse en DOS lugares (`_DASH_NAV` y el sidebar). Fuente de
   divergencia futura.

3. **La constante `MODULOS` en `menu_lateral.py` (líneas 14-39) es una
   tercera taxonomía de nombres de módulo, ya desincronizada de las dos
   anteriores:** usa `"ventas"`, `"clientes"`, `"merma"` (singular, el código
   real es `"MERMAS"` plural), `"finanzas_unificadas"`, `"contabilidad"`
   (¡no existe como ruta en ningún lugar del sistema!), `"inteligencia_bi"`.
   Confirmado por grep que esta lista **no se referencia en ningún otro
   punto del archivo ni del proyecto** — es código muerto que debe eliminarse
   (ver `application_shell_legacy_inventory.md` §4.1, clasificado DELETE)
   antes de que alguien la tome por error como fuente de verdad al construir
   `RouteRegistry`.

4. **`GROWTH_ENGINE` como código de ruta apunta a `ModuloFidelidadConfig`,
   no a `ModuloGrowthEngine`.** Existe una clase `ModuloGrowthEngine`
   importada al final de `main_window.py` (líneas 1554-1557, tras la
   definición de `MainWindow`) que **nunca se usa** en
   `_construir_todas_las_pantallas()` ni se conecta a ningún código de ruta
   — es un import muerto. El botón visible "⭐ Fidelización" (código
   `GROWTH_ENGINE`) en realidad abre la pantalla de configuración de
   fidelidad (`ModuloFidelidadConfig`), lo cual es semánticamente razonable,
   pero el nombre del código de ruta (`GROWTH_ENGINE`) y el nombre de la
   clase que de verdad se muestra no coinciden, y hay una clase huérfana
   (`ModuloGrowthEngine`) que sugiere que hubo una intención de pantalla
   separada que nunca se completó o fue reemplazada sin limpiar el import.

5. **Doble punto de entrada a `CONFIG_HARDWARE`** (sidebar "Sistema →
   🖨️ Hardware" y menú superior "🖨️ Hardware → ⚙️ Configurar Dispositivos")
   — no es una ambigüedad de identidad (mismo código de ruta exacto en ambos
   casos), solo redundancia de UX a documentar, no a "arreglar" con lógica.

6. **Placeholder cuando falla un import (`_registrar_placeholder`)
   reutiliza el mismo código de ruta que la pantalla real habría usado.**
   Esto es correcto por diseño (permite que el sidebar siga funcionando y
   navegue a un aviso de error en vez de romper toda la app), pero significa
   que "la ruta existe" y "la pantalla realmente carga" son dos cosas
   distintas que el futuro `RouteRegistry` debe modelar explícitamente (hoy
   se resuelve con un `try/except` silencioso alrededor de la instanciación
   en `_conectar()`).

## 4. Mapeo sugerido hacia el catálogo objetivo (Inicio, Punto de Venta, Pedidos y Delivery, Clientes y Fidelización, Productos, Inventario, Transferencias, Compras, Procesamiento Cárnico, Mermas, Caja, Finanzas, RRHH, Activos, Inteligencia y Reportes, Configuración)

| Categoría objetivo | Código(s) actuales que consolida | Nota de consolidación |
|---|---|---|
| Inicio | `BIENVENIDA` + `DASHBOARD` (hoy sin botón) | Unificar en una sola pantalla de inicio con botón propio en el sidebar — hoy son 2 pantallas distintas y solo una es alcanzable por navegación directa |
| Punto de Venta | `POS` | 1:1, sin cambios |
| Pedidos y Delivery | `DELIVERY` + `WHATSAPP` | Hoy son 2 entradas separadas en "Comercial"/"Administración"; el catálogo objetivo las junta en una sola categoría — decidir si siguen siendo 2 pantallas bajo 1 categoría o se fusionan de verdad |
| Clientes y Fidelización | `CLIENTES_CRM` + `GROWTH_ENGINE` (alias de `ModuloFidelidadConfig`) + `TARJETAS_FIDELIDAD` | Hoy son 3 entradas separadas (2 en Administración, 1 en Operaciones); el objetivo las agrupa en una sola categoría de navegación |
| Productos | `PRODUCTOS` + `ETIQUETAS` (hoy en "Producción") | Etiquetas es más un sub-flujo de Productos que de Producción cárnica — revisar en FASE de rearquitectura |
| Inventario | `INVENTARIO` | 1:1 |
| Transferencias | `TRANSFERENCIAS` | 1:1 |
| Compras | `COMPRAS` + `COTIZACIONES` + `PLANEACION_COMPRAS` | Hoy 3 entradas en 2 secciones distintas (Comercial / Producción) |
| Procesamiento Cárnico | `PRODUCCION` | 1:1 |
| Mermas | `MERMAS` | 1:1 |
| Caja | `CAJA` | 1:1 |
| Finanzas | `FINANZAS_UNIFICADAS` | 1:1 (ya consolidó Tesorería + Proveedores en v13.4, según comentarios del código) |
| RRHH | `RRHH` | 1:1 |
| Activos | `ACTIVOS` | 1:1 |
| Inteligencia y Reportes | `INTELIGENCIA_BI` | 1:1 (ya consolidó BI + BI Pro + Decisiones según comentarios del código) |
| Configuración | `CONFIG_HARDWARE` + `CONFIG_MODULOS` + `CONFIG_SEGURIDAD` + `DISEÑADOR_TICKETS` | Hoy 4 entradas separadas en "Sistema" |

---

*Generado en FASE SHELL-0 (auditoría). No se modificó ningún archivo de aplicación.*
