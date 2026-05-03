# Plan de Mejora — pos_spj ERP v13.4
## Resultado de Auditoría Técnica Completa (2026-04-29)

---

## Resumen Ejecutivo

La auditoría completa del repositorio identificó **6 bugs críticos que causan pérdida silenciosa de datos en producción**, junto con 14 deficiencias de arquitectura que comprometen la escalabilidad. Este plan define las correcciones en orden estricto de prioridad, con criterios de aceptación medibles por fase.

**Impacto actual estimado:**
- Cualquier usuario con contraseña hasheada con bcrypt **no puede iniciar sesión**
- Todos los pedidos de WhatsApp **pierden sus líneas de detalle** (tabla errónea)
- Cada recepción de compra por QR **triplica el stock** en BD
- El motor de producción cárnica lanza `AttributeError` en toda operación
- Las anulaciones de venta **no generan asiento contable** — inventario invisible al audit
- La reserva de stock tiene race condition — overselling posible en alta concurrencia

---

## Fase A — Parches de Emergencia (Semana 1, 2–3 días)

> **Criterio de entrada:** Sistema en producción con usuarios reales.  
> **Criterio de salida:** Los 6 bugs críticos corregidos y verificados con tests.

### A1. BCrypt: verificación siempre falla

**Archivo:** `pos_spj_v13.4/security/auth.py` línea 105–113

**Bug:**
```python
# ROTO — SHA256 nunca produce string "$2b$..."
if stored.startswith(("$2b$", "$2a$", "$2y$")):
    return (__import__("hashlib").sha256(raw.encode()).hexdigest() == stored)
```

**Corrección:**
```python
def verify_password(raw: str, stored: str) -> bool:
    if not raw or not stored:
        return False
    if stored.startswith(("$2b$", "$2a$", "$2y$")):
        if not HAS_BCRYPT:
            return False
        try:
            return bcrypt.checkpw(raw.encode("utf-8"), stored.encode("utf-8"))
        except Exception:
            return False
    # Legacy texto plano
    return raw == stored
```

**Aceptación:** Test con usuario bcrypt migrado autentica correctamente.

---

### A2. ERPBridge: tabla `detalle_ventas` no existe

**Archivo:** `whatsapp_service/erp/bridge.py` líneas 153, 175, 304

**Bug:**
```python
self.db.execute("INSERT INTO detalle_ventas ...")   # tabla inexistente
self.db.execute("SELECT ... FROM detalle_ventas ...") # tabla inexistente
```

**Corrección:** Reemplazar las 3 ocurrencias:
```python
# Buscar: detalle_ventas
# Reemplazar: detalles_venta
```

**Aceptación:** Pedido completo por WhatsApp guarda líneas en `detalles_venta`; query de historial retorna filas.

---

### A3. Triple actualización de stock en recepción QR

**Archivo:** `pos_spj_v13.4/modulos/compras.py` (bloque post-commit de recepción QR)

**Bug:** La recepción llama a:
1. `PurchaseService.receive_order()` — actualiza stock
2. Loop UI sobre ítems — actualiza stock nuevamente
3. Bloque post-commit `app_svc.registrar_compra()` — actualiza stock por tercera vez

**Corrección:** Eliminar el bloque 3 (post-commit). Si se necesita el asiento contable, llamar solo `finance_service.registrar_egreso()` sin el componente de inventario:
```python
# ELIMINAR el bloque post-commit que llama a app_svc.registrar_compra()
# MANTENER solo el registro de egreso de tesorería:
finance_service.registrar_egreso(
    concepto=f"Compra OC #{orden_id}",
    monto=total,
    categoria="compras"
)
```

**Aceptación:** Recepción de 10 unidades → `productos.existencia` incrementa exactamente 10.

---

### A4. `DatabaseWrapper` sin propiedad `.conn`

**Archivo:** `pos_spj_v13.4/core/db/connection.py`

**Bug:** `DatabaseWrapper.__slots__ = ("_conn",)` — `ProductionEngine` accede a `self.db.conn` → `AttributeError`.

**Corrección:** Agregar propiedad al final de la clase `DatabaseWrapper`:
```python
@property
def conn(self) -> sqlite3.Connection:
    return self._conn
```

**Aceptación:** `ProductionEngine.open_batch()` ejecuta sin `AttributeError`; `close_batch()` completa transacción atómica.

---

### A5. GrowthEngine es `None` en SalesService

**Archivo:** `pos_spj_v13.4/core/app_container.py` (~línea 509)

**Bug:** `SalesService` se construye en línea ~180 con `growth_engine=None`; `GrowthEngine` se inicializa en línea ~501.

**Corrección:** Agregar asignación posterior a la inicialización de GrowthEngine:
```python
# Inmediatamente después de: self.growth_engine = GrowthEngine(...)
if hasattr(self, 'sales_service') and self.sales_service is not None:
    self.sales_service.growth_engine = self.growth_engine
```

**Aceptación:** Venta POS genera puntos de lealtad; `growth_engine` no es `None` en `sales_service`.

---

### A6. `anular_venta()` sin asiento contable ni inventario completo

**Archivo:** `pos_spj_v13.4/core/services/sales_service.py`

**Bug:** La anulación solo actualiza `productos.existencia`; no toca `inventario_actual`, `branch_inventory`, ni genera asiento en `financial_event_log`.

**Corrección:**
```python
def anular_venta(self, folio: str, usuario_id: int, motivo: str = "") -> dict:
    # ... validaciones existentes ...
    with self.db.transaction("ANULAR_VENTA"):
        for d in detalles:
            pid = int(d["producto_id"])
            qty = float(d["cantidad"])
            # 1. Tabla global
            self.db.execute(
                "UPDATE productos SET existencia = COALESCE(existencia,0) + ? WHERE id=?",
                (qty, pid)
            )
            # 2. inventario_actual (por sucursal)
            self.db.execute("""
                INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad)
                VALUES (?, ?, ?)
                ON CONFLICT(producto_id, sucursal_id)
                DO UPDATE SET cantidad = cantidad + excluded.cantidad
            """, (pid, sucursal_id, qty))
            # 3. Movimiento de auditoría
            self.db.execute("""
                INSERT INTO movimientos_inventario
                    (producto_id, tipo, cantidad, referencia, usuario_id, sucursal_id)
                VALUES (?, 'DEVOLUCION_ANULACION', ?, ?, ?, ?)
            """, (pid, qty, folio, usuario_id, sucursal_id))

        # 4. Asiento contable
        self.finance_service.registrar_asiento(
            concepto=f"Anulación venta {folio}: {motivo}",
            cuenta_debe="ventas",
            cuenta_haber="inventario",
            monto=float(venta["total"]),
            referencia=folio,
            usuario_id=usuario_id,
        )
        # 5. Marcar venta anulada
        self.db.execute(
            "UPDATE ventas SET estado='ANULADA', notas=? WHERE folio=?",
            (motivo, folio)
        )
```

**Aceptación:** Anular venta → `movimientos_inventario` tiene fila `DEVOLUCION_ANULACION`; `financial_event_log` tiene asiento balanceado.

---

## Fase B — Consolidación de Inventario (Semanas 2–3)

> **Criterio de entrada:** Fase A completa.  
> **Criterio de salida:** Una sola ruta canónica para escrituras de inventario; todas las tablas sincronizadas.

### B1. Autoridad única de escritura

Todas las operaciones de entrada/salida de inventario deben pasar por `InventoryRepository.update_inventory_cache()`. Eliminar las llamadas directas a `UPDATE productos SET existencia` dispersas en:
- `ERPApplicationService._entrada_directa()` / `_salida_directa()` → delegar a `inventory_service`
- `modulos/ventas.py` directas → delegar a `SalesService`
- `modulos/compras.py` directas → delegar a `PurchaseService`

### B2. `branch_inventory` sincronizado en ventas

`ventas.py` valida stock contra `branch_inventory` pero `InventoryRepository` no la actualiza. Agregar al final de `update_inventory_cache()`:

```python
def update_inventory_cache(self, producto_id, sucursal_id, delta, conn=None):
    _conn = conn or self.db
    # ... lógica existente para inventario_actual ...
    _conn.execute("""
        INSERT INTO branch_inventory (product_id, branch_id, quantity, updated_at)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(product_id, branch_id)
        DO UPDATE SET
            quantity    = quantity + excluded.quantity,
            updated_at  = excluded.updated_at
    """, (producto_id, sucursal_id, delta))
```

### B3. Script de reconciliación

Crear `scripts/reconcile_inventory.py` que detecte y corrija divergencias entre las tres tablas:

```python
"""
Reconcilia productos.existencia vs SUM(inventario_actual) vs SUM(branch_inventory).
Fuente de verdad: movimientos_inventario (inmutable).
"""
def reconcile(conn):
    rows = conn.execute("""
        SELECT
            p.id,
            p.existencia              AS glob,
            SUM(ia.cantidad)          AS ia_sum,
            SUM(bi.quantity)          AS bi_sum,
            SUM(mi.delta_qty)         AS mov_sum
        FROM productos p
        LEFT JOIN inventario_actual ia ON ia.producto_id = p.id
        LEFT JOIN branch_inventory  bi ON bi.product_id  = p.id
        LEFT JOIN movimientos_inventario mi ON mi.producto_id = p.id
        GROUP BY p.id
        HAVING ABS(COALESCE(glob,0) - COALESCE(mov_sum,0)) > 0.01
            OR ABS(COALESCE(ia_sum,0) - COALESCE(mov_sum,0)) > 0.01
    """).fetchall()
    for r in rows:
        print(f"DIVERGENCIA producto_id={r['id']}: glob={r['glob']} ia={r['ia_sum']} mov={r['mov_sum']}")
        # Aplicar corrección desde mov_sum como fuente de verdad
```

### B4. Sync engine: tablas faltantes

**Archivo:** `pos_spj_v13.4/sync/sync_engine.py`

Agregar a `TABLAS_SINCRONIZABLES`:
```python
TABLAS_SINCRONIZABLES = [
    # ... existentes ...
    "mermas",
    "transferencias",
    "production_batches",
    "production_batch_outputs",
    "branch_inventory",
]
```

**Aceptación:** Reconciliation script reporta 0 divergencias en BD de prueba después de 100 ventas simuladas.

---

## Fase C — Seguridad y Autorización (Semanas 3–4)

> **Criterio de salida:** Ningún bypass de permisos; reservas de stock atómicas; MP webhook distingue órdenes.

### C1. Race condition en StockReservationService

**Archivo:** `pos_spj_v13.4/core/services/stock_reservation_service.py`

Envolver lectura+escritura en SAVEPOINT:
```python
def reservar(self, folio, items):
    with self.db.transaction("RESERVAR_STOCK"):
        for item in items:
            pid, cant = item["producto_id"], item["cantidad"]
            row = self.db.execute(
                "SELECT COALESCE(SUM(cantidad),0) FROM stock_reservas "
                "WHERE producto_id=? AND estado='ACTIVA'", (pid,)
            ).fetchone()
            reservado = row[0] if row else 0
            stock_row = self.db.execute(
                "SELECT existencia FROM productos WHERE id=?", (pid,)
            ).fetchone()
            disponible = (stock_row[0] or 0) - reservado
            if disponible + 1e-6 < cant:
                raise ValueError(f"Stock insuficiente: producto {pid}")
        # Insertar reservas dentro del mismo SAVEPOINT
        for item in items:
            self.db.execute(
                "INSERT INTO stock_reservas (folio, producto_id, cantidad, estado, creado_en) "
                "VALUES (?, ?, ?, 'ACTIVA', datetime('now'))",
                (folio, item["producto_id"], item["cantidad"])
            )
```

### C2. TTL para reservas huérfanas

Agregar columna y proceso de expiración:
```sql
-- Migración nueva
ALTER TABLE stock_reservas ADD COLUMN expira_en TEXT;
```

```python
# En StockReservationService.__init__ o en scheduler:
def expirar_reservas(self, ttl_minutos: int = 30):
    self.db.execute("""
        UPDATE stock_reservas
        SET estado = 'EXPIRADA'
        WHERE estado = 'ACTIVA'
          AND expira_en IS NOT NULL
          AND expira_en < datetime('now')
    """)
```

### C3. `external_reference` único en MercadoPago

**Archivo:** `whatsapp_service/flows/pago_flow.py` línea 91

```python
import uuid
payload = {
    # ...
    "external_reference": f"{ctx.phone}_{ctx.folio_pedido}_{uuid.uuid4().hex[:8]}",
    "expiration_date_to": (datetime.utcnow() + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S.000-03:00"),
}
```

### C4. Permisos fail-closed

**Archivo:** `pos_spj_v13.4/core/permissions.py` línea 94–96

```python
    except Exception as e:
        logger.error("verificar_permiso error inesperado: %s", e, exc_info=True)
        return False  # Fail-CLOSED: ante duda, denegar
```

**Aceptación:** Test con excepción simulada en `session.tiene_permiso()` retorna `False`, no `True`.

---

## Fase D — Motor de Producción Cárnica Completo (Semanas 4–6)

> **Criterio de salida:** `ProductionEngine` es el único motor; UI de producción funciona end-to-end; batches generan asientos y mermas automáticas.

### D1. Consolidar en `ProductionEngine`

- Deprecar `RecipeEngine` (mover a `_legacy/recipe_engine_deprecated.py`)
- Corregir los nombres de SAVEPOINT hardcodeados usando identificadores dinámicos:
  ```python
  import uuid
  sp_name = f"sp_{uuid.uuid4().hex[:8]}"
  ```
- Unificar esquema de recetas: migrar datos de `recetas`+`recipe_components` a `product_recipes`+`product_recipe_components` con script de migración

### D2. Merma automática en cierres de batch

```python
def close_batch(self, batch_id: int, operador_id: int):
    with self.db.transaction("CLOSE_BATCH"):
        # ... lógica existente ...
        # Auto-registrar merma si hay diferencia input vs output
        merma_qty = input_total - output_total - expected_loss
        if merma_qty > 0.01:
            self.db.execute("""
                INSERT INTO mermas (producto_id, cantidad, motivo, batch_id, usuario_id, fecha)
                VALUES (?, ?, 'MERMA_PRODUCCION', ?, ?, datetime('now'))
            """, (input_product_id, merma_qty, batch_id, operador_id))
        # Asiento contable de la producción
        self.finance_service.registrar_asiento(
            concepto=f"Producción batch #{batch_id}",
            cuenta_debe="inventario_terminado",
            cuenta_haber="inventario_materia_prima",
            monto=costo_total,
        )
```

### D3. Agregar tablas de producción al sync

Ver B4 — `production_batches` y `production_batch_outputs` ya incluidos.

**Aceptación:** Ciclo completo open→add_output→close_batch sin excepciones; `mermas` tiene registro; `financial_event_log` tiene asiento.

---

## Fase E — Arquitectura Limpia (Meses 2–3)

> **Criterio de salida:** `modulos/ventas.py` sin SQL directo; capa `domain/` con entidades puras; UI delega a application layer.

### E1. Extracción de `modulos/ventas.py`

Prioridad máxima por tamaño (~3663 líneas con SQL embebido):

```
domain/entities/sale.py           — Sale, SaleItem (validaciones puras)
domain/services/sale_domain_service.py — cálculo de totales, validación de stock
application/use_cases/create_sale_use_case.py — orquestación (ya existe, expandir)
application/use_cases/cancel_sale_use_case.py — anulación (nueva)
ui/qt5/ventas_window.py           — solo eventos UI, delega a use cases
```

### E2. Unificación de esquema de recetas

```sql
-- Migración: copiar datos legacy al esquema nuevo
INSERT OR IGNORE INTO product_recipes (product_id, name, yield_quantity, yield_unit)
SELECT producto_resultado_id, nombre, rendimiento, unidad
FROM recetas;

INSERT OR IGNORE INTO product_recipe_components
    (recipe_id, ingredient_id, quantity, unit, waste_pct)
SELECT pr.id, rc.ingrediente_id, rc.cantidad, rc.unidad, 0
FROM recipe_components rc
JOIN recetas r ON r.id = rc.receta_id
JOIN product_recipes pr ON pr.product_id = r.producto_resultado_id;
```

### E3. SQL seguro en toda la UI

- Auditoría automática: `grep -rn "execute(" pos_spj_v13.4/modulos/` — toda ocurrencia es candidata a extracción
- Ningún `INSERT/UPDATE/DELETE` directo en archivos bajo `modulos/`

**Aceptación:** `grep -rn "\.execute(" pos_spj_v13.4/modulos/` retorna 0 resultados.

---

## Fase F — API REST Externa (Meses 3–4)

> **Criterio de salida:** ERPBridge usa HTTP en lugar de SQLite directo; gateway FastAPI expone endpoints autenticados.

### F1. Gateway FastAPI

```
infrastructure/api/
├── main.py          — FastAPI app, CORS, JWT auth
├── routers/
│   ├── ventas.py    — POST /ventas, GET /ventas/{folio}
│   ├── inventario.py — GET /stock, POST /movimientos
│   └── whatsapp.py  — webhook handler
└── deps.py          — get_db(), get_current_user()
```

### F2. Migrar ERPBridge a HTTP

```python
# whatsapp_service/erp/bridge.py
class ERPBridge:
    def __init__(self, erp_base_url: str, api_key: str):
        self.base_url = erp_base_url
        self.headers = {"X-API-Key": api_key}

    async def crear_pedido(self, data: dict) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/ventas",
                json=data,
                headers=self.headers,
                timeout=10.0
            )
            resp.raise_for_status()
            return resp.json()
```

**Aceptación:** ERPBridge no importa `sqlite3`; tests de integración pasan contra servidor de prueba.

---

## Fase G — Tests Continuos (Paralela a todas las fases)

> Ejecutar en CI en cada PR. No bloquear merge por cobertura, sí bloquear por fallo.

### G1. Tests de integridad de inventario

```python
# tests/test_inventory_integrity.py
def test_venta_decrementa_todas_las_tablas(db, sale_service):
    before = get_stock_all_tables(db, producto_id=1, sucursal_id=1)
    sale_service.execute_sale(items=[{"producto_id": 1, "cantidad": 3}], ...)
    after = get_stock_all_tables(db, producto_id=1, sucursal_id=1)
    assert after["existencia"] == before["existencia"] - 3
    assert after["inventario_actual"] == before["inventario_actual"] - 3
    assert after["branch_inventory"] == before["branch_inventory"] - 3

def test_anulacion_genera_asiento(db, sale_service):
    folio = sale_service.execute_sale(...)["folio"]
    sale_service.anular_venta(folio, usuario_id=1, motivo="test")
    row = db.execute(
        "SELECT * FROM financial_event_log WHERE referencia=?", (folio,)
    ).fetchone()
    assert row is not None
    assert row["cuenta_debe"] == "ventas"
```

### G2. Stress test de concurrencia

```python
# tests/test_concurrency.py
def test_no_overselling_concurrent(db):
    """10 threads intentan vender la última unidad — solo 1 debe lograrse."""
    import threading
    results = []
    def try_sell():
        try:
            sale_service.execute_sale(items=[{"producto_id": 1, "cantidad": 1}], ...)
            results.append("ok")
        except Exception:
            results.append("fail")
    threads = [threading.Thread(target=try_sell) for _ in range(10)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count("ok") == 1
```

### G3. Health check horario

```python
# scripts/health_check.py — ejecutar en cron cada hora
checks = {
    "auth_bcrypt": lambda: verify_password("test", hash_password("testtest")),
    "inventory_consistent": lambda: len(reconcile(conn)) == 0,
    "no_orphan_reservas": lambda: conn.execute(
        "SELECT COUNT(*) FROM stock_reservas WHERE estado='ACTIVA' "
        "AND creado_en < datetime('now','-2 hours')"
    ).fetchone()[0] == 0,
}
```

---

## Tabla de Prioridades

| # | Defecto | Impacto | Esfuerzo | Fase |
|---|---------|---------|----------|------|
| 1 | BCrypt siempre falla → login imposible | CRÍTICO | 5 min | A1 |
| 2 | `detalle_ventas` tabla errónea → líneas WA perdidas | CRÍTICO | 10 min | A2 |
| 3 | Triple actualización stock en QR | CRÍTICO | 30 min | A3 |
| 4 | `.conn` AttributeError → producción caída | CRÍTICO | 5 min | A4 |
| 5 | GrowthEngine None → puntos no acumulan | ALTO | 10 min | A5 |
| 6 | Anulación sin asiento → audit trail roto | ALTO | 2 h | A6 |
| 7 | Race condition reservas → overselling | ALTO | 4 h | C1 |
| 8 | Reservas huérfanas → stock congelado | MEDIO | 2 h | C2 |
| 9 | MP external_reference no único | MEDIO | 30 min | C3 |
| 10 | Fail-open permisos | MEDIO | 5 min | C4 |
| 11 | Tres tablas inventario desincronizadas | ALTO | 1 sem | B1–B3 |
| 12 | Sync engine tablas faltantes | MEDIO | 2 h | B4 |
| 13 | Motor producción consolidación | ALTO | 2 sem | D |
| 14 | SQL en UI (modulos/) | MEDIO | 2 mes | E |
| 15 | API REST externa | BAJO | 1 mes | F |

---

## Métricas de Éxito

| Métrica | Actual | Objetivo Fase A | Objetivo Final |
|---------|--------|-----------------|----------------|
| Login bcrypt exitoso | 0% | 100% | 100% |
| Líneas WA guardadas | 0% | 100% | 100% |
| Divergencia inventario (tablas) | Alta | — | 0 divergencias |
| Cobertura tests inventario | ~0% | 10% | ≥80% |
| SQL directo en `modulos/` | ~200 líneas | — | 0 líneas |
| Producción batch exit sin error | 0% | 100% (A4) | 100% |
| Overselling bajo concurrencia | Posible | — | Imposible |

---

## Orden de Implementación (estricto)

```
A1 → A2 → A3 → A4 → A5 → A6   (mismo sprint, 2-3 días)
      ↓
B1 → B2 → B3 → B4              (sprint 2, semana 2)
      ↓
C1 → C2 → C3 → C4              (sprint 3, semana 3)
      ↓
D1 → D2 → D3                   (sprint 4-6, semanas 4-6)
      ↓
E1 → E2 → E3                   (mes 2-3)
      ↓
F1 → F2                        (mes 3-4)

G (tests) — paralelo a todas las fases desde el día 1
```

---

*Auditoría realizada el 2026-04-29. Documento generado por el Codebase Auditor Engine.*  
*Siguiente revisión sugerida: después de completar Fase A (≤ 1 semana).*
