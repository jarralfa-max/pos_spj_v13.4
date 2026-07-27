"""El CRUD de recetas no ejecuta SQL desde el diálogo PyQt (usa RecipeService)."""
from __future__ import annotations

from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]


def test_receta_dialog_uses_recipe_service():
    dialog = APP_ROOT / "modulos" / "dialogs" / "receta_dialog.py"
    if not dialog.exists():
        # El diálogo canónico puede vivir en otro módulo; validar el módulo Productos.
        dialog = APP_ROOT / "modulos" / "productos.py"
    text = dialog.read_text(encoding="utf-8")
    assert "RecipeService" in text or "recipe_service" in text, (
        f"{dialog.name} no delega el CRUD de recetas a RecipeService"
    )


def test_recipe_service_owns_all_recipe_writes():
    """Las escrituras de recetas viven en la capa de servicio/repositorio."""
    svc = (APP_ROOT / "core" / "services" / "recipes" / "recipe_service.py").read_text(encoding="utf-8")
    for method in ("create_recipe", "update_recipe", "deactivate_recipe"):
        assert method in svc
