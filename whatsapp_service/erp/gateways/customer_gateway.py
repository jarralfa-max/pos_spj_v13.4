from __future__ import annotations


class CustomerGateway:
    def __init__(self, bridge):
        self._bridge = bridge

    def find_by_phone(self, phone: str):
        return self._bridge._find_cliente_by_phone_impl(phone)

    def create_minimal(self, nombre: str, telefono: str):
        return self._bridge._create_cliente_minimo_impl(nombre, telefono)
