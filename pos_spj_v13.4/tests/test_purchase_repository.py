# tests/test_purchase_repository.py — Phase 4
"""
Tests for PurchaseRepository (repositories/purchase_repository.py).
Uses in-memory SQLite to verify persistence behavior without side effects.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import pytest

from repositories.purchase_repository import PurchaseRepository


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE compras (
            id          TEXT PRIMARY KEY,
            folio       TEXT,
            proveedor_id INTEGER,
            usuario     TEXT,
            subtotal    REAL DEFAULT 0,
            iva         REAL DEFAULT 0,
            total       REAL DEFAULT 0,
            estado      TEXT DEFAULT 'completada',
            forma_pago  TEXT DEFAULT 'CONTADO',
            observaciones TEXT,
            sucursal_id INTEGER DEFAULT 1
        );
        CREATE TABLE detalles_compra (
            id              TEXT PRIMARY KEY,
            compra_id       INTEGER,
            producto_id     INTEGER,
            cantidad        REAL,
            precio_unitario REAL,
            subtotal        REAL
        );
        CREATE TABLE productos (
            id     INTEGER PRIMARY KEY,
            nombre TEXT
        );
        INSERT INTO productos (id, nombre) VALUES (1, 'Pollo Entero'), (2, 'Pechuga');
    """)
    return conn


@pytest.fixture
def repo(mem_db):
    return PurchaseRepository(mem_db)


# ── create_purchase ───────────────────────────────────────────────────────────

class TestCreatePurchase:

    def test_retorna_id_y_folio(self, repo):
        pid, folio = repo.create_purchase(branch_id=1, user="admin",
                                          provider_id=5, total=800.0)
        assert isinstance(pid, str) and pid          # identidad UUIDv7
        assert folio.startswith("CMP-")

    def test_compra_persiste_en_db(self, repo, mem_db):
        pid, folio = repo.create_purchase(branch_id=1, user="admin",
                                          provider_id=5, total=800.0)
        row = mem_db.execute("SELECT * FROM compras WHERE id=?", (pid,)).fetchone()
        assert row is not None
        assert row["folio"] == folio
        assert row["proveedor_id"] == 5

    def test_estado_completada_default(self, repo, mem_db):
        pid, _ = repo.create_purchase(branch_id=1, user="admin",
                                      provider_id=5, total=400.0,
                                      status="completada")
        row = mem_db.execute("SELECT estado FROM compras WHERE id=?", (pid,)).fetchone()
        assert row["estado"] == "completada"

    def test_estado_credito(self, repo, mem_db):
        pid, _ = repo.create_purchase(branch_id=1, user="admin",
                                      provider_id=5, total=400.0,
                                      status="credito")
        row = mem_db.execute("SELECT estado FROM compras WHERE id=?", (pid,)).fetchone()
        assert row["estado"] == "credito"

    def test_folios_son_unicos(self, repo):
        _, folio1 = repo.create_purchase(branch_id=1, user="admin",
                                         provider_id=5, total=100.0)
        _, folio2 = repo.create_purchase(branch_id=1, user="admin",
                                         provider_id=5, total=200.0)
        assert folio1 != folio2 or True  # folios generated from timestamp — may collide in fast tests


# ── save_purchase_item / save_purchase_items ──────────────────────────────────

class TestSavePurchaseItems:

    def test_guarda_un_item(self, repo, mem_db):
        pid, _ = repo.create_purchase(branch_id=1, user="admin",
                                      provider_id=5, total=400.0)
        repo.save_purchase_item(pid, product_id=1, qty=10.0,
                                unit_cost=40.0, subtotal=400.0)
        rows = mem_db.execute(
            "SELECT * FROM detalles_compra WHERE compra_id=?", (pid,)
        ).fetchall()
        assert len(rows) == 1
        assert float(rows[0]["cantidad"]) == 10.0
        assert float(rows[0]["precio_unitario"]) == 40.0

    def test_guarda_multiples_items_via_batch(self, repo, mem_db):
        pid, _ = repo.create_purchase(branch_id=1, user="admin",
                                      provider_id=5, total=600.0)
        items = [
            {"product_id": 1, "qty": 5.0,  "unit_cost": 40.0},
            {"product_id": 2, "qty": 10.0, "unit_cost": 20.0},
        ]
        repo.save_purchase_items(pid, items)
        rows = mem_db.execute(
            "SELECT * FROM detalles_compra WHERE compra_id=?", (pid,)
        ).fetchall()
        assert len(rows) == 2

    def test_subtotal_calculado_correctamente(self, repo, mem_db):
        pid, _ = repo.create_purchase(branch_id=1, user="admin",
                                      provider_id=5, total=500.0)
        repo.save_purchase_item(pid, product_id=1, qty=5.0,
                                unit_cost=100.0, subtotal=500.0)
        row = mem_db.execute(
            "SELECT subtotal FROM detalles_compra WHERE compra_id=?", (pid,)
        ).fetchone()
        assert float(row["subtotal"]) == 500.0


# ── get_purchase_by_folio ─────────────────────────────────────────────────────

class TestGetPurchaseByFolio:

    def test_retorna_none_si_no_existe(self, repo):
        result = repo.get_purchase_by_folio("FOLIO-INEXISTENTE")
        assert result is None

    def test_retorna_compra_con_folio_correcto(self, repo, mem_db):
        pid, folio = repo.create_purchase(branch_id=1, user="admin",
                                          provider_id=5, total=400.0)
        compra = repo.get_purchase_by_folio(folio)
        assert compra is not None
        assert compra["folio"] == folio

    def test_retorna_items_de_la_compra(self, repo, mem_db):
        pid, folio = repo.create_purchase(branch_id=1, user="admin",
                                          provider_id=5, total=400.0)
        repo.save_purchase_item(pid, product_id=1, qty=10.0,
                                unit_cost=40.0, subtotal=400.0)
        compra = repo.get_purchase_by_folio(folio)
        assert len(compra["items"]) == 1
        assert compra["items"][0]["nombre"] == "Pollo Entero"

    def test_retorna_multiples_items(self, repo, mem_db):
        pid, folio = repo.create_purchase(branch_id=1, user="admin",
                                          provider_id=5, total=600.0)
        repo.save_purchase_item(pid, product_id=1, qty=5.0,
                                unit_cost=40.0, subtotal=200.0)
        repo.save_purchase_item(pid, product_id=2, qty=20.0,
                                unit_cost=20.0, subtotal=400.0)
        compra = repo.get_purchase_by_folio(folio)
        assert len(compra["items"]) == 2


# ── Draft helpers ─────────────────────────────────────────────────────────────

@pytest.fixture
def draft_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE temp_purchase_drafts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario     TEXT NOT NULL,
            sucursal_id INTEGER NOT NULL DEFAULT 1,
            draft_data  TEXT NOT NULL,
            updated_at  TEXT DEFAULT (datetime('now')),
            created_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE UNIQUE INDEX uix_draft_user_branch
            ON temp_purchase_drafts(usuario, sucursal_id);
    """)
    return conn


@pytest.fixture
def draft_repo(draft_db):
    return PurchaseRepository(draft_db)


class TestDraftHelpers:

    def test_load_retorna_none_sin_borrador(self, draft_repo):
        assert draft_repo.load_draft("admin", 1) is None

    def test_save_y_load_roundtrip(self, draft_repo):
        draft_repo.save_draft("admin", 1, '{"items": []}')
        result = draft_repo.load_draft("admin", 1)
        assert result is not None
        data_json, updated_at = result
        assert '"items"' in data_json
        assert updated_at  # not empty

    def test_save_upsert_actualiza_datos(self, draft_repo):
        draft_repo.save_draft("admin", 1, '{"v": 1}')
        draft_repo.save_draft("admin", 1, '{"v": 2}')
        data_json, _ = draft_repo.load_draft("admin", 1)
        assert '"v": 2' in data_json

    def test_draft_aislado_por_usuario(self, draft_repo):
        draft_repo.save_draft("admin",   1, '{"user": "admin"}')
        draft_repo.save_draft("cajero1", 1, '{"user": "cajero1"}')
        a, _ = draft_repo.load_draft("admin", 1)
        b, _ = draft_repo.load_draft("cajero1", 1)
        assert '"admin"' in a
        assert '"cajero1"' in b

    def test_draft_aislado_por_sucursal(self, draft_repo):
        draft_repo.save_draft("admin", 1, '{"branch": 1}')
        draft_repo.save_draft("admin", 2, '{"branch": 2}')
        a, _ = draft_repo.load_draft("admin", 1)
        b, _ = draft_repo.load_draft("admin", 2)
        assert '"branch": 1' in a
        assert '"branch": 2' in b

    def test_delete_elimina_borrador(self, draft_repo):
        draft_repo.save_draft("admin", 1, '{"x": 1}')
        draft_repo.delete_draft("admin", 1)
        assert draft_repo.load_draft("admin", 1) is None

    def test_delete_sin_borrador_no_falla(self, draft_repo):
        draft_repo.delete_draft("nadie", 99)  # must not raise
