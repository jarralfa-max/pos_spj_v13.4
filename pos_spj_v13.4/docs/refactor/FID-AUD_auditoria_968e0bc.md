# FID-AUD — Respuesta a la auditoría de Fidelidad 968e0bc

Fecha: 2026-10-22 a 2026-10-24. Migraciones: **346** (valor del punto por movimiento, acumulación diferida a crédito, margen mínimo), **349** (lotes físicos de cupones y vales y sus permisos). Cambios sin commit, en la rama `claude/erp-financial-bounded-context-uqxz6b`.

## Hallazgos

| ID | Severidad | Respuesta | Prueba |
|---|---|---|---|
| FID-01 | Crítica | El canje de puntos y el guardado de la venta son **una** transacción. Si guardar la venta falla, los puntos regresan. | `test_loyalty_audit_968e0bc.py::test_points_come_back_if_saving_the_sale_fails` |
| FID-02 | Alta | Cada movimiento guarda `point_value` y `monetary_value` (migr. 346). Un reintento del mismo canje devuelve el descuento original aunque el valor del punto haya cambiado entre intentos. | `test_retry_after_a_point_value_change_keeps_the_original_discount` |
| FID-03 | Alta | Margen mínimo protegido por categoría, con excepción por producto (`loyalty_margin_floors`). Ningún beneficio se aplica sobre un producto sin costo confiable; la cajera puede pedir autorización en caliente. Los puntos se recortan al margen disponible. | `test_budget_policy_*`, `test_points_are_trimmed_*`, `test_margin_floor_*` |
| FID-04 | Alta | Una sola base elegible para la vista previa y la venta confirmada. Pagar con vale no acumula. Lo vendido a crédito acumula **al cobrarse** (decisión del usuario), una vez por aplicación de cobro; una devolución antes del cobro reduce lo pendiente. | `test_paying_with_vouchers_never_earns` y siguientes |
| FID-05 | Alta | La corrección manual exige documento, respeta topes y la aprueba otra persona. El escritorio sólo ofrece la corrección controlada. | `test_manual_*`, `test_the_desktop_offers_only_the_controlled_correction` |
| FID-06 | Media | Las consultas y los comandos exigen un actor con permiso. Un comando no puede reclamar una sucursal fuera de la sesión. | `test_member_profile_requires_*`, `test_commands_cannot_claim_*` |
| FID-07 | Media | Menú reagrupado en las vistas que propone la auditoría, ver más abajo. | `test_fidelidad_workspace.py`, `test_route_sidebar_icons.py` |
| FID-08 | Media | Sin `dashboard.ver`, el Resumen explica por qué no hay indicadores en vez de fallar. | `tests/unit/loyalty/test_overview_page_partial_permissions.py` |
| FID-09 | Media | «Configuración» pasó a llamarse **Economía del punto** y se movió a *Programa vigente*. Muestra en vivo, mientras se edita, cuánto regresa cada punto, cuánto hay que comprar para el primer canje y qué tope del ticket se paga con puntos (`ProgramEconomy`, dominio puro). | `test_program_settings_and_seed.py::test_the_page_explains_the_program_economy_*` |
| FID-10 | Media | Ya estaba implementado: `loyalty_sales_tick` corre al arrancar y como tarea periódica del shell, así que no depende de que el POS esté abierto. La prueba obsoleta `tests/test_loyalty_event_wiring_phase7.py` se reemplazó por `tests/integration/loyalty/test_loyalty_live_wiring.py`. | ese archivo |

Dos defectos más aparecieron durante la ronda y quedaron corregidos:

- **Orden del canje en Ventas:** primero se verifica que el cliente tenga puntos y después el margen. Antes, un cliente sin puntos recibía un mensaje de margen.
- **Doble conteo en la proyección de costo:** la salida de producción se contaba dos veces en la existencia previa (113.33 en lugar de 120). `on_hand_before` ahora excluye la salida de la propia orden.

### Menú (FID-07)

| Grupo | Rutas |
|---|---|
| Resumen | Resumen |
| Programa vigente | Programas, Reglas de acumulación, Niveles, Economía del punto |
| Miembros | Perfil de miembro, Membresías, Puntos |
| Beneficios | Recompensas, Combinación de beneficios |
| Campañas | Campañas, Retención, Retos y misiones, Referidos, Cumpleaños |
| Control | Alertas, Antifraude, Auditoría, Contabilidad |
| Cupones y vales *(especializado)* | Cupones, Vales, **Lotes de vales y cupones** |
| Sorteos *(especializado)* | Campañas de sorteo, Sorteo y ganadores |
| Tarjetas de fidelidad *(especializado)* | sin cambios |

## Ampliación: lotes físicos de vales y cupones, con canje configurable

**Ciclo.**

1. **Borrador:** sólo papel.
2. **Por aprobar.**
3. **Aprobado:** lo aprueba **otra persona**. Se generan las piezas, una instancia por pieza, en estado `ISSUED`. Todavía no se pueden canjear y no hay efecto contable.
4. **Impreso:** pliego PDF carta 2×5 con Code 128. Reimprimir da los **mismos** códigos y deja constancia.
5. **Activo:** los vales reciben su saldo en el libro y se publica `VOUCHER_ISSUED` con `batch_id` y `funding_source`. Aquí, y no antes, Finanzas reconoce el pasivo.
6. **Cancelado:** posible antes de activar.

**Código de pieza.**

- Forma: `VAL`/`CUP` + 16 caracteres Base32, derivados con HMAC del secreto de la instalación (`commercial_instrument_secrets`), del id de la pieza y de su versión.
- Sólo se guardan la huella SHA-256 y un prefijo de 6 caracteres; el código completo existe únicamente mientras se imprime.
- El folio (`VAL7F3A-00001`) es legible y **no sirve para canjear**.
- Retirar una pieza extraviada rota su código: el impreso deja de servir y se puede imprimir la reposición sola.

**Reglas por pieza.** Se fijan al aprobar, en `voucher_instance_rules`, y cambiar el lote después no revaloriza piezas entregadas:

- un solo uso o varios usos, con tope de canjes;
- tope porcentual por venta, calculado sobre el total antes o después de descuentos;
- en un solo uso, qué pasa si el saldo no cabe en la venta:
  - *debe usarse completo*: se rechaza el canje;
  - *el sobrante se pierde*: se asienta como transacción `EXPIRE` y se publica `VOUCHER_EXPIRED`, de modo que Finanzas libera esa parte del pasivo;
- quién lo paga: promocional o compensación (sujetos al margen protegido de FID-03), o tercero;
- sucursales y vigencia por día.

Los cupones son siempre de un solo uso. **Los vales prepagados no se emiten por lote**: se venden en caja, pieza por pieza.

**Caja.**

- El cajero escanea la pieza como si fuera un producto. El cupón va al carrito como descuento y el vale al cobro como forma de pago.
- Un vale personal exige a su titular en la venta.
- Escanear dos veces el mismo vale en una venta no cuenta como segundo canje.
- Los rechazos se explican en lenguaje de cajero: pieza no activa, retirada, fuera de vigencia o de otra sucursal.

**Permisos.** `GROWTH_ENGINE.lote.ver/crear/aprobar/imprimir/revocar`, sembrados por la 349 con el criterio de la 290:

- dueño y admin: todos;
- gerente: ver, crear e imprimir.

Aprobar, activar, cancelar y revocar quedan fuera para el gerente, porque revocar rota el código.

**Pruebas.**

- `tests/unit/commercial_instruments/test_instrument_batch_domain.py`: 11 pruebas.
- `tests/integration/loyalty/test_instrument_batches.py`: 15 pruebas, incluidas las de la pantalla real del POS.
- `tests/integration/loyalty/test_instrument_batches_page.py`: 2 pruebas.
- `test_loy29_migrations.py::TestSeed349`.

**Base real.** Las migraciones 347, 348 y 349 corrieron dos veces sobre una copia de la base real; el resultado:

- son idempotentes y `integrity_check` sale ok;
- no hay violaciones de llave foránea en las tablas nuevas;
- los permisos quedaron sembrados en `admin`, `gerente` y `system_owner`.

El motor completo **se detiene antes, en la 345** (contrato financiero born-clean de FIN-ERP), porque esa base trae 39 tablas financieras anteriores al contrato. Eso es de la ronda de Finanzas, no de ésta.

## Pruebas reparadas en el camino

- `tests/integration/sales/test_sales_pos_coupons_vouchers.py` se quedaba **colgada** desde FID-03. El producto del fixture no tenía costo, así que aplicar un cupón abría el diálogo modal de autorización de margen. El fixture ahora da costo ($50) y neutraliza ese diálogo. Ésta era la corrida de regresión que se atoraba al 74 %.
- `tests/integration/sales/test_sales_pos_loyalty.py` tenía la misma cuelga al canjear puntos. Su fixture ahora da costo ($30, para que el tope del 50 % quepa en el margen) y neutraliza el diálogo.

## Pendiente (no hecho)

- Rediseño completo por tareas de FID-07/09:
  - guía de configuración inicial con simulación de compra (efectivo, crédito, vale, puntos, cupón, margen bajo) antes de activar reglas;
  - catálogo único de recompensas y descuentos con costo real.

  Esta ronda reagrupó el menú y explicó la economía; no rehízo las páginas genéricas de registros.
- Impresión de pliegos en térmica (sólo hay PDF).
- Vales financiados por tercero: su recuperación contra el proveedor no se modela todavía.
