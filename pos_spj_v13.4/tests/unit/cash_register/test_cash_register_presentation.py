import unittest

from frontend.desktop.modules.cash_register.presentation import (
    UUID_RE,
    direction_label,
    display_code,
    mask_technical_ids,
    movement_label,
    origin_label,
    scope_label,
    status_label,
    user_facing_error,
)


class CashRegisterPresentationTests(unittest.TestCase):
    def test_translates_operational_enums(self):
        self.assertEqual(movement_label("SAFE_DROP"), "Retiro a boveda")
        self.assertEqual(movement_label("CASH_REFUND"), "Reembolso en efectivo")
        self.assertEqual(direction_label("INFLOW"), "Entrada")
        self.assertEqual(status_label("OPEN"), "Abierto")
        self.assertEqual(status_label("UNDER_REVIEW"), "En revision")
        self.assertEqual(scope_label("REGISTER"), "Caja")

    def test_visible_codes_do_not_expose_full_uuid(self):
        entity_id = "01900000-0000-7000-8000-00000000abcd"
        code = display_code("MOV", entity_id)
        self.assertEqual(code, "MOV-00ABCD")
        self.assertNotRegex(code, UUID_RE)

    def test_origin_label_uses_business_context(self):
        sale_id = "01900000-0000-7000-8000-00000000abcd"
        self.assertEqual(origin_label(sale_id=sale_id), "Venta VTA-00ABCD")

    def test_error_mapper_masks_technical_identity(self):
        message = user_facing_error(
            "Identidad no valida: 01900000-0000-7000-8000-00000000abcd"
        )
        self.assertNotRegex(message, UUID_RE)
        self.assertIn("registro seleccionado", message)
        self.assertNotRegex(mask_technical_ids("x 01900000-0000-7000-8000-00000000abcd"), UUID_RE)


if __name__ == "__main__":
    unittest.main()
