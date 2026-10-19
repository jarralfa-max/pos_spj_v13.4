# UI/UX Design — escritorio, web y móvil

Especificación objetivo desde cero basada en patrones del código existente. Las cuatro aplicaciones administrativas web se diseñan en [WEB_APPS.md](WEB_APPS.md); la consola WhatsApp en [WHATSAPP_SERVICE.md](WHATSAPP_SERVICE.md).

## 1. Objetivo y principios

Diseñar una aplicación de operación diaria para cajeros, almacén, compras, producción, administración y gerencia. El usuario ve folios, nombres, cantidades, unidades, fechas y estados; UUIDv7 sólo en diagnóstico técnico. Los cambios sensibles se explican antes de confirmar y permanecen auditables. Pantallas y mensajes en español; accesibles por teclado, mouse y lector de códigos.

El código incluye `frontend/desktop/modules/*`, shell, componentes `page_header.py`, `kpi_bar.py`, `tables.py`, `search_input.py`, `search_selector.py`, `product_search_box.py`, `customer_search_box.py`, `searchable_combo.py` y tema bajo `frontend/desktop/themes/`. Reutilizarlos; este documento prescribe su uso, sin afirmar que cada pantalla actual ya cumple.

## 2. Arquitectura de información

| Grupo | Navegación principal | Tarea inicial |
| --- | --- | --- |
| Comercial | POS, Clientes, Precios, Fidelidad, Pedidos/Delivery | Buscar cliente/producto, vender y consultar historial. |
| Abastecimiento | Compras, Logística, Transferencias, Inventario | Orden o compra directa, recolección, recepción y ubicación. |
| Operación | Producción cárnica, Calidad, Mermas | Seleccionar lote y esquema, transformar y liberar. |
| Control | Caja, Finanzas, RR. HH., Activos, BI | Cierre, conciliación, aprobaciones y métricas. |
| Sistema | Configuración, Seguridad, Dispositivos, Integraciones, Actualizaciones | Alcance, permisos, credenciales y diagnóstico. |

Navegación por capacidad instalada + feature flag + permiso. El acceso directo a ruta también verifica backend. Si logística sólo está disponible dentro de Compras en la implementación actual, mostrarla allí hasta completar un shell independiente y su capability; no duplicar la pantalla.

## 3. Patrón de página y componentes

- Encabezado `PageHeader`: título, breadcrumb, sucursal/almacén y acciones permitidas.
- Filtros persistentes para sucursal, fechas, almacén y estado; chips activos y acción «Limpiar filtros».
- KPIs desde QueryService mediante `KPIBar`; cada KPI enlaza al listado filtrado.
- Listado `StandardTable` con paginación, orden, columnas descriptivas expansibles, cantidades alineadas a la derecha y menú contextual. Selección conserva identidad aun al filtrar/refrescar.
- Búsqueda unificada: `ProductSearchBox`/`CustomerSearchBox` o `SearchInput` con debounce, estado cargando, resultados con nombre/SKU/unidad/sucursal y accesibilidad de teclado. Selección se guarda explícitamente en el modelo del diálogo; no depender del `currentItem` de una lista que puede vaciarse al cerrar.
- Diálogos `StandardDialog`: título, resumen, errores junto al campo, acción primaria clara y cancelación segura. Validar antes de cerrar; nunca aceptar y luego avisar en la página de que faltó producto.
- Tema desde tokens/QSS existentes, sin colores locales. Verde JUANIS como identidad visual sólo donde lo resuelva el tema; color por sí solo nunca expresa aceptación o peligro.

## 4. Pantallas críticas

### Compras → Recolección en origen

Asistente de 4 pasos: **Origen** (OC, compra directa o borrador sin documento según política) → **Carga** (contenedores, árbol y líneas) → **Control** (pesos, evidencia, temperatura, sello) → **Despacho** (resumen, responsable, custodia). Al elegir «sin documento», mostrar que el embarque no crea inventario ni CxP hasta la regularización. Permitir «Registrar contenedor» desde pantalla autónoma y desde el contexto del embarque. Mostrar folio del embarque y código corto del contenedor, con QR verificable.

### Recepción

Vista de tres columnas: documento esperado, conteo/peso escaneado, resultado. Diferencias explícitas por línea; destino **aceptado / cuarentena / rechazado**, lote y ubicación. Guardar borrador sin contabilizar; «Confirmar recepción» muestra cantidades que ingresarán a stock y motivos de diferencia. Doble confirmación sólo para excepción material.

### Producción directa

Pantalla «Transformar ahora»: buscar producto/lote fuente con disponibilidad real; elegir esquema y versión; mostrar expectativa por corte según porcentaje sobre peso de entrada; capturar peso real por salida y merma; resumen masa/costo; ejecutar. Campos reales comienzan vacíos o 0, nunca precargados con esperado. Una orden planificada permanece como ruta distinta pero comparte caso de ejecución. Si falta perfil o lote, estado accionable y enlace al catálogo/almacén. Separar `factor de cantidad` de `porcentaje de rendimiento` en la etiqueta y fórmula visibles.

### POS

Mantener el patrón visible actual: barra superior con cajero, sucursal y caja; izquierda búsqueda/escáner/categorías y producto con existencia; derecha cliente, carrito, subtotal, descuentos, impuestos, puntos y cobro. Peso estable y unidad antes de añadir pieza a granel. En checkout mostrar beneficio aplicado, margen permitido, puntos a ganar y motivo de bloqueo si un vale/crédito impide combinación. «Reconstruir físicamente» exige existencia de todos los cortes, autorización y confirmación; bundle virtual sólo calcula componentes para venta. Pago y ticket muestran folio, logo/branding, código de barras/QR opcionales según plantilla configurable; reimpresión identifica original y operador.

### Caja y Finanzas

Caja: apertura, efectivo esperado, conteo ciego, movimientos, corte X y cierre Z en secuencia; diferencia y autorización visibles antes de entregar custodia. Finanzas: documentos origen y estado de contabilización, conciliación, partidas pendientes/rechazadas; no confundir «venta cobrada» con «asiento contabilizado».

## 5. Estados comunes

| Estado | Mensaje y acción |
| --- | --- |
| Cargando | Skeleton o progreso; evitar acción duplicada. |
| Vacío | Explicar filtro y ofrecer «Crear» o «Limpiar filtros». |
| Sin permiso | Mostrar permiso/capacidad requerida sin revelar información sensible. |
| Sin conexión | Distinguir consulta local, borrador y operación confirmada. |
| Pendiente de sincronizar | Número de operaciones, último intento y botón reintentar. |
| Conflicto | Valor local vs remoto, responsable y acción de resolución. |
| Bloqueado | Razón concreta (lote cuarentena, margen, turno cerrado, sello roto). |
| Éxito | Folio comercial, siguientes acciones y vínculo al registro. |

## 6. Accesibilidad y validación

Orden de tabulación previsible, foco tras escaneo/diálogo, atajos rotulados, etiquetas de lector de pantalla, contraste y textos no cortados a 1366×768. Vista de 1920×1080 y escalado Windows; claro/oscuro y cambio de tema en caliente. Ensayos con teclado y lector, compra directa sin PO, recepción con diferencia, producción parcial y venta por peso. Cronometrar tareas reales y registrar dónde el usuario abandona o corrige valores.

**Referencias de implementación:** `frontend/desktop/modules/purchasing/pages/logistics_related_page.py`, `frontend/desktop/modules/meat_processing/dialogs.py`, `frontend/desktop/modules/sales_pos/`, `frontend/desktop/modules/cash_register/`, `frontend/desktop/components/`.

## 7. Design system compartido

Una taxonomía y tokens de diseño versionados: color semántico, espaciado, tipografía, densidad, foco, elevación, iconos, tamaños mínimos, fechas y unidades. Adaptadores PyQt y web comparten especificación, no necesariamente código de widgets. Documentar variantes `default/hover/focus/disabled/loading/error`, teclado y lector, estados de acceso, validación en línea y patrones de confirmación. No copiar QSS a CSS ni recrear componentes en cada módulo; pruebas visuales y accesibilidad por tema y resolución.

| Familia | Requisito transversal |
| --- | --- |
| Búsqueda/selector | Id capturado al elegir, resultados diferenciados, cancelación de requests obsoletos, teclado y entrada por escáner. |
| Tabla/detalle | Columnas/scope configurables, drill-down, densidad adaptable, totales calculados en consulta; exportar con permiso. |
| Formulario | Validación por campo, autosave borrador cuando aplique, warnings de cambios concurrentes, unidades visibles y confirmación de importe/peso. |
| Dashboard | KPI con definición, rango, comparación, refresco, watermark y vista vacía; charts con paleta accesible. |
| Autorización | Modal con motivo, aprobador, impacto, vigencia; denegación clara, no PIN hardcode en UI. |
| Estado financiero | «Pendiente de pago», «Pagado», «Pendiente de contabilizar» y «Conciliado» diferenciados. |

## 8. Mapa de experiencia por dispositivo

| Dispositivo | Casos preferentes | Restricción UX |
| --- | --- | --- |
| Terminal POS Windows | Carrito, báscula, cobro, caja, ticket | Flujo sin mouse y tolerancia a red caída; información esencial visible a 1366×768. |
| Escritorio de gestión | Productos, compras, finanzas, producción, RR. HH. | Tablas densas, múltiples filtros, aprobaciones y trazabilidad. |
| Web administrativa | CRM, Compras, Finanzas, BI | URLs compartibles con scope, formularios responsivos, accesibilidad, datos actuales con watermark. |
| Móvil de almacén/logística | QR, peso, fotos, custodia, movimientos, recepción | Grandes targets táctiles, trabajo con guantes, offline y confirmación de sincronización. |
| Móvil de repartidor | Ruta, entrega, evidencia, cobro | Progresión guiada y bloqueo de entregas duplicadas. |
| Consola WhatsApp web | Bandeja, handoff, plantillas, métricas y configuración | Estado de envío distinto de entrega; historial de consentimiento. |

## 9. Wireflow textual de las cuatro web apps

- **CRM:** Inicio → Lead/cliente buscado → Ficha 360 → Actividad/oportunidad → Cotización con precio y stock → Aprobación → Pedido; una conversación WhatsApp puede abrir bandeja lateral sin crear un cliente duplicado.
- **Compras:** Necesidad → Requisición → RFQ/comparativo → Aprobación → OC o compra directa → Embarque/recepción → Match factura → CxP; el usuario ve diferencia esperada/recibida/aceptada.
- **Finanzas:** Pendientes → Hecho origen → Propuesta de asiento o conciliación → Revisión → Publicación → Periodo; enlaces de reversa y error no editan historial.
- **BI:** Catálogo métrica → Filtros y frescura → Dashboard → Drill-down autorizado → Documento origen o exportación auditada; no extrapolar datos offline como definitivos.

## 10. Investigación con usuarios y criterios de aceptación

Probar tareas con cajero, comprador, almacenista, producción y contador de al menos dos sucursales. Métricas: tiempo y errores por operación, búsquedas sin resultado, correcciones de peso, doble clic, aprobaciones mal asignadas, tasa de sincronización y capacidad para explicar diferencia de caja/margen. Aceptar UX si completan escenarios críticos sin asistencia, entienden cuándo una acción es sólo borrador y no confunden folio con UUID. Registrar hallazgos y revisar el diseño antes de implementar pantalla adicional.
