"""LabelVariableSet — SET-14 "Variables": a validated, named collection
of `LabelVariable` declarations a label template expects. Deliberately
not persisted on its own — no new table — the same non-persistence call
SET-12 made for `SectionLayout`: for this cut, a label template's
variable schema is a validation aid a caller builds alongside the
template's `content`, not yet queried independently by any admin UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from backend.domain.document_output.enums import LabelVariableType
from backend.domain.document_output.exceptions import DocumentInvalidValueError, LabelVariableMissingError
from backend.domain.document_output.value_objects.label_variable import LabelVariable

_EXPECTED_PYTHON_TYPES = {
    LabelVariableType.STRING: str,
    LabelVariableType.DECIMAL: Decimal,
    LabelVariableType.INTEGER: int,
    LabelVariableType.DATE: date,
}


@dataclass(frozen=True, slots=True)
class LabelVariableSet:
    variables: tuple[LabelVariable, ...]

    @classmethod
    def create(cls, variables: tuple[LabelVariable, ...] | list[LabelVariable]) -> "LabelVariableSet":
        variables = tuple(variables)
        if not variables:
            raise DocumentInvalidValueError("LabelVariableSet requiere al menos una variable")
        names = [variable.name for variable in variables]
        if len(names) != len(set(names)):
            raise DocumentInvalidValueError(f"Nombres de variable duplicados: {names}")
        return cls(variables=variables)

    def assert_satisfied(self, provided: dict) -> None:
        """Every required variable must be present in ``provided`` with
        a value of its declared type (bool never satisfies INTEGER —
        same discipline as everywhere else in this bounded context that
        an int-looking bool is rejected, not silently coerced)."""
        for variable in self.variables:
            if variable.name not in provided:
                if variable.required:
                    raise LabelVariableMissingError(
                        f"Falta la variable requerida {variable.name!r}"
                    )
                continue
            value = provided[variable.name]
            expected_type = _EXPECTED_PYTHON_TYPES[variable.var_type]
            if isinstance(value, bool) or not isinstance(value, expected_type):
                raise LabelVariableMissingError(
                    f"La variable {variable.name!r} debe ser {variable.var_type.value}, "
                    f"recibido {value!r}"
                )
