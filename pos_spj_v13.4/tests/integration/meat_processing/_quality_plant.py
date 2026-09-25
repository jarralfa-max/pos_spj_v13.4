"""Una orden ejecutada con una salida sujeta a inspección (datos de Productos:
`quality_controlled`) y otra que no. Filete de pescado: el filete se inspecciona,
la cabeza no."""
from __future__ import annotations

from backend.application.quality.wiring import dispatch_quality_outbox
from backend.domain.meat_processing.enums import ProcessType
from tests.integration.meat_processing._generic_plant import (
    Planta,
    build_db,
    bus_with_real_wiring,
)


class PlantaConCalidad:
    def __init__(self) -> None:
        self.conn = build_db()
        p = self.p = Planta(self.conn)
        marino = p.especie("Pescado")
        self.entero = p.producto("Robalo entero", lote=True, especie=marino)
        self.filete = p.producto("Filete de robalo", lote=True, calidad=True, especie=marino)
        self.cabeza = p.producto("Cabeza de robalo", lote=True, especie=marino)
        self.espinas = p.producto("Espinas", especie=marino)
        p.despiece(self.entero, [(self.filete, "MAIN_PRODUCT", "0.40"),
                                 (self.cabeza, "BY_PRODUCT", "0.20"),
                                 (self.espinas, "WASTE", "0.40")], especie=marino)
        p.costo(self.entero, "110")
        p.precio(self.filete, "380"); p.precio(self.cabeza, "40")
        self.lote_entrada = p.existencia(self.entero, "50", lote="ROB-3", vence="2031-05-01")
        self.bus = bus_with_real_wiring(self.conn)
        self.oid = p.lista(ProcessType.DISASSEMBLY, self.entero, "20")
        r = p.ejecutar(self.oid, {self.filete: "8", self.cabeza: "4", self.espinas: "8"})
        assert r.success, r.message

    def despachar(self, conn):
        return dispatch_quality_outbox(conn, self.bus)

    def salida(self, producto):
        return self.p.salida(self.oid, producto)

    def lote_de(self, producto):
        return self.conn.execute("SELECT quality_status FROM inventory_lots WHERE id=?",
                                 (self.salida(producto).lot_id,)).fetchone()[0]

    def estados_en_inventario(self, producto) -> dict[str, str]:
        return {r[0]: str(r[1]) for r in self.conn.execute(
            "SELECT inventory_status, quantity FROM inventory_balances WHERE product_id=?"
            " AND CAST(quantity AS REAL) > 0", (producto,)).fetchall()}
