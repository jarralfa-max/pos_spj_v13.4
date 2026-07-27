"""
tests/test_recipe_resolver.py — FASE 4 ERP Refactor

Verifica que RecipeResolver:
  - Explota correctamente el BOM para productos compuestos (resolve_for_sale)
  - Productos simples/procesables/producidos → deducción directa (sin explosión)
  - Explosión recursiva: compuesto de compuestos
  - Detección de ciclos: A→B→A no provoca recursión infinita
  - virtual_availability: mínimo de componentes disponibles
  - resolve_for_production: plan de entradas/salidas por tipo de receta
"""
from __future__ import annotations

import sqlite3
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.services.recipes.recipe_resolver import (
    RecipeResolver, BOMExplosion, BOMCycleError, DeductionLine,
)


# ── Fixture: in-memory DB ─────────────────────────────────────────────────────

@pytest.fixture()
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE productos (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre        TEXT NOT NULL,
            unidad        TEXT DEFAULT 'kg',
            activo        INTEGER DEFAULT 1,
            tipo_producto TEXT DEFAULT 'simple',
            existencia    REAL DEFAULT 0
        );

        CREATE TABLE branch_inventory (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            branch_id  INTEGER NOT NULL,
            quantity   REAL DEFAULT 0
        );

        CREATE TABLE product_recipes (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_receta     TEXT NOT NULL,
            product_id        INTEGER,
            tipo_receta       TEXT DEFAULT 'SUBPRODUCTO',
            total_rendimiento REAL DEFAULT 0,
            total_merma       REAL DEFAULT 0,
            is_active         INTEGER NOT NULL DEFAULT 1,
            peso_promedio_kg  REAL DEFAULT 1.0
        );

        CREATE TABLE product_recipe_components (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id            INTEGER NOT NULL,
            component_product_id INTEGER NOT NULL,
            cantidad             REAL DEFAULT 0,
            rendimiento_pct      REAL DEFAULT 0,
            merma_pct            REAL DEFAULT 0,
            tolerancia_pct       REAL DEFAULT 2.0,
            orden                INTEGER DEFAULT 0
        );
    """)

    # Products
    # id=1  Pollo Entero    procesable  — has own stock
    # id=2  Pechuga         procesable  — has own stock
    # id=3  Pierna          procesable  — has own stock
    # id=4  Surtido         compuesto   — virtual (no own stock)
    # id=5  Pack Familiar   compuesto   — virtual, contains Surtido (nested)
    # id=6  Insumo Simple   simple
    conn.executescript("""
        INSERT INTO productos (nombre, tipo_producto, existencia)
        VALUES
            ('Pollo Entero',   'procesable', 10.0),
            ('Pechuga',        'procesable',  8.0),
            ('Pierna',         'procesable',  6.0),
            ('Surtido',        'compuesto',   0.0),
            ('Pack Familiar',  'compuesto',   0.0),
            ('Insumo Simple',  'simple',      5.0);
    """)

    # branch_inventory for branch 1
    conn.executescript("""
        INSERT INTO branch_inventory (product_id, branch_id, quantity)
        VALUES
            (1, 1, 10.0),   -- Pollo Entero
            (2, 1,  8.0),   -- Pechuga
            (3, 1,  6.0),   -- Pierna
            (6, 1,  5.0);   -- Insumo Simple
    """)

    # Recipe for Surtido (compuesto):
    #   60% Pechuga + 40% Pierna  → stored as rendimiento_pct
    conn.execute(
        "INSERT INTO product_recipes (nombre_receta, product_id, tipo_receta) "
        "VALUES ('Surtido Básico', 4, 'COMBINACION')"
    )
    surtido_recipe_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO product_recipe_components "
        "(recipe_id, component_product_id, rendimiento_pct) VALUES (?, 2, 60.0)",
        (surtido_recipe_id,)
    )
    conn.execute(
        "INSERT INTO product_recipe_components "
        "(recipe_id, component_product_id, rendimiento_pct) VALUES (?, 3, 40.0)",
        (surtido_recipe_id,)
    )

    # Recipe for Pack Familiar (compuesto of compuesto):
    #   50% Surtido + 50% Pierna  — nested BOM
    conn.execute(
        "INSERT INTO product_recipes (nombre_receta, product_id, tipo_receta) "
        "VALUES ('Pack Familiar Grande', 5, 'COMBINACION')"
    )
    pack_recipe_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO product_recipe_components "
        "(recipe_id, component_product_id, rendimiento_pct) VALUES (?, 4, 50.0)",
        (pack_recipe_id,)  # 50% Surtido (itself compuesto)
    )
    conn.execute(
        "INSERT INTO product_recipe_components "
        "(recipe_id, component_product_id, rendimiento_pct) VALUES (?, 3, 50.0)",
        (pack_recipe_id,)  # 50% Pierna
    )

    # Recipe for Pollo Entero (subproducto):
    #   100kg Pollo Entero → 40kg Pechuga + 30kg Pierna + 20kg Ala + 10% merma
    conn.execute(
        "INSERT INTO product_recipes "
        "(nombre_receta, product_id, tipo_receta, peso_promedio_kg) "
        "VALUES ('Despiece Pollo', 1, 'SUBPRODUCTO', 1.0)"
    )
    despiece_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO product_recipe_components "
        "(recipe_id, component_product_id, rendimiento_pct, merma_pct) "
        "VALUES (?, 2, 40.0, 5.0)",
        (despiece_id,)  # 40% Pechuga + 5% merma
    )
    conn.execute(
        "INSERT INTO product_recipe_components "
        "(recipe_id, component_product_id, rendimiento_pct) VALUES (?, 3, 30.0)",
        (despiece_id,)  # 30% Pierna
    )

    conn.commit()
    yield conn
    conn.close()


@pytest.fixture()
def resolver(db):
    return RecipeResolver(db)


# ── resolve_for_sale — productos directos ─────────────────────────────────────

class TestResolveForSaleDirect:

    def test_simple_product_returns_direct_deduction(self, resolver):
        explosion = resolver.resolve_for_sale(6, 3.0, branch_id=1)
        assert not explosion.is_virtual
        assert not explosion.cycle_detected
        assert len(explosion.deductions) == 1
        d = explosion.deductions[0]
        assert d.product_id == 6
        assert abs(d.quantity - 3.0) < 0.001

    def test_procesable_product_returns_direct_deduction(self, resolver):
        explosion = resolver.resolve_for_sale(2, 1.5, branch_id=1)
        assert not explosion.is_virtual
        assert len(explosion.deductions) == 1
        assert explosion.deductions[0].product_id == 2
        assert abs(explosion.deductions[0].quantity - 1.5) < 0.001

    def test_root_product_id_preserved(self, resolver):
        explosion = resolver.resolve_for_sale(6, 2.0, branch_id=1)
        assert explosion.root_product_id == 6
        assert abs(explosion.requested_qty - 2.0) < 0.001


# ── resolve_for_sale — productos compuestos (BOM) ─────────────────────────────

class TestResolveForSaleCompuesto:

    def test_surtido_explodes_into_components(self, resolver):
        """Surtido (compuesto): 60% Pechuga + 40% Pierna."""
        explosion = resolver.resolve_for_sale(4, 2.0, branch_id=1)
        assert explosion.is_virtual
        assert not explosion.cycle_detected
        assert len(explosion.deductions) == 2

        by_pid = {d.product_id: d for d in explosion.deductions}
        assert 2 in by_pid  # Pechuga
        assert 3 in by_pid  # Pierna
        assert abs(by_pid[2].quantity - 1.2) < 0.001   # 2.0 * 0.60
        assert abs(by_pid[3].quantity - 0.8) < 0.001   # 2.0 * 0.40

    def test_surtido_does_not_deduct_itself(self, resolver):
        explosion = resolver.resolve_for_sale(4, 1.0, branch_id=1)
        pids = {d.product_id for d in explosion.deductions}
        assert 4 not in pids  # Surtido itself must NOT be deducted

    def test_compuesto_sin_receta_falls_back_to_direct(self, resolver, db):
        """A compuesto product with no active recipe falls back to direct deduction."""
        db.execute(
            "INSERT INTO productos (nombre, tipo_producto, existencia) "
            "VALUES ('Sin Receta', 'compuesto', 3.0)"
        )
        db.commit()
        pid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        explosion = resolver.resolve_for_sale(pid, 1.0, branch_id=1)
        assert len(explosion.deductions) == 1
        assert explosion.deductions[0].product_id == pid


# ── Explosión recursiva ───────────────────────────────────────────────────────

class TestRecursiveBOM:

    def test_pack_familiar_expands_nested_compuesto(self, resolver):
        """
        Pack Familiar (compuesto) = 50% Surtido + 50% Pierna
        Surtido (compuesto)       = 60% Pechuga + 40% Pierna

        Selling 1kg Pack Familiar:
          0.5kg Surtido → 0.30kg Pechuga + 0.20kg Pierna
          0.5kg Pierna
        Net deductions: 0.30kg Pechuga + 0.70kg Pierna
        """
        explosion = resolver.resolve_for_sale(5, 1.0, branch_id=1)
        assert explosion.is_virtual
        assert not explosion.cycle_detected

        # Aggregate by product_id (same product can appear multiple times from
        # different BOM paths — the caller is responsible for merging)
        totals: dict[int, float] = {}
        for d in explosion.deductions:
            totals[d.product_id] = totals.get(d.product_id, 0) + d.quantity

        # Pechuga: 0.5 * 0.60 = 0.30
        assert abs(totals.get(2, 0) - 0.30) < 0.001
        # Pierna: (0.5 * 0.40) from Surtido + 0.5 from Pack = 0.70
        assert abs(totals.get(3, 0) - 0.70) < 0.001
        # Pack Familiar itself: not deducted
        assert 5 not in totals
        # Surtido itself: not deducted (expanded)
        assert 4 not in totals

    def test_recursion_depth_one(self, resolver):
        """Single-level BOM has correct deductions."""
        explosion = resolver.resolve_for_sale(4, 10.0, branch_id=1)
        totals = {d.product_id: d.quantity for d in explosion.deductions}
        assert abs(totals.get(2, 0) - 6.0) < 0.001  # 10 * 0.60
        assert abs(totals.get(3, 0) - 4.0) < 0.001  # 10 * 0.40


# ── Detección de ciclos ───────────────────────────────────────────────────────

class TestCycleDetection:

    def _create_cycle(self, db):
        """Create cycle: product A uses product B, B uses A."""
        db.execute(
            "INSERT INTO productos (nombre, tipo_producto) VALUES ('CyclA', 'compuesto')"
        )
        pid_a = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.execute(
            "INSERT INTO productos (nombre, tipo_producto) VALUES ('CyclB', 'compuesto')"
        )
        pid_b = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        db.execute(
            "INSERT INTO product_recipes (nombre_receta, product_id, tipo_receta) "
            "VALUES ('RecA', ?, 'COMBINACION')", (pid_a,)
        )
        rec_a = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.execute(
            "INSERT INTO product_recipe_components "
            "(recipe_id, component_product_id, rendimiento_pct) VALUES (?, ?, 100.0)",
            (rec_a, pid_b)
        )

        db.execute(
            "INSERT INTO product_recipes (nombre_receta, product_id, tipo_receta) "
            "VALUES ('RecB', ?, 'COMBINACION')", (pid_b,)
        )
        rec_b = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.execute(
            "INSERT INTO product_recipe_components "
            "(recipe_id, component_product_id, rendimiento_pct) VALUES (?, ?, 100.0)",
            (rec_b, pid_a)
        )
        db.commit()
        return pid_a, pid_b

    def test_cycle_detected_flag_set(self, resolver, db):
        pid_a, _ = self._create_cycle(db)
        explosion = resolver.resolve_for_sale(pid_a, 1.0, branch_id=1)
        assert explosion.cycle_detected is True

    def test_cycle_does_not_recurse_infinitely(self, resolver, db):
        """resolve_for_sale must return within reasonable time when cycle exists."""
        import time
        pid_a, _ = self._create_cycle(db)
        t0 = time.time()
        resolver.resolve_for_sale(pid_a, 1.0, branch_id=1)
        elapsed = time.time() - t0
        assert elapsed < 1.0, f"BOM expansion took {elapsed:.2f}s — likely infinite recursion"

    def test_cycle_fallback_to_direct_deduction(self, resolver, db):
        pid_a, _ = self._create_cycle(db)
        explosion = resolver.resolve_for_sale(pid_a, 2.0, branch_id=1)
        # Falls back to direct deduction of root product
        assert len(explosion.deductions) == 1
        assert explosion.deductions[0].product_id == pid_a
        assert abs(explosion.deductions[0].quantity - 2.0) < 0.001

    def test_check_cycle_returns_true(self, resolver, db):
        pid_a, _ = self._create_cycle(db)
        assert resolver.check_cycle(pid_a) is True

    def test_check_cycle_returns_false_for_clean_bom(self, resolver):
        assert resolver.check_cycle(4) is False   # Surtido — no cycle
        assert resolver.check_cycle(5) is False   # Pack Familiar — no cycle

    def test_diamond_dependency_not_a_cycle(self, resolver, db):
        """A → B + C, B → D, C → D (diamond): valid, not a cycle."""
        db.execute(
            "INSERT INTO productos (nombre, tipo_producto) "
            "VALUES ('Dia_A','compuesto'),('Dia_B','compuesto'),"
            "       ('Dia_C','compuesto'),('Dia_D','simple')"
        )
        db.commit()
        # Get IDs
        rows = db.execute(
            "SELECT id FROM productos WHERE nombre IN ('Dia_A','Dia_B','Dia_C','Dia_D') "
            "ORDER BY id"
        ).fetchall()
        a, b, c, d = [r[0] for r in rows]

        for pid, comp_id in [(a, b), (a, c), (b, d), (c, d)]:
            db.execute(
                "INSERT INTO product_recipes (nombre_receta, product_id, tipo_receta) "
                "VALUES (?, ?, 'COMBINACION')", (f"rec_{pid}", pid)
            )
            rid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.execute(
                "INSERT INTO product_recipe_components "
                "(recipe_id, component_product_id, rendimiento_pct) VALUES (?, ?, 50.0)",
                (rid, comp_id)
            )
        db.commit()

        # A → B + C → D + D is a valid diamond (not a cycle)
        assert resolver.check_cycle(a) is False
        explosion = resolver.resolve_for_sale(a, 1.0, branch_id=1)
        assert not explosion.cycle_detected


# ── virtual_availability ──────────────────────────────────────────────────────

class TestVirtualAvailability:

    def test_simple_product_returns_own_stock(self, resolver):
        avail = resolver.virtual_availability(6, branch_id=1)
        assert abs(avail - 5.0) < 0.001

    def test_procesable_returns_own_stock(self, resolver):
        avail = resolver.virtual_availability(2, branch_id=1)
        assert abs(avail - 8.0) < 0.001

    def test_surtido_limited_by_pierna(self, resolver):
        """
        Surtido = 60% Pechuga + 40% Pierna.
        Stock: Pechuga=8, Pierna=6.
        Max from Pechuga = 8 / 0.60 = 13.33
        Max from Pierna  = 6 / 0.40 = 15.0
        virtual_availability = min(13.33, 15.0) = 13.33
        """
        avail = resolver.virtual_availability(4, branch_id=1)
        assert abs(avail - 13.333) < 0.01

    def test_surtido_limited_by_pechuga(self, resolver, db):
        """Reduce Pechuga stock so it becomes the constraint."""
        db.execute("UPDATE branch_inventory SET quantity=3.0 WHERE product_id=2 AND branch_id=1")
        db.commit()
        avail = resolver.virtual_availability(4, branch_id=1)
        # Max from Pechuga = 3 / 0.60 = 5.0
        # Max from Pierna  = 6 / 0.40 = 15.0
        assert abs(avail - 5.0) < 0.001

    def test_compuesto_sin_receta_returns_zero(self, resolver, db):
        db.execute(
            "INSERT INTO productos (nombre, tipo_producto, existencia) "
            "VALUES ('SinRec', 'compuesto', 0.0)"
        )
        db.commit()
        pid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        avail = resolver.virtual_availability(pid, branch_id=1)
        assert avail == 0.0

    def test_zero_stock_component_gives_zero(self, resolver, db):
        db.execute("UPDATE branch_inventory SET quantity=0.0 WHERE product_id=2 AND branch_id=1")
        db.commit()
        avail = resolver.virtual_availability(4, branch_id=1)
        assert avail == 0.0


# ── resolve_for_production ────────────────────────────────────────────────────

class TestResolveForProduction:

    def test_subproducto_inputs_are_base_product(self, resolver, db):
        """SUBPRODUCTO: base product is consumed (input)."""
        rid = db.execute(
            "SELECT id FROM product_recipes WHERE product_id=1 AND tipo_receta='SUBPRODUCTO'"
        ).fetchone()[0]
        plan = resolver.resolve_for_production(rid, qty=10.0)
        assert plan.recipe_type == "subproducto"
        assert len(plan.inputs) == 1
        assert plan.inputs[0].product_id == 1   # Pollo Entero consumed
        assert abs(plan.inputs[0].quantity - 10.0) < 0.001

    def test_subproducto_outputs_include_components(self, resolver, db):
        """SUBPRODUCTO: components are the outputs (sub-products produced)."""
        rid = db.execute(
            "SELECT id FROM product_recipes WHERE product_id=1 AND tipo_receta='SUBPRODUCTO'"
        ).fetchone()[0]
        plan = resolver.resolve_for_production(rid, qty=10.0)
        output_types = [o.movement_type for o in plan.outputs]
        assert "PRODUCE" in output_types

        by_pid = {o.product_id: o for o in plan.outputs if o.movement_type == "PRODUCE"}
        # 40% of 10kg = 4kg Pechuga
        assert abs(by_pid[2].quantity - 4.0) < 0.001
        # 30% of 10kg = 3kg Pierna
        assert abs(by_pid[3].quantity - 3.0) < 0.001

    def test_subproducto_merma_in_waste_outputs(self, resolver, db):
        rid = db.execute(
            "SELECT id FROM product_recipes WHERE product_id=1 AND tipo_receta='SUBPRODUCTO'"
        ).fetchone()[0]
        plan = resolver.resolve_for_production(rid, qty=10.0)
        waste = [o for o in plan.outputs if o.movement_type == "WASTE"]
        assert len(waste) > 0
        # Pechuga has 5% merma → 0.5kg on 10kg base
        pechuga_waste = next((w for w in waste if w.product_id == 2), None)
        assert pechuga_waste is not None
        assert abs(pechuga_waste.quantity - 0.5) < 0.001

    def test_combinacion_inputs_are_components(self, resolver, db):
        """COMBINACION: components are consumed (inputs)."""
        rid = db.execute(
            "SELECT id FROM product_recipes WHERE product_id=4 AND tipo_receta='COMBINACION'"
        ).fetchone()[0]
        plan = resolver.resolve_for_production(rid, qty=5.0)
        assert plan.recipe_type == "combinacion"
        # Surtido components: Pechuga (60%) + Pierna (40%)
        pids = {i.product_id for i in plan.inputs if i.movement_type == "CONSUME"}
        assert 2 in pids or 3 in pids

    def test_combinacion_output_is_base_product(self, resolver, db):
        """COMBINACION: base product is produced (output)."""
        rid = db.execute(
            "SELECT id FROM product_recipes WHERE product_id=4 AND tipo_receta='COMBINACION'"
        ).fetchone()[0]
        plan = resolver.resolve_for_production(rid, qty=5.0)
        produce = [o for o in plan.outputs if o.movement_type == "PRODUCE"]
        assert len(produce) == 1
        assert produce[0].product_id == 4    # Surtido
        assert abs(produce[0].quantity - 5.0) < 0.001

    def test_invalid_recipe_id_raises(self, resolver):
        with pytest.raises(ValueError, match="recipe_id"):
            resolver.resolve_for_production(9999, qty=1.0)
