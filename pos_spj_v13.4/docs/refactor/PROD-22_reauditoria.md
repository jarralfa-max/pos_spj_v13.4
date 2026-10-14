# PROD-22 — Re-auditoría del prompt maestro de Productos

Fecha: 2026-10-09/10 · Migraciones: 324, 325 · Base: copia de `data/spj_pos_database.db`

PROD-0..20 se construyó y cerró el 2026-07-30 (ver `products_acceptance_report.md`)
y PROD-21 (imagen sin fondo) el 2026-10-09. Esta vuelta midió el estado real contra
el prompt maestro en lugar de reconstruir.

## 1. Hallazgos medidos

| # | Severidad | Hallazgo | Evidencia |
|---|---|---|---|
| 1 | P0 seguridad | Ningún rol tenía un solo permiso granular de Productos (68 otorgables, 0 otorgados). El puente concedía aprobar/activar con `editar`, y **todo código sin mapeo con la sola vista**: cajero y solo_lectura podían habilitar productos por sucursal (lo que vende el POS), gestionar especies/cortes/códigos, crear internos, aprobar importaciones externas, cambiar configuración y alertas de WhatsApp, y ver la bitácora. | `rol_permisos` real: 5 códigos gruesos por rol |
| 2 | P0 funcional | El microservicio WhatsApp leía la tabla legacy `productos` (vacía): su menú y catálogo de pedidos no encontraban ningún producto. | `productos`: 0 filas; `products`: 11 |
| 3 | P1 pantalla | El catálogo no cabía a 1366×768 (11 botones en una fila, buscador aplastado) y, por ser la página más ancha, imponía scroll horizontal a **todas** las secciones. Las acciones sin selección no hacían nada. «Activar» se habilitaba con `editar`. | capturas sobre la copia real |
| 4 | P1 pantalla | Backend completo sin pantalla: clasificación cárnica (12 especies sembradas, **0 regiones y 0 cortes** porque no había dónde capturarlos), códigos de barras, perfiles de vida útil/calidad/logística, bitácora de auditoría. | grep presenter/páginas |
| 5 | P1 datos | Marcar un código como principal no desmarcaba el anterior; el POS une por `is_primary=1` y el producto aparecería dos veces en las tarjetas. Reasignar el mismo código dejaba auditoría y evento de algo que no pasó. | prueba sobre copia real |
| 6 | Legacy §48 | El ratchet de lectores de `productos` decía 42; medido: **7**, de ellos 6 código sin llamadores y 1 docstring. Las 18 tablas legacy y 3 dependientes, vacías. | `_current_consumers()` |

## 2. Qué se corrigió

**Permisos (§37-39).** Migración 324 siembra la matriz por rol; el puente
(`permission_bridge.py`) sólo traduce lo que el permiso grueso significa (ver →
consultar, crear → alta, editar → mantener la ficha, eliminar → bajas). Aprobar,
activar, bloquear, descontinuar, clasificación cárnica, surtido por sucursal,
internos, catálogos externos, configuración, notificaciones, WhatsApp, costo de
referencia y bitácora exigen su código granular. Lo no mapeado se deniega.

| Rol | Antes (efectivo) | Ahora |
|---|---|---|
| system_owner / admin | todo (admin por comodín) | todo (68) |
| gerente | todo vía `editar` | 64: todo salvo configuración del módulo, notificaciones, WhatsApp, reglas de código |
| almacen | aprobaba y activaba vía `editar` | 43: captura y mantenimiento técnico; sin aprobar/activar/habilitar por sucursal |
| cajero / solo_lectura | gestionaban surtido, cortes, códigos… vía `ver` | sólo consulta (sin bitácora) |

**WhatsApp.** `whatsapp_service/erp/catalog_sql.py`: una sola consulta de catálogo
con el criterio del POS (activo + vendible + no interno; precio de la lista BASE
activa, sucursal primero, vigente; existencia de `inventory_balances`). Repuntados
el bridge (menú, categorías, producto, verificación de stock, anticipo por
categoría, proveedor preferido vía `supplier_products.preferred`), el
`ProductMatcher`, la confirmación de pedido y el router de entregas.
Verificado en la copia real: 10 productos ofrecibles con los precios del POS.

**Pantallas (§41-42).** Sin duplicar (regla del usuario: el menú no repite el
expediente):
- Catálogo: búsqueda + 4 acciones + «Más acciones» (variantes, recetas,
  rendimientos, despiece, combos, unidades de compra, imágenes, **códigos de
  barras**, **calidad/vida útil/logística**); filtro de **familia** (cárnicos,
  internos, materiales, subproductos, servicios) en vez de tres secciones con la
  misma tabla. Mínimo nativo 786 px (cabe en el shell a 1366×768).
- Nueva sección **Clasificación cárnica**: especies, regiones anatómicas y cortes
  jerárquicos (canal → primario → secundario → porcionado), con hueso/grasa/grado.
- Nueva sección **Auditoría**: bitácora con filtro, usuario y detalle antes/después.

**Legacy (§48).** Borrados por cero consumidores: `ProductCatalogService`,
`Create/Update/Deactivate/RestoreProductUseCase`, `product_commands.py`,
`ProductRepository`, `BranchProductRepository`, `QrContainersReadRepository`,
`InventoryBalanceQueryService` (su docstring nombraba como únicos llamadores
archivos ya borrados) y las lecturas legacy de `ProductQueryService`. Ratchet
`test_products_legacy_consumers_ratchet.py`: **allowlist vacía**. Migración 325
retira el esquema legacy. `scripts/verify_tables.py` ahora exige `products` e
`inventory_balances`.

## 3. Verificación

- Nuevos: `test_products_granular_permissions_seed.py` (26),
  `test_drop_legacy_products_schema.py` (4), `test_prod22_master_data_screens.py` (13),
  `whatsapp_service/tests/test_catalog_sql_canonical.py` (6).
- Suites de Productos + POS + guardrails de UI: sin fallos nuevos; los 19 que
  fallan importan paquetes legacy ya borrados (`core`, `modulos`, `repositories`).
- WhatsApp: 667 pasan en su suite propia, 0 fallos nuevos contra la línea base de
  HEAD; `tests/test_wa_bridge.py` reescrito sobre el esquema canónico.
- Copia de la base real: 324 y 325 aplicadas, integridad OK, sin violaciones de FK.
  Las 3 vistas rotas que quedan (`v_negative_inventory`, `v_whatsapp_config`,
  `v_flujo_caja_diario`) ya estaban rotas antes y no son de Productos.
- Arranque desde cero: 0 migraciones pendientes, 0 tablas legacy, identidad UUIDv7 OK.

## 4. Pendiente (honesto)

- ~~El microservicio WhatsApp sigue usando `float` para precio y existencia~~ →
  cerrado en §6.
- La matriz de roles de la 324 es la misma política que Precios; si se quiere otra
  (p. ej. que almacén apruebe), se ajusta en Configuración → Permisos.
- ~~Las alertas por WhatsApp no se reintentan sin conexión~~ → cerrado en §6
  (cola en el ERP).
- Los parámetros del §45 que son reglas de dominio obligatorias (especie requerida,
  aprobación de recetas, segregación) NO se volvieron configurables: el §7 las
  prohíbe relajar. Sólo se agregaron parámetros que el código lee. → §6: el
  usuario decidió «sólo endurecer»; se agregaron exigencias que bloquean activar.

## 5. Pendientes cerrados (2026-10-10, migraciones 326-329)

| Pendiente | Qué quedó | Hallazgo de paso |
|---|---|---|
| Clasificación cárnica del producto | «Más acciones → Clasificación cárnica y peso variable…»: categoría, región y corte filtrados por la especie; reclasificar exige motivo; eventos `MEAT_PRODUCT_CLASSIFIED/…_CHANGED` (migr. 326) | Peso variable: rango vacío se aceptaba como 0–0; `''` como unidad violaba la FK |
| Bandeja de aprobación | Sección **Aprobaciones técnicas**: versiones de receta, rendimiento, despiece y combo en borrador, revisión o aprobadas, de todos los productos | Despiece y combos no guardaban creador: quien capturaba aprobaba y activaba (migr. 327, segregación aplicada) |
| Calidad de datos | Sección **Calidad de datos**: puntaje 0-100 y pendientes por producto con las MISMAS reglas de las alertas §35, más «cárnico sin clasificar» y «vendible sin imagen»; botón «Corregir» abre el diálogo correcto | En la base real: 11 productos, promedio 62 (10 sin clasificar ni imagen, 1 sin perfil de calidad) |
| Catálogo externo | Sección **Catálogo externo**: buscar (Open Food Facts), revisar, aprobar/rechazar, importar con tipo/unidad/categoría | No había ninguna fuente registrada (migr. 328); volver a buscar regresaba a «pendiente» lo ya revisado y devolvía ids inexistentes; quien traía el registro lo aprobaba |
| Notificaciones | Alertas §35 cableadas por fin: a la campana de los roles configurados y, las de alto impacto, por WhatsApp a teléfonos; sección **Notificaciones** con el historial (teléfonos enmascarados) | Nunca se disparaban: nadie pasaba servicio ni destinatarios, y una misma lista mezclaba ids de usuario y teléfonos |
| Configuración del módulo | Sección **Configuración**: tipo y unidad por omisión de la ficha, alertas, WhatsApp; guardado en el catálogo gobernado (versionado y auditado), cada bloque con su permiso (migr. 329) | — |

Tests nuevos: `test_prod22_meat_product_and_approvals.py` (9),
`test_prod22_external_catalog_and_quality.py` (8), `test_prod22_settings_and_alerts.py`
(10), más segregación en `test_product_cutting.py`, `test_product_bundles.py` y
`test_external_catalog_use_cases.py` (cuyos casos «mismo usuario captura y aprueba»
se corrigieron: eso es justo lo que el §39 prohíbe).

## 6. Lo que se dejó deliberadamente y quedó cerrado (2026-10-10, migraciones 330-331)

Decisiones del usuario: «sólo endurecer», «bloquear la activación», «cola en el
ERP», «todo el microservicio a Decimal».

| Tema | Qué quedó |
|---|---|
| Parámetros del §45 | Productos → Configuración → **Exigencias para activar**: clasificación cárnica, vida útil en perecederos, perfil de calidad en cárnicos y rango de peso variable. Encendidas, la activación (y el desbloqueo) se rechazan con «Faltan datos para activar: …»; la consulta de preparación y el caso de uso usan la MISMA regla. Sólo aplican donde tienen sentido (vida útil a perecederos; clasificación/calidad a cárnicos). Las prohibiciones del §7 no tienen clave. Tolerancia de rendimiento por omisión para perfiles nuevos (migr. 330). |
| Reintentos de WhatsApp | `product_whatsapp_outbox` (migr. 331): la alerta se encola; el servicio de fondo `products.whatsapp_outbox` de la shell la drena cada 60 s con espera 1→240 min y 8 intentos; sección **Notificaciones → Cola de WhatsApp** con estado, intentos, último error y «Reintentar» (permiso + auditoría). |
| `float` en el microservicio WhatsApp | `whatsapp_service/domain/money.py` (`to_decimal` vía texto, `quantize_money` HALF_UP, `dumps_decimal`/`loads_decimal`). 50+ archivos convertidos: precios, totales, anticipos, cantidades, existencias, pesos, porcentajes y puntajes de confianza/coincidencia en Decimal; tiempos y plazos en enteros (s/ns). El JSON hacia ERP, Mercado Pago y Ollama lleva Decimal como **número exacto**; el estado persistido (contexto, idempotencia, outbox, recordatorios) y los webhooks se leen con Decimal. El catálogo devuelve precio/existencia en texto → Decimal (`catalog_row`). Guarda por tokens: ningún `float` ni literal decimal en el código del servicio. |

Límite honesto: SQLite sólo suma en doble precisión; la existencia agregada del
catálogo se redondea a 4 decimales en texto antes de llegar a Python (las cantidades
se guardan con ≤ 4). FastAPI serializa sus respuestas con su propio codificador.

Verificación: `test_prod22_activation_requirements.py` (5),
`test_prod22_whatsapp_outbox.py` (7), `test_prod22_settings_and_alerts.py` (10),
composición de la shell (6); microservicio: 678 pasan, mismas 7 fallas y 9 errores
de colección que antes del cambio (preexistentes: ciclo de vida, firma de servicio,
imports `whatsapp_service.`), +5 de la guarda; pruebas WA del ERP idénticas a la
línea base.
