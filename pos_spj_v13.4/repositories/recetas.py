# repositories/recetas.py
# ── RecetaRepository — Enterprise Repository Layer ───────────────────────────
# Enforces: no cyclic dependencies, no self-reference,
#           sum(componentes.rendimiento + merma) <= 100%,
#           FK constraints, ON DELETE RESTRICT, one recipe per base product.
from __future__ import annotations

import logging
import sqlite3
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Set

from backend.shared.ids import new_uuid
from core.events.event_bus import EventBus

logger = logging.getLogger("spj.repositories.recetas")

RECETA_CREADA      = "RECETA_CREADA"
RECETA_ACTUALIZADA = "RECETA_ACTUALIZADA"

TOLERANCE = Decimal("0.01")
MAX_TOTAL = Decimal("100.00")


class RecetaError(Exception):
    pass


class RecetaCyclicError(RecetaError):
    pass


class RecetaSelfReferenceError(RecetaError):
    pass


class RecetaPercentageError(RecetaError):
    pass


class RecetaDuplicadaError(RecetaError):
    pass


class RecetaRepository:

    def __init__(self, db):
        # Usar DatabaseWrapper para garantizar fetchall/fetchone/transaction
        from core.db.connection import wrap
        self.db = wrap(db)

        # Detect all columns in product_recipes
        self._product_columns = self._get_table_columns('product_recipes')
        self._component_columns = self._get_table_columns('product_recipe_components')
        # Determine which column to use for product reference (prefer product_id if exists)
        self._product_col = self._detect_product_column()
        self._ensure_component_columns()

    def _get_table_columns(self, table_name: str) -> Set[str]:
        """Return a set of column names for the given table."""
        try:
            rows = self.db.execute(f"PRAGMA table_info({table_name})").fetchall()
            return {row[1] for row in rows}
        except Exception as e:
            logger.warning(f"Could not get columns for {table_name}: {e}")
            return set()

    def _detect_product_column(self) -> str:
        """Determine which column to use for product reference (prefer product_id)."""
        if 'product_id' in self._product_columns:
            return 'product_id'
        elif 'base_product_id' in self._product_columns:
            return 'base_product_id'
        else:
            # Fallback: use base_product_id as it was just added by _ensure_product_recipes_columns
            logger.warning("product_recipes missing product columns — using base_product_id fallback")
            return 'base_product_id'

    # ── Read ─────────────────────────────────────────────────────────────────

    def get_all(self, *, include_inactive: bool = False) -> List[Dict]:
        where = "" if include_inactive else "WHERE r.is_active = 1"
        rows = self.db.execute(f"""
            SELECT r.id, r.nombre_receta,
                   r.{self._product_col} AS base_product_id,
                   p.nombre AS base_product_nombre,
                   r.total_rendimiento, r.total_merma,
                   r.is_active, r.created_at
            FROM product_recipes r
            LEFT JOIN productos p ON p.id = r.{self._product_col}
            {where}
            ORDER BY r.nombre_receta
        """).fetchall()
        return [dict(r) for r in rows]

    def get_by_id(self, receta_id: int) -> Optional[Dict]:
        row = self.db.execute(f"""
            SELECT r.*, p.nombre AS base_product_nombre,
                   r.{self._product_col} AS base_product_id
            FROM product_recipes r
            LEFT JOIN productos p ON p.id = r.{self._product_col}
            WHERE r.id = ?
        """, (receta_id,)).fetchone()
        return dict(row) if row else None

    def get_components(self, receta_id: int) -> List[Dict]:
        unidad_expr = "COALESCE(rc.unidad, p.unidad, 'kg')" if "unidad" in self._component_columns else "COALESCE(p.unidad, 'kg')"
        cantidad_expr = "COALESCE(rc.cantidad, 0)" if "cantidad" in self._component_columns else "0"
        role_expr = "COALESCE(rc.component_role, '')" if "component_role" in self._component_columns else "''"
        factor_expr = "COALESCE(rc.factor_costo, 1.0)" if "factor_costo" in self._component_columns else "1.0"
        rows = self.db.execute(f"""
            SELECT rc.id, rc.recipe_id, rc.component_product_id,
                   p.nombre AS component_nombre, {unidad_expr} AS unidad,
                   {cantidad_expr} AS cantidad,
                   {role_expr} AS component_role,
                   {factor_expr} AS factor_costo,
                   rc.rendimiento_pct, rc.merma_pct, rc.orden, rc.descripcion
            FROM product_recipe_components rc
            LEFT JOIN productos p ON p.id = rc.component_product_id
            WHERE rc.recipe_id = ?
            ORDER BY rc.orden, rc.id
        """, (receta_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_for_product(self, base_product_id: int) -> Optional[Dict]:
        row = self.db.execute(f"""
            SELECT *, {self._product_col} AS base_product_id
            FROM product_recipes
            WHERE {self._product_col} = ? AND is_active = 1
        """, (base_product_id,)).fetchone()
        return dict(row) if row else None

    def get_all_components_flat(self) -> List[Dict]:
        rows = self.db.execute("""
            SELECT rc.recipe_id, rc.component_product_id,
                   rc.rendimiento_pct, rc.merma_pct
            FROM product_recipe_components rc
            JOIN product_recipes r ON r.id = rc.recipe_id
            WHERE r.is_active = 1
        """).fetchall()
        return [dict(r) for r in rows]

    # ── Validation ───────────────────────────────────────────────────────────

    def validate_no_cycle(self, base_product_id: int,
                           component_ids: List[int]) -> None:
        """Raises RecetaCyclicError or RecetaSelfReferenceError if cycle detected."""
        if base_product_id in component_ids:
            raise RecetaSelfReferenceError("SELF_REFERENCE_DETECTED")

        # BFS: if any component_id leads back to base_product_id through recipes
        visited: set = {base_product_id}
        queue = list(component_ids)

        while queue:
            current = queue.pop(0)
            if current == base_product_id:
                raise RecetaCyclicError(
                    f"CYCLE_DETECTED: product {current} is ancestor of base {base_product_id}"
                )
            if current in visited:
                continue
            visited.add(current)
            # Find recipes that use current as base product
            rows = self.db.execute(f"""
                SELECT rc.component_product_id
                FROM product_recipe_components rc
                JOIN product_recipes r ON r.id = rc.recipe_id
                WHERE r.{self._product_col} = ? AND r.is_active = 1
            """, (current,)).fetchall()
            for r in rows:
                if r["component_product_id"] not in visited:
                    queue.append(r["component_product_id"])

    def validate_percentages(self, components: List[Dict], tipo_receta: str = "SUBPRODUCTO") -> None:
        """Validación por tipo de receta (FASE 3)."""
        tipo = (tipo_receta or "SUBPRODUCTO").upper().strip()
        if tipo not in {"SUBPRODUCTO", "COMBINACION", "PRODUCCION"}:
            raise RecetaPercentageError(f"TIPO_RECETA_INVALIDO: {tipo_receta}")

        total = Decimal("0")
        for comp in components:
            rend = Decimal(str(comp.get("rendimiento_pct", 0)))
            merma = Decimal(str(comp.get("merma_pct", 0)))
            cantidad = Decimal(str(comp.get("cantidad", 0)))

            if tipo == "SUBPRODUCTO":
                if rend < 0 or merma < 0:
                    raise RecetaPercentageError("NEGATIVE_PERCENTAGE")
                row_total = rend + merma
                if row_total > MAX_TOTAL:
                    raise RecetaPercentageError(
                        f"COMPONENT_EXCEEDS_100: rend={rend} merma={merma}"
                    )
                total += row_total
            else:
                if cantidad <= 0:
                    raise RecetaPercentageError(f"{tipo}_CANTIDAD_DEBE_SER_POSITIVA")

        if tipo == "SUBPRODUCTO":
            if total > MAX_TOTAL + TOLERANCE:
                raise RecetaPercentageError(
                    f"TOTAL_RENDIMIENTO_EXCEEDS_100: {total}"
                )
            if abs(total - MAX_TOTAL) > TOLERANCE:
                raise RecetaPercentageError(
                    f"TOTAL_RENDIMIENTO_MUST_BE_100: {total}"
                )

    def check_unique_base_product(self, base_product_id: int,
                                   exclude_id: Optional[int] = None) -> None:
        if exclude_id:
            row = self.db.execute(f"""
                SELECT id FROM product_recipes
                WHERE {self._product_col} = ? AND id != ? AND is_active = 1
            """, (base_product_id, exclude_id)).fetchone()
        else:
            row = self.db.execute(f"""
                SELECT id FROM product_recipes
                WHERE {self._product_col} = ? AND is_active = 1
            """, (base_product_id,)).fetchone()
        if row:
            raise RecetaDuplicadaError(
                f"RECETA_DUPLICADA: product {base_product_id} already has a recipe"
            )

    def validate_component_products_exist(self, component_ids: List[int]) -> None:
        prod_cols = self._get_table_columns('productos')
        active_col = "is_active" if "is_active" in prod_cols else ("activo" if "activo" in prod_cols else None)
        for cid in component_ids:
            if active_col:
                row = self.db.execute(
                    f"SELECT id FROM productos WHERE id = ? AND COALESCE({active_col},1)=1", (cid,)
                ).fetchone()
            else:
                row = self.db.execute(
                    "SELECT id FROM productos WHERE id = ?", (cid,)
                ).fetchone()
            if not row:
                raise RecetaError(f"COMPONENT_NOT_FOUND: {cid}")

    def _ensure_component_columns(self) -> None:
        alters = []
        if "cantidad" not in self._component_columns:
            alters.append("ALTER TABLE product_recipe_components ADD COLUMN cantidad REAL DEFAULT 0")
        if "unidad" not in self._component_columns:
            alters.append("ALTER TABLE product_recipe_components ADD COLUMN unidad TEXT DEFAULT 'kg'")
        if "component_role" not in self._component_columns:
            alters.append("ALTER TABLE product_recipe_components ADD COLUMN component_role TEXT DEFAULT ''")
        if "factor_costo" not in self._component_columns:
            alters.append("ALTER TABLE product_recipe_components ADD COLUMN factor_costo REAL DEFAULT 1.0")
        for sql in alters:
            try:
                self.db.execute(sql)
            except Exception as exc:
                logger.warning("No se pudo aplicar migración idempotente de componentes: %s", exc)
        if alters:
            self._component_columns = self._get_table_columns('product_recipe_components')

    # ── Write ────────────────────────────────────────────────────────────────

    def create(self, nombre: str, base_product_id: int,
               components: List[Dict], usuario: str,
               tipo_receta: str = "SUBPRODUCTO") -> int:
        """
        components: list of dicts with keys:
            component_product_id, rendimiento_pct, merma_pct, orden, descripcion

        tipo_receta must match the producto's tipo_producto:
            COMBINACION → tipo_producto 'compuesto'
            SUBPRODUCTO → tipo_producto 'procesable'
            PRODUCCION  → tipo_producto 'producido'
        """
        from core.services.recipes.recipe_validation_service import (
            RecipeValidationService, RecetaTypeError as _RTE,
        )

        component_ids = [c["component_product_id"] for c in components]

        # Validate tipo_receta ↔ tipo_producto compatibility
        prod_row = self.db.execute(
            "SELECT tipo_producto FROM productos WHERE id = ?",
            (base_product_id,)
        ).fetchone()
        if prod_row is None:
            raise RecetaError(f"PRODUCT_NOT_FOUND: {base_product_id}")
        tipo_producto = (dict(prod_row) if hasattr(prod_row, 'keys') else
                         {"tipo_producto": prod_row[0]})["tipo_producto"] or "simple"
        try:
            RecipeValidationService.validate_tipo_receta_producto(tipo_receta, tipo_producto)
        except _RTE as exc:
            raise RecetaError(str(exc)) from exc

        # Validate
        self.check_unique_base_product(base_product_id)
        self.validate_no_cycle(base_product_id, component_ids)
        self.validate_component_products_exist(component_ids)
        self.validate_percentages(components, tipo_receta)

        total_rend = sum(
            Decimal(str(c.get("rendimiento_pct", 0))) for c in components
        )
        total_merma = sum(
            Decimal(str(c.get("merma_pct", 0))) for c in components
        )

        from datetime import datetime
        now = datetime.utcnow().isoformat()

        # Build dynamic INSERT — solo columnas que REALMENTE existen en product_recipes
        # para evitar OperationalError con columnas opcionales (activa, validates_at, etc.)
        columns: list = []
        placeholders: list = []
        parameters: list = []

        def _add(col: str, val) -> None:
            if col in self._product_columns:
                columns.append(col)
                placeholders.append('?')
                parameters.append(val)

        # Identidad UUIDv7 (REGLA CERO): mintar el id explícito, nunca lastrowid.
        receta_id = new_uuid()
        _add('id',               receta_id)
        _add('nombre_receta',    nombre.strip())
        _add('tipo_receta',      tipo_receta.upper())
        _add('total_rendimiento', float(total_rend))
        _add('total_merma',      float(total_merma))
        _add('is_active',        1)
        _add('activa',           1)           # columna opcional (legacy)
        _add('created_at',       now)
        _add('validates_at',     now)         # columna opcional (legacy)
        # Columnas de referencia al producto base (detectadas dinámicamente)
        # FASE 0: Forzar piece_product_id = base_product_id para evitar IntegrityError
        _add('piece_product_id', base_product_id)
        _add('product_id',       base_product_id)
        _add('base_product_id',  base_product_id)
        # piece_product_id: NOT NULL — usar base_product_id como valor por defecto
        # evita IntegrityError cuando el llamador no provee este campo (Fase 0 hotfix)
        _add('piece_product_id', base_product_id)

        if not columns:
            raise RecetaError("No se encontraron columnas válidas en product_recipes")

        with self.db.transaction("RECETA_CREATE"):
            # Insert the recipe (id UUIDv7 explícito, ya incluido en columns)
            sql = f"INSERT INTO product_recipes ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"
            self.db.execute(sql, parameters)

            # Insert components (cada línea con su propio id UUIDv7)
            for i, comp in enumerate(components):
                self.db.execute("""
                    INSERT INTO product_recipe_components (
                        id, recipe_id, component_product_id,
                        rendimiento_pct, merma_pct, cantidad, unidad, component_role, factor_costo,
                        tolerancia_pct, orden, descripcion
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    new_uuid(),
                    receta_id,
                    comp["component_product_id"],
                    float(Decimal(str(comp.get("rendimiento_pct", 0)))),
                    float(Decimal(str(comp.get("merma_pct", 0)))),
                    float(Decimal(str(comp.get("cantidad", 0)))),
                    (comp.get("unidad") or "kg"),
                    (comp.get("component_role") or ""),
                    float(Decimal(str(comp.get("factor_costo", 1.0)))),
                    float(comp.get("tolerancia_pct", 2.0)),
                    comp.get("orden", i),
                    comp.get("descripcion", ""),
                ))

            self._rebuild_dependency_graph(receta_id, base_product_id, component_ids)

        EventBus().publish(RECETA_CREADA, {
            "receta_id":       receta_id,
            "base_product_id": base_product_id,
            "tipo_receta":     tipo_receta.upper(),
        })
        return receta_id

    def update(self, receta_id: int, nombre: str,
               components: List[Dict], usuario: str) -> None:
        existing = self.get_by_id(receta_id)
        if not existing:
            raise RecetaError("RECETA_NOT_FOUND")

        base_product_id = existing["base_product_id"]
        component_ids = [c["component_product_id"] for c in components]

        from core.services.recipes.recipe_validation_service import (
            RecipeValidationService, RecetaTypeError as _RTE,
        )

        tipo_receta = (existing.get("tipo_receta") or "SUBPRODUCTO").upper().strip()
        prod_row = self.db.execute(
            "SELECT tipo_producto FROM productos WHERE id = ?",
            (base_product_id,)
        ).fetchone()
        tipo_producto = (dict(prod_row) if hasattr(prod_row, "keys") else {"tipo_producto": prod_row[0]})["tipo_producto"] if prod_row else "simple"
        try:
            RecipeValidationService.validate_tipo_receta_producto(tipo_receta, tipo_producto)
        except _RTE as exc:
            raise RecetaError(str(exc)) from exc

        self.validate_no_cycle(base_product_id, component_ids)
        self.validate_component_products_exist(component_ids)
        self.validate_percentages(components, tipo_receta)

        total_rend = sum(
            Decimal(str(c.get("rendimiento_pct", 0))) for c in components
        )
        total_merma = sum(
            Decimal(str(c.get("merma_pct", 0))) for c in components
        )

        from datetime import datetime
        now = datetime.utcnow().isoformat()

        with self.db.transaction("RECETA_UPDATE"):
            self.db.execute("""
                UPDATE product_recipes SET
                    nombre_receta = ?,
                    total_rendimiento = ?,
                    total_merma = ?,
                    validates_at = ?
                WHERE id = ?
            """, (
                nombre.strip(),
                float(total_rend), float(total_merma),
                now, receta_id,
            ))

            # Replace components atomically
            self.db.execute(
                "DELETE FROM product_recipe_components WHERE recipe_id = ?",
                (receta_id,)
            )
            for i, comp in enumerate(components):
                self.db.execute("""
                    INSERT INTO product_recipe_components (
                        recipe_id, component_product_id,
                        rendimiento_pct, merma_pct, cantidad, unidad, component_role, factor_costo,
                        tolerancia_pct, orden, descripcion
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    receta_id,
                    comp["component_product_id"],
                    float(Decimal(str(comp.get("rendimiento_pct", 0)))),
                    float(Decimal(str(comp.get("merma_pct", 0)))),
                    float(Decimal(str(comp.get("cantidad", 0)))),
                    (comp.get("unidad") or "kg"),
                    (comp.get("component_role") or ""),
                    float(Decimal(str(comp.get("factor_costo", 1.0)))),
                    float(comp.get("tolerancia_pct", 2.0)),
                    comp.get("orden", i),
                    comp.get("descripcion", ""),
                ))

            self._rebuild_dependency_graph(receta_id, base_product_id, component_ids)

        EventBus().publish(RECETA_ACTUALIZADA, {
            "receta_id": receta_id,
            "base_product_id": base_product_id
        })

    def deactivate(self, receta_id: int, usuario: str) -> None:
        with self.db.transaction("RECETA_DEACTIVATE"):
            self.db.execute(
                "UPDATE product_recipes SET is_active = 0, activa = 0 WHERE id = ?",
                (receta_id,)
            )
            self.db.execute(
                "DELETE FROM recipe_dependency_graph WHERE parent_recipe_id = ?",
                (receta_id,)
            )

    # ── Internals ─────────────────────────────────────────────────────────────

    def _rebuild_dependency_graph(self, receta_id: int,
                                   base_product_id: int,
                                   component_ids: List[int]) -> None:
        self.db.execute(
            "DELETE FROM recipe_dependency_graph WHERE parent_recipe_id = ?",
            (receta_id,)
        )
        for cid in component_ids:
            try:
                self.db.execute("""
                    INSERT OR IGNORE INTO recipe_dependency_graph
                    (parent_recipe_id, child_product_id, depth)
                    VALUES (?,?,1)
                """, (receta_id, cid))
            except Exception as exc:
                logger.warning("dependency_graph insert failed: %s", exc)

    # ── Métodos de lectura rápida (antes en recipe_repository.py) ─────────
    # Usados por SalesService para productos compuestos

    def get_active_recipe_for_product(self, base_product_id: int):
        """Receta activa para un producto base."""
        row = self.db.execute(f"""
            SELECT id, nombre_receta, total_rendimiento, total_merma
            FROM product_recipes
            WHERE {self._product_col} = ? AND is_active = 1 LIMIT 1
        """, (base_product_id,)).fetchone()
        return dict(row) if row else None

    def get_recipe_items(self, recipe_id: int) -> list:
        """Componentes de una receta por recipe_id."""
        rows = self.db.execute(
            "SELECT component_product_id, rendimiento_pct, merma_pct, orden "
            "FROM product_recipe_components WHERE recipe_id=? ORDER BY orden",
            (recipe_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_recipe_items_by_product(self, combo_product_id: int) -> list:
        """Componentes de un producto compuesto (para descuento en venta)."""
        rows = self.db.execute(f"""
            SELECT rc.component_product_id,
                   COALESCE(rc.cantidad, 0) AS cantidad,
                   COALESCE(rc.rendimiento_pct, 0) AS rendimiento_pct,
                   COALESCE(rc.merma_pct, 0) AS merma_pct,
                   COALESCE(r.tipo_receta, 'combinacion') AS tipo_receta
            FROM product_recipe_components rc
            JOIN product_recipes r ON r.id = rc.recipe_id
            WHERE r.{self._product_col} = ? AND r.is_active = 1
            ORDER BY rc.orden, rc.id
        """, (combo_product_id,)).fetchall()
        if rows:
            return [dict(r) for r in rows]
        # Fallback: legacy componentes_producto
        rows2 = self.db.execute(
            "SELECT producto_componente_id AS component_product_id, cantidad "
            "FROM componentes_producto WHERE producto_compuesto_id = ?",
            (combo_product_id,)
        ).fetchall()
        return [dict(r) for r in rows2]

    def get_ids_con_receta(self, product_ids: list) -> set:
        """Batch check: returns set of product IDs that have at least one active recipe."""
        if not product_ids:
            return set()
        ph = ",".join("?" * len(product_ids))
        ids = list(product_ids)
        try:
            rows = self.db.execute(
                f"""SELECT DISTINCT c FROM (
                        SELECT producto_id      AS c FROM recetas
                        WHERE  producto_id      IN ({ph}) AND (activa=1 OR activo=1)
                        UNION
                        SELECT producto_base_id AS c FROM recetas
                        WHERE  producto_base_id IN ({ph}) AND (activa=1 OR activo=1)
                    )""",
                ids + ids,
            ).fetchall()
            return {r[0] for r in rows}
        except Exception:
            return set()

    def get_componentes_insumo(self, producto_id: int) -> list:
        """Return recipe components for a product (tries legacy receta_componentes first)."""
        try:
            rows = self.db.execute("""
                SELECT rc.producto_id AS insumo_id,
                       COALESCE(rc.cantidad, 0) AS cantidad_insumo,
                       p.nombre AS insumo_nombre
                FROM receta_componentes rc
                JOIN recetas r ON r.id = rc.receta_id
                JOIN productos p ON p.id = rc.producto_id
                WHERE (r.producto_base_id=? OR r.producto_id=?)
                  AND (r.activo=1 OR r.activa=1)
            """, (producto_id, producto_id)).fetchall()
            if rows:
                return [dict(r) for r in rows]
        except Exception:
            pass
        try:
            rows = self.db.execute("""
                SELECT rc.component_product_id AS insumo_id,
                       COALESCE(rc.cantidad, 0) AS cantidad_insumo,
                       p.nombre AS insumo_nombre
                FROM product_recipe_components rc
                JOIN product_recipes r ON r.id = rc.recipe_id
                JOIN productos p ON p.id = rc.component_product_id
                WHERE r.base_product_id=? AND r.is_active=1
            """, (producto_id,)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
