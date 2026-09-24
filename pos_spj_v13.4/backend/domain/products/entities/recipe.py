"""Recipe — the master record a set of versions belongs to (§21).

A recipe is bound to the product it produces/explodes and carries its type
(sales explosion, production BOM, disassembly, formula…). The concrete component
and output structure lives in its versions (§22).

La reconstrucción inversa (armar el producto con sus partes) NO se decide
aquí: su fuente es el esquema de corte (`CuttingScheme.reverse_reconstruction_
allowed`), el mismo despiece que ejecuta Cárnico — decisión del usuario, Fase
7, 2026-09-19. Antes esta entidad llevaba esa marca y el despiece había que
definirlo dos veces.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.products.exceptions import InvalidRecipeError
from backend.domain.products.recipe_enums import RecipeType
from backend.shared.ids import new_uuid


@dataclass
class Recipe:
    product_id: str
    recipe_type: RecipeType
    name: str
    id: str = field(default_factory=new_uuid)
    active: bool = True

    def __post_init__(self) -> None:
        if not self.product_id:
            raise InvalidRecipeError("La receta requiere producto")
        if not (self.name or "").strip():
            raise InvalidRecipeError("La receta requiere un nombre")
        if not isinstance(self.recipe_type, RecipeType):
            try:
                self.recipe_type = RecipeType(str(self.recipe_type))
            except ValueError as exc:
                raise InvalidRecipeError(
                    f"Tipo de receta inválido: {self.recipe_type!r}") from exc
