"""§1/§25 — el MISMO código ejecuta cualquier especie. Lo que cambia entre una
canal bovina, un lomo porcino y un pescado entero son DATOS (esquema de corte,
banderas de lote/calidad, tolerancias configuradas), nunca una rama del código.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.meat_processing.enums import ProcessType
from tests.integration.meat_processing._generic_plant import Planta, build_db

ESPECIES = [("Bovino", "Canal bovina", "Pulpa"),
            ("Porcino", "Lomo de cerdo entero", "Chuleta"),
            ("Pescado", "Huachinango entero", "Filete"),
            ("Ovino", "Canal de borrego", "Pierna de borrego")]


class _Orden:
    def __init__(self, nombre_especie, nombre_entrada, nombre_salida) -> None:
        self.conn = build_db()
        p = self.p = Planta(self.conn)
        self.especie = p.especie(nombre_especie)
        self.entrada = p.producto(nombre_entrada, lote=True, especie=self.especie)
        self.salida = p.producto(nombre_salida, lote=True, especie=self.especie)
        self.merma = p.producto("Merma", especie=self.especie)
        p.despiece(self.entrada, [(self.salida, "MAIN_PRODUCT", "0.65"),
                                  (self.merma, "WASTE", "0.35")], especie=self.especie)
        p.costo(self.entrada, "100")
        p.existencia(self.entrada, "20", lote="L-1", vence="2031-01-01")
        self.oid = p.lista(ProcessType.DISASSEMBLY, self.entrada, "10")

    def ejecutar(self, real: str):
        return self.p.ejecutar(self.oid, {self.salida: real,
                                          self.merma: str(Decimal("10") - Decimal(real))})


@pytest.mark.parametrize("especie, entrada, salida", ESPECIES)
def test_every_species_runs_through_the_same_pipeline_with_the_same_result(especie, entrada,
                                                                            salida):
    orden = _Orden(especie, entrada, salida)
    r = orden.ejecutar("6.5")
    assert r.success, r.message
    fila = [f for f in r.data["results"] if f["output_type"] == "MAIN_PRODUCT"][0]
    assert tuple(Decimal(str(fila[k])) for k in ("expected_weight", "actual_weight",
                                                  "yield_pct")) == (
        Decimal("6.500"), Decimal("6.500"), Decimal("65.00"))
    assert r.data["out_of_tolerance"] is False


def test_a_species_tolerance_is_configuration_not_code():
    """6 kg de 6.5 esperados (−7.7 %) queda fuera de la tolerancia global (5 %)
    y dentro de la de la especie cuando alguien la configura en 10 %."""
    orden = _Orden("Pescado", "Huachinango entero", "Filete")
    r = orden.ejecutar("6")
    assert not r.success and r.error_code == "YIELD_AUTHORIZATION_REQUIRED"

    orden.conn.execute("INSERT OR REPLACE INTO configuraciones (clave, valor) VALUES (?,?)",
                       (f"meat_processing.yield.tolerance_pct@SPECIES:{orden.especie}", "10"))
    orden.conn.commit()
    r = orden.ejecutar("6")
    assert r.success, r.message
    assert r.data["out_of_tolerance"] is False
