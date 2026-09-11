"""Planeación de Compras / Forecast: prohibido SQL directo en PyQt.

Las lecturas van por el servicio de consulta de planeación; el pronóstico va
por ForecastService con identidades UUID string.

ESTA GUARDIA MIRABA A UN ARCHIVO BORRADO
----------------------------------------
Vigilaba `modulos/planeacion_compras.py`. Ese archivo ya no existe, así que el
escaneo no producía ni una línea y la primera prueba pasaba en verde sin
comprobar nada, mientras la segunda moría con un `FileNotFoundError` que no
decía qué pasaba realmente.

Lo que pasa realmente es un hueco: la pantalla de Planeación de Compras no se
ha reconstruido. `PurchasePlanningQueryService` sí existe, en
`backend/application/queries/`, y no tiene NI UN consumidor — se exporta desde
`__init__.py` y ahí se acaba. La "PLANEACIÓN" que aparece en
`purchasing/navigation.py` es la etiqueta de sección de Solicitudes, no una
pantalla de planeación.
"""

from __future__ import annotations

import re

import pytest

from .architecture_guardrails import APP_ROOT, SQL_RE, collect_regex_violations

#: `\.execute\(` a secas marca TAMBIEN `use_case.execute(...)`, que es una
#: llamada a un caso de uso y no a la base. Cualquier presentador que invoque un
#: caso de uso —o sea, todos— quedaba senalado, y una guardia permanentemente
#: roja por un motivo falso se acaba ignorando. Se exige que el receptor sea una
#: conexion, una base o un cursor.
EXECUTE_RE = re.compile(
    r"\w*(?:conn|cnx|db|cursor)\w*\s*(?:\(\s*\))?\s*\.\s*"
    r"(?:execute|executemany|executescript|cursor)\s*\(",
    re.IGNORECASE,
)

#: La UI de Compras entera: es donde vivirá la planeación cuando se construya, y
#: mientras tanto la regla "sin SQL en PyQt" vale igual para el resto de sus
#: pantallas. Apuntar a un solo archivo fue lo que dejó la guardia vacía cuando
#: ese archivo desapareció.
PLANNING_UI = (APP_ROOT / "frontend" / "desktop" / "modules" / "purchasing",)


def test_no_forecast_sql_in_pyqt() -> None:
    violations = collect_regex_violations(pattern=SQL_RE, roots=PLANNING_UI)
    violations += collect_regex_violations(pattern=EXECUTE_RE, roots=PLANNING_UI)
    assert not violations, (
        "SQL directo en la UI de Compras:\n"
        + "\n".join(f"{v.relative_path}:{v.line_number}: {v.text}" for v in violations)
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "HUECO CONOCIDO: la pantalla de Planeación de Compras no se ha "
        "reconstruido. El servicio de consulta existe y nadie lo llama. Esta "
        "prueba es el trinquete del hueco: en cuanto alguien construya la "
        "pantalla empezará a pasar, pytest lo reportará como XPASS —que con "
        "strict=True es un fallo— y quien la construya tendrá que venir a "
        "quitar este marcador. Así el hueco no se cierra en silencio ni se "
        "queda abierto sin que nadie lo vea."
    ),
)
def test_planning_ui_uses_query_service() -> None:
    fuentes = [
        path.read_text(encoding="utf-8", errors="ignore")
        for root in PLANNING_UI
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    ]
    assert any(
        "PurchasePlanningQueryService" in texto or "PurchasePlanningReadService" in texto
        for texto in fuentes
    ), "ninguna pantalla de Compras consume el servicio de planeación"
