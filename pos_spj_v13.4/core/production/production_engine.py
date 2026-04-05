
# core/production/production_engine.py
# ── ProductionEngine — Motor Central de Producción Cárnica Industrial ─────────
#
# RESPONSABILIDADES:
#   ✔ Crear lote (production_batches) en estado 'abierto'
#   ✔ Agregar / quitar subproductos (production_outputs) mientras abierto
#   ✔ Cerrar lote:
#       a. Validar balance matemático (tolerancia 0.5%)
#       b. Validar costo (protección financiera)
#       c. Consumir materia prima → branch_inventory PRODUCCION_CONSUMO
#       d. Generar subproductos → branch_inventory PRODUCCION_GENERACION
#       e. Registrar en movimientos_inventario
#       f. Distribuir costos → production_cost_ledger
#       g. Análisis de rendimiento → production_yield_analysis
#       h. Alertas de merma → production_alerts
#       i. Publicar PRODUCTION_BATCH_CREATED
#   ✔ Cancelar lote (solo si abierto)
#   ✔ Consultas: lotes, outputs, historial, rendimiento promedio
#
# GARANTÍAS:
#   ✔ BEGIN IMMEDIATE en cierre de lote (operación crítica)
#   ✔ InventoryEngine.process_movement(conn=conn) para branch_inventory
#   ✔ ROLLBACK total ante cualquier fallo
#   ✔ Idempotencia por operation_id
#   ✔ Sin stock negativo (salvo configuración)
#
# Versión: 1.0 — Fase 9
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from core.production.yield_calculator import YieldCalculator, OutputSpec, YieldResult
from core.production.cost_allocator import CostAllocator
from core.services.inventory_engine import InventoryEngine

logger = logging.getLogger("spj.production.engine")

COST_TOLERANCE_PCT = Decimal("10.0")   # 10% diferencia costo total vs valor inventario


# ── Excepciones ───────────────────────────────────────────────────────────────

class ProductionEngineError(Exception):
    pass

class BatchNotFoundError(ProductionEngineError):
    pass

class BatchAlreadyClosedError(ProductionEngineError):
    pass

class WeightBalanceError(ProductionEngineError):
    pass

class CostProtectionError(ProductionEngineError):
    pass

class DuplicateOutputError(ProductionEngineError):
    pass

class InvalidWeightError(ProductionEngineError):
    pass


# ── DTOs ──────────────────────────────────────────────────────────────────────

@dataclass
class BatchOpenDTO:
    batch_id: str
    folio: str
    product_source_id: int
    source_nombre: str
    source_weight: float
    source_cost_total: float
    branch_id: int
    receta_id: Optional[int]

@dataclass
class BatchCloseDTO:
    batch_id: str
    folio: str
    yield_result: YieldResult
    inventory_movements: int
    cost_allocations: int
    alertas: int
    operation_id: str

@dataclass
class OutputDTO:
    output_id: str
    batch_id: str
    product_id: int
    nombre: str
    weight: float
    expected_pct: float
    is_waste: bool


# ══════════════════════════════════════════════════════════════════════════════

class ProductionEngine:
    """
    Motor de producción cárnica industrial.

    Uso típico:
        engine = ProductionEngine(db, branch_id=1)

        # 1. Abrir lote
        batch = engine.open_batch(
            product_source_id=1, source_weight=100.0,
            source_cost_total=4500.0, created_by="Juan"
        )

        # 2. Agregar subproductos
        engine.add_output(batch.batch_id, product_id=2, weight=32.0)
        engine.add_output(batch.batch_id, product_id=3, weight=28.0, is_waste=False)

        # 3. Cerrar lote (atómico)
        result = engine.close_batch(batch.batch_id, closed_by="Juan")
    """

    def __init__(self, db, branch_id: int):
        self.db = db
        self.branch_id = branch_id

    def _now(self) -> str:
        return datetime.utcnow().isoformat()

    def _generar_folio(self, conn) -> str:
        n = conn.execute("SELECT COUNT(*) FROM production_batches").fetchone()[0]
        return f"PROD{datetime.now().strftime('%Y%m%d')}-{(n or 0) + 1:04d}"

    def _get_batch(self, conn, batch_id: str) -> dict:
        row = conn.execute(
            "SELECT * FROM production_batches WHERE id = ?", (batch_id,)
        ).fetchone()
        if not row:
            raise BatchNotFoundError(f"Lote {batch_id} no encontrado")
        return dict(row)

    def _get_outputs(self, conn, batch_id: str) -> List[dict]:
        rows = conn.execute("""
            SELECT po.*, p.nombre AS prod_nombre
            FROM production_outputs po
            LEFT JOIN productos p ON p.id = po.product_id
            WHERE po.batch_id = ?
            ORDER BY po.is_waste, p.nombre
        """, (batch_id,)).fetchall()
        return [dict(r) for r in rows]

    def _get_receta_componentes(self, conn, receta_id: int) -> List[dict]:
        rows = conn.execute("""
        SELECT rc.*, p.nombre AS prod_nombre
            FROM receta_componentes rc
            LEFT JOIN productos p ON p.id = rc.producto_id
            WHERE rc.receta_id = ?
            ORDER BY rc.orden
        """, (receta_id,)).fetchall()
        return [dict(r) for r in rows]

    def _publicar_evento(self, batch_id: str, folio: str, branch_id: int) -> None:
        try:
            from core.events.event_bus import get_bus
            get_bus().publish("PRODUCTION_BATCH_CREATED", {
                "batch_id": batch_id,
                "folio": folio,
                "branch_id": branch_id,
            })
        except Exception as exc:
            logger.warning("EventBus PRODUCTION falló (no crítico): %s", exc)

    # ═════════════════════════════════════════════════════════════════════════
    # ABRIR LOTE
    # ═════════════════════════════════════════════════════════════════════════

    def open_batch(
        self,
        product_source_id: int,
        source_weight: float,
        created_by: str,
        source_cost_total: float = 0.0,
        receta_id: Optional[int] = None,
        notas: str = "",
        branch_id: Optional[int] = None,
        operation_id: Optional[str] = None,
    ) -> BatchOpenDTO:
        """
        Crea un lote de producción en estado 'abierto'.
        No toca inventario — solo registra el lote.
        """
        if source_weight <= 0:
            raise InvalidWeightError("source_weight debe ser > 0")
        if not created_by:
            raise ProductionEngineError("created_by es obligatorio")

        bid = branch_id or self.branch_id
        op_id = operation_id or str(uuid.uuid4())
        batch_id = str(uuid.uuid4())

        conn = self.db.conn
        folio = self._generar_folio(conn)

        conn.execute(f"SAVEPOINT sp_b85df2")
        try:
            # Verificar producto fuente existe
            prod = conn.execute(
                "SELECT id, nombre, costo FROM productos WHERE id=? AND activo=1",
                (product_source_id,)
            ).fetchone()
            if not prod:
                raise ProductionEngineError(f"Producto fuente {product_source_id} no existe o no activo")

            # Si no se provee costo, usar costo del producto × peso
            costo = source_cost_total if source_cost_total > 0 else float(prod["costo"] or 0) * source_weight

            conn.execute("""
                INSERT INTO production_batches (
                    id, folio, product_source_id, source_weight,
                    processed_weight, waste_weight,
                    source_cost_total, branch_id, receta_id,
                    estado, created_by, created_at, operation_id, notas
                ) VALUES (?,?,?,?,0,0,?,?,?,
                          'abierto',?,datetime('now'),?,?)
            """, (batch_id, folio, product_source_id, source_weight,
                  costo, bid, receta_id, created_by, op_id, notas))
            conn.execute(f"RELEASE SAVEPOINT sp_b85df2")
        except Exception:
            try: conn.execute(f"ROLLBACK TO SAVEPOINT sp_b85df2")
            except Exception: pass
            raise

        logger.info("Lote abierto: id=%s folio=%s fuente=%s peso=%.3f",
                    batch_id[:8], folio, prod["nombre"], source_weight)

        return BatchOpenDTO(
            batch_id=batch_id, folio=folio,
            product_source_id=product_source_id,
            source_nombre=prod["nombre"],
            source_weight=source_weight,
            source_cost_total=costo,
            branch_id=bid,
            receta_id=receta_id,
        )

    # ═════════════════════════════════════════════════════════════════════════
    # AGREGAR / QUITAR SUBPRODUCTO
    # ═════════════════════════════════════════════════════════════════════════

    def add_output(
        self,
        batch_id: str,
        product_id: int,
        weight: float,
        expected_pct: float = 0.0,
        is_waste: bool = False,
    ) -> OutputDTO:
        """Agrega un subproducto al lote (solo si está abierto)."""
        if weight < 0:
            raise InvalidWeightError("peso no puede ser negativo")

        conn = self.db.conn
        conn.execute(f"SAVEPOINT sp_06cfbd")
        try:
            batch = self._get_batch(conn, batch_id)
            if batch["estado"] != "abierto":
                raise BatchAlreadyClosedError(f"Lote {batch_id[:8]} ya está {batch['estado']}")

            # Verificar producto existe
            prod = conn.execute(
                "SELECT id, nombre FROM productos WHERE id=? AND activo=1",
                (product_id,)
            ).fetchone()
            if not prod:
                raise ProductionEngineError(f"Producto {product_id} no existe o no activo")

            output_id = str(uuid.uuid4())
            conn.execute("""
                INSERT INTO production_outputs
                    (id, batch_id, product_id, weight, expected_pct,
                     expected_weight, cost_allocated, is_waste)
                VALUES (?,?,?,?,?,?,0,?)
                ON CONFLICT(batch_id, product_id) DO UPDATE SET
                    weight=excluded.weight,
                    expected_pct=excluded.expected_pct,
                    expected_weight=excluded.expected_weight
            """, (output_id, batch_id, product_id, weight, expected_pct,
                  round(float(batch["source_weight"]) * expected_pct / 100, 4),
                  1 if is_waste else 0))

            # Obtener ID real (puede ser el existente en caso de UPDATE)
            actual_id = conn.execute(
                "SELECT id FROM production_outputs WHERE batch_id=? AND product_id=?",
                (batch_id, product_id)
            ).fetchone()[0]

            conn.execute(f"RELEASE SAVEPOINT sp_06cfbd")
        except Exception:
            try: conn.execute(f"ROLLBACK TO SAVEPOINT sp_06cfbd")
            except Exception: pass
            raise

        return OutputDTO(
            output_id=actual_id, batch_id=batch_id,
            product_id=product_id, nombre=prod["nombre"],
            weight=weight, expected_pct=expected_pct, is_waste=is_waste,
        )

    def remove_output(self, batch_id: str, product_id: int) -> None:
        """Elimina un subproducto del lote (solo si abierto)."""
        conn = self.db.conn
        conn.execute(f"SAVEPOINT sp_0cbb1a")
        try:
            batch = self._get_batch(conn, batch_id)
            if batch["estado"] != "abierto":
                raise BatchAlreadyClosedError("Lote ya cerrado, no se puede modificar")
            conn.execute(
                "DELETE FROM production_outputs WHERE batch_id=? AND product_id=?",
                (batch_id, product_id)
            )
            conn.execute(f"RELEASE SAVEPOINT sp_0cbb1a")
        except Exception:
            try: conn.execute(f"ROLLBACK TO SAVEPOINT sp_0cbb1a")
            except Exception: pass
            raise

    # ═════════════════════════════════════════════════════════════════════════
    # CARGAR OUTPUTS DESDE RECETA
    # ═════════════════════════════════════════════════════════════════════════

    def load_outputs_from_receta(self, batch_id: str) -> List[OutputDTO]:
        """
        Carga los subproductos esperados desde la receta del lote.
        Útil para pre-rellenar el formulario de producción.
        """
        conn = self.db.conn
        batch = self._get_batch(conn, batch_id)
        receta_id = batch.get("receta_id")
        if not receta_id:
            return []
        comps = self._get_receta_componentes(conn, receta_id)
        outputs = []
        for c in comps:
            pct = float(c.get("rendimiento_porcentaje", 0) or 0)
            merma = float(c.get("merma_porcentaje", 0) or 0)
            is_waste = merma > 0 and pct == 0
            expected_w = float(batch["source_weight"]) * pct / 100
            dto = self.add_output(
                batch_id, c["producto_id"],
                weight=round(expected_w, 3),
                expected_pct=pct, is_waste=is_waste,
            )
            outputs.append(dto)
        return outputs

    # ═════════════════════════════════════════════════════════════════════════
    # PREVIEW (sin modificar DB)
    # ═════════════════════════════════════════════════════════════════════════

    def preview_batch(self, batch_id: str) -> YieldResult:
        """Calcula rendimiento y costos sin cerrar el lote."""
        conn = self.db.conn
        batch = self._get_batch(conn, batch_id)
        raw_outputs = self._get_outputs(conn, batch_id)

        # Obtener rendimiento esperado de receta
        exp_usable_pct = 0.0
        exp_waste_pct  = 0.0
        if batch.get("receta_id"):
            receta = conn.execute(
                "SELECT rendimiento_esperado_pct, merma_esperada_pct FROM recetas WHERE id=?",
                (batch["receta_id"],)
            ).fetchone()
            if receta:
                exp_usable_pct = float(receta["rendimiento_esperado_pct"] or 0)
                exp_waste_pct  = float(receta["merma_esperada_pct"] or 0)

        specs = [
            OutputSpec(
                product_id=r["product_id"], nombre=r["prod_nombre"],
                expected_pct=float(r["expected_pct"] or 0),
                real_weight=float(r["weight"]),
                is_waste=bool(r["is_waste"]),
            )
            for r in raw_outputs
        ]
        return YieldCalculator.calculate(
            source_weight=float(batch["source_weight"]),
            outputs=specs,
            source_cost_total=float(batch["source_cost_total"]),
            expected_usable_pct=exp_usable_pct,
            expected_waste_pct=exp_waste_pct,
        )

    # ═════════════════════════════════════════════════════════════════════════
    # CERRAR LOTE (OPERACIÓN ATÓMICA)
    # ═════════════════════════════════════════════════════════════════════════

    def close_batch(
        self,
        batch_id: str,
        closed_by: str,
        force_financial: bool = False,
    ) -> BatchCloseDTO:
        """
        Cierra un lote de producción en una transacción BEGIN IMMEDIATE.

        Flujo:
            1. Validar lote abierto
            2. Calcular rendimiento (YieldCalculator)
            3. Validar balance matemático
            4. Validar protección financiera (opcional, bloqueable)
            5. Consumir materia prima (InventoryEngine)
            6. Generar subproductos (InventoryEngine, uno por output)
            7. Actualizar production_batches (processed/waste weight, closed)
            8. Actualizar production_outputs (cost_allocated)
            9. INSERT production_yield_analysis
            10. INSERT production_alerts si merma excesiva
            11. INSERT production_cost_ledger
            12. Publicar PRODUCTION_BATCH_CREATED
        """
        op_id = str(uuid.uuid4())
        inv_eng = InventoryEngine(self.db, self.branch_id, closed_by)

        with self.db.transaction("CLOSE_BATCH"):
            conn = self.db.conn

            batch = self._get_batch(conn, batch_id)
            if batch["estado"] == "cerrado":
                raise BatchAlreadyClosedError(f"Lote {batch_id[:8]} ya está cerrado")
            if batch["estado"] == "cancelado":
                raise BatchAlreadyClosedError(f"Lote {batch_id[:8]} fue cancelado")

            raw_outputs = self._get_outputs(conn, batch_id)
            if not raw_outputs:
                raise ProductionEngineError("El lote no tiene subproductos. Agregue al menos uno.")

            src_weight = float(batch["source_weight"])
            src_cost   = float(batch["source_cost_total"])
            bid        = int(batch["branch_id"])
            src_prod_id= int(batch["product_source_id"])

            # ── Rendimiento esperado desde receta ─────────────────────────
            exp_usable_pct = 0.0
            exp_waste_pct  = 0.0
            if batch.get("receta_id"):
                receta = conn.execute(
                    "SELECT rendimiento_esperado_pct, merma_esperada_pct FROM recetas WHERE id=?",
                    (batch["receta_id"],)
                ).fetchone()
                if receta:
                    exp_usable_pct = float(receta["rendimiento_esperado_pct"] or 0)
                    exp_waste_pct  = float(receta["merma_esperada_pct"] or 0)

            specs = [
                OutputSpec(
                    product_id=r["product_id"], nombre=r["prod_nombre"],
                    expected_pct=float(r["expected_pct"] or 0),
                    real_weight=float(r["weight"]),
                    is_waste=bool(r["is_waste"]),
                )
                for r in raw_outputs
            ]

            # ── 3. Validar balance matemático ─────────────────────────────
            ok, msg = YieldCalculator.validate_weight_balance(src_weight, specs)
            if not ok:
                raise WeightBalanceError(msg)

            # ── 4. Calcular rendimiento ───────────────────────────────────
            yr = YieldCalculator.calculate(
                source_weight=src_weight, outputs=specs,
                source_cost_total=src_cost,
                expected_usable_pct=exp_usable_pct,
                expected_waste_pct=exp_waste_pct,
            )

            # ── 5. Validar protección financiera ──────────────────────────
            if not force_financial and src_cost > 0:
                valor_generado = sum(o.cost_allocated for o in yr.outputs)
                diferencia_pct = abs(valor_generado - src_cost) / src_cost * 100
                if diferencia_pct > float(COST_TOLERANCE_PCT):
                    raise CostProtectionError(
                        f"COSTO_INCONSISTENTE: costo_fuente=${src_cost:.2f} "
                        f"vs valor_generado=${valor_generado:.2f} "
                        f"diferencia={diferencia_pct:.1f}% > {COST_TOLERANCE_PCT}%"
                    )

            # ── 6. Consumir materia prima ─────────────────────────────────
            inv_eng.process_movement(
                product_id=src_prod_id, branch_id=bid,
                quantity=-src_weight,
                movement_type="PRODUCCION_CONSUMO",
                operation_id=f"{op_id}_CONSUMO",
                reference_id=None, reference_type="PRODUCTION_BATCH",
                conn=conn,
            )
            # También registrar en movimientos_inventario legacy
            conn.execute("""
                INSERT INTO movimientos_inventario
                    (uuid, producto_id, tipo, tipo_movimiento, cantidad,
                     costo_unitario, descripcion, referencia_tipo,
                     usuario, sucursal_id, fecha)
                VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'))
            """, (str(uuid.uuid4()), src_prod_id, "salida", "PRODUCCION_CONSUMO",
                  src_weight,
                  src_cost / src_weight if src_weight else 0,
                  f"Consumo lote {batch['folio']}", "PRODUCTION_BATCH",
                  closed_by, bid))

            # ── 7. Generar subproductos en inventario ─────────────────────
            output_id_map = {r["product_id"]: r["id"] for r in raw_outputs}
            for out_yield in yr.outputs:
                if out_yield.real_weight <= 0:
                    continue
                inv_eng.process_movement(
                    product_id=out_yield.product_id, branch_id=bid,
                    quantity=+out_yield.real_weight,
                    movement_type="PRODUCCION_GENERACION",
                    operation_id=f"{op_id}_OUT_{out_yield.product_id}",
                    reference_id=None, reference_type="PRODUCTION_BATCH",
                    conn=conn,
                )
                # Legacy movimientos_inventario
                conn.execute("""
                    INSERT INTO movimientos_inventario
                        (uuid, producto_id, tipo, tipo_movimiento, cantidad,
                         costo_unitario, descripcion, referencia_tipo,
                         usuario, sucursal_id, fecha)
                    VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'))
                """, (str(uuid.uuid4()), out_yield.product_id, "entrada", "PRODUCCION_GENERACION",
                      out_yield.real_weight,
                      out_yield.cost_allocated / out_yield.real_weight if out_yield.real_weight else 0,
                      f"Generado lote {batch['folio']}", "PRODUCTION_BATCH",
                      closed_by, bid))

            # ── 8. Actualizar production_batches ──────────────────────────
            conn.execute("""
                UPDATE production_batches SET
                    processed_weight = ?,
                    waste_weight = ?,
                    estado = 'cerrado',
                    closed_by = ?,
                    closed_at = datetime('now')
                WHERE id = ?
            """, (yr.usable_weight, yr.waste_weight, closed_by, batch_id))

            # ── 9. Actualizar production_outputs (costo asignado) ─────────
            for out_yield in yr.outputs:
                conn.execute("""
        UPDATE production_outputs SET cost_allocated = ?
                    WHERE batch_id = ? AND product_id = ?
                """, (out_yield.cost_allocated, batch_id, out_yield.product_id))

            # ── 10. Análisis de rendimiento ───────────────────────────────
            yield_analysis_id = str(uuid.uuid4())
            conn.execute("""
        INSERT INTO production_yield_analysis
                    (id, batch_id, expected_yield, real_yield,
                     waste_expected, waste_real, alerta_merma)
                VALUES (?,?,?,?,?,?,?)
            """, (yield_analysis_id, batch_id,
                  exp_usable_pct, yr.usable_pct,
                  exp_waste_pct, yr.waste_pct,
                  1 if yr.alerta_merma else 0))

            # ── 11. Alertas de merma ──────────────────────────────────────
            alertas = 0
            if yr.alerta_merma:
                conn.execute("""
        INSERT INTO production_alerts
                        (batch_id, tipo, mensaje, valor_esperado, valor_real, varianza)
                    VALUES (?,?,?,?,?,?)
                """, (batch_id, "MERMA_EXCESIVA",
                      f"Merma real {yr.waste_pct:.2f}% supera esperado {exp_waste_pct:.2f}%",
                      exp_waste_pct, yr.waste_pct, yr.waste_pct - exp_waste_pct))
                alertas += 1

            # Alerta si varianza de rendimiento > 5%
            if abs(yr.variance_pct) > 5.0 and exp_usable_pct > 0:
                conn.execute("""
                    INSERT INTO production_alerts
                        (batch_id, tipo, mensaje, valor_esperado, valor_real, varianza)
                    VALUES (?,?,?,?,?,?)
                """, (batch_id, "RENDIMIENTO_VARIANZA",
                      f"Rendimiento real {yr.usable_pct:.2f}% vs esperado {exp_usable_pct:.2f}%",
                      exp_usable_pct, yr.usable_pct, yr.variance_pct))
                alertas += 1

            # ── 12. Distribución de costos ────────────────────────────────
            allocations = YieldCalculator.allocate_costs(yr.outputs, src_cost)
            allocator = CostAllocator(conn)
            allocator.persist_allocations(batch_id, allocations, output_id_map)
            # Actualizar costo promedio en productos
            for a in allocations:
                if a.cost_per_kg > 0:
                    allocator.update_product_average_cost(a.product_id, a.cost_per_kg)

        # Publicar evento (fuera de transacción)
        self._publicar_evento(batch_id, batch["folio"], bid)

        logger.info(
            "Lote cerrado: %s folio=%s rendimiento=%.2f%% merma=%.2f%% alertas=%d",
            batch_id[:8], batch["folio"], yr.usable_pct, yr.waste_pct, alertas
        )

        return BatchCloseDTO(
            batch_id=batch_id, folio=batch["folio"],
            yield_result=yr,
            inventory_movements=len(raw_outputs) + 1,
            cost_allocations=len(allocations),
            alertas=alertas,
            operation_id=op_id,
        )

    # ═════════════════════════════════════════════════════════════════════════
    # CANCELAR LOTE
    # ═════════════════════════════════════════════════════════════════════════

    def cancel_batch(self, batch_id: str, cancelled_by: str, motivo: str = "") -> None:
        """Cancela un lote si está abierto."""
        conn = self.db.conn
        conn.execute(f"SAVEPOINT sp_35582a")
        try:
            batch = self._get_batch(conn, batch_id)
            if batch["estado"] == "cerrado":
                raise BatchAlreadyClosedError("No se puede cancelar un lote ya cerrado")
            conn.execute("""
                UPDATE production_batches SET
                    estado = 'cancelado',
                    closed_by = ?,
                    closed_at = datetime('now'),
                    notas = COALESCE(notas,'') || ' | CANCELADO: ' || ?
                WHERE id = ?
            """, (cancelled_by, motivo, batch_id))
            conn.execute(f"RELEASE SAVEPOINT sp_35582a")
        except Exception:
            try: conn.execute(f"ROLLBACK TO SAVEPOINT sp_35582a")
            except Exception: pass
            raise
        logger.info("Lote cancelado: %s por %s", batch_id[:8], cancelled_by)

    # ═════════════════════════════════════════════════════════════════════════
    # CONSULTAS
    # ═════════════════════════════════════════════════════════════════════════

    def get_batches(
        self,
        branch_id: Optional[int] = None,
        estado: Optional[str] = None,
        fecha_desde: str = "",
        fecha_hasta: str = "",
        limit: int = 100,
    ) -> List[Dict]:
        filters, params = [], []
        if branch_id:
            filters.append("pb.branch_id=?"); params.append(branch_id)
        if estado:
            filters.append("pb.estado=?"); params.append(estado)
        if fecha_desde:
            filters.append("pb.created_at>=?"); params.append(fecha_desde)
        if fecha_hasta:
            filters.append("pb.created_at<=?"); params.append(fecha_hasta + "T23:59:59")
        where = "WHERE " + " AND ".join(filters) if filters else ""
        params.append(limit)
        rows = self.db.fetchall(f"""
            SELECT pb.*,
                   p.nombre AS fuente_nombre, p.unidad AS fuente_unidad,
                   s.nombre AS sucursal_nombre,
                   pya.real_yield, pya.expected_yield, pya.variance,
                   pya.waste_real, pya.alerta_merma,
                   COUNT(po.id) AS total_outputs,
                   (SELECT COUNT(*) FROM production_alerts pa
                    WHERE pa.batch_id = pb.id AND pa.resuelta = 0) AS alertas_abiertas
            FROM production_batches pb
            LEFT JOIN productos p ON p.id = pb.product_source_id
            LEFT JOIN sucursales s ON s.id = pb.branch_id
            LEFT JOIN production_yield_analysis pya ON pya.batch_id = pb.id
            LEFT JOIN production_outputs po ON po.batch_id = pb.id
            {where}
            GROUP BY pb.id
            ORDER BY pb.created_at DESC
            LIMIT ?
        """, params)
        return [dict(r) for r in rows]

    def get_batch_detail(self, batch_id: str) -> Dict:
        """Detalle completo de un lote con outputs y análisis."""
        conn = self.db.conn
        batch = self._get_batch(conn, batch_id)
        outputs = self._get_outputs(conn, batch_id)
        yield_analysis = conn.execute(
            "SELECT * FROM production_yield_analysis WHERE batch_id=?",
            (batch_id,)
        ).fetchone()
        alerts = conn.execute(
            "SELECT * FROM production_alerts WHERE batch_id=? ORDER BY created_at",
            (batch_id,)
        ).fetchall()
        cost_ledger = conn.execute(
            "SELECT cl.*, p.nombre AS prod_nombre FROM production_cost_ledger cl "
            "LEFT JOIN productos p ON p.id = cl.product_id WHERE cl.batch_id=?",
            (batch_id,)
        ).fetchall()
        return {
            "batch": batch,
            "outputs": outputs,
            "yield_analysis": dict(yield_analysis) if yield_analysis else None,
            "alerts": [dict(a) for a in alerts],
            "cost_ledger": [dict(c) for c in cost_ledger],
        }

    def get_rendimiento_promedio(
        self,
        branch_id: Optional[int] = None,
        product_source_id: Optional[int] = None,
        dias: int = 30,
    ) -> Dict:
        """Análisis de rendimiento promedio de los últimos N días."""
        filters, params = ["pb.estado='cerrado'"], []
        if branch_id:
            filters.append("pb.branch_id=?"); params.append(branch_id)
        if product_source_id:
            filters.append("pb.product_source_id=?"); params.append(product_source_id)
        filters.append(f"pb.created_at >= datetime('now','-{dias} days')")
        where = "WHERE " + " AND ".join(filters)
        row = self.db.fetchone(f"""
            SELECT
                COUNT(pb.id)            AS total_lotes,
                SUM(pb.source_weight)   AS total_fuente_kg,
                SUM(pb.processed_weight) AS total_procesado_kg,
                SUM(pb.waste_weight)    AS total_merma_kg,
                AVG(pya.real_yield)     AS rendimiento_promedio,
                AVG(pya.waste_real)     AS merma_promedio,
                MIN(pya.real_yield)     AS rendimiento_min,
                MAX(pya.real_yield)     AS rendimiento_max,
                SUM(pb.source_cost_total) AS costo_total
            FROM production_batches pb
            LEFT JOIN production_yield_analysis pya ON pya.batch_id = pb.id
            {where}
        """, params)
        return dict(row) if row else {}

    def get_produccion_por_sucursal(self, dias: int = 30) -> List[Dict]:
        rows = self.db.fetchall("""
        SELECT
                s.nombre AS sucursal,
                COUNT(pb.id) AS lotes,
                SUM(pb.source_weight) AS total_kg_entrada,
                SUM(pb.processed_weight) AS total_kg_salida,
                AVG(pya.real_yield) AS rendimiento_prom,
                SUM(pb.source_cost_total) AS costo_total
            FROM production_batches pb
            LEFT JOIN sucursales s ON s.id = pb.branch_id
            LEFT JOIN production_yield_analysis pya ON pya.batch_id = pb.id
            WHERE pb.estado='cerrado'
              AND pb.created_at >= datetime('now', ? || ' days')
            GROUP BY pb.branch_id
            ORDER BY lotes DESC
        """, (f"-{dias}",))
        return [dict(r) for r in rows]

    def get_alertas_activas(self, branch_id: Optional[int] = None) -> List[Dict]:
        params = []
        where = "WHERE pa.resuelta=0"
        if branch_id:
            where += " AND pb.branch_id=?"
            params.append(branch_id)
        rows = self.db.fetchall(f"""
            SELECT pa.*, pb.folio, pb.branch_id, p.nombre AS fuente_nombre
            FROM production_alerts pa
            JOIN production_batches pb ON pb.id = pa.batch_id
            LEFT JOIN productos p ON p.id = pb.product_source_id
            {where}
            ORDER BY pa.created_at DESC
        """, params)
        return [dict(r) for r in rows]

    def resolver_alerta(self, alerta_id: int) -> None:
        self.db.execute(
            "UPDATE production_alerts SET resuelta=1 WHERE id=?",
            (alerta_id,)
        )
