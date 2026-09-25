"""Humo: despiece de una canal bovina de punta a punta por la ruta canónica."""
from decimal import Decimal

from backend.domain.meat_processing.enums import ProcessType
from tests.integration.meat_processing._generic_plant import Planta, build_db


def test_bovine_carcass_disassembly_end_to_end():
    conn = build_db()
    p = Planta(conn)
    bovino = p.especie("Bovino")
    canal = p.producto("Canal bovina", lote=True, especie=bovino)
    lomo = p.producto("Lomo", lote=True, calidad=True, especie=bovino)
    falda = p.producto("Falda", lote=True, especie=bovino)
    hueso = p.producto("Hueso", especie=bovino)
    p.despiece(canal, [(lomo, "MAIN_PRODUCT", "0.30"), (falda, "CO_PRODUCT", "0.50"),
                       (hueso, "WASTE", "0.20")], especie=bovino)
    p.costo(canal, "100")
    p.precio(lomo, "300"); p.precio(falda, "120"); p.precio(hueso, "5")
    p.existencia(canal, "150", lote="CANAL-01", vence="2030-01-01")

    oid = p.lista(ProcessType.DISASSEMBLY, canal, "100")
    assert p.reservado(canal) == Decimal("100")
    r = p.ejecutar(oid, {lomo: "30", falda: "50", hueso: "20"})
    assert r.success, (r.message, r.data)
    assert p.saldo(canal) == Decimal("50")
    assert p.saldo(lomo, "QUARANTINED") == Decimal("30")
    assert p.saldo(falda) == Decimal("50")
