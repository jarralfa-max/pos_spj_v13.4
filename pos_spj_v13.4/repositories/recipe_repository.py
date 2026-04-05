# repositories/recipe_repository.py — SHIM
# La fuente canónica es repositories/recetas.py (RecetaRepository)
# Este shim mantiene compatibilidad con AppContainer y SalesService.
from repositories.recetas import RecetaRepository as RecipeRepository  # noqa: F401

__all__ = ['RecipeRepository']
