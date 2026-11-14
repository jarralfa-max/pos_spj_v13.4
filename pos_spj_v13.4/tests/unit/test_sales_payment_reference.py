"""SDLC-PAY-002 — un pago de procesador no puede respaldar dos ventas.

Decisión del responsable (2026-11-05): la referencia es obligatoria y única
para Mercado Pago, Tarjeta y Transferencia.
"""

from __future__ import annotations

import importlib
import sqlite3
from decimal import Decimal

import pytest

from backend.application.sales.authorization import (
    AllowAllSalesPermissionCheckerForTests,
    SalesAuthorizationPolicy,
)
from backend.application.sales.use_cases.cart_use_cases import (
    AddSaleLineUseCase,
    StartSaleUseCase,
)
from backend.application.sales.use_cases.lifecycle_use_cases import (
    BeginSaleCheckoutUseCase,
    CancelSaleUseCase,
)
from backend.application.sales.use_cases.payment_use_cases import (
    RecordSalePaymentUseCase,
    payment_reference_problem,
)
from backend.application.sales.use_cases.payment_void_use_cases import VoidSalePaymentUseCase
from backend.domain.sales.enums import PaymentMethod
from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
from backend.infrastructure.db.schema.sales_schema import (
    create_payment_reference_index,
    create_sales_schema,
)
from backend.shared.ids import new_uuid


def _auth() -> SalesAuthorizationPolicy:
    return SalesAuthorizationPolicy(AllowAllSalesPermissionCheckerForTests())


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sales_schema(c)
    create_payment_reference_index(c)
    c.commit()
    yield c
    c.close()


def _sale(conn, *, price="100.00") -> tuple[str, str]:
    branch, cashier = new_uuid(), new_uuid()
    sale_id = StartSaleUseCase(_auth()).execute(
        conn, branch_id=branch, cashier_user_id=cashier, operation_id=new_uuid(),
        actor_user_id=cashier).entity_id
    AddSaleLineUseCase(_auth()).execute(
        conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
        unit_price=Decimal(price), actor_user_id=cashier, operation_id=new_uuid())
    BeginSaleCheckoutUseCase(_auth()).execute(
        conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
    return sale_id, cashier


def _pay(conn, sale_id, cashier, *, method="MERCADO_PAGO", reference=None, amount="100.00"):
    return RecordSalePaymentUseCase(_auth()).execute(
        conn, sale_id=sale_id, method=method, amount=Decimal(amount),
        actor_user_id=cashier, operation_id=new_uuid(), reference=reference)


class TestReferenciaObligatoria:
    @pytest.mark.parametrize("method", ["MERCADO_PAGO", "CARD", "TRANSFER"])
    @pytest.mark.parametrize("reference", [None, "", "   "])
    def test_el_procesador_exige_referencia(self, conn, method, reference):
        sale_id, cashier = _sale(conn)
        result = _pay(conn, sale_id, cashier, method=method, reference=reference)
        assert result.success is False
        assert result.error_code == "PAYMENT_REFERENCE_REQUIRED"
        assert SaleRepository(conn).get(sale_id).payments == []

    @pytest.mark.parametrize("reference", ["abc", "con espacio", "x" * 65, "ñandú-123", "-12345"])
    def test_formato_invalido(self, conn, reference):
        sale_id, cashier = _sale(conn)
        result = _pay(conn, sale_id, cashier, reference=reference)
        assert result.success is False
        assert result.error_code == "PAYMENT_REFERENCE_INVALID"

    @pytest.mark.parametrize("reference", ["123456789012", "mp-payment-123", "AB12/34.5_6"])
    def test_formatos_validos(self, conn, reference):
        sale_id, cashier = _sale(conn)
        assert _pay(conn, sale_id, cashier, reference=reference).success is True

    def test_efectivo_no_la_exige(self, conn):
        sale_id, cashier = _sale(conn)
        assert _pay(conn, sale_id, cashier, method="CASH").success is True


class TestReferenciaUnica:
    def test_la_misma_referencia_en_dos_ventas_falla_la_segunda(self, conn):
        primera, cajero_1 = _sale(conn)
        segunda, cajero_2 = _sale(conn)
        assert _pay(conn, primera, cajero_1, reference="1234567890").success is True
        result = _pay(conn, segunda, cajero_2, reference="1234567890")
        assert result.success is False
        assert result.error_code == "PAYMENT_REFERENCE_DUPLICATED"
        assert SaleRepository(conn).get(segunda).payments == []

    @pytest.mark.parametrize("method", ["CARD", "TRANSFER"])
    def test_tambien_para_tarjeta_y_transferencia(self, conn, method):
        primera, cajero_1 = _sale(conn)
        segunda, cajero_2 = _sale(conn)
        assert _pay(conn, primera, cajero_1, method=method, reference="AUTH-0001").success
        result = _pay(conn, segunda, cajero_2, method=method, reference="AUTH-0001")
        assert result.error_code == "PAYMENT_REFERENCE_DUPLICATED"

    def test_mayusculas_y_espacios_no_la_vuelven_otra(self, conn):
        primera, cajero_1 = _sale(conn)
        segunda, cajero_2 = _sale(conn)
        assert _pay(conn, primera, cajero_1, reference="mp-777888").success
        result = _pay(conn, segunda, cajero_2, reference="  MP-777888 ")
        assert result.error_code == "PAYMENT_REFERENCE_DUPLICATED"

    def test_dos_lineas_de_la_misma_venta_tampoco(self, conn):
        sale_id, cashier = _sale(conn)
        assert _pay(conn, sale_id, cashier, reference="MP-1000", amount="40.00").success
        result = _pay(conn, sale_id, cashier, reference="MP-1000", amount="60.00")
        assert result.error_code == "PAYMENT_REFERENCE_DUPLICATED"

    def test_el_mismo_numero_en_otro_metodo_es_otro_pago(self, conn):
        primera, cajero_1 = _sale(conn)
        segunda, cajero_2 = _sale(conn)
        assert _pay(conn, primera, cajero_1, method="CARD", reference="555666").success
        assert _pay(conn, segunda, cajero_2, method="TRANSFER", reference="555666").success

    def test_segundo_pago_de_la_venta_no_choca_con_el_delete_insert(self, conn):
        sale_id, cashier = _sale(conn)
        assert _pay(conn, sale_id, cashier, reference="MP-2000", amount="40.00").success
        # El repositorio borra y reinserta los pagos de la venta en cada guardado.
        assert _pay(conn, sale_id, cashier, method="CASH", amount="60.00").success
        assert len(SaleRepository(conn).get(sale_id).payments) == 2


class TestAnulada:
    def test_anular_el_pago_libera_la_referencia(self, conn):
        primera, cajero_1 = _sale(conn)
        pagado = _pay(conn, primera, cajero_1, reference="MP-3000")
        payment_id = pagado.data["sale"].payments[0].id
        assert VoidSalePaymentUseCase(_auth()).execute(
            conn, sale_id=primera, payment_id=payment_id, reason="Monto equivocado",
            actor_user_id=cajero_1, operation_id=new_uuid()).success is True
        segunda, cajero_2 = _sale(conn)
        assert _pay(conn, segunda, cajero_2, reference="MP-3000").success is True

    def test_cancelar_la_venta_libera_la_referencia(self, conn):
        primera, cajero_1 = _sale(conn)
        assert _pay(conn, primera, cajero_1, reference="MP-4000").success
        assert CancelSaleUseCase(_auth()).execute(
            conn, sale_id=primera, reason="Cliente desistió", actor_user_id=cajero_1,
            operation_id=new_uuid()).success is True
        segunda, cajero_2 = _sale(conn)
        assert _pay(conn, segunda, cajero_2, reference="MP-4000").success is True


class TestRestriccionEnBase:
    def test_el_indice_rechaza_aunque_el_caso_de_uso_no_lo_vea(self, conn, monkeypatch):
        """Dos cajas a la vez: ambas pasan la revisión previa; decide el índice."""
        primera, cajero_1 = _sale(conn)
        segunda, cajero_2 = _sale(conn)
        assert _pay(conn, primera, cajero_1, reference="MP-5000").success
        monkeypatch.setattr(SaleRepository, "find_live_payment_reference",
                            lambda self, **_: None)
        result = _pay(conn, segunda, cajero_2, reference="MP-5000")
        assert result.success is False
        assert result.error_code == "PAYMENT_REFERENCE_DUPLICATED"
        assert SaleRepository(conn).get(segunda).payments == []

    def test_insert_directo_duplicado_falla(self, conn):
        primera, cajero_1 = _sale(conn)
        assert _pay(conn, primera, cajero_1, reference="MP-5100").success
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sale_payments (id, sale_id, method, amount, reference,"
                " captured_by_user_id, captured_at) VALUES (?,?,?,?,?,?,?)",
                (new_uuid(), primera, "MERCADO_PAGO", "1", "mp-5100", cajero_1, "2026-11-06"))

    def test_referencia_vacia_no_participa(self, conn):
        primera, cajero_1 = _sale(conn)
        for _ in range(2):
            conn.execute(
                "INSERT INTO sale_payments (id, sale_id, method, amount, reference,"
                " captured_by_user_id, captured_at) VALUES (?,?,?,?,?,?,?)",
                (new_uuid(), primera, "CASH", "1", None, cajero_1, "2026-11-06"))


class TestConsultaDelDialogo:
    def test_dice_por_que_antes_de_iniciar_el_cobro(self, conn):
        primera, cajero_1 = _sale(conn)
        assert _pay(conn, primera, cajero_1, reference="MP-6000").success
        assert "obligatoria" in payment_reference_problem(
            conn, method="MERCADO_PAGO", reference=None)
        assert "ya está registrada" in payment_reference_problem(
            conn, method="MERCADO_PAGO", reference="MP-6000")
        assert payment_reference_problem(conn, method="MERCADO_PAGO", reference="MP-6001") is None
        assert payment_reference_problem(conn, method="CASH", reference=None) is None

    def test_tambien_ve_las_lineas_aun_no_guardadas(self, conn):
        assert "ya está en los pagos" in payment_reference_problem(
            conn, method="CARD", reference="auth-1", taken=(("CARD", "AUTH-1"),))
        assert payment_reference_problem(
            conn, method="CARD", reference="auth-1", taken=(("TRANSFER", "AUTH-1"),)) is None


class TestMigracion:
    def _migracion(self):
        return importlib.import_module("migrations.standalone.384_sale_payment_reference_unique")

    def _base(self, *refs):
        c = sqlite3.connect(":memory:")
        create_sales_schema(c)
        for i, (method, ref) in enumerate(refs):
            c.execute(
                "INSERT INTO sale_payments (id, sale_id, method, amount, reference,"
                " captured_by_user_id, captured_at) VALUES (?,?,?,?,?,?,?)",
                (f"p{i}", "s", method, "1", ref, "u", f"2026-01-0{i + 1}"))
        c.commit()
        return c

    def test_base_sin_duplicados(self):
        c = self._base(("MERCADO_PAGO", "A1"), ("CARD", None), ("CARD", ""))
        self._migracion().run(c)
        self._migracion().run(c)  # idempotente
        with pytest.raises(sqlite3.IntegrityError):
            c.execute(
                "INSERT INTO sale_payments (id, sale_id, method, amount, reference,"
                " captured_by_user_id, captured_at) VALUES ('x','s','MERCADO_PAGO','1','a1','u',"
                " '2026-02-01')")

    def test_duplicados_historicos_se_conservan_y_lo_nuevo_queda_protegido(self):
        c = self._base(("MERCADO_PAGO", "A1"), ("MERCADO_PAGO", "a1"), ("CARD", "B2"))
        self._migracion().run(c)
        assert c.execute("SELECT COUNT(*) FROM sale_payments").fetchone()[0] == 3
        c.execute(
            "INSERT INTO sale_payments (id, sale_id, method, amount, reference,"
            " captured_by_user_id, captured_at) VALUES ('n1','s','CARD','1','C3','u','2026-02-01')")
        with pytest.raises(sqlite3.IntegrityError):
            c.execute(
                "INSERT INTO sale_payments (id, sale_id, method, amount, reference,"
                " captured_by_user_id, captured_at)"
                " VALUES ('n2','s','CARD','1','c3','u','2026-02-02')")

    def test_base_sin_ventas_canonicas(self):
        c = sqlite3.connect(":memory:")
        self._migracion().run(c)

    def test_registrada_en_el_motor(self):
        from migrations.engine import MIGRATIONS

        assert ("384" in {m.version for m in MIGRATIONS})

    def test_metodos_del_indice_son_los_de_la_politica(self):
        from backend.domain.sales.policies.payment_policy import REFERENCE_REQUIRED_METHODS

        assert REFERENCE_REQUIRED_METHODS == {
            PaymentMethod.MERCADO_PAGO, PaymentMethod.CARD, PaymentMethod.TRANSFER}
