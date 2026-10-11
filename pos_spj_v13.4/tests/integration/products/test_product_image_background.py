"""PROD-21 — imagen de producto con fondo quitado, visible en la tarjeta del POS.

Flujo completo sobre el esquema canónico: agregar imagen (se copia a la carpeta
de la aplicación) → quitar fondo → el catálogo del POS entrega la versión sin
fondo → la tarjeta la dibuja. Más restaurar, eliminar (limpia archivos),
auditoría, outbox, permisos y la migración 323 sobre una tabla vieja.
"""

from __future__ import annotations

import importlib
import os
import sqlite3
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backend.application.products.authorization.policy import (  # noqa: E402
    ProductsAuthorizationPolicy,
)
from backend.application.products.commands.product_image_commands import (  # noqa: E402
    AddProductImageCommand,
    RemoveImageBackgroundCommand,
    RemoveProductImageCommand,
    RestoreImageBackgroundCommand,
)
from backend.application.products.permissions import ProductPermissions  # noqa: E402
from backend.application.products.queries.product_image_query_service import (  # noqa: E402
    ProductImageQueryService,
)
from backend.application.products.use_cases.product_image_use_cases import (  # noqa: E402
    AddProductImageUseCase,
    RemoveImageBackgroundUseCase,
    RemoveProductImageUseCase,
    RestoreImageBackgroundUseCase,
)
from backend.application.sales.queries.catalog_query_service import (  # noqa: E402
    SalesCatalogQueryService,
)
from backend.domain.products.exceptions import (  # noqa: E402
    ProductImageProcessingError,
    ProductPermissionDeniedError,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema  # noqa: E402
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema  # noqa: E402
from backend.infrastructure.db.schema.products_schema import create_products_schema  # noqa: E402
from backend.infrastructure.media.background_removal import (  # noqa: E402
    EdgeConnectedBackgroundRemover,
)
from backend.infrastructure.media.local_product_image_storage import (  # noqa: E402
    LocalProductImageStorage,
)
from backend.shared.ids import new_uuid  # noqa: E402

BRANCH = "branch-1"


class _Checker:
    def __init__(self, granted):
        self._granted = set(granted)

    def has_permission(self, user_id, code):
        return code in self._granted


_MANAGE = ProductsAuthorizationPolicy(_Checker({ProductPermissions.IMAGES_MANAGE}))


@pytest.fixture(scope="module")
def qapp():
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    create_pricing_schema(c)
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


@pytest.fixture
def storage(tmp_path):
    return LocalProductImageStorage(tmp_path / "imagenes_productos")


@pytest.fixture
def photo(tmp_path) -> str:
    """Foto de producto: disco rojo sobre fondo claro, en el 'escritorio'."""
    desk = tmp_path / "escritorio"
    desk.mkdir()
    img = Image.new("RGB", (600, 450), (244, 244, 240))
    ImageDraw.Draw(img).ellipse((150, 75, 450, 375), fill=(165, 46, 42))
    path = desk / "pechuga.jpg"
    img.save(path, quality=90)
    return str(path)


def _product(conn, name="Pechuga de pollo") -> str:
    pid = new_uuid()
    conn.execute(
        "INSERT INTO products (id, code, name, product_type, base_unit_id, "
        "lifecycle_status) VALUES (?,?,?,?,?,?)",
        (pid, f"P-{pid[-4:]}", name, "RESALE_PRODUCT", "KG", "ACTIVE"))
    row = conn.execute("SELECT id FROM price_list WHERE kind='BASE'").fetchone()
    list_id = row["id"] if row else new_uuid()
    if row is None:
        conn.execute("INSERT INTO price_list (id, code, name, kind, status, discount_pct) "
                     "VALUES (?, 'BASE', 'Base', 'BASE', 'ACTIVE', '0')", (list_id,))
    conn.execute("INSERT INTO product_price (id, price_list_id, product_id, sale_price, "
                 "branch_id) VALUES (?,?,?,?,'')", (new_uuid(), list_id, pid, "120"))
    conn.commit()
    return pid


def _add(conn, storage, pid, uri, auth=_MANAGE):
    return AddProductImageUseCase(conn, auth, storage).execute(
        AddProductImageCommand(operation_id=new_uuid(), product_id=pid, uri=uri,
                               user_id="u1"))


def _remove_bg(conn, storage, image_id, remover=None):
    return RemoveImageBackgroundUseCase(
        conn, _MANAGE, storage, remover or EdgeConnectedBackgroundRemover()).execute(
        RemoveImageBackgroundCommand(operation_id=new_uuid(), image_id=image_id,
                                     user_id="u1"))


# ── agregar: el archivo se copia ────────────────────────────────────────────
def test_add_copies_the_file_into_the_app_folder(conn, storage, photo):
    pid = _product(conn)
    res = _add(conn, storage, pid, photo)
    assert res.success
    image = ProductImageQueryService(conn).primary_image(pid)
    stored = Path(image["uri"])
    assert stored.parent == storage.directory and stored.is_file()
    assert stored != Path(photo)
    os.remove(photo)  # el original del usuario puede desaparecer
    assert stored.is_file()


def test_add_rejects_a_file_that_is_not_an_image(conn, storage, tmp_path):
    pid = _product(conn)
    bogus = tmp_path / "factura.png"
    bogus.write_bytes(b"%PDF-1.4 no soy imagen")
    res = _add(conn, storage, pid, str(bogus))
    assert not res.success and "no es una imagen" in res.message
    assert ProductImageQueryService(conn).list_images(pid) == []


# ── quitar fondo → POS ──────────────────────────────────────────────────────
def test_removed_background_reaches_the_pos_card(conn, storage, photo, qapp):
    from frontend.desktop.modules.sales_pos.components.product_grid import ProductGrid

    pid = _product(conn)
    image_id = _add(conn, storage, pid, photo).image_id
    res = _remove_bg(conn, storage, image_id)
    assert res.success, res.message

    listed = ProductImageQueryService(conn).list_images(pid)[0]
    assert listed["background_removed"] is True
    assert Path(listed["source_uri"]).is_file()          # el original se conserva
    with Image.open(listed["uri"]) as processed:
        assert processed.mode == "RGBA"
        assert processed.getpixel((0, 0))[3] == 0         # esquina transparente

    entry = SalesCatalogQueryService(conn).search(branch_id=BRANCH)[0]
    assert entry.image_reference == listed["uri"]

    grid = ProductGrid()
    grid.set_products([entry])
    from frontend.desktop.components.image_thumbnail import ImageThumbnail
    thumb = grid._cards[0].findChild(ImageThumbnail, "posProductImage")
    assert thumb is not None and thumb.has_image()
    assert thumb.accessibleName() == "Imagen de Pechuga de pollo"


def test_pos_card_without_image_shows_initials_and_keeps_height(conn, storage, photo, qapp):
    from frontend.desktop.components.image_thumbnail import ImageThumbnail
    from frontend.desktop.modules.sales_pos.components.product_grid import ProductGrid

    with_image = _product(conn, "Pechuga de pollo")
    _add(conn, storage, with_image, photo)
    _product(conn, "Costilla de res")
    entries = SalesCatalogQueryService(conn).search(branch_id=BRANCH)
    grid = ProductGrid()
    grid.set_products(entries)
    thumbs = {c.findChild(ImageThumbnail, "posProductImage").accessibleName(): c.findChild(
        ImageThumbnail, "posProductImage") for c in grid._cards}
    empty = thumbs["Imagen de Costilla de res"]
    assert not empty.has_image() and empty.text() == "CD"
    assert empty.property("empty") == "true"
    assert len({t.height() for t in thumbs.values()}) == 1


def test_missing_file_on_this_machine_falls_back_to_initials(conn, qapp):
    from frontend.desktop.components.image_thumbnail import ImageThumbnail
    thumb = ImageThumbnail(width=100, height=80)
    assert thumb.set_image("C:/no/existe/foto.png", placeholder="Arrachera") is False
    assert thumb.text() == "A"


# ── restaurar / doble proceso / fallo ───────────────────────────────────────
def test_restore_goes_back_to_the_original_and_discards_the_processed_file(
        conn, storage, photo):
    pid = _product(conn)
    image_id = _add(conn, storage, pid, photo).image_id
    original = ProductImageQueryService(conn).primary_image(pid)["uri"]
    _remove_bg(conn, storage, image_id)
    processed = ProductImageQueryService(conn).primary_image(pid)["uri"]

    res = RestoreImageBackgroundUseCase(conn, _MANAGE, storage).execute(
        RestoreImageBackgroundCommand(operation_id=new_uuid(), image_id=image_id,
                                      user_id="u1"))
    assert res.success
    listed = ProductImageQueryService(conn).list_images(pid)[0]
    assert listed["uri"] == original and listed["background_removed"] is False
    assert listed["source_uri"] is None
    assert not Path(processed).exists()


def test_background_cannot_be_removed_twice(conn, storage, photo):
    pid = _product(conn)
    image_id = _add(conn, storage, pid, photo).image_id
    assert _remove_bg(conn, storage, image_id).success
    again = _remove_bg(conn, storage, image_id)
    assert not again.success and "ya no tiene fondo" in again.message


def test_restore_without_removal_is_rejected(conn, storage, photo):
    pid = _product(conn)
    image_id = _add(conn, storage, pid, photo).image_id
    res = RestoreImageBackgroundUseCase(conn, _MANAGE, storage).execute(
        RestoreImageBackgroundCommand(operation_id=new_uuid(), image_id=image_id,
                                      user_id="u1"))
    assert not res.success


class _FailingRemover:
    def remove_background(self, source_path, target_path):
        Path(target_path).write_bytes(b"a medias")
        raise ProductImageProcessingError("No se detectó un fondo uniforme")


def test_failed_removal_leaves_the_image_untouched_and_no_orphan_file(
        conn, storage, photo):
    pid = _product(conn)
    image_id = _add(conn, storage, pid, photo).image_id
    before = sorted(p.name for p in storage.directory.iterdir())
    res = _remove_bg(conn, storage, image_id, remover=_FailingRemover())
    assert not res.success and "fondo uniforme" in res.message
    assert ProductImageQueryService(conn).list_images(pid)[0]["background_removed"] is False
    assert sorted(p.name for p in storage.directory.iterdir()) == before


def test_original_missing_on_this_machine_is_explained(conn, storage):
    pid = _product(conn)
    # Imagen heredada: ruta de otro equipo, nunca copiada.
    AddProductImageUseCase(conn, _MANAGE).execute(AddProductImageCommand(
        operation_id=new_uuid(), product_id=pid, uri="D:/otra_pc/foto.jpg", user_id="u1"))
    image_id = ProductImageQueryService(conn).primary_image(pid)["id"]
    res = _remove_bg(conn, storage, image_id)
    assert not res.success and "no está en este equipo" in res.message


# ── eliminar limpia archivos administrados ─────────────────────────────────
def test_remove_image_deletes_both_managed_files(conn, storage, photo):
    pid = _product(conn)
    image_id = _add(conn, storage, pid, photo).image_id
    _remove_bg(conn, storage, image_id)
    listed = ProductImageQueryService(conn).list_images(pid)[0]
    res = RemoveProductImageUseCase(conn, _MANAGE, storage).execute(
        RemoveProductImageCommand(operation_id=new_uuid(), image_id=image_id,
                                  user_id="u1"))
    assert res.success
    assert not Path(listed["uri"]).exists() and not Path(listed["source_uri"]).exists()
    assert Path(photo).exists()  # el archivo del usuario nunca se toca


# ── auditoría, outbox y permisos ───────────────────────────────────────────
def test_every_image_mutation_is_audited_and_published(conn, storage, photo):
    pid = _product(conn)
    image_id = _add(conn, storage, pid, photo).image_id
    _remove_bg(conn, storage, image_id)
    RestoreImageBackgroundUseCase(conn, _MANAGE, storage).execute(
        RestoreImageBackgroundCommand(operation_id=new_uuid(), image_id=image_id,
                                      user_id="u1"))
    actions = [r["action"] for r in conn.execute(
        "SELECT action FROM product_audit_log WHERE entity_id=? ORDER BY occurred_at, rowid",
        (pid,))]
    assert actions == ["PRODUCT_IMAGE_ADDED", "PRODUCT_IMAGE_BACKGROUND_REMOVED",
                       "PRODUCT_IMAGE_BACKGROUND_RESTORED"]
    events = {r["event_name"] for r in conn.execute("SELECT event_name FROM product_outbox")}
    assert {"PRODUCT_IMAGE_BACKGROUND_REMOVED",
            "PRODUCT_IMAGE_BACKGROUND_RESTORED"} <= events


def test_removing_the_background_requires_the_images_permission(conn, storage, photo):
    pid = _product(conn)
    image_id = _add(conn, storage, pid, photo).image_id
    denied = ProductsAuthorizationPolicy(_Checker(set()))
    with pytest.raises(ProductPermissionDeniedError):
        RemoveImageBackgroundUseCase(
            conn, denied, storage, EdgeConnectedBackgroundRemover()).execute(
            RemoveImageBackgroundCommand(operation_id=new_uuid(), image_id=image_id,
                                         user_id="u2"))


# ── migración 323 sobre la tabla anterior ──────────────────────────────────
def test_migration_323_adds_the_columns_to_an_existing_table():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE product_images (
        id TEXT NOT NULL PRIMARY KEY, product_id TEXT NOT NULL, uri TEXT NOT NULL,
        alt_text TEXT, is_primary INTEGER NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL
        DEFAULT 0, created_by TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')))""")
    c.execute("INSERT INTO product_images (id, product_id, uri, is_primary) "
              "VALUES ('i1','p1','/img/a.png',1)")
    migration = importlib.import_module(
        "migrations.standalone.323_product_image_background_removal")
    migration.run(c)
    migration.run(c)  # idempotente
    row = ProductImageQueryService(c).list_images("p1")[0]
    assert row["background_removed"] is False and row["source_uri"] is None


# ── galería: botones quitar fondo / restaurar ─────────────────────────────
def test_gallery_dialog_removes_and_restores_the_background(conn, storage, photo, qapp):
    from backend.application.products.queries.catalog_read_service import (
        ProductCatalogReadService,
    )
    from backend.application.products.use_cases.product_image_use_cases import (
        SetPrimaryImageUseCase,
    )
    from frontend.desktop.modules.products.dialogs.image_gallery_dialog import (
        ImageGalleryDialog,
    )
    from frontend.desktop.modules.products.presenter import ProductsPresenter

    class _Session:
        user_id = "u1"

    presenter = ProductsPresenter(
        read_service_factory=lambda: ProductCatalogReadService(conn),
        images_read_factory=lambda: ProductImageQueryService(conn),
        images_write_factory=lambda: {
            "add": AddProductImageUseCase(conn, _MANAGE, storage),
            "set_primary": SetPrimaryImageUseCase(conn, _MANAGE),
            "remove": RemoveProductImageUseCase(conn, _MANAGE, storage),
            "remove_background": RemoveImageBackgroundUseCase(
                conn, _MANAGE, storage, EdgeConnectedBackgroundRemover()),
            "restore_background": RestoreImageBackgroundUseCase(conn, _MANAGE, storage),
        },
        session_context=_Session())
    pid = _product(conn)
    assert presenter.add_image(product_id=pid, uri=photo)[0]

    dlg = ImageGalleryDialog(presenter, product_id=pid, product_name="Pechuga")
    assert dlg.table.rowCount() == 1 and dlg.preview.has_image()
    assert dlg.btn_remove_bg.isEnabled() and not dlg.btn_restore_bg.isEnabled()

    dlg.btn_remove_bg.click()
    assert dlg.table.item(0, 2).text() == "Sin fondo"
    assert dlg.btn_restore_bg.isEnabled() and not dlg.btn_remove_bg.isEnabled()
    assert dlg.preview_caption.text() == "Sin fondo"

    dlg.btn_restore_bg.click()
    assert dlg.table.item(0, 2).text() == "Original"
    assert dlg._error.text() == ""
