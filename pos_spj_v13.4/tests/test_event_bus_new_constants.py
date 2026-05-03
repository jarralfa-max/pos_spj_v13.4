# tests/test_event_bus_new_constants.py — SPJ POS v13.5
"""
Verifica que las nuevas constantes y aliases del EventBus v13.5
existan y tengan los valores correctos.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


class TestEventBusConstantsV135:

    def test_nomina_pagada_constant_exists(self):
        from core.events.event_bus import NOMINA_PAGADA
        assert NOMINA_PAGADA == "NOMINA_PAGADA"

    def test_cliente_registrado_is_alias_for_cliente_creado(self):
        from core.events.event_bus import CLIENTE_REGISTRADO, CLIENTE_CREADO
        assert CLIENTE_REGISTRADO == CLIENTE_CREADO

    def test_compra_procesada_is_alias_for_compra_registrada(self):
        from core.events.event_bus import COMPRA_PROCESADA, COMPRA_REGISTRADA
        assert COMPRA_PROCESADA == COMPRA_REGISTRADA

    def test_existing_payroll_generated_unchanged(self):
        from core.events.event_bus import PAYROLL_GENERATED
        assert PAYROLL_GENERATED == "PAYROLL_GENERATED"

    def test_existing_compra_registrada_unchanged(self):
        from core.events.event_bus import COMPRA_REGISTRADA
        assert COMPRA_REGISTRADA == "COMPRA_REGISTRADA"

    def test_existing_cliente_creado_unchanged(self):
        from core.events.event_bus import CLIENTE_CREADO
        assert CLIENTE_CREADO == "CLIENTE_CREADO"

    def test_all_new_constants_importable(self):
        from core.events.event_bus import (
            NOMINA_PAGADA,
            CLIENTE_REGISTRADO,
            COMPRA_PROCESADA,
        )
        assert all([NOMINA_PAGADA, CLIENTE_REGISTRADO, COMPRA_PROCESADA])
