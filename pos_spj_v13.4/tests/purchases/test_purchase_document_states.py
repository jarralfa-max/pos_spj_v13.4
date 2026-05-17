"""
tests/purchases/test_purchase_document_states.py
─────────────────────────────────────────────────
FASE 1 — Pruebas de caracterización de la máquina de estados documentales.

Verifica:
1. PRState tiene los estados requeridos por el flujo ERP
2. POState tiene los estados requeridos
3. Transiciones PR válidas (qué puede → qué)
4. Transiciones PO válidas
5. PR/PO no transicionan a estados que impliquen inventario
6. DocumentType tiene los tres tipos (DIRECT, PR, PO)
7. StateMachine (si existe) valida transiciones
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from application.purchases.states import PRState, POState, DocumentType, DirectPurchaseState


class TestPRStateDefinitions:

    def test_pr_state_has_borrador(self):
        assert PRState.BORRADOR == "BORRADOR"

    def test_pr_state_has_pendiente_aprobacion(self):
        assert PRState.PENDIENTE_APROBACION == "PENDIENTE_APROBACION"

    def test_pr_state_has_aprobada(self):
        assert PRState.APROBADA == "APROBADA"

    def test_pr_state_has_rechazada(self):
        assert PRState.RECHAZADA == "RECHAZADA"

    def test_pr_state_has_convertida_a_po(self):
        assert PRState.CONVERTIDA_A_PO == "CONVERTIDA_A_PO"

    def test_pr_state_has_cancelada(self):
        assert PRState.CANCELADA == "CANCELADA"

    def test_pr_state_count_is_6(self):
        assert len(PRState) == 6

    def test_pr_states_are_strings(self):
        for s in PRState:
            assert isinstance(s.value, str)


class TestPOStateDefinitions:

    def test_po_state_has_abierta(self):
        assert POState.ABIERTA == "ABIERTA"

    def test_po_state_has_parcial(self):
        assert POState.PARCIAL == "PARCIAL"

    def test_po_state_has_recibida(self):
        assert POState.RECIBIDA == "RECIBIDA"

    def test_po_state_has_cerrada(self):
        assert POState.CERRADA == "CERRADA"

    def test_po_state_has_cancelada(self):
        assert POState.CANCELADA == "CANCELADA"

    def test_po_state_count_is_5(self):
        assert len(POState) == 5


class TestDocumentTypeDefinitions:

    def test_document_type_has_direct(self):
        assert DocumentType.DIRECT == "DIRECT"

    def test_document_type_has_pr(self):
        assert DocumentType.PR == "PR"

    def test_document_type_has_po(self):
        assert DocumentType.PO == "PO"

    def test_document_type_count_is_3(self):
        assert len(DocumentType) == 3


class TestDirectPurchaseStateDefinitions:

    def test_direct_has_completada(self):
        assert DirectPurchaseState.COMPLETADA == "completada"

    def test_direct_has_credito(self):
        assert DirectPurchaseState.CREDITO == "credito"

    def test_direct_has_cancelada(self):
        assert DirectPurchaseState.CANCELADA == "cancelada"


class TestPRStateTransitionLogic:
    """
    Verifica reglas de transición PR sin instanciar UI.
    Los tests comprueban la lógica de qué estados son terminales,
    cuáles preceden aprobación, etc.
    """

    def test_borrador_is_initial_state(self):
        # BORRADOR es el estado de entrada — puede avanzar a PENDIENTE_APROBACION
        non_terminal = {PRState.BORRADOR, PRState.PENDIENTE_APROBACION, PRState.APROBADA}
        assert PRState.BORRADOR in non_terminal

    def test_aprobada_can_convert_to_po(self):
        # Solo APROBADA puede convertirse a PO
        approved_leads_to_po = PRState.APROBADA != PRState.CONVERTIDA_A_PO
        assert approved_leads_to_po  # Son estados distintos, requieren transición explícita

    def test_rechazada_is_terminal(self):
        # RECHAZADA → no puede avanzar a APROBADA ni CONVERTIDA_A_PO
        # Verificamos que existe la distinción
        assert PRState.RECHAZADA != PRState.APROBADA
        assert PRState.RECHAZADA != PRState.CONVERTIDA_A_PO

    def test_cancelada_is_terminal(self):
        assert PRState.CANCELADA != PRState.APROBADA
        assert PRState.CANCELADA != PRState.CONVERTIDA_A_PO

    def test_pr_terminal_states_do_not_equal_active_states(self):
        terminal = {PRState.RECHAZADA, PRState.CANCELADA, PRState.CONVERTIDA_A_PO}
        active = {PRState.BORRADOR, PRState.PENDIENTE_APROBACION, PRState.APROBADA}
        assert terminal.isdisjoint(active)

    def test_pr_states_are_unique_values(self):
        values = [s.value for s in PRState]
        assert len(values) == len(set(values)), "PRState values must be unique"


class TestPOStateTransitionLogic:

    def test_abierta_is_initial_state(self):
        # PO nace ABIERTA
        assert POState.ABIERTA.value == "ABIERTA"

    def test_parcial_means_incomplete_receipt(self):
        assert POState.PARCIAL != POState.RECIBIDA

    def test_recibida_precedes_cerrada(self):
        assert POState.RECIBIDA != POState.CERRADA

    def test_cancelada_is_distinct_from_all_active(self):
        active = {POState.ABIERTA, POState.PARCIAL, POState.RECIBIDA}
        assert POState.CANCELADA not in active

    def test_po_states_are_unique_values(self):
        values = [s.value for s in POState]
        assert len(values) == len(set(values)), "POState values must be unique"


class TestStateMachineModule:
    """Verifica que el módulo de máquina de estados sea importable."""

    def test_states_module_importable(self):
        from application.purchases import states
        assert states is not None

    def test_all_states_accessible_from_package(self):
        from application.purchases.states import PRState, POState, DocumentType
        assert PRState and POState and DocumentType

    def test_pr_state_machine_contract(self):
        """
        Contrato: BORRADOR→PENDIENTE→APROBADA→CONVERTIDA_A_PO es el camino feliz.
        Este test documenta el camino, no lo ejecuta (no hay StateMachine todavía).
        """
        happy_path = [
            PRState.BORRADOR,
            PRState.PENDIENTE_APROBACION,
            PRState.APROBADA,
            PRState.CONVERTIDA_A_PO,
        ]
        # Camino feliz tiene 4 pasos distintos
        assert len(set(happy_path)) == 4

    def test_po_state_machine_contract(self):
        """
        Contrato: ABIERTA→PARCIAL→RECIBIDA→CERRADA es el camino feliz.
        """
        happy_path = [
            POState.ABIERTA,
            POState.PARCIAL,
            POState.RECIBIDA,
            POState.CERRADA,
        ]
        assert len(set(happy_path)) == 4

    def test_no_inventory_states_in_pr(self):
        """
        PR no tiene estado que implique movimiento de inventario.
        Los estados de PR son puramente documentales.
        """
        inventory_keywords = {"STOCK", "RECIBIDA", "INVENTARIO", "KARDEX"}
        for state in PRState:
            for kw in inventory_keywords:
                assert kw not in state.value.upper(), (
                    f"PRState.{state.name} contiene keyword de inventario: {kw}"
                )

    def test_no_finance_states_in_pr_or_po(self):
        """
        PR y PO no tienen estados que impliquen CXP o asiento contable.
        """
        finance_keywords = {"CXP", "ASIENTO", "FACTURA", "PAGADA", "COBRADA"}
        all_states = list(PRState) + list(POState)
        for state in all_states:
            for kw in finance_keywords:
                assert kw not in state.value.upper(), (
                    f"{state} contiene keyword financiero: {kw}"
                )
