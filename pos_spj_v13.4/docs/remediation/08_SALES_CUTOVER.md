# Fase 7 (inicio): retirada de consumidores del SalesService legacy

Fecha de validación: 2026-09-06. Rama: `claude/erp-financial-bounded-context-uqxz6b`.
Parte de: `ead5176a`.

## Alcance de esta fase

§11 exige migrar todos los consumidores productivos de `core/services/sales_service.py`
(1615 líneas) y después eliminarlo. Esta fase **no completa el corte**: retira los dos
consumidores que estaban **fuera** del clúster legacy, que es la parte que se podía cerrar
con verificación real.

| Momento | Puntos de consumo |
| --- | ---: |
| Antes | 6 (en 5 archivos) |
| Ahora | **4 (en 4 archivos, todos dentro de `core/` legacy)** |

Lo relevante no es el número sino **cuáles**: `backend/` y `api/` ya no importan el
servicio legacy en código. La dependencia que quedaba de la capa canónica hacia la legacy
está cortada.

## Consumidor 1 — un import muerto en la API

`api/routers/ventas.py:129` importaba `SalesService` dentro de `anular_venta()` y **no lo
usaba nunca**. El propio código lo delataba: un comentario decía "Obtener sales_service del
container" y otro "Usar sales_service si está disponible en el scope", pero el cuerpo hace
SQL directo y jamás toca el servicio. Se retira el import.

**Hallazgo separado que NO crea esta limpieza y que queda abierto**: ese endpoint anula una
venta con

    UPDATE ventas SET estado='cancelada', notas=? WHERE id=?

sin generar reversa contable, sin devolver inventario, sin liberar reservas y sin publicar
ningún evento. Es una violación de §11 y §31 (todo impacto financiero necesita asiento) que
existía antes y sigue existiendo. Se documenta aquí y se deja anotada en el propio archivo
para que la próxima persona que lo lea no la confunda con algo que este cambio introdujo.
Corregirla exige el caso de uso canónico de reversa, no un parche en el router.

## Consumidor 2 — 1615 líneas importadas por una cadena estática

`backend/infrastructure/integrations/sales_receipt_client.py` importaba el servicio legacy
completo para obtener `SalesService._default_ticket_template()`: una plantilla HTML por
defecto, estática, sin ninguna lógica de venta.

Se movió a `core/engines/template_engine.py` como `default_ticket_template()`, que es su
hogar natural — es una plantilla por defecto y ese módulo es quien la renderiza. Ambos
consumidores (el propio `SalesService` y el cliente de recibos) la importan ahora desde
ahí. No se dejó ningún alias ni wrapper de compatibilidad (§48).

La plantilla se movió **íntegra**, verificado por contenido: conserva las 7 variables que
su prueba exige (`{{nombre_empresa}}`, `{{sucursal_nombre}}`, `{{folio}}`, `{{fecha}}`,
`{{cajero}}`, `{{total}}`, `{{forma_pago}}`) y los 491 caracteres originales.

Tres pruebas la referenciaban. Dos se repuntan al nombre nuevo. La tercera
(`test_sales_service_never_raises_on_missing_template`) comprueba por **texto fuente** que
la ruta de venta tiene fallback en vez de lanzar `ValueError`; su aserción se actualiza a
`"default_ticket_template()" in text`, conservando la intención exacta: no se relaja, se
repunta al símbolo real.

## Los 4 consumidores que quedan, y por qué no se cierran aquí

    core/app_container.py:37,426              construye self.sales_service
    core/services/cotizacion_service.py:73    construye uno propio
    core/services/sales/unified_sales_service.py:112   construye uno propio
    core/services/ventas_facade.py:67         factory

Los cuatro son **legacy llamando a legacy**. `unified_sales_service.py` está a su vez
deprecado y vallado tras `ALLOW_LEGACY_UNIFIED_SALES_SERVICE`, y `app_container.py` es el
Composition Root que §5 manda eliminar de todas formas.

Cerrarlos no es un ejercicio de imports: depende del cutover de `AppContainer` (fase 5) y
de que `backend/application/sales/` cubra los flujos que `cotizacion_service` y
`ventas_facade` todavía delegan. Hacerlo por partes ahora dejaría el sistema con dos rutas
de venta simultáneas, que es justo lo que §49 prohíbe.

## Pruebas y evidencia

```text
./scripts/ci/run_domain_tests.sh ventas
```

| Momento | Resultado |
| --- | --- |
| Antes (código de HEAD) | 5 failed, 30 passed |
| Después | 5 failed, 30 passed |

**Los mismos 5 fallos, verificados como preexistentes por sustitución directa**: se
respaldaron los 4 archivos modificados, se colocaron en su lugar las versiones de `HEAD`,
se ejecutó la suite (mismos 5 fallos), y se restauraron los cambios. No es una inferencia
a partir del total: es la misma lista de nombres en ambas corridas. Los fallos son de
configuración de mocks (`assert res.venta_id == 100` recibiendo un `MagicMock`) y de flujo
de Mercado Pago, ajenos a la plantilla.

```text
python -m pytest tests/integration/test_sale_ticket_default_template.py \
  tests/integration/test_ticket_contains_branch_header.py \
  tests/unit/test_sales_receipts.py -q
```
Resultado: **19 passed**.

## Riesgos residuales

El corte de Ventas sigue **abierto**. `sales_service.py` conserva sus 1615 líneas, su SQL
directo, su dinero en float (34 conversiones, el mayor foco del sistema — ver
`07_MONEY_DECIMAL.md`) y sus flags `ALLOW_LEGACY_*` con fecha de eliminación vencida
(`2026-06-30`).

El endpoint `anular_venta` sigue cancelando ventas por SQL directo sin reversa contable.

Los 5 fallos preexistentes de la suite `ventas` no se han diagnosticado; sólo se ha probado
que no los causa este cambio.

## Siguiente fase

El cutover de `AppContainer` (fase 5), que es el que desbloquea los 4 consumidores
restantes. Sin él, cualquier intento de eliminar `sales_service.py` deja el arranque roto.
