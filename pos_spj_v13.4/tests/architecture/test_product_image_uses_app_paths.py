from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCTS_UI = ROOT / "modulos/productos.py"
APP_PATHS = ROOT / "backend/shared/app_paths.py"


def test_product_images_are_resolved_with_app_paths() -> None:
    ui = PRODUCTS_UI.read_text(encoding="utf-8")
    paths = APP_PATHS.read_text(encoding="utf-8")
    assert "ProductImageService" in ui
    assert "product_images_dir" in paths
    assert 'os.makedirs("imagenes_productos"' not in ui
    assert 'os.path.join("imagenes_productos"' not in ui
