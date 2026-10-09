"""Imágenes y videos en la pantalla del cliente (migración 313).

Antes el contenido IMAGE/VIDEO sólo admitía texto escrito a mano y la pantalla
mostraba un aviso en su lugar: no había dónde guardar el archivo.
"""

from __future__ import annotations

import importlib
import os
import struct
import zlib

import pytest

from backend.application.customer_display.queries.advertising_query_service import (
    AdvertisingQueryService,
)
from backend.application.use_cases.configuracion.customer_display_advertising_use_cases import (
    CreateContentUseCase,
    ImportDisplayMediaUseCase,
)
from backend.domain.customer_display.exceptions import CustomerDisplayInvalidValueError
from backend.infrastructure.customer_display.media_storage import DisplayMediaStorage
from tests.integration._born_clean_db import make_db

def _png(width: int = 4, height: int = 4) -> bytes:
    """PNG válido generado aquí (rojo), con sus CRC correctos."""
    def chunk(tipo: bytes, datos: bytes) -> bytes:
        return (struct.pack(">I", len(datos)) + tipo + datos
                + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF))
    filas = b"".join(bytes([0]) + bytes([255, 0, 0]) * width for _ in range(height))
    return (bytes([137]) + b"PNG" + bytes([13, 10, 26, 10])
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(filas)) + chunk(b"IEND", b""))


_PNG = _png()


@pytest.fixture
def conn():
    c = make_db()
    importlib.import_module("migrations.standalone.313_customer_display_media").run(c)
    yield c
    c.close()


@pytest.fixture
def storage(tmp_path):
    return DisplayMediaStorage(tmp_path / "media")


def _file(tmp_path, name, data=_PNG):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def test_an_image_is_copied_and_registered_once(conn, storage, tmp_path):
    use_case = ImportDisplayMediaUseCase(conn, storage)
    first = use_case.execute(source_path=_file(tmp_path, "promo.png"), media_type="IMAGE")
    again = use_case.execute(source_path=_file(tmp_path, "copia.png"), media_type="IMAGE")
    assert first.id == again.id  # mismo contenido, un solo registro
    assert storage.path_for(first.stored_name).read_bytes() == _PNG
    assert first.original_name == "promo.png" and first.stored_name == f"{first.id}.png"


@pytest.mark.parametrize("name, media_type", [("promo.exe", "IMAGE"), ("promo.png", "VIDEO")])
def test_wrong_formats_are_refused(conn, storage, tmp_path, name, media_type):
    with pytest.raises(CustomerDisplayInvalidValueError, match="no admitido"):
        ImportDisplayMediaUseCase(conn, storage).execute(
            source_path=_file(tmp_path, name), media_type=media_type)


def test_a_missing_file_is_refused(conn, storage, tmp_path):
    with pytest.raises(CustomerDisplayInvalidValueError, match="no existe"):
        ImportDisplayMediaUseCase(conn, storage).execute(
            source_path=str(tmp_path / "nada.png"), media_type="IMAGE")


def test_image_content_needs_an_attached_file_not_a_typed_path(conn, storage, tmp_path):
    with pytest.raises(CustomerDisplayInvalidValueError, match="Adjunta"):
        CreateContentUseCase(conn).execute(title="Promo", content_type="IMAGE",
                                           body=r"C:\Users\alguien\promo.png")
    media = ImportDisplayMediaUseCase(conn, storage).execute(
        source_path=_file(tmp_path, "promo.png"), media_type="IMAGE")
    with pytest.raises(CustomerDisplayInvalidValueError, match="imagen"):
        CreateContentUseCase(conn).execute(title="Promo", content_type="VIDEO", body=media.id)
    content = CreateContentUseCase(conn).execute(title="Promo", content_type="IMAGE", body=media.id)
    assert content.body == media.id


def test_the_display_receives_the_managed_file_path(conn, storage, tmp_path):
    media = ImportDisplayMediaUseCase(conn, storage).execute(
        source_path=_file(tmp_path, "promo.png"), media_type="IMAGE")
    content = CreateContentUseCase(conn).execute(title="Promo", content_type="IMAGE", body=media.id)
    query = AdvertisingQueryService(conn, storage)
    assert query._media_path(content) == str(storage.path_for(media.stored_name))
    storage.path_for(media.stored_name).unlink()
    assert query._media_path(content) is None  # el archivo desapareció: la pantalla lo dice


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QtWidgets = pytest.importorskip("PyQt5.QtWidgets")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_the_customer_screen_paints_the_image(app, tmp_path):
    from frontend.desktop.modules.sales_pos.customer_display_window import CustomerDisplayWindow

    window = CustomerDisplayWindow()
    window.render_idle_ad("IMAGE", "Promo", "", _file(tmp_path, "promo.png"))
    assert window._ad_label.pixmap() is not None and not window._ad_label.pixmap().isNull()
    window.render_idle_ad("IMAGE", "Promo", "", None)
    assert "ya no está disponible" in window._ad_label.text()
    window.close()


def test_the_dialog_attaches_a_file_for_images(app):
    from frontend.desktop.modules.configuracion.dialogs.customer_display_advertising_dialogs import (
        ContentCreateDialog,
    )

    dlg = ContentCreateDialog()
    dlg.title_field.setText("Promo")
    dlg.content_type.set_current_id("IMAGE")
    assert dlg.media_file.isVisibleTo(dlg) and not dlg.body.isVisibleTo(dlg)
    dlg.media_file.set_path(r"C:\fotos\promo.png")
    assert dlg.values()["media_path"] == r"C:\fotos\promo.png"
    dlg.content_type.set_current_id("TEXT")
    assert dlg.body.isVisibleTo(dlg) and "media_path" not in dlg.values()
