"""P1 — flujo presenter/UI de la galería de imágenes."""

import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backend.application.products.queries.catalog_read_service import (  # noqa: E402
    ProductCatalogReadService,
)
from backend.application.products.queries.product_image_query_service import (  # noqa: E402
    ProductImageQueryService,
)
from backend.application.products.use_cases.product_image_use_cases import (  # noqa: E402
    AddProductImageUseCase,
    RemoveProductImageUseCase,
    SetPrimaryImageUseCase,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema  # noqa: E402
from frontend.desktop.modules.products.presenter import ProductsPresenter  # noqa: E402

_PID = "prod-1"


class _Session:
    user_id = "u1"


@pytest.fixture
def presenter():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_products_schema(conn)
    conn.commit()

    p = ProductsPresenter(
        read_service_factory=lambda: ProductCatalogReadService(conn),
        images_read_factory=lambda: ProductImageQueryService(conn),
        images_write_factory=lambda: {
            "add": AddProductImageUseCase(conn),
            "set_primary": SetPrimaryImageUseCase(conn),
            "remove": RemoveProductImageUseCase(conn),
        },
        session_context=_Session())
    p._conn = conn
    yield p
    conn.close()


def test_presenter_can_manage_images(presenter):
    assert presenter.can_manage_images is True


def test_add_and_list_images(presenter):
    ok, _msg = presenter.add_image(product_id=_PID, uri="/img/a.png")
    assert ok
    ok2, _m2 = presenter.add_image(product_id=_PID, uri="/img/b.png")
    assert ok2
    images = presenter.list_images(_PID)
    assert len(images) == 2 and images[0]["is_primary"]  # la primera es principal


def test_set_primary_and_remove(presenter):
    presenter.add_image(product_id=_PID, uri="/img/a.png")
    ok, _m = presenter.add_image(product_id=_PID, uri="/img/b.png")
    assert ok
    imgs = presenter.list_images(_PID)
    second = next(i for i in imgs if i["uri"] == "/img/b.png")
    presenter.set_primary_image(second["id"])
    assert presenter.list_images(_PID)[0]["uri"] == "/img/b.png"


def test_gallery_dialog_lists_and_adds(presenter):
    from PyQt5.QtWidgets import QApplication

    from frontend.desktop.modules.products.dialogs.image_gallery_dialog import (
        ImageGalleryDialog,
    )
    presenter.add_image(product_id=_PID, uri="/img/a.png")
    app = QApplication.instance() or QApplication([])
    dlg = ImageGalleryDialog(presenter, product_id=_PID, product_name="Prod")
    assert dlg.table.rowCount() == 1
