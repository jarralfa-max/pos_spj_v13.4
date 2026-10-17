# UI/UX Design — SPJ ERP/POS

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
