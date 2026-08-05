import unittest
from decimal import Decimal

from backend.application.cash_register.hardware import (
    CashHardwareError, PrintJob, TerminalPaymentRequest,
)
from backend.infrastructure.hardware.cash_register.drivers import (
    EscPosDrawerDriver, PaymentTerminalDriver, ReceiptPrinterDriver,
)


class Transport:
    def __init__(self): self.calls = []
    def write(self, device_id, payload): self.calls.append((device_id, payload))
    def print_bytes(self, printer_id, payload, copies): self.calls.append((printer_id, payload, copies))


class Client:
    def __init__(self, response): self.response, self.calls = response, []
    def charge(self, terminal_id, **kwargs):
        self.calls.append((terminal_id, kwargs)); return self.response


class CashHardwareDriversTest(unittest.TestCase):
    def test_drawer_sends_configured_escpos_pulse(self):
        transport = Transport()
        EscPosDrawerDriver(transport, b"pulse").open_drawer("drawer")
        self.assertEqual(transport.calls, [("drawer", b"pulse")])

    def test_printer_delegates_binary_job_and_copies(self):
        transport = Transport()
        ReceiptPrinterDriver(transport).print_job("printer", PrintJob("doc", b"ticket", 2))
        self.assertEqual(transport.calls, [("printer", b"ticket", 2)])

    def test_terminal_propagates_idempotency_key(self):
        client = Client({"approved": True, "transaction_id": "tx-1", "response_code": "00"})
        result = PaymentTerminalDriver(client).charge(
            "terminal", TerminalPaymentRequest("op-1", Decimal("12.30"), "MXN", "sale-1"))
        self.assertTrue(result.approved)
        self.assertEqual(client.calls[0][1]["idempotency_key"], "op-1")
        self.assertEqual(client.calls[0][1]["amount"], "12.30")

    def test_terminal_rejects_response_without_transaction(self):
        with self.assertRaises(CashHardwareError) as caught:
            PaymentTerminalDriver(Client({"approved": True})).charge(
                "terminal", TerminalPaymentRequest("op", Decimal("1"), "MXN", "sale"))
        self.assertEqual(caught.exception.code, "TERMINAL_INVALID_RESPONSE")


if __name__ == "__main__": unittest.main()
