"""PROD-23 — códigos de catálogo automáticos y código de barras en el alta.

* Categorías, marcas, atributos, opciones, especies, regiones y cortes: si no se
  escribe código, sale del nombre (sin acentos, ``_``, único en su ámbito); el
  escrito a mano se respeta.
* «Nuevo producto» puede llevar su código de barras principal (escaneado,
  tecleado o EAN-13 interno generado), asignado en la MISMA transacción: si el
  código no sirve o ya es de otro producto, no se crea el producto.
"""

from __future__ import annotations

import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backend.application.products.authorization.policy import (  # noqa: E402
    ProductsAuthorizationPolicy,
)
from backend.application.products.catalog_codes import (  # noqa: E402
    CatalogCodeKind,
    CatalogCodeSuggestionQueryService,
)
from backend.application.products.commands.product_attribute_commands import (  # noqa: E402
    AddAttributeOptionCommand,
    CreateAttributeCommand,
)
from backend.application.products.commands.product_brand_commands import (  # noqa: E402
    CreateBrandCommand,
)
from backend.application.products.commands.product_category_commands import (  # noqa: E402
    CreateCategoryCommand,
)
from backend.application.products.commands.product_master_commands import (  # noqa: E402
    CreateProductMasterCommand,
)
from backend.application.products.commands.product_meat_classification_commands import (  # noqa: E402,E501
    CreateAnatomicalRegionCommand,
    CreateSpeciesCommand,
)
from backend.application.products.permissions import ProductPermissions  # noqa: E402
from backend.application.products.queries.internal_barcode import (  # noqa: E402
    preview_internal_barcode,
)
from backend.application.products.use_cases.product_attribute_use_cases import (  # noqa: E402
    AddAttributeOptionUseCase,
    CreateProductAttributeUseCase,
)
from backend.application.products.use_cases.product_brand_use_cases import (  # noqa: E402
    CreateProductBrandUseCase,
)
from backend.application.products.use_cases.product_category_use_cases import (  # noqa: E402
    CreateProductCategoryUseCase,
)
from backend.application.products.use_cases.product_master_use_cases import (  # noqa: E402
    CreateProductMasterUseCase,
)
from backend.application.products.use_cases.product_meat_classification_use_cases import (  # noqa: E402,E501
    CreateAnatomicalRegionUseCase,
    CreateSpeciesUseCase,
)
from backend.domain.products.exceptions import ProductPermissionDeniedError  # noqa: E402
from backend.domain.products.policies.catalog_code_policy import (  # noqa: E402
    code_from_name,
    unique_code,
)
from backend.domain.products.value_objects.barcode import (  # noqa: E402
    Barcode,
    internal_ean13,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema  # noqa: E402


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    c.execute("INSERT INTO units_of_measure (id, code, name, dimension) "
              "VALUES ('u-pza','PZA','Pieza','COUNT')")
    c.commit()
    yield c
    c.close()


# ── dominio ──────────────────────────────────────────────────────────────
def test_code_from_name_strips_accents_and_joins_words():
    assert code_from_name("Pechuga sin hueso") == "PECHUGA_SIN_HUESO"
    assert code_from_name("Lácteos & Huevo") == "LACTEOS_HUEVO"
    assert code_from_name("  ¿?  ") == "COD"
    long = code_from_name("Embutidos artesanales importados de temporada")
    assert len(long) <= 24 and long == "EMBUTIDOS_ARTESANALES"  # no parte palabras


def test_unique_code_appends_counter_within_length():
    taken = {"POLLO", "POLLO_2"}
    assert unique_code("POLLO", taken.__contains__) == "POLLO_3"
    base = "A" * 24
    assert unique_code(base, {base}.__contains__) == "A" * 22 + "_2"


# ── casos de uso de catálogo ─────────────────────────────────────────────
def test_blank_code_is_generated_unique_and_written_code_is_kept(conn):
    uc = CreateProductCategoryUseCase(conn)

    def create(op, code, name):
        return uc.execute(CreateCategoryCommand(operation_id=op, code=code, name=name,
                                                user_id="u1"))
    first = create("o1", "", "Pollo fresco")
    again = create("o2", "", "Pollo  fresco")
    manual = create("o3", "av", "Aves")
    codes = {r["id"]: r["code"] for r in conn.execute("SELECT id, code FROM product_categories")}
    assert codes[first.category_id] == "POLLO_FRESCO"
    assert codes[again.category_id] == "POLLO_FRESCO_2"
    assert codes[manual.category_id] == "AV"
    dup = create("o4", "AV", "Otra")
    assert not dup.success and "ya existe" in dup.message


def test_brand_attribute_and_options_generate_codes(conn):
    brand = CreateProductBrandUseCase(conn).execute(
        CreateBrandCommand(operation_id="b", code="", name="Granja Ávila", user_id="u1"))
    assert brand.success
    assert conn.execute("SELECT code FROM product_brands").fetchone()[0] == "GRANJA_AVILA"
    attrs = CreateProductAttributeUseCase(conn)
    color = attrs.execute(CreateAttributeCommand(operation_id="a1", code="", name="Color",
                                                 user_id="u1"))
    size = attrs.execute(CreateAttributeCommand(operation_id="a2", code="", name="Tamaño",
                                                user_id="u1"))
    options = AddAttributeOptionUseCase(conn)
    for attr in (color, size):  # la misma etiqueta en dos atributos: mismo código
        assert options.execute(AddAttributeOptionCommand(
            operation_id=f"o-{attr.entity_id}", attribute_id=attr.entity_id, code="",
            label="Grande", user_id="u1")).success
    second = options.execute(AddAttributeOptionCommand(
        operation_id="o-x", attribute_id=color.entity_id, code="", label="Grande",
        user_id="u1"))
    rows = conn.execute("SELECT attribute_id, code FROM product_attribute_options "
                        "ORDER BY rowid").fetchall()
    assert [r[1] for r in rows] == ["GRANDE", "GRANDE", "GRANDE_2"] and second.success


def test_species_and_region_codes_scoped_by_species(conn):
    sp = CreateSpeciesUseCase(conn).execute(
        CreateSpeciesCommand(operation_id="s", code="", name="Res", user_id="u1"))
    assert sp.success
    region = CreateAnatomicalRegionUseCase(conn).execute(CreateAnatomicalRegionCommand(
        operation_id="r", species_id=sp.entity_id, code="", name="Pierna trasera",
        user_id="u1"))
    assert region.success
    assert conn.execute("SELECT code FROM anatomical_regions").fetchone()[0] == \
        "PIERNA_TRASERA"
    # la vista previa ya ve el código tomado y ofrece el siguiente
    assert CatalogCodeSuggestionQueryService(conn).suggest(
        CatalogCodeKind.ANATOMICAL_REGION, "Pierna trasera",
        scope_id=sp.entity_id) == "PIERNA_TRASERA_2"


# ── código de barras en el alta ──────────────────────────────────────────
def _create(conn, *, barcode=None, barcode_type="EAN", auth=None, name="Refresco"):
    return CreateProductMasterUseCase(conn, auth).execute(CreateProductMasterCommand(
        operation_id=f"op-{name}", code="", name=name, product_type="FINISHED_GOOD",
        base_unit_id="u-pza", user_id="u1", auto_generate_code=True,
        initial_barcode=barcode, initial_barcode_type=barcode_type))


def test_product_is_created_with_its_primary_barcode(conn):
    result = _create(conn, barcode="7501055300075")
    assert result.success
    row = conn.execute("SELECT product_id, barcode_type, is_primary, active "
                       "FROM product_barcodes").fetchone()
    assert tuple(row) == (result.product_id, "EAN", 1, 1)


def test_invalid_or_taken_barcode_creates_nothing(conn):
    bad = _create(conn, barcode="7501055300076")  # dígito verificador mal
    assert not bad.success and "verificador" in bad.message
    assert _create(conn, barcode="7501055300075", name="Producto A").success
    taken = _create(conn, barcode="7501055300075", name="Producto B")
    assert not taken.success
    assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM product_barcodes").fetchone()[0] == 1


def test_barcode_in_create_requires_barcode_permission(conn):
    class _Checker:
        def has_permission(self, _user, code):
            return code != ProductPermissions.BARCODES_MANAGE
    auth = ProductsAuthorizationPolicy(_Checker())
    with pytest.raises(ProductPermissionDeniedError):
        _create(conn, barcode="7501055300075", auth=auth)
    assert _create(conn, auth=auth).success  # sin código de barras sí puede


def test_internal_barcode_is_valid_ean_and_never_repeats(conn):
    first = preview_internal_barcode(conn)
    assert first == internal_ean13(1) and first.startswith("04")
    Barcode(value=first, barcode_type="EAN")  # dígito verificador correcto
    assert preview_internal_barcode(conn) == first  # la vista previa no consume
    assert _create(conn, barcode=first, name="Chorizo").success
    second = preview_internal_barcode(conn)
    assert second == internal_ean13(2)
    # uno interno capturado a mano más adelante también se salta
    assert _create(conn, barcode=internal_ean13(7), name="Longaniza").success
    assert preview_internal_barcode(conn) == internal_ean13(8)


# ── diálogos ─────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def qapp():
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _presenter(conn):
    import importlib

    from frontend.desktop.modules.products.composition import (
        _Session as LiveSession,
        build_products_presenter,
    )
    codes = {f"PRODUCTOS.{a}" for a in importlib.import_module(
        "migrations.standalone.324_seed_products_granular_permissions")._TODAS}

    class _S:
        user_id, sucursal_id, is_active = "u-dueno", None, True

        def tiene_permiso(self, code):
            return code in codes
    live = _S()
    return build_products_presenter(conn, LiveSession(live), live_session=live)


def test_category_dialog_fills_code_from_name_and_respects_override(conn, qapp):
    from PyQt5.QtTest import QTest

    from frontend.desktop.modules.products.dialogs.category_form_dialog import (
        CategoryFormDialog,
    )
    presenter = _presenter(conn)
    dlg = CategoryFormDialog(presenter)
    dlg.name.setText("Carnes frías")
    assert dlg.code.text() == "CARNES_FRIAS" and not dlg._auto.is_manual
    QTest.keyClicks(dlg.code, "X")  # el usuario lo toca → se respeta
    assert dlg._auto.is_manual
    dlg.name.setText("Embutidos")
    assert dlg.code.text().endswith("X")
    dlg.code.clear()
    dlg._auto._on_code_edited("")  # borrarlo vuelve a automático
    assert dlg.code.text() == "EMBUTIDOS"
    dlg._on_save()
    assert conn.execute("SELECT code FROM product_categories").fetchone()[0] == "EMBUTIDOS"


def test_new_product_dialog_captures_and_generates_barcode(conn, qapp):
    from frontend.desktop.modules.products.dialogs.product_form_dialog import (
        ProductFormDialog,
    )
    presenter = _presenter(conn)
    dlg = ProductFormDialog(presenter)
    assert not dlg.barcode_box.isHidden() and not dlg.barcode_box.isChecked()
    dlg.name.setText("Agua natural")
    dlg.base_unit.set_current_id("u-pza")
    dlg.barcode_box.setChecked(True)
    dlg._on_save()  # marcado sin código → no guarda
    assert "código de barras" in dlg._error.text()
    dlg._generate_barcode()
    assert dlg.barcode_value.text() == internal_ean13(1)
    assert dlg.barcode_type.currentData() == "EAN"
    dlg._on_save()
    assert dlg.result() == dlg.Accepted, dlg._error.text()
    row = conn.execute("SELECT b.barcode_value, b.is_primary, p.name FROM product_barcodes b "
                       "JOIN products p ON p.id = b.product_id").fetchone()
    assert tuple(row) == (internal_ean13(1), 1, "Agua natural")


def test_edit_product_dialog_hides_barcode_box(conn, qapp):
    from frontend.desktop.modules.products.dialogs.product_form_dialog import (
        ProductFormDialog,
    )
    result = _create(conn)
    dlg = ProductFormDialog(_presenter(conn), product_id=result.product_id)
    assert dlg.barcode_box.isHidden()
    assert hasattr(dlg, "_btn_barcodes")
