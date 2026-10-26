# Alta de productos, mínimos de stock y notificaciones

**Rama:** `claude/erp-financial-bounded-context-uqxz6b` · **Comparación:** `main` · **Fecha:** 2026-10-26. Se comparó código directamente.

## Comparación real

| Función | `main`: `modulos/productos.py::DialogoProducto` | Rama actual antes del cambio: `frontend/desktop/modules/products/dialogs/product_form_dialog.py` | Decisión |
|---|---|---|---|
| Navegación | Pestañas General, Configuración, Precios, Receta, Referencias; al menos 650×500. | Formulario vertical de 460 px, capacidades y especie en la misma columna. | Pestañas General, Operación, Inventario e Imágenes; pie fijo y scroll canónico. |
| Imagen | Miniatura, seleccionar/quitar en el propio diálogo. | Galería externa solo al editar. | Selección y vista previa también durante el alta; guarda con el caso de uso existente tras crear el producto. La galería conserva eliminación, principal y fondo. |
| Código de barras | Campo directo. | Escáner, tipo, validación y generación interna, pero al final del formulario. | Se conserva el componente y queda en General; Enter de escáner no guarda el diálogo. |
| Precio y costo | Editables con `QDoubleSpinBox` en el alta; ruta directa. | Son propiedad de Precios/Costos, sin entrada en este formulario. | Conservar la propiedad actual. Queda pendiente un acceso explícito al flujo de Precio inicial tras activar el producto; no escribir precios desde Productos. |
| Mínimo | `productos.stock_minimo` global y `stock_min_local` legacy, tipo `REAL`. | La regla canónica `inventory_replenishment_rule` ya existe, pero no se presenta en el alta. | Captura de mínimo y objetivo por sucursal/almacén, `Decimal`, mediante `SetReplenishmentRuleUseCase` y permiso `INVENTARIO.reposicion.configurar`. |
| Avisos | Sin una cadena moderna de entrega desde la regla canónica. | Bandeja personal, campana, configuración de roles/teléfonos y cola WhatsApp existen; no había un evaluador conectado al mínimo. | Monitor periódico sobre saldos canónicos, reutilizando el notificador, su límite de repetición, bandeja y cola; centro con búsqueda y no leídas. |

## Flujo implementado

1. El usuario registra el producto; opcionalmente selecciona imagen y almacén de su sucursal, mínimo y objetivo. El maestro nace en `DRAFT` y el precio permanece fuera de este diálogo.
2. Productos guarda el maestro. Inventario guarda su propia regla solo con sesión activa y permiso específico. La imagen se agrega con el caso de uso existente. Un fallo secundario se muestra como **producto guardado, configuración pendiente**, y reintentar no crea de nuevo el maestro.
3. Cada cinco minutos el monitor lee reglas activas y stock **disponible menos reservado** por almacén. Solo considera productos `ACTIVE`, mínimo positivo y configuración de alertas encendida. Si el saldo es igual o menor al umbral, escribe en `notification_inbox` para roles configurados en esa sucursal y, cuando corresponde, en `product_whatsapp_outbox` para los teléfonos configurados. Una regla de almacén tiene identidad propia para deduplicar y limitar a un aviso por canal y destinatario en 24 horas. El estado de agotado tiene alerta crítica distinta.
4. La campana muestra avisos recientes. «Ver centro de notificaciones» permite leer el historial reciente, buscar, filtrar no leídas y acusar un aviso del usuario autenticado. La página de Productos → Notificaciones enseña entregas y reintentos WhatsApp.

## Limitaciones y siguientes pasos

- Los teléfonos WhatsApp se configuran como lista compartida en Productos → Configuración. **No existe un teléfono canónico por empleado/almacenista** para resolver WhatsApp automáticamente por sucursal. Los avisos internos sí se filtran por la sucursal de `usuarios` (los usuarios de alcance global reciben avisos de todas). Para un enrutamiento exacto por usuario/rol y sucursal, ampliar la agenda de empleados y la configuración de rutas canónicas sin duplicar otra tabla de usuarios.
- La alerta recorre reglas cada cinco minutos y vuelve a avisar a las 24 h mientras siga bajo mínimo; aún no hay alerta de recuperación ni reconocimiento/silencio individual de un incidente persistente. Se pueden añadir sobre el mismo registro de reglas y bandeja.
- La entrega por WhatsApp depende del microservicio, API y credenciales. El ERP encola y reintenta; las pruebas locales no demuestran una entrega a la red real.
- El centro muestra hasta 200 avisos recientes; una bandeja global con paginación servidor, acciones masivas y rutas contextuales requiere ampliar el QueryService y el shell.
- El guardado del maestro, la regla y la imagen son tres casos de uso propietarios separados. El diálogo informa un guardado parcial y permite reintento; no hay transacción distribuida entre contextos.

## Evidencia

- `tests/integration/inventory/test_stock_minimum_inbox.py`: alerta por almacén, deduplicación e inbox correcto.
- `tests/integration/products/test_product_form_flow.py`: alta, código automático, edición y reintento de mínimo sin duplicar maestro.
- `tests/ui/test_products_standard_dialog_adoption.py`: pie fijo, scroll y densidades/temas, adaptado a pestañas.
- `tests/ui/shell/test_notification_inbox_feed.py`: historial, filtro y lectura con aislamiento por usuario.
- Además se ejecutaron suites de reposición, agregación de stock, configuración de alertas y cola de WhatsApp existentes. Las pruebas usan dobles de envío; no certifican integración de red.
