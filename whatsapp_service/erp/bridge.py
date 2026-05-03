# erp/bridge.py — Puente al ERP existente
"""
Wrapper que conecta con los use cases y servicios del ERP
sin modificar ningún archivo existente.

IMPORTANTE: Todo acceso al ERP pasa por aquí.
No se importa nada del ERP directamente en los flows.

Modo de operación:
  - Si api_url + api_key están configurados, las operaciones de escritura
    (crear_pedido_wa, create_cliente_minimo, actualizar_estado_pedido) usan
    el REST API Gateway.
  - Las consultas sin endpoint REST todavía usan conexión directa a SQLite.
  - Configura ERP_API_URL y ERP_API_KEY en el entorno del microservicio WA.
"""
from __future__ import annotations
import os
import sqlite3
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger("wa.erp")


class ERPBridge:
    """Puente al ERP — acceso read/write a la BD y servicios."""

    def __init__(self, db_path: str,
                 api_url: str = "",
                 api_key: str = ""):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

        # REST API settings (override with env vars)
        self._api_url = (api_url or os.environ.get("ERP_API_URL", "")).rstrip("/")
        self._api_key = api_key or os.environ.get("ERP_API_KEY", "")
        self._http: Any = None  # httpx.Client, lazy

    # ── HTTP client ───────────────────────────────────────────────────────────

    @property
    def _use_api(self) -> bool:
        return bool(self._api_url and self._api_key)

    @property
    def _client(self):
        """Lazy httpx.Client with auth header."""
        if self._http is None:
            import httpx
            self._http = httpx.Client(
                base_url=self._api_url,
                headers={"X-API-Key": self._api_key},
                timeout=10.0,
            )
        return self._http

    def _api_get(self, path: str, **params) -> Any:
        resp = self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    def _api_post(self, path: str, body: dict) -> Any:
        resp = self._client.post(path, json=body)
        resp.raise_for_status()
        return resp.json()

    def _api_patch(self, path: str, **params) -> Any:
        resp = self._client.patch(path, params=params)
        resp.raise_for_status()
        return resp.json()

    # ── Direct SQLite connection (read-only fallback) ─────────────────────────

    @property
    def db(self) -> sqlite3.Connection:
        if not self._conn:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    # ── Sucursales ────────────────────────────────────────────────────────────

    def get_sucursales(self) -> List[Dict]:
        rows = self.db.execute(
            "SELECT id, nombre, COALESCE(direccion,'') as direccion "
            "FROM sucursales WHERE activa=1 ORDER BY nombre"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_sucursal(self, sucursal_id: int) -> Optional[Dict]:
        row = self.db.execute(
            "SELECT id, nombre FROM sucursales WHERE id=? AND activa=1",
            (sucursal_id,)
        ).fetchone()
        return dict(row) if row else None

    # ── Clientes ──────────────────────────────────────────────────────────────

    def find_cliente_by_phone(self, phone: str) -> Optional[Dict]:
        phone_clean = phone[-10:] if len(phone) > 10 else phone

        if self._use_api:
            try:
                data = self._api_get("/api/v1/clientes", q=phone_clean, limit=1)
                clientes = data.get("clientes", [])
                if not clientes:
                    return None
                cliente = clientes[0]
                cliente["credito_disponible"] = (
                    cliente.get("credit_limit", 0) - cliente.get("credit_balance", 0)
                )
                return cliente
            except Exception as exc:
                logger.warning("find_cliente_by_phone via API failed: %s — fallback to DB", exc)

        row = self.db.execute("""
            SELECT *
            FROM clientes
            WHERE telefono LIKE ? AND activo=1
            LIMIT 1
        """, (f"%{phone_clean}",)).fetchone()

        if not row:
            return None

        cliente = dict(row)
        cliente["credito_disponible"] = (
            cliente.get("credit_limit", 0) - cliente.get("credit_balance", 0)
        )
        return cliente

    def create_cliente_minimo(self, nombre: str, telefono: str) -> int:
        """Crea un cliente con datos mínimos (registro rápido por WA)."""
        if self._use_api:
            try:
                data = self._api_post("/api/v1/clientes", {
                    "nombre": nombre,
                    "telefono": telefono,
                })
                return data["cliente_id"]
            except Exception as exc:
                logger.warning("create_cliente_minimo via API failed: %s — fallback to DB", exc)

        cursor = self.db.execute(
            "INSERT INTO clientes (nombre, telefono, activo) VALUES (?, ?, 1)",
            (nombre, telefono))
        self.db.commit()
        return cursor.lastrowid

    def get_credito_disponible(self, cliente_id: int) -> float:
        row = self.db.execute("""
            SELECT COALESCE(credit_limit,0) - COALESCE(credit_balance,0)
            FROM clientes WHERE id=?
        """, (cliente_id,)).fetchone()
        return float(row[0]) if row else 0.0

    # ── Productos ─────────────────────────────────────────────────────────────

    def get_productos_by_category(self, categoria: str,
                                  sucursal_id: int) -> List[Dict]:
        rows = self.db.execute("""
            SELECT p.id, p.nombre, p.precio,
                   COALESCE(bi.quantity, p.existencia, 0) as stock,
                   COALESCE(p.unidad, 'kg') as unidad, p.categoria
            FROM productos p
            LEFT JOIN branch_inventory bi ON bi.product_id=p.id AND bi.branch_id=?
            WHERE p.activo=1 AND COALESCE(p.oculto,0)=0
              AND LOWER(p.categoria) = LOWER(?)
            ORDER BY p.nombre
        """, (sucursal_id, categoria)).fetchall()
        return [dict(r) for r in rows]

    def get_categorias(self, sucursal_id: int) -> List[str]:
        rows = self.db.execute("""
            SELECT DISTINCT p.categoria
            FROM productos p
            WHERE p.activo=1 AND COALESCE(p.oculto,0)=0
              AND p.categoria IS NOT NULL AND p.categoria != ''
            ORDER BY p.categoria
        """).fetchall()
        return [r[0] for r in rows]

    def get_producto(self, producto_id: int,
                     sucursal_id: int) -> Optional[Dict]:
        row = self.db.execute("""
            SELECT p.id, p.nombre, p.precio,
                   COALESCE(bi.quantity, p.existencia, 0) as stock,
                   COALESCE(p.unidad, 'kg') as unidad, p.categoria
            FROM productos p
            LEFT JOIN branch_inventory bi ON bi.product_id=p.id AND bi.branch_id=?
            WHERE p.id=?
        """, (sucursal_id, producto_id)).fetchone()
        return dict(row) if row else None

    # ── Ventas / Pedidos ──────────────────────────────────────────────────────

    def crear_pedido_wa(self, items: List[Dict], cliente_id: int,
                        sucursal_id: int, tipo_entrega: str,
                        direccion: str = "", fecha_entrega: str = "",
                        notas: str = "") -> Dict:
        """
        Crea un pedido desde WhatsApp.
        Usa el API Gateway cuando está disponible; cae a SQLite como fallback.
        """
        if self._use_api:
            try:
                api_items = [
                    {
                        "producto_id": it["producto_id"],
                        "nombre":      it.get("nombre", ""),
                        "cantidad":    float(it["cantidad"]),
                        "precio_unitario": float(it["precio_unitario"]),
                    }
                    for it in items
                ]
                data = self._api_post("/api/v1/pedidos", {
                    "cliente_id":    cliente_id,
                    "items":         api_items,
                    "tipo_entrega":  tipo_entrega,
                    "direccion":     direccion,
                    "fecha_entrega": fecha_entrega,
                    "notas":         notas,
                    "sucursal_id":   sucursal_id,
                    "canal":         "whatsapp",
                })
                return {
                    "venta_id": data["venta_id"],
                    "folio":    data["folio"],
                    "total":    data["total"],
                }
            except Exception as exc:
                logger.warning("crear_pedido_wa via API failed: %s — fallback to DB", exc)

        # Fallback: direct SQLite write
        import uuid
        folio = f"WA-{uuid.uuid4().hex[:8].upper()}"
        total = sum(it["cantidad"] * it["precio_unitario"] for it in items)

        cursor = self.db.execute("""
            INSERT INTO ventas (folio, cliente_id, total, estado,
                               sucursal_id, tipo_entrega, direccion_entrega,
                               fecha_entrega_programada, notas, canal, fecha)
            VALUES (?, ?, ?, 'pendiente_wa', ?, ?, ?, ?, ?, 'whatsapp',
                    datetime('now'))
        """, (folio, cliente_id, total, sucursal_id, tipo_entrega,
              direccion, fecha_entrega, notas))
        venta_id = cursor.lastrowid

        for it in items:
            self.db.execute("""
                INSERT INTO detalles_venta (venta_id, producto_id, nombre,
                    cantidad, precio_unitario, subtotal)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (venta_id, it["producto_id"], it["nombre"],
                  it["cantidad"], it["precio_unitario"],
                  it["cantidad"] * it["precio_unitario"]))

        self.db.commit()
        return {"venta_id": venta_id, "folio": folio, "total": total}

    def actualizar_estado_pedido(self, pedido_id: int, estado: str,
                                  notas: str = "") -> bool:
        """Actualiza el estado de un pedido vía API o DB directa."""
        if self._use_api:
            try:
                self._api_patch(
                    f"/api/v1/pedidos/{pedido_id}/estado",
                    estado=estado,
                    notas=notas,
                )
                return True
            except Exception as exc:
                logger.warning("actualizar_estado_pedido via API failed: %s — fallback", exc)

        try:
            self.db.execute(
                "UPDATE ventas SET estado=? WHERE id=?",
                (estado, pedido_id)
            )
            self.db.commit()
            return True
        except Exception as exc:
            logger.warning("actualizar_estado_pedido DB fallback failed: %s", exc)
            return False

    def get_ultimo_pedido(self, cliente_id: int) -> Optional[Dict]:
        """Obtiene el último pedido del cliente para "repetir"."""
        row = self.db.execute("""
            SELECT v.id, v.folio, v.total, v.fecha
            FROM ventas v
            WHERE v.cliente_id = ? AND v.estado NOT IN ('cancelada')
            ORDER BY v.fecha DESC LIMIT 1
        """, (cliente_id,)).fetchone()
        if not row:
            return None

        items = self.db.execute("""
            SELECT producto_id, nombre, cantidad,
                   precio_unitario, COALESCE(unidad, 'kg') as unidad
            FROM detalles_venta WHERE venta_id=?
        """, (row["id"],)).fetchall()

        return {
            "venta_id": row["id"], "folio": row["folio"],
            "total": float(row["total"]), "fecha": row["fecha"],
            "items": [dict(i) for i in items],
        }

    def get_estado_pedido(self, folio: str) -> Optional[Dict]:
        row = self.db.execute(
            "SELECT folio, estado, total, fecha FROM ventas WHERE folio=?",
            (folio,)
        ).fetchone()
        return dict(row) if row else None

    # ── Cotizaciones ──────────────────────────────────────────────────────────

    def crear_cotizacion_wa(self, items: List[Dict], cliente_id: int,
                            sucursal_id: int, usuario: str = "whatsapp") -> Dict:
        import uuid
        folio = f"CWA-{uuid.uuid4().hex[:6].upper()}"
        total = sum(it["cantidad"] * it["precio_unitario"] for it in items)

        cursor = self.db.execute("""
            INSERT INTO cotizaciones (folio, cliente_id, cliente_nombre, total,
                                     estado, usuario, sucursal_id, fecha)
            VALUES (?, ?, (SELECT nombre FROM clientes WHERE id=?),
                    ?, 'pendiente', ?, ?, datetime('now'))
        """, (folio, cliente_id, cliente_id, total, usuario, sucursal_id))
        cot_id = cursor.lastrowid

        for it in items:
            self.db.execute("""
                INSERT INTO cotizaciones_detalle (cotizacion_id, producto_id,
                    nombre, cantidad, precio_unitario, subtotal)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (cot_id, it["producto_id"], it["nombre"],
                  it["cantidad"], it["precio_unitario"],
                  it["cantidad"] * it["precio_unitario"]))

        self.db.commit()
        return {"cotizacion_id": cot_id, "folio": folio, "total": total}

    # ── Anticipos ─────────────────────────────────────────────────────────────

    def requiere_anticipo(self, cliente_id: int, total: float,
                          programado: bool = False) -> bool:
        credito = self.get_credito_disponible(cliente_id)
        if credito < total:
            return True
        if programado:
            return True
        return False

    def registrar_anticipo(self, venta_id: int, monto: float,
                           metodo: str = "mercadopago") -> int:
        cursor = self.db.execute("""
            INSERT INTO anticipos (venta_id, monto, metodo, estado, fecha)
            VALUES (?, ?, ?, 'pendiente', datetime('now'))
        """, (venta_id, monto, metodo))
        self.db.commit()
        return cursor.lastrowid

    # ── Staff / RRHH ──────────────────────────────────────────────────────────

    def get_staff_phones(self, sucursal_id: int,
                         rol: str = "") -> List[str]:
        q = ("SELECT telefono FROM empleados "
             "WHERE sucursal_id=? AND activo=1 AND telefono IS NOT NULL")
        params: list = [sucursal_id]
        if rol:
            q += " AND rol=?"
            params.append(rol)
        rows = self.db.execute(q, params).fetchall()
        return [r[0] for r in rows if r[0]]

    def close(self):
        if self._http:
            self._http.close()
            self._http = None
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Conversión Cotización → Venta ─────────────────────────────────────────

    def convertir_cotizacion_a_venta(self, cotizacion_id: int,
                                     usuario: str = "whatsapp") -> Optional[Dict]:
        cot = self.db.execute(
            "SELECT * FROM cotizaciones WHERE id=? AND estado='pendiente'",
            (cotizacion_id,)
        ).fetchone()
        if not cot:
            return None

        cot = dict(cot)
        items = self.db.execute(
            "SELECT * FROM cotizaciones_detalle WHERE cotizacion_id=?",
            (cotizacion_id,)
        ).fetchall()
        items = [dict(i) for i in items]

        if not items:
            return None

        result = self.crear_pedido_wa(
            items=[{
                "producto_id":    it["producto_id"],
                "nombre":         it["nombre"],
                "cantidad":       it["cantidad"],
                "precio_unitario": it["precio_unitario"],
            } for it in items],
            cliente_id=cot["cliente_id"],
            sucursal_id=cot.get("sucursal_id", 1),
            tipo_entrega="sucursal",
        )

        self.db.execute(
            "UPDATE cotizaciones SET estado='convertida', venta_ref_id=? WHERE id=?",
            (result["venta_id"], cotizacion_id)
        )
        self.db.commit()
        return {**result, "cotizacion_id": cotizacion_id}

    # ── Calcular anticipo según reglas del ERP ────────────────────────────────

    def calcular_anticipo_rules(self, cliente_id: int, total: float,
                                 items: Optional[List[Dict]] = None) -> Dict:
        credito = self.get_credito_disponible(cliente_id)

        if credito >= total:
            if items:
                for it in items:
                    prod_id = it.get("producto_id")
                    if prod_id:
                        regla = self.db.execute("""
                            SELECT porcentaje FROM anticipo_reglas
                            WHERE tipo='categoria' AND activo=1
                            AND categoria = (SELECT categoria FROM productos WHERE id=?)
                            ORDER BY porcentaje DESC LIMIT 1
                        """, (prod_id,)).fetchone()
                        if regla:
                            pct = float(regla[0]) / 100.0
                            return {"requiere": True,
                                    "monto": round(total * pct, 2),
                                    "razon": "producto_especial"}
            return {"requiere": False, "monto": 0.0, "razon": "credito_suficiente"}

        regla_monto = self.db.execute("""
            SELECT porcentaje FROM anticipo_reglas
            WHERE tipo='monto' AND activo=1
              AND ? BETWEEN COALESCE(monto_minimo,0) AND COALESCE(monto_maximo,999999)
            ORDER BY porcentaje DESC LIMIT 1
        """, (total,)).fetchone()

        pct = float(regla_monto[0]) / 100.0 if regla_monto else 0.5

        return {"requiere": True,
                "monto": round(total * pct, 2),
                "razon": "sin_credito"}

    # ── Confirmar pago de anticipo ────────────────────────────────────────────

    def confirmar_pago_anticipo(self, venta_id: int, monto: float,
                                 referencia: str = "",
                                 metodo: str = "mercadopago") -> bool:
        try:
            self.db.execute("""
                UPDATE anticipos SET estado='pagado', fecha_pago=datetime('now'),
                    referencia=? WHERE venta_id=? AND estado='pendiente'
            """, (referencia, venta_id))
            self.db.execute(
                "UPDATE ventas SET estado='confirmada', anticipo_pagado=? WHERE id=?",
                (monto, venta_id)
            )
            self.db.commit()
            return True
        except Exception as e:
            logger.warning("confirmar_pago_anticipo: %s", e)
            return False

    # ── Verificar stock y generar OC ──────────────────────────────────────────

    def verificar_stock_items(self, items: List[Dict],
                               sucursal_id: int) -> List[Dict]:
        resultado = []
        for it in items:
            prod_id = it.get("producto_id")
            cantidad = float(it.get("cantidad", 0))
            if not prod_id:
                continue
            stock_row = self.db.execute("""
                SELECT COALESCE(bi.quantity, p.existencia, 0)
                FROM productos p
                LEFT JOIN branch_inventory bi ON bi.product_id=p.id AND bi.branch_id=?
                WHERE p.id=?
            """, (sucursal_id, prod_id)).fetchone()
            stock_actual = float(stock_row[0]) if stock_row else 0.0
            falta = max(0.0, cantidad - stock_actual)
            resultado.append({**it, "stock_actual": stock_actual, "falta": falta})
        return resultado

    def generar_orden_compra(self, producto_id: int, cantidad: float,
                              sucursal_id: int,
                              notas: str = "OC automática desde WA") -> Optional[int]:
        try:
            prod = self.db.execute(
                "SELECT nombre, proveedor_id FROM productos WHERE id=?",
                (producto_id,)
            ).fetchone()
            if not prod:
                return None

            proveedor_id = prod["proveedor_id"] if prod["proveedor_id"] else None
            cursor = self.db.execute("""
                INSERT INTO ordenes_compra (
                    producto_id, proveedor_id, cantidad, estado,
                    sucursal_id, notas, fecha_creacion
                ) VALUES (?, ?, ?, 'pendiente', ?, ?, datetime('now'))
            """, (producto_id, proveedor_id, cantidad, sucursal_id, notas))
            self.db.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.warning("generar_orden_compra: %s", e)
            return None

    # ── Programar delivery ────────────────────────────────────────────────────

    def programar_delivery(self, venta_id: int, direccion: str,
                            fecha_entrega: str = "",
                            telefono_cliente: str = "") -> bool:
        if self._use_api:
            try:
                self._api_patch(
                    f"/api/v1/pedidos/{venta_id}/estado",
                    estado="confirmado",
                    notas=f"delivery:{direccion}",
                )
                # Fallthrough to also update delivery fields via DB
            except Exception as exc:
                logger.warning("programar_delivery via API: %s", exc)

        try:
            self.db.execute("""
                UPDATE ventas SET tipo_entrega='domicilio',
                    direccion_entrega=?,
                    fecha_entrega_programada=COALESCE(NULLIF(?,''),(datetime('now','+1 day')))
                WHERE id=?
            """, (direccion, fecha_entrega, venta_id))
            self.db.commit()
            return True
        except Exception as e:
            logger.warning("programar_delivery: %s", e)
            return False

    # ── Compras / OC staff phones ─────────────────────────────────────────────

    def get_compras_phones(self, sucursal_id: int) -> List[str]:
        rows = self.db.execute("""
            SELECT COALESCE(telefono, '') as tel
            FROM configuraciones
            WHERE clave LIKE 'tel_compras%' AND COALESCE(valor,'') != ''
        """).fetchall()
        if rows:
            return [r[0] for r in rows if r[0]]
        return self.get_staff_phones(sucursal_id, rol="compras")
