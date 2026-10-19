# Recuperación funcional POS — implementación (2026-10-17)

## Alcance y estado
Se trabaja en `claude/erp-financial-bounded-context-uqxz6b`, sobre HEAD `32cfbf27`.
El árbol tenía 363 modificaciones previas. Se preservan; este informe describe la
recuperación POS y no atribuye todo el diff del repositorio a esta intervención.
No se abrió ni modificó la base operativa. Las integraciones usan SQLite en memoria.

## Cambios
- Checkout: reserva para tres filas según densidad, selector de cliente en popup,
  resumen compacto y dos filas de acciones persistentes. Cobrar/F9, suspender/F6,
  reanudar/F7 y cancelar/F8 permanecen visibles. Operaciones adicionales en “Más”.
  Canje sigue accesible junto al cliente cuando corresponde.
- Descuento individual: selección por UUID, acción en Opciones, reutilización de
  `ApplyLineDiscountUseCase` con importe cero. No se crea otro motor de descuentos.
  Permiso `DISCOUNT_APPLY` validado también en backend. La repetición no altera
  otra vez los importes; conserva descuentos de otras líneas y de venta.
- ProductCards: `InteractiveSummaryCard` reutilizable, selección, foco, Enter/Espacio,
  animación de sombra sin mover geometría, opción de movimiento reducido y colores
  del tema. Inventario sigue clasificado por `SalesCatalogQueryService`.
- Báscula: registro canónico de Configuración, asignación de estación/sucursal,
  adaptadores USB-COM Rhino y SICS, worker Qt sin SQL, estado estable/vencido/error,
  validación de cantidad y vigencia en agregar y editar, importe desde Pricing.
- Monitor: proyección pública autorizada, impuestos, unidades, descuento por línea,
  puntos estimados/acreditados, lectura actual; estados de cobro, agradecimiento y
  nueva venta. Errores del monitor se registran sin impedir el cobro.
- Publicidad: región independiente durante carrito; pausa en cobro/agradecimiento;
  la actualización del carrito conserva la reproducción.
- Configuración: `customer_display.*`, `sales.scale_stale_seconds`, herencia por
  ámbitos permitidos. Migración 344 registrada en el motor; añade secciones nuevas
  sin habilitar las que ya estaban expresamente desactivadas.
- Instalador: imports explícitos de QtMultimedia, QtMultimediaWidgets y pyserial
  en `installer/windows/spj.spec`. No se ha construido ni instalado un EXE.

## Servicios conservados
SalesAuthorizationPolicy, SalesUnitOfWork/outbox, ApplyLineDiscountUseCase,
SalePricePreviewService/Pricing, LoyaltyAccrualEvaluator y ledger de fidelidad,
Device Management, ConfigurationReader, CustomerDisplayQueryService,
SalesCustomerDisplayClient, AdvertisingQueryService, TicketDesignQueryService,
repositorios canónicos y componentes/tokens existentes. No se importó el POS legacy,
ni se añadieron consultas SQL a widgets.

## Archivos principales
- `frontend/desktop/modules/sales_pos/`: workspace, presenter, composition,
  customer_display_window, scale_monitor; componentes cart_table, checkout_panel,
  customer_panel, totals_card, actions_panel, cashier_bar, catalog_panel, product_grid;
  diálogos weight_confirmation_dialog y payment_dialog.
- `frontend/desktop/components/cards.py`, `themes/qss_builder.py`.
- `backend/application/sales/`: scale_reading_service, queries/scale_configuration_query,
  queries/customer_display_query_service, dto, use_cases/cart_use_cases, pricing_resolution.
- `backend/infrastructure/hardware/scale_gateway.py`.
- `backend/infrastructure/integrations/sales_customer_display_client.py`,
  `sales_loyalty_client.py`; repositorio de transacciones de fidelidad.
- `backend/application/customer_display/queries/display_preferences_query.py`,
  `backend/application/settings/catalog.py`, enums de display/dispositivos,
  caso de uso y diálogo de perfiles de Dispositivos.
- `migrations/standalone/344_sales_display_recovery.py`, `migrations/engine.py`,
  `installer/windows/spj.spec`.
- Pruebas: `tests/unit/sales_pos/test_functional_recovery.py`, `test_live_scale.py`,
  `test_customer_display_window.py`; integraciones de ventas, display y Configuración;
  `tests/visual/capture_sales_recovery.py`.

## Protección y validación
Resultados de cierre, 2026-10-18:
- Suite funcional ampliada: **332 passed**, 119.80 s, en
  `sales_recovery_test_results_final.txt`.
- Seguimiento intermedio de las regresiones: **65 passed**, 71.52 s.
- Configuración/asignaciones/adaptador de sesión y flujos POS: **64 passed**, 114.64 s.
- Worker de báscula y controles/geométricas: **18 passed**, 18.26 s.
- Validación posterior de monitor, preferencias heredadas, estaciones, presentación
  monetaria y flujos: **134 passed**, 97.48 s. Estas ejecuciones se superponen;
  sus cantidades no se suman como pruebas únicas.
- Cierre/reapertura de ventana secundaria y geometría, tras el ajuste final:
  **45 passed**, 9.57 s, una advertencia, en `sales_recovery_layout_lifecycle_results.txt`.
- Arquitectura segmentada: **26 passed, 1 failed**, 52.83 s. Falla la regla global
  de `CREATE/ALTER TABLE` fuera de migrations en archivos ajenos a esta recuperación;
  se conserva la evidencia y la comparación de base en `schema_guard_baseline.json`.
  De los 41 archivos señalados, 40 ya exceden la allowlist en el HEAD exterior;
  el restante es `branding_schema.py`, trabajo local anterior ajeno a este cambio.
- El intento de arquitectura global se interrumpió antes de terminar; había cinco
  errores de preparación y un skip. No se reporta esa suite como aprobada.
- Capturas: **32 geometrías del shell verificadas** (16 a DPI 1 y 16 a DPI 1.5),
  sin scroll de página, con tres filas completas y cuatro acciones principales
  dentro del viewport. Incluye área cliente lógica,
  no la barra de tareas de un monitor físico.
- Sintaxis de `spj.spec` compilada correctamente; no se ejecutó PyInstaller.

Los nuevos casos de lectura futura, sin zona horaria, inestable, invalidación en
vuelo y perfil USB reprodujeron cinco fallos antes de sus correcciones.
La prueba de sucursales y la de migración también fallaron antes de corregirse.
Una ejecución ampliada detectó dos regresiones (canje oculto y código de estación
no único), posteriormente corregidas. Consultar los archivos `sales_recovery_*results*.txt`
para resultados ejecutados; no confundir los registros iniciales con el final.

## Commits
No se realizaron commits: los archivos intervenidos mezclan cambios anteriores del
usuario y los de esta recuperación. Se propone separar, revisando hunks:
1. geometría y tarjetas; 2. báscula/configuración/validadores; 3. monitor/publicidad/
branding/puntos; 4. pruebas, evidencias e instalador. No se añade todo el árbol al index.

## Límites
La aceptación física de la BAR-8RS, dos monitores reales, codecs del equipo y
un instalador construido sigue pendiente. Los informes específicos delimitan
qué fue probado y qué requiere ese equipo.

## Seguimiento de descuentos y monitor — 2026-10-18
El descuento personalizado y los porcentajes rápidos aplicaban un descuento de
venta; la tabla sólo proyectaba descuentos de línea. Se expone
`Sale.sale_level_discount` en `SaleDTO` sin recalcularlo en UI, y se muestra una
fila «Descuento de venta», sin identidad de producto. Opciones ofrece «Quitar
descuento de venta», mediante el mismo ApplySaleDiscountUseCase con monto cero.
La prueba verifica que conserva el descuento de línea y actualiza el total.
La columna Desc. ya no se oculta automáticamente; «Quitar descuento» sigue
retirando el de la línea seleccionada. Se conservan permisos y rutas canónicas.

Los ajustes del monitor, selección de campañas y resultados del seguimiento
están en `customer_display_enhancement_report.md`. No se modificó la base
operativa ni se crearon commits mezclando cambios preexistentes.
