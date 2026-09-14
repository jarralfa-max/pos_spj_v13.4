# Iconos de las barras laterales de módulos

Fecha: **2026-09-14**. Corrección de «las sidebar de los módulos usan el mismo
icono en todas las tabs».

## Causa y resultado

El catálogo de IconProvider contenía los identificadores, pero 11 módulos
construían sus filas con `add_section(label)` y sus grupos sin icono explícito.
`SideNav` usaba entonces `Icons.HOME` en todas esas opciones. Otros seis módulos
tenían listas propias que no dibujaban el `entry.icon` declarado; cuatro
sustituían el título por una inicial al contraerse.

Los **17 módulos afectados** ahora transmiten iconos semánticos desde sus rutas
y composiciones reales. Caja, Clientes/CRM, Fidelidad, Tarjetas y Activos
incorporan metadatos explícitos para **139 rutas y 36 grupos**. Finanzas, RR. HH.
y Compras declaran también sus iconos. Productos, Inventario y Precios aprovechan
los catálogos existentes y preservan su construcción perezosa de páginas.

Mermas, Cárnicos, Pedidos/Reparto, BI, Transferencias y Configuración reutilizan
SideNav dentro de sus widgets existentes, con el toggle interno oculto para
conservar sus controles externos. Sus señales, roles de datos, permisos,
contadores y selección mantienen el contrato anterior. Las barras contraídas
muestran iconos; los grupos conservan su indicador de expansión y muestran su
icono semántico en modo reducido. Sus menús muestran el icono de cada destino.

El QSS no causaba la repetición. Esta corrección transmite los datos visuales al
componente canónico y conserva los colores del tema. No modifica reglas de
negocio, servicios, consultas, identidad, rutas o permisos.

## Protección

- Pruebas Qt de icono dibujado, tema, colapso, menú, señal de navegación, página
  activa, filtros de permisos, estado sin acceso, badges y carga perezosa.
- En los cinco módulos por rutas se comparan también los píxeles de los iconos
  hermanos: distintos identificadores no bastan si comparten el mismo dibujo.
- Guardrail AST para llamadas `add_section`/`add_group` sobre instancias y
  subclases de SideNav/ModuleSidebar. Rechaza iconos omitidos, nulos o vacíos;
  conserva la comprobación de nombres registrados.

Resultados reproducibles, XML/logs, hashes y límites de las capturas en el
[manifiesto de validación](evidence/module_sidebar_icons/validation.json).
Las capturas de navegación se pueden comparar en el
[visor](evidence/module_sidebar_icons/index.html).

La regresión operacional conserva un fallo previo:
`test_legacy_produccion_menu_entry_and_module_are_not_touched_yet` busca
`interfaz/menu_lateral.py`, ausente también en HEAD. No se restaura esa ruta
legacy para satisfacer la prueba. El resultado de los segmentos afectados no
equivale a una suite global verde ni a la migración completa de todas las
pantallas del ERP.

## Archivos de esta corrección

Modificados en `frontend/desktop/modules/`:

- `finance/finance_view.py`, `hr/hr_view.py`.
- `purchasing/navigation.py`, `purchasing/purchasing_module_shell.py`.
- `products/products_view.py`, `products/composition.py`.
- `inventory/inventory_view.py`, `pricing/pricing_workspace.py`.
- `widgets/*_sidebar_widget.py` de losses, meat_processing, orders_delivery,
  business_intelligence, transfers y configuracion.
- `*_routes.py` y `*_workspace.py` de cash_register, customers_crm, fidelidad,
  tarjetas_fidelidad y assets.

Pruebas creadas: `tests/ui/test_finance_hr_sidebar_icons.py`,
`test_purchasing_sidebar_icons.py`, `test_operational_sidebar_icons.py`,
`test_route_sidebar_icons.py` y `test_module_sidebar_icon_visuals.py`.
Pruebas actualizadas: `tests/architecture/test_icon_catalog.py` y el lector de
metadatos de Finanzas en `tests/integration/suppliers/test_supplier_ui.py`.
Documentación: este informe, evidencia, guía de adopción, informe del punto 5
y auditoría general. Archivos eliminados: **ninguno**.

Siguiente paso del trabajo general: continuar el punto elegido por el usuario;
esta corrección no declara una auditoría nueva del QSS global ni completa la
integración de los recursos oficiales de marca.
