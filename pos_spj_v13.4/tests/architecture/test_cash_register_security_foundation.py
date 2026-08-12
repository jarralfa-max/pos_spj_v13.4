"""CASH-1 guardrails for the canonical Cash Register security boundary."""
import ast
from pathlib import Path
import unittest

from backend.application.cash_register.permissions import ALL_CASH_PERMISSIONS


REPO = Path(__file__).resolve().parents[2]
ROOTS = (
    REPO / "backend" / "application" / "cash_register",
    REPO / "backend" / "domain" / "cash_register",
)


class CashRegisterSecurityArchitectureTests(unittest.TestCase):
    def test_permission_catalog_is_granular(self):
        required = {
            "CAJA.turno.abrir", "CAJA.turno.cerrar", "CAJA.movimiento.retiro",
            "CAJA.conteo.confirmar", "CAJA.corte_z.generar",
            "CAJA.diferencia.resolver", "CAJA.entrega.recibir",
            "CAJA.reembolso.autorizar", "CAJA.cajon.abrir_sin_venta",
        }
        self.assertTrue(required <= ALL_CASH_PERMISSIONS)
        self.assertTrue({"ADMIN_CAJA", "PUEDE_CERRAR_CAJA"}.isdisjoint(
            ALL_CASH_PERMISSIONS))

    def test_security_foundation_has_no_float_contracts_or_legacy_permissions(self):
        offenders = []
        legacy = {"CAJA", "ADMIN_CAJA", "PUEDE_CERRAR_CAJA", "PUEDE_VER_CORTE"}
        for root in ROOTS:
            for path in root.rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Constant) and isinstance(node.value, float):
                        offenders.append(f"{path.relative_to(REPO)}:{node.lineno}: float literal")
                    if isinstance(node, ast.Constant) and node.value in legacy:
                        offenders.append(f"{path.relative_to(REPO)}:{node.lineno}: {node.value}")
        self.assertFalse(offenders, "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()

