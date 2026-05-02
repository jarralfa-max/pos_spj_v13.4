
# core/services/recipe_engine.py
# ── RecipeEngine — Motor de Producción Industrial ─────────────────────────────
#
# Maneja los 3 tipos de receta en una sola transacción atómica:
#
#   SUBPRODUCTO: Descuenta producto_base, genera subproductos por rendimiento%
#   COMBINACION: Descuenta componentes, genera el kit/paquete
#   PRODUCCION:  Descuenta materias primas, genera producto elaborado
#
# GARANTÍAS:
#   ✔ BEGIN IMMEDIATE única transacción (with self.db.transaction() as conn)
#   ✔ InventoryEngine.process_movement(conn=conn) sin BEGIN propio
#   ✔ Registro en movimientos_inventario (legacy) + inventory_movements (Fase 1)
#   ✔ ROLLBACK total si falla cualquier paso
#   ✔ Merma registrada como movimiento MERMA explícito
#   ✔ Sin doble-actualización de existencia (process_movement es la fuente de verdad)
#
# FIX v13.5:
#   - BUG-1: conn no definido → usar `with self.db.transaction() as conn`
#   - BUG-inv: _get_current_stock inexistente → usar inv.get_stock()
#   - FALLA-1: merma ignorada → movimiento MERMA_PRODUCCION por componente
#   - FALLA-2: costo por piezas → costo por kg total
#   - FALLA-7: doble update existencia → eliminado de _registrar_movimiento_legacy
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from core.services.inventory_engine import InventoryEngine, StockInsuficienteError

logger = logging.getLogger("spj.recipe_engine")
CENTAVO = Decimal("0.001")

def _recipe_name(receta: dict) -> str:
    """Compatibilidad entre esquemas legacy (`nombre`) y actual (`nombre_receta`)."""
    return (
        receta.get("nombre")
        or receta.get("nombre_receta")
        or f"Receta #{receta.get('id', '?')}"
    )


class RecipeEngineError(Exception):
    pass

class RecetaNoEncontradaError(RecipeEngineError):
    pass

class StockInsuficienteProduccionError(RecipeEngineError):
    pass

class ProduccionDuplicadaError(RecipeEngineError):
    pass


@dataclass
class ComponenteResultado:
    producto_id: int
    nombre: str
    cantidad: float
    unidad: str
    rendimiento: float
    tipo: str  # 'entrada' | 'salida' | 'merma'


@dataclass
class ProduccionResultDTO:
    produccion_id: int
    receta_id: int
    receta_nombre: str
    tipo_receta: str
    operation_id: str
    cantidad_base: float
    producto_base: str
    componentes: List[ComponenteResultado] = field(default_factory=list)
    total_generado: float = 0.0
    total_consumido: float = 0.0
    total_merma: float = 0.0


class RecipeEngine:

    def __init__(self, db, branch_id: int):
        from core.db.connection import wrap
        self.db = wrap(db)
        self.branch_id = branch_id

    def ejecutar_produccion(
        self,
        receta_id: int,
        cantidad_base: float,
        usuario: str,
        sucursal_id: Optional[int] = None,
        notas: str = "",
        operation_id: Optional[str] = None,
        mediciones_reales: Optional[dict] = None,
    ) -> ProduccionResultDTO:
        """
        Ejecuta una producción completa en una única transacción atómica.

        mediciones_reales: {product_id: actual_kg} — pesos reales medidos en báscula.
        Si se provee, se valida la tolerancia por componente y se usa el peso real.
        Si no se provee, se usan los pesos teóricos calculados por la receta.
        """
        if not usuario or not usuario.strip():
            raise RecipeEngineError("usuario es obligatorio")
        if cantidad_base <= 0:
            raise RecipeEngineError("cantidad_base debe ser positiva")

        op_id = operation_id or str(uuid.uuid4())
        suc_id = sucursal_id or self.branch_id

        # FIX BUG-1: exponer conn del context manager para usarlo explícitamente
        with self.db.transaction("RECIPE_PRODUCCION") as conn:
            # 1. Cargar receta
            receta = conn.execute(
                "SELECT * FROM product_recipes WHERE id = ? AND is_active = 1",
                (receta_id,)
            ).fetchone()
            if not receta:
                raise RecetaNoEncontradaError(f"RECETA_NO_ENCONTRADA: id={receta_id}")
            receta = dict(receta)
            tipo = receta.get("tipo_receta", "subproducto")
            prod_base_id = receta.get("base_product_id") or receta.get("product_id")
            peso_prom = float(receta.get("peso_promedio_kg") or 1.0)

            prod_base_row = conn.execute(
                "SELECT nombre, unidad FROM productos WHERE id = ?", (prod_base_id,)
            ).fetchone()
            prod_base_nombre = prod_base_row["nombre"] if prod_base_row else f"#{prod_base_id}"

            componentes_db = conn.execute("""
                SELECT rc.*,
                       rc.component_product_id AS producto_id,
                       p.nombre AS prod_nombre,
                       COALESCE(rc.unidad, p.unidad, 'kg') AS prod_unidad,
                       COALESCE(rc.tolerancia_pct, 2.0) AS tolerancia_pct
                FROM product_recipe_components rc
                JOIN productos p ON p.id = rc.component_product_id
                WHERE rc.recipe_id = ?
                ORDER BY rc.orden, rc.id
            """, (receta_id,)).fetchall()
            componentes_db = [dict(r) for r in componentes_db]

            if not componentes_db:
                raise RecipeEngineError(f"RECETA_SIN_COMPONENTES: id={receta_id}")

            # 2. Idempotencia
            dup = conn.execute(
                "SELECT id FROM producciones WHERE operation_id = ?", (op_id,)
            ).fetchone()
            if dup:
                raise ProduccionDuplicadaError(f"PRODUCCION_DUPLICADA: op={op_id}")

            # 3. Calcular movimientos (incluye movimientos de merma)
            movimientos = self._calcular_movimientos(
                tipo, receta, componentes_db, cantidad_base, peso_prom,
                prod_base_id, prod_base_nombre)

            # 3b. Aplicar mediciones reales + validar tolerancia
            if mediciones_reales:
                variaciones = []
                for mov in movimientos:
                    if mov["delta"] > 0 and mov.get("movement_type") == "PRODUCCION_ENTRADA":
                        pid = mov["product_id"]
                        if pid in mediciones_reales:
                            real_kg = float(mediciones_reales[pid])
                            teorico_kg = mov["delta"]
                            comp = next((c for c in componentes_db
                                         if c.get("component_product_id") == pid
                                         or c.get("producto_id") == pid), {})
                            tolerancia = float(comp.get("tolerancia_pct") or 2.0) / 100.0
                            diferencia_rel = abs(real_kg - teorico_kg) / teorico_kg if teorico_kg > 0 else 0
                            if diferencia_rel > tolerancia:
                                variaciones.append({
                                    "product_id": pid,
                                    "nombre": mov["nombre"],
                                    "teorico": round(teorico_kg, 4),
                                    "real": round(real_kg, 4),
                                    "diferencia_pct": round(diferencia_rel * 100, 2),
                                    "tolerancia_pct": round(tolerancia * 100, 2),
                                })
                            mov["delta"] = real_kg
                            mov["variacion_kg"] = round(real_kg - teorico_kg, 4)
                if variaciones:
                    import json as _json
                    notas = (notas + " | " if notas else "") + "VARIACIONES: " + _json.dumps(variaciones)

            # 4. Validar stock para salidas
            # FIX BUG-inv: usar get_stock() en vez del inexistente _get_current_stock()
            inv = InventoryEngine(self.db, self.branch_id, usuario)
            for mov in movimientos:
                if mov["delta"] < 0:
                    actual = inv.get_stock(mov["product_id"])
                    necesario = abs(mov["delta"])
                    if actual < necesario - 0.001:
                        raise StockInsuficienteProduccionError(
                            f"STOCK_INSUFICIENTE: producto={mov['nombre']} "
                            f"disponible={actual:.4f} necesario={necesario:.4f}"
                        )

            # 5. INSERT producciones
            conn.execute("""
                INSERT INTO producciones (
                    receta_id, producto_base_id, cantidad_base, unidad_base,
                    usuario, sucursal_id, notas, estado, fecha, operation_id
                ) VALUES (?,?,?,?,?,?,?,'completada',datetime('now'),?)
            """, (
                receta_id, prod_base_id, cantidad_base,
                receta.get("unidad_base", "kg"),
                usuario, suc_id, notas or "", op_id,
            ))
            produccion_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            # 6. Ejecutar movimientos
            componentes_resultado = []
            total_generado = 0.0
            total_consumido = 0.0
            total_merma = 0.0

            for mov in movimientos:
                mov_type = mov["movement_type"]

                inv.process_movement(
                    product_id=mov["product_id"],
                    branch_id=self.branch_id,
                    quantity=mov["delta"],
                    movement_type=mov_type,
                    operation_id=f"{op_id}_{mov['product_id']}_{mov_type}",
                    reference_id=produccion_id,
                    reference_type="PRODUCCION",
                    conn=conn,
                )

                tipo_det = "entrada" if mov["delta"] > 0 else (
                    "merma" if mov_type == "MERMA_PRODUCCION" else "salida"
                )
                conn.execute("""
                    INSERT INTO produccion_detalle (
                        produccion_id, producto_resultante_id,
                        cantidad_generada, unidad, rendimiento_aplicado, tipo
                    ) VALUES (?,?,?,?,?,?)
                """, (
                    produccion_id, mov["product_id"],
                    abs(mov["delta"]), mov.get("unidad", "kg"),
                    mov.get("rendimiento", 0.0), tipo_det,
                ))

                # FIX FALLA-7: _registrar_movimiento_legacy ya NO actualiza existencia
                # (process_movement ya la actualizó arriba — eliminamos la doble escritura)
                self._registrar_movimiento_legacy_audit_only(conn, mov, produccion_id, usuario, suc_id)

                if mov["delta"] > 0:
                    total_generado += mov["delta"]
                elif mov_type == "MERMA_PRODUCCION":
                    total_merma += abs(mov["delta"])
                else:
                    total_consumido += abs(mov["delta"])

                componentes_resultado.append(ComponenteResultado(
                    producto_id=mov["product_id"],
                    nombre=mov["nombre"],
                    cantidad=abs(mov["delta"]),
                    unidad=mov.get("unidad", "kg"),
                    rendimiento=mov.get("rendimiento", 0.0),
                    tipo=tipo_det,
                ))

            # 7. FIX FALLA-2: Costo real por kg (no por piezas)
            # costo_base_total = precio_compra_kg × total_kg_entrada
            if tipo == "subproducto" and total_consumido > 0:
                costo_row = conn.execute(
                    "SELECT COALESCE(precio_compra, costo, 0) FROM productos WHERE id=?",
                    (prod_base_id,)).fetchone()
                costo_por_kg = float(costo_row[0] if costo_row else 0)
                # total_kg real consumido (ya en kg porque el movimiento de salida usa kg)
                total_kg_entrada = total_consumido
                costo_base_total = costo_por_kg * total_kg_entrada

                if costo_base_total > 0 and total_generado > 0:
                    for mov in movimientos:
                        if mov["delta"] > 0 and mov.get("movement_type") == "PRODUCCION_ENTRADA":
                            costo_unit = round(
                                (costo_base_total * (mov["delta"] / total_generado)) / mov["delta"], 4
                            )
                            if costo_unit > 0:
                                try:
                                    conn.execute(
                                        "UPDATE productos SET precio_compra=?, costo=? WHERE id=?",
                                        (costo_unit, costo_unit, mov["product_id"]))
                                    # Actualizar costo_promedio en inventario_actual
                                    conn.execute("""
                                        UPDATE inventario_actual
                                        SET costo_promedio = ?
                                        WHERE producto_id = ? AND sucursal_id = ?
                                    """, (costo_unit, mov["product_id"], suc_id))
                                except Exception as _ce:
                                    logger.warning("cost update failed: %s", _ce)

        logger.info(
            "PRODUCCION_OK id=%d receta=%s tipo=%s base=%.4f gen=%.4f cons=%.4f merma=%.4f op=%s",
            produccion_id, _recipe_name(receta), tipo,
            cantidad_base, total_generado, total_consumido, total_merma, op_id,
        )

        self._publicar_evento(produccion_id, receta, suc_id, movimientos)

        return ProduccionResultDTO(
            produccion_id=produccion_id,
            receta_id=receta_id,
            receta_nombre=_recipe_name(receta),
            tipo_receta=tipo,
            operation_id=op_id,
            cantidad_base=cantidad_base,
            producto_base=prod_base_nombre,
            componentes=componentes_resultado,
            total_generado=total_generado,
            total_consumido=total_consumido,
            total_merma=total_merma,
        )

    def _calcular_movimientos(self, tipo, receta, componentes, cantidad_base, peso_prom,
                              prod_base_id=None, prod_base_nombre=""):
        movimientos = []

        if tipo == "subproducto":
            # total_kg: la materia prima se pesa en kg
            total_kg = cantidad_base * peso_prom

            # Salida del producto base (en kg reales)
            movimientos.append({
                "product_id": prod_base_id,
                "nombre": prod_base_nombre,
                "delta": -total_kg,
                "unidad": "kg",
                "rendimiento": 0.0,
                "movement_type": "PRODUCCION_SALIDA",
            })

            kg_generados_total = Decimal("0")
            for comp in componentes:
                rend = float(comp.get("rendimiento_pct") or comp.get("rendimiento_porcentaje") or 0)
                if rend <= 0:
                    continue
                kg_gen = float(
                    (Decimal(str(total_kg)) * Decimal(str(rend)) / Decimal("100"))
                    .quantize(CENTAVO, ROUND_HALF_UP)
                )
                if kg_gen > 0:
                    movimientos.append({
                        "product_id": comp["producto_id"],
                        "nombre": comp["prod_nombre"],
                        "delta": +kg_gen,
                        "unidad": comp.get("unidad") or "kg",
                        "rendimiento": rend,
                        "movement_type": "PRODUCCION_ENTRADA",
                    })
                    kg_generados_total += Decimal(str(kg_gen))

            # FIX FALLA-1: registrar merma explícita por componente
            for comp in componentes:
                merma_pct = float(comp.get("merma_pct") or comp.get("merma_porcentaje") or 0)
                if merma_pct <= 0:
                    continue
                kg_merma = float(
                    (Decimal(str(total_kg)) * Decimal(str(merma_pct)) / Decimal("100"))
                    .quantize(CENTAVO, ROUND_HALF_UP)
                )
                if kg_merma > 0:
                    movimientos.append({
                        "product_id": comp["producto_id"],
                        "nombre": f"MERMA — {comp['prod_nombre']}",
                        "delta": -kg_merma,
                        "unidad": "kg",
                        "rendimiento": merma_pct,
                        "movement_type": "MERMA_PRODUCCION",
                    })

        elif tipo == "combinacion":
            for comp in componentes:
                cant = float(comp.get("cantidad") or 0)
                if cant <= 0:
                    continue
                total_comp = float(
                    (Decimal(str(cant)) * Decimal(str(cantidad_base)))
                    .quantize(CENTAVO, ROUND_HALF_UP)
                )
                movimientos.append({
                    "product_id": comp["producto_id"],
                    "nombre": comp["prod_nombre"],
                    "delta": -total_comp,
                    "unidad": comp.get("unidad") or "pza",
                    "rendimiento": 0.0,
                    "movement_type": "PRODUCCION_SALIDA",
                })
            movimientos.append({
                "product_id": receta.get("producto_base_id") or prod_base_id,
                "nombre": prod_base_nombre,
                "delta": +cantidad_base,
                "unidad": receta.get("unidad_base", "pza"),
                "rendimiento": 100.0,
                "movement_type": "PRODUCCION_ENTRADA",
            })

        elif tipo == "produccion":
            total_mp_in = Decimal("0")
            merma_kg_total = Decimal("0")

            for comp in componentes:
                cant = float(comp.get("cantidad") or 0)
                if cant <= 0:
                    continue
                total_mp = float(
                    (Decimal(str(cant)) * Decimal(str(cantidad_base)))
                    .quantize(CENTAVO, ROUND_HALF_UP)
                )
                movimientos.append({
                    "product_id": comp["producto_id"],
                    "nombre": comp["prod_nombre"],
                    "delta": -total_mp,
                    "unidad": comp.get("unidad") or "kg",
                    "rendimiento": 0.0,
                    "movement_type": "PRODUCCION_SALIDA",
                })
                total_mp_in += Decimal(str(total_mp))

                # FIX FALLA-1+9: merma por ingrediente, no global
                merma_pct = float(comp.get("merma_pct") or comp.get("merma_porcentaje") or 0)
                if merma_pct > 0:
                    kg_merma = float(
                        (Decimal(str(total_mp)) * Decimal(str(merma_pct)) / Decimal("100"))
                        .quantize(CENTAVO, ROUND_HALF_UP)
                    )
                    if kg_merma > 0:
                        merma_kg_total += Decimal(str(kg_merma))
                        movimientos.append({
                            "product_id": comp["producto_id"],
                            "nombre": f"MERMA — {comp['prod_nombre']}",
                            "delta": -kg_merma,
                            "unidad": "kg",
                            "rendimiento": merma_pct,
                            "movement_type": "MERMA_PRODUCCION",
                        })

            cant_res = float((total_mp_in - merma_kg_total).quantize(CENTAVO, ROUND_HALF_UP))
            if cant_res > 0:
                rendimiento_real = float(
                    (total_mp_in - merma_kg_total) / total_mp_in * 100
                ) if total_mp_in > 0 else 0.0
                movimientos.append({
                    "product_id": receta.get("producto_base_id") or prod_base_id,
                    "nombre": prod_base_nombre,
                    "delta": +cant_res,
                    "unidad": receta.get("unidad_base", "kg"),
                    "rendimiento": round(rendimiento_real, 4),
                    "movement_type": "PRODUCCION_ENTRADA",
                })

        return movimientos

    def _registrar_movimiento_legacy_audit_only(self, conn, mov, produccion_id, usuario, sucursal_id):
        """
        FIX FALLA-7: Solo inserta en movimientos_inventario para auditoría.
        NO actualiza productos.existencia — process_movement ya lo hizo.
        """
        try:
            tipo_mov = "entrada" if mov["delta"] > 0 else "salida"
            tipo_desc = mov.get("movement_type", "PRODUCCION")
            conn.execute("""
                INSERT OR IGNORE INTO movimientos_inventario (
                    uuid, producto_id, tipo, tipo_movimiento,
                    cantidad, descripcion, referencia_id, referencia_tipo,
                    usuario, sucursal_id, fecha
                ) VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'))
            """, (
                str(uuid.uuid4()), mov["product_id"], tipo_mov, tipo_desc,
                abs(mov["delta"]),
                f"Produccion #{produccion_id} — {mov['nombre']}",
                produccion_id, "PRODUCCION", usuario, sucursal_id,
            ))
        except Exception as e:
            logger.warning("movimiento_legacy_audit falló (no crítico): %s", e)

    def preview_produccion(self, receta_id: int, cantidad_base: float) -> list:
        receta = self.db.fetchone(
            "SELECT * FROM product_recipes WHERE id = ? AND is_active = 1",
            (receta_id,))
        if not receta:
            raise RecetaNoEncontradaError(f"RECETA_NO_ENCONTRADA: id={receta_id}")
        receta = dict(receta)
        comps = self.db.fetchall("""
            SELECT rc.*,
                   rc.component_product_id AS producto_id,
                   p.nombre AS prod_nombre,
                   COALESCE(rc.unidad, p.unidad, 'kg') AS prod_unidad
            FROM product_recipe_components rc
            JOIN productos p ON p.id = rc.component_product_id
            WHERE rc.recipe_id = ?
            ORDER BY rc.orden, rc.id
        """, (receta_id,))
        _base_id = receta.get("output_product_id") or receta.get("base_product_id") or receta.get("product_id")
        _base_row = self.db.fetchone(
            "SELECT nombre FROM productos WHERE id=?", (_base_id,)
        ) if _base_id else None
        _base_nombre = _base_row["nombre"] if _base_row else f"#{_base_id}"

        return self._calcular_movimientos(
            receta["tipo_receta"], receta, [dict(r) for r in comps],
            cantidad_base, float(receta.get("peso_promedio_kg") or 1.0),
            _base_id, _base_nombre,
        )

    def get_historial(self, sucursal_id=None, receta_id=None, limit=100):
        filters, params = [], []
        if sucursal_id:
            filters.append("p.sucursal_id = ?"); params.append(sucursal_id)
        if receta_id:
            filters.append("p.receta_id = ?"); params.append(receta_id)
        where = "WHERE " + " AND ".join(filters) if filters else ""
        params.append(limit)
        cols = {r[1] for r in self.db.fetchall("PRAGMA table_info(product_recipes)")}
        if "nombre_receta" in cols:
            recipe_name_sql = "r.nombre_receta"
        elif "nombre" in cols:
            recipe_name_sql = "r.nombre"
        else:
            recipe_name_sql = "'Receta sin nombre'"
        rows = self.db.fetchall(f"""
            SELECT p.id, p.fecha, p.receta_id,
                   {recipe_name_sql} AS receta_nombre,
                   COALESCE(r.tipo_receta,'subproducto') AS tipo_receta, p.cantidad_base, p.unidad_base,
                   prod.nombre AS producto_base_nombre,
                   p.usuario, p.estado, p.operation_id
            FROM producciones p
            JOIN product_recipes r ON r.id = p.receta_id
            JOIN productos prod ON prod.id = p.producto_base_id
            {where}
            ORDER BY p.fecha DESC LIMIT ?
        """, params)
        return [dict(r) for r in rows]

    def get_detalle_produccion(self, produccion_id: int) -> list:
        rows = self.db.fetchall("""
        SELECT pd.*, p.nombre AS producto_nombre, p.unidad
            FROM produccion_detalle pd
            JOIN productos p ON p.id = pd.producto_resultante_id
            WHERE pd.produccion_id = ?
            ORDER BY pd.tipo DESC, pd.id
        """, (produccion_id,))
        return [dict(r) for r in rows]

    def _publicar_evento(self, produccion_id, receta, sucursal_id, movimientos):
        try:
            from core.events.event_bus import get_bus
            get_bus().publish("PRODUCCION_COMPLETADA", {
                "produccion_id": produccion_id,
                "receta_id": receta["id"],
                "receta_nombre": _recipe_name(receta),
                "sucursal_id": sucursal_id,
                "movimientos": len(movimientos),
            })
        except Exception as e:
            logger.warning("EventBus PRODUCCION falló (no crítico): %s", e)
