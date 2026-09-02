# Fuga de lógica de negocio — Canal WhatsApp (FASE CERO — Auditoría)

Evidencia concreta (archivo:línea + fragmento) de dónde el canal WhatsApp calcula o decide
negocio que, según el prompt maestro, debería pertenecer a otro bounded context
(Pricing/Inventory/Orders/Quotes/Payments/Delivery/Customers/Loyalty). Se distingue
explícitamente **"ya delega" (cumple)** de **"calcula localmente" (fuga)**.

---

## 1. Precio y total de carrito — calculado en el propio modelo de conversación

**Archivo**: `whatsapp_service/models/context.py`
**Líneas**: 49-51, 114-115

```python
@property
def subtotal(self) -> float:
    return self.cantidad * self.precio_unitario
...
def total_pedido(self) -> float:
    return sum(i.subtotal for i in self.pedido_items)
```

**Clasificación**: fuga. `PedidoItem` (el modelo de línea de carrito del canal WhatsApp) es dueño de
la aritmética `cantidad × precio_unitario`, y `ConversationContext.total_pedido()` suma esas líneas
para producir el total que se muestra al cliente en cada paso del flujo (`resumen_pedido()`, línea
117-124) y el que se usa como `unit_price` al generar el link de MercadoPago (ver §4). El precio
unitario en sí viene de una lectura directa del catálogo (`ERPBridge.get_producto`, sin pasar por un
motor de pricing/promociones — ver §2), así que el total mostrado al cliente durante toda la
conversación es un cálculo 100% local, nunca confirmado contra el ERP hasta que `crear_pedido_wa`
recalcula server-side (`erp/bridge.py:472`, ver §3). Si el precio cambia entre el momento en que el
cliente arma el carrito y el momento de confirmación (por ejemplo por una promoción o cambio de
precio), el total que el cliente vio en el chat puede no coincidir con el que termina cobrándose —
riesgo de UX/disputa, no solo de arquitectura.

**Dueño correcto**: Orders (carrito) + Pricing (precio unitario vigente).

---

## 2. Precio unitario y disponibilidad — leído crudo del catálogo, sin motor de pricing ni de disponibilidad

**Archivo**: `whatsapp_service/flows/pedido_flow.py`
**Líneas**: 152-159, 162-168

```python
# Verificar stock
if prod.get("stock", 0) < qty:
    stock_disp = prod.get("stock", 0)
    await send_text(ctx.phone, f"⚠️ Solo hay *{stock_disp:.1f} {prod.get('unidad','kg')}* ...")
    return FlowResult(FlowState.PEDIDO_CANTIDAD)
...
item = PedidoItem(
    producto_id=prod["id"], nombre=prod["nombre"], cantidad=qty,
    unidad=prod.get("unidad", "kg"), precio_unitario=prod.get("precio", 0),
)
```

`prod` viene de `ERPBridge.get_producto()` (`erp/bridge.py:382-392`):

```python
SELECT p.id, p.nombre, p.precio,
       COALESCE(bi.quantity, p.existencia, 0) as stock, ...
FROM productos p LEFT JOIN branch_inventory bi ON ...
```

**Clasificación**: fuga parcial. El flujo lee `p.precio` directo de la tabla `productos` (sin pasar
por ningún servicio de pricing/promociones/listas de precio por cliente) y decide localmente si hay
"stock suficiente" comparando un snapshot leído en ese instante contra la cantidad pedida — sin
reservar inventario, sin considerar otras conversaciones concurrentes descontando el mismo stock. La
misma lectura cruda se repite en `flows/cotizacion_flow.py:69-70, 78-79`.

**Dueño correcto**: Pricing (precio vigente por producto/cliente/sucursal) e Inventory (disponibilidad
con reserva, no solo lectura de snapshot).

---

## 3. Total del pedido — recalculado (correctamente) en el fallback SQLite, pero SIGUE siendo WhatsApp quien lo calcula

**Archivo**: `whatsapp_service/erp/bridge.py`
**Líneas**: 472, 700

```python
total = sum(it["cantidad"] * it["precio_unitario"] for it in items)   # _crear_pedido_wa_impl
...
total = sum(it["cantidad"] * it["precio_unitario"] for it in items)   # _crear_cotizacion_wa_impl
```

**Clasificación**: fuga, con matiz. Cuando `ERP_API_URL`/`ERP_API_KEY` están configurados
(`self._use_api` verdadero), la creación del pedido pasa por `POST /api/v1/pedidos` y es el ERP quien
recalcula el total del lado servidor (comportamiento correcto — **cumple**). Pero el fallback SQLite
(que se activa automáticamente en `development`/`test`, y en `production` solo si
`_assert_sqlite_write_allowed` no aborta primero — línea 467, 695) hace el mismo cálculo de
`cantidad*precio` **dentro de código propiedad de WhatsApp**, usando el `precio_unitario` que el
propio flow ya venía cargando (§1-2), sin ninguna revalidación contra el catálogo en el momento de
guardar. Es decir: incluso en el camino "de respaldo", WhatsApp sigue siendo la autoridad de facto
del total de una venta.

**Dueño correcto**: Orders/Sales (el ERP, vía el endpoint REST, siempre — el fallback SQLite de
negocio no debería existir en absoluto según la regla explícita del propio proyecto,
`WHATSAPP_REFACTOR_PLAN.md` regla 3: *"En producción, WhatsApp no debe escribir negocio directo en
SQLite"*).

---

## 4. Total usado para generar el cobro (MercadoPago) — mismo total local, sin revalidar

**Archivo**: `whatsapp_service/flows/pago_flow.py`
**Líneas**: 80, 92-98

```python
total = ctx.total_pedido()
...
payload = {
    "items": [{"title": "Pedido SPJ POS", "quantity": 1, "unit_price": total, "currency_id": "MXN"}],
    ...
    "external_reference": ext_ref,
    ...
}
```

**Clasificación**: fuga. El monto que MercadoPago efectivamente va a cobrar (`unit_price`) sale del
mismo `ctx.total_pedido()` local de §1 — no se vuelve a consultar `ventas.total` (el valor que el ERP
ya guardó al confirmar el pedido, potencialmente recalculado) antes de generar el link de pago. Si
hubo cualquier ajuste server-side entre la confirmación del pedido y la generación del link (por
ejemplo un ajuste de peso o una promoción aplicada), el link cobra el monto que el chat calculó, no
el monto real de la venta.

**Dueño correcto**: Payments, usando el total canónico ya persistido en `ventas`/`cotizaciones`, no
un total recalculado en memoria de la conversación.

---

## 5. Reglas de anticipo y autorización de crédito — motor completo duplicado dentro de `ERPBridge`

**Archivo**: `whatsapp_service/erp/bridge.py`
**Líneas**: 860-893

```python
def calcular_anticipo_rules(self, cliente_id, total, items=None) -> Dict:
    credito = self.get_credito_disponible(cliente_id)
    if credito >= total:
        if items:
            for it in items:
                ...
                regla = self.db.execute("""
                    SELECT porcentaje FROM anticipo_reglas
                    WHERE tipo='categoria' AND activo=1
                    AND categoria = (SELECT categoria FROM productos WHERE id=?)
                    ORDER BY porcentaje DESC LIMIT 1
                """, (prod_id,)).fetchone()
                if regla:
                    pct = float(regla[0]) / 100.0
                    return {"requiere": True, "monto": round(total * pct, 2), "razon": "producto_especial"}
        return {"requiere": False, "monto": 0.0, "razon": "credito_suficiente"}
    regla_monto = self.db.execute("""
        SELECT porcentaje FROM anticipo_reglas WHERE tipo='monto' AND activo=1
          AND ? BETWEEN COALESCE(monto_minimo,0) AND COALESCE(monto_maximo,999999)
        ORDER BY porcentaje DESC LIMIT 1
    """, (total,)).fetchone()
    pct = float(regla_monto[0]) / 100.0 if regla_monto else 0.5
    return {"requiere": True, "monto": round(total * pct, 2), "razon": "sin_credito"}
```

**Clasificación**: fuga grave — este NO es un fallback de última instancia, es el camino que
efectivamente se ejecuta hoy por defecto. `whatsapp_service/erp/business_orchestrator.py:161` y
`:218` lo llaman directamente (`self.erp.calcular_anticipo_rules(...)`), y `BusinessOrchestrator` está
activo por defecto: `_check_flag("whatsapp_advanced_enabled")` devuelve `True` si la fila del feature
flag no existe (`business_orchestrator.py:55-63`, `except Exception: return True`). Esta función:
consulta el crédito disponible del cliente (autorización de crédito), consulta reglas de anticipo por
categoría de producto y por rango de monto directamente contra las tablas `anticipo_reglas`, calcula
el porcentaje y **redondea un monto de dinero** — sin pasar en ningún momento por el motor oficial que
el propio código del proyecto documenta como existente
(`core/services/anticipo_service.py:AnticipoCotizacionService`, mencionado explícitamente en
`whatsapp_service/application/confirm_order_use_case.py:96-123` como "camino profesional"). Es decir:
**hay dos implementaciones del mismo cálculo de negocio (anticipo/crédito) en el repo**, una oficial
(`AnticipoCotizacionService`) y una duplicada dentro de `ERPBridge`, y es la duplicada la que
`BusinessOrchestrator` usa.

**Dueño correcto**: Payments/Credit (política de anticipo) — vía `AnticipoCotizacionService` o el
puerto que lo reemplace (`PricingPort`/`CreditPort`/`PaymentPolicyPort`, ya anunciados como pendientes
en `WHATSAPP_AUDIT.md` §13 desde 2026-05-28 y todavía no construidos).

---

## 6. Fallback de porcentaje de anticipo — segundo cálculo de dinero, cuando NO hay orchestrator

**Archivo**: `whatsapp_service/application/confirm_order_use_case.py`
**Líneas**: 91-141 (fallback final en 134-141)

```python
pct = self._get_default_advance_pct(default=30.0)
return {
    "requiere": pct > 0,
    "pct": pct,
    "monto": round(total * pct / 100.0, 2),
    "razon": "fallback_pct_default",
    "exento": pct <= 0,
}
```

**Clasificación**: fuga (de último recurso, pero real). El propio comentario del archivo (líneas
39-43) es explícito sobre la intención: *"No se debe hardcodear 50% ni consultar columnas inventadas
en WhatsApp... se delega a AnticipoCotizacionService cuando está disponible"* — pero el código
igualmente conserva un cuarto camino (`hasattr(erp, "requiere_anticipo")` → `AnticipoCotizacionService`
→ `erp.calcular_anticipo_rules` legacy → este fallback final) que sí calcula el monto localmente si
las tres opciones anteriores fallan o no existen. Es una fuga defensiva, documentada como tal, pero
sigue siendo WhatsApp decidiendo cuánto anticipo cobrar.

**Dueño correcto**: mismo que §5.

---

## 7. Verificación de stock y generación automática de orden de compra

**Archivo**: `whatsapp_service/erp/bridge.py` (líneas 938-959) y
`whatsapp_service/erp/business_orchestrator.py` (líneas 320-350)

```python
# bridge.py — _verificar_stock_items_impl
stock_actual = float(stock_row[0]) if stock_row else 0.0
falta = max(0.0, cantidad - stock_actual)
resultado.append({**it, "stock_actual": stock_actual, "falta": falta})

# business_orchestrator.py — _verificar_y_generar_oc
for it in items_check:
    if it.get("falta", 0) > 0:
        oc_id = self.erp.generar_orden_compra(
            producto_id=it["producto_id"], cantidad=it["falta"],
            sucursal_id=self.sucursal_id,
            notas=f"OC automática por pedido WA #{venta_id}",
        )
```

**Clasificación**: fuga. Un pedido por WhatsApp con faltante de stock genera automáticamente una
orden de compra (`INSERT INTO ordenes_compra`, `erp/bridge.py:999-1004`) sin ningún criterio de
negocio más allá de "faltante > 0" — no considera proveedor preferente más allá de
`productos.proveedor_id`, no considera lead time, no aplica ningún umbral mínimo de compra. Esta es
una decisión de reabastecimiento/compras tomada íntegramente desde el canal conversacional.

**Dueño correcto**: Procurement/Inventory (decisión de generar OC automática, si el negocio la quiere,
debería vivir en el motor de compras/forecast, disparada por un evento `INVENTORY_SHORTFALL_DETECTED`
o similar — no ejecutada directamente por WhatsApp).

---

## 8. Ajuste de peso — subtotal recalculado en dos lugares distintos del árbol WhatsApp

**Archivo A**: `whatsapp_service/erp/adjustment_approval.py`, línea 81

```python
pending_subtotal = float(data.get("pending_subtotal") or (pending_qty * float(data.get("precio_unitario") or 0)))
```

**Archivo B (lado ERP, pipeline legacy)**: `pos_spj_v13.4/core/services/pedidos_whatsapp_service.py`,
líneas 44-68

```python
def ajustar_pesos(self, pedido_id, pesos: dict) -> float:
    total_nuevo = 0.0
    for item_id, peso in pesos.items():
        ...
        subtotal = round(float(peso) * precio, 2)
        total_nuevo += subtotal
        self.db.execute("UPDATE pedidos_whatsapp_items SET cantidad_pesada=?, subtotal=? WHERE id=?", ...)
    total_nuevo = round(total_nuevo, 2)
    self.db.execute("UPDATE pedidos_whatsapp SET total=?, estado='pesando' WHERE id=?", (total_nuevo, pedido_id))
```

**Clasificación**: fuga en ambos, con matiz distinto:
- **Archivo A** (`adjustment_approval.py`, pipeline nuevo/delivery): el fallback de `pending_subtotal`
  es defensivo (solo se usa si el campo no vino precalculado), y el total del pedido en sí **sí** se
  delega correctamente después a `OrderTotalService(self.db).recalculate_order_total(order_id)`
  (línea 109) — es decir, el cálculo final de autoridad está bien ubicado (ERP-side, servicio
  dedicado); solo el subtotal de línea individual tiene un cálculo local de respaldo.
- **Archivo B** (`pedidos_whatsapp_service.py`, pipeline legacy paralelo): aquí **no hay** delegación
  a ningún servicio de totales — el cálculo y el `UPDATE` del total del pedido completo se hacen
  directamente en este servicio, sin motor de pricing ni de totales intermedio.

**Dueño correcto**: Orders/Delivery (recalculo de totales tras ajuste de cantidad/peso) — ya existe un
servicio dedicado (`OrderTotalService`) para el pipeline nuevo; el pipeline legacy (archivo B) no lo
usa en absoluto.

---

## 9. Resumen — mapa de fugas por bounded context objetivo

| Bounded context dueño | Qué debería decidir | Dónde lo decide hoy WhatsApp | Severidad |
|---|---|---|---|
| Pricing | Precio unitario vigente por producto/cliente/promoción | `ERPBridge.get_producto()` lee `productos.precio` crudo (§2) | Media — no hay motor de pricing en absoluto en el camino WA |
| Inventory | Disponibilidad con reserva concurrente | `pedido_flow.py` compara contra snapshot de stock (§2), `bridge.py._verificar_stock_items_impl` (§7) | Media |
| Orders | Total del carrito/pedido | `PedidoItem.subtotal` + `ConversationContext.total_pedido()` (§1), fallback SQLite en `bridge.py` (§3) | Alta — es el cálculo que ve el cliente y el que se usa para cobrar (§4) |
| Payments/Credit | Requiere anticipo, monto, autorización de crédito | `ERPBridge.calcular_anticipo_rules` (§5, camino activo por defecto), fallback en `confirm_order_use_case.py` (§6) | **Crítica** — hay dos motores de anticipo/crédito duplicados en el repo y el canal usa el no-oficial |
| Procurement | Generar orden de compra por faltante | `business_orchestrator._verificar_y_generar_oc` (§7) | Media-Alta — mueve dinero/compromiso con proveedor sin pasar por Compras |
| Payments | Monto a cobrar vía link de pago | `pago_flow._generar_link_pago` (§4) | Alta — dinero real cobrado a un tercero (MercadoPago) basado en un total no revalidado |
| Orders (recalculo por ajuste) | Recalcular total tras ajuste de peso | `adjustment_approval.py` (parcial, delega bien al final) vs `pedidos_whatsapp_service.py` (no delega, §8) | Media (nuevo) / Alta (legacy) |

**Patrón que ya cumple** (para contraste, no todo es fuga): `flows/delivery_flow.py` delega
correctamente a `erp.delivery.schedule()` sin recalcular nada; `core/delivery/infrastructure/whatsapp_delivery_notifier.py`
solo formatea montos que recibe como parámetro, nunca los calcula; `webhook/whatsapp.py` y
`middleware/hmac_validator.py` no contienen lógica de negocio, solo seguridad de transporte.
