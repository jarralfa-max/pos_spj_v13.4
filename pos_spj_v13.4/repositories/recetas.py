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


class _SQLiteTransaction:
    """Context manager for SQLite transactions."""
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        self.conn.execute("BEGIN")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()


class SQLiteConnectionWrapper:
    """Wrapper for sqlite3.Connection that adds a transaction method."""
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def transaction(self, name=None):
        """Return a transaction context manager."""
        return _SQLiteTransaction(self._conn)

    def execute(self, sql, parameters=None):
        """Delegate execute to the underlying connection."""
        if parameters is None:
            return self._conn.execute(sql)
        return self._conn.execute(sql, parameters)

    def __getattr__(self, name):
        """Delegate any other attribute to the underlying connection."""
        return getattr(self._conn, name)


class RecetaRepository:

    def __init__(self, db):
        # Wrap db if it doesn't have a transaction method
        if not hasattr(db, 'transaction'):
            db = SQLiteConnectionWrapper(db)
        self.db = db

        # Detect all columns in product_recipes
        self._product_columns = self._get_table_columns('product_recipes')
        # Determine which column to use for product reference (prefer product_id if exists)
        self._product_col = self._detect_product_column()

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
            raise RecetaError("No product column found in product_recipes")

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
        rows = self.db.execute("""
            SELECT rc.id, rc.recipe_id, rc.component_product_id,
                   p.nombre AS component_nombre, p.unidad,
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

    def validate_percentages(self, components: List[Dict]) -> None:
        """Validates sum(rendimiento_pct + merma_pct) <= 100.00 per component,
        and total rendimiento does not exceed 100%."""
        total = Decimal("0")
        for comp in components:
            rend = Decimal(str(comp.get("rendimiento_pct", 0)))
            merma = Decimal(str(comp.get("merma_pct", 0)))
            if rend < 0 or merma < 0:
                raise RecetaPercentageError("NEGATIVE_PERCENTAGE")
            row_total = rend + merma
            if row_total > MAX_TOTAL:
                raise RecetaPercentageError(
                    f"COMPONENT_EXCEEDS_100: rend={rend} merma={merma}"
                )
            total += rend

        if total > MAX_TOTAL + TOLERANCE:
            raise RecetaPercentageError(
                f"TOTAL_RENDIMIENTO_EXCEEDS_100: {total}"
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
        for cid in component_ids:
            row = self.db.execute(
                "SELECT id FROM productos WHERE id = ? AND is_active = 1", (cid,)
            ).fetchone()
            if not row:
                raise RecetaError(f"COMPONENT_NOT_FOUND: {cid}")

    # ── Write ────────────────────────────────────────────────────────────────

    def create(self, nombre: str, base_product_id: int,
               components: List[Dict], usuario: str) -> int:
        """
        components: list of dicts with keys:
            component_product_id, rendimiento_pct, merma_pct, orden, descripcion
        """
        component_ids = [c["component_product_id"] for c in components]

        # Validate
        self.check_unique_base_product(base_product_id)
        self.validate_no_cycle(base_product_id, component_ids)
        self.validate_component_products_exist(component_ids)
        self.validate_percentages(components)

        total_rend = sum(
            Decimal(str(c.get("rendimiento_pct", 0))) for c in components
        )
        total_merma = sum(
            Decimal(str(c.get("merma_pct", 0))) for c in components
        )

        from datetime import datetime
        now = datetime.utcnow().isoformat()

        # Build dynamic INSERT with all required product columns
        columns = ['nombre_receta', 'total_rendimiento', 'total_merma',
                   'is_active', 'activa', 'created_at', 'validates_at']
        placeholders = ['?'] * len(columns)
        parameters = [nombre.strip(), float(total_rend), float(total_merma), 1, 1, now, now]

        # Ensure product_id is always inserted if it exists (to avoid NOT NULL constraint)
        if 'product_id' in self._product_columns:
            if 'product_id' not in columns:
                columns.append('product_id')
                placeholders.append('?')
                parameters.append(base_product_id)
        # Also insert base_product_id if it exists (for backward compatibility)
        if 'base_product_id' in self._product_columns:
            if 'base_product_id' not in columns:
                columns.append('base_product_id')
                placeholders.append('?')
                parameters.append(base_product_id)

        with self.db.transaction("RECETA_CREATE"):
            # Insert the recipe
            sql = f"INSERT INTO product_recipes ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"
            self.db.execute(sql, parameters)

            # Retrieve the generated ID
            row = self.db.execute(f"""
                SELECT id FROM product_recipes
                WHERE {self._product_col} = ?
                ORDER BY id DESC LIMIT 1
            """, (base_product_id,)).fetchone()
            receta_id = row["id"]

            # Insert components
            for i, comp in enumerate(components):
                self.db.execute("""
                    INSERT INTO product_recipe_components (
                        recipe_id, component_product_id,
                        rendimiento_pct, merma_pct,
                        tolerancia_pct, orden, descripcion
                    ) VALUES (?,?,?,?,?,?,?)
                """, (
                    receta_id,
                    comp["component_product_id"],
                    float(Decimal(str(comp.get("rendimiento_pct", 0)))),
                    float(Decimal(str(comp.get("merma_pct", 0)))),
                    float(comp.get("tolerancia_pct", 2.0)),
                    comp.get("orden", i),
                    comp.get("descripcion", ""),
                ))

            self._rebuild_dependency_graph(receta_id, base_product_id, component_ids)

        EventBus.publish(RECETA_CREADA, {
            "receta_id": receta_id,
            "base_product_id": base_product_id
        })
        return receta_id

    def update(self, receta_id: int, nombre: str,
               components: List[Dict], usuario: str) -> None:
        existing = self.get_by_id(receta_id)
        if not existing:
            raise RecetaError("RECETA_NOT_FOUND")

        base_product_id = existing["base_product_id"]
        component_ids = [c["component_product_id"] for c in components]

        self.validate_no_cycle(base_product_id, component_ids)
        self.validate_component_products_exist(component_ids)
        self.validate_percentages(components)

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
                        rendimiento_pct, merma_pct,
                        tolerancia_pct, orden, descripcion
                    ) VALUES (?,?,?,?,?,?,?)
                """, (
                    receta_id,
                    comp["component_product_id"],
                    float(Decimal(str(comp.get("rendimiento_pct", 0)))),
                    float(Decimal(str(comp.get("merma_pct", 0)))),
                    float(comp.get("tolerancia_pct", 2.0)),
                    comp.get("orden", i),
                    comp.get("descripcion", ""),
                ))

            self._rebuild_dependency_graph(receta_id, base_product_id, component_ids)

        EventBus.publish(RECETA_ACTUALIZADA, {
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