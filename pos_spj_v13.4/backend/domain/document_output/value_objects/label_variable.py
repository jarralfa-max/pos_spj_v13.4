"""LabelVariable — SET-14 "Variables": one named, typed placeholder a
label template declares (e.g. "product_name" is a required STRING,
"net_weight" is a required DECIMAL). Lets a caller validate the data it
supplies before rendering — see `label_variable_set.py::LabelVariableSet.
assert_satisfied()` — rather than only discovering a missing placeholder
when the printed label comes out wrong.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.document_output.enums import LabelVariableType
from backend.domain.document_output.exceptions import DocumentInvalidValueError


@dataclass(frozen=True, slots=True)
class LabelVariable:
    name: str
    var_type: LabelVariableType
    required: bool = True

    @classmethod
    def create(
        cls, *, name: str, var_type: LabelVariableType, required: bool = True,
    ) -> "LabelVariable":
        if not name.strip():
            raise DocumentInvalidValueError("name es obligatorio")
        return cls(name=name.strip(), var_type=var_type, required=bool(required))
