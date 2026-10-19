# Auditoría de recuperación POS — 2026-10-17

## Base y protección

Rama: `claude/erp-financial-bounded-context-uqxz6b`, HEAD `32cfbf27`.
363 cambios locales preexistentes; se preservan. La referencia remota local está
7 commits por delante. `main` local (`28d96911`) diverge de `origin/main`
(24 propios / 1077 remotos); no existe merge-base disponible con HEAD.
Comparación realizada con `git diff main HEAD` y `git show main:…`, sin merge.
Las referencias remotas no se han actualizado por red.

Al contrastar la deuda de arquitectura se detectó además un `.git` anidado dentro
del paquete, en `main` / `80dec503`, cuyo índice espera otra carpeta de paquete.
Ese índice informa muchas rutas ausentes y no representa el checkout usado para
esta recuperación. No se modificó ninguno de los índices ni se cambió de rama.
Toda comparación Git de este informe usa explícitamente el repositorio exterior
(`git -C <raíz exterior> ...`); ejecutar Git desde el paquete puede seleccionar
el repositorio anidado. Esto refuerza la decisión de no crear commits mezclados.

## Matriz funcional verificada antes de implementación

| Capacidad | main | Árbol actual | Brecha / clasificación | Reutilización / acción |
|---|---|---|---|---|
| Carrito | `modulos/ventas.py`: mínimo `3 * 48 + 28` | `CartTable` sin mínimo; `CheckoutPanel` da stretch 1 | Necesita refactor: `ModuleLayout` envuelve todo en `PageViewport`, permitiendo desplazar acciones | Compactar cliente/resumen/acciones, reservar filas por métricas y evitar overflow externo del POS |
| Descuento individual | `_quitar_descuento_por_uid` | `ApplyLineDiscountUseCase`, `Sale.apply_line_discount` | Backend implementado, eliminación desconectada de UI | Usar monto cero por UUID y permiso DISCOUNT_APPLY, preservar cupones/canje separados |
| Tarjetas | `ProductCard` | `ProductGrid._build_card` reemplaza `mousePressEvent` | Parcial: badge semántico existe; falta teclado/selección/transición | Especializar `SummaryCard`, tokens y señales Qt |
| Inventario | colores en tarjeta | `SalesCatalogQueryService` clasifica; ProductGrid traduce | Funcional; crítica y baja comparten warning | Conservar clasificación canónica, mejorar semántica de alerta |
| Báscula | `peso_actual`, timer, hardware legacy | `ScaleGateway` sólo Protocol, Stub y Manual; `WeightCaptureDialog` sólo entrada manual | Ausente en runtime POS: no existe adaptador físico actual | Reutilizar registro Device Management y gateway; no recuperar imports legacy |
| Peso/importe | muestra lectura y producto pendiente | `price_preview` canónico existe; diálogo no muestra importe | Parcial | Preview Decimal desde Pricing; caducidad y estabilidad independientes del carrito |
| Puntos | tarjeta histórica | `TotalsCard` y `SalesPosPresenter.points_to_earn` vía Loyalty | Funcional, presentación mejorable | Distinguir estimación y acreditación; nunca inferir acreditación por total |
| Monitor | pantalla legacy | `CustomerDisplayWindow`, `QtCustomerDisplayGateway`, `SalesCustomerDisplayClient` | Parcial: CART/IDLE/PAYMENT_PENDING/THANK_YOU existen pero UI no proyecta el ciclo de cobro | Extender proyección pública, conservar filtro por layout |
| Multimedia | publicidad | `AdvertisingQueryService`, repositorios, ventana imagen/video, timer workspace | Funcional sólo en reposo; video sin recuperación de error | Reutilizar playlists e impresiones; regiones separadas |
| Branding | marca histórica | LOGO en enum pero desactivado por defecto; infraestructura branding local ya existe | Desconectado | Resolver recursos oficiales desde Configuración |
| Seguridad | permisos legacy | SalesAuthorizationPolicy, permisos canónicos, UoW/outbox | Implementado | Ninguna mutación directa desde widget; fallos del monitor aislados |

## Rutas verificadas

- `frontend/desktop/modules/sales_pos/sales_pos_workspace.py`: `_refresh`, `_on_checkout_requested`, `_push_customer_display`, `_on_ad_timer_tick`.
- `frontend/desktop/modules/sales_pos/components/checkout_panel.py`: `CheckoutPanel.__init__`, `render_sale`.
- `frontend/desktop/modules/sales_pos/components/cart_table.py`: `CartTable.set_lines`, `_refresh_line_actions`.
- `frontend/desktop/components/module_layout.py`: `ModuleLayout.__init__` crea `PageViewport` para todo el cuerpo.
- `backend/application/sales/use_cases/discount_use_cases.py`: `_DiscountUseCase._run`, `ApplyLineDiscountUseCase.execute`.
- `backend/domain/sales/entities.py:328`: descuento propio de línea separado de `sale_level_discount`, `coupons`, `loyalty_redeemed_amount`.
- `backend/application/sales/queries/customer_display_query_service.py`: proyección autorizada, sin unidad/descuento por línea/impuestos/puntos/báscula.
- `backend/infrastructure/integrations/sales_customer_display_client.py`: `_build_content`, bootstrap y layouts persistidos.
- `backend/domain/device_management/value_objects/weight_reading.py`: lectura temporal; `policies/scale_stability_policy.py`: estabilidad configurable.
- `backend/infrastructure/hardware/scale_gateway.py`: frontera existente, sin controlador físico.

## Limitaciones previas

El Python global no tiene pytest. Existe `.venv/Scripts/python.exe` externo con
pytest y PyQt5: se usa para validación. No se modifica ninguna base operativa.
No se afirma conexión física, reproducción de codec ni instalación de EXE sin pruebas.
