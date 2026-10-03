"""LOY-29 — re-auditoría de Fidelidad: el módulo de punta a punta.

Recorre, por el presenter REAL y los casos de uso reales, lo que antes era un
letrero de "en construcción" o simplemente no funcionaba:

* Programas: el creador NO puede aprobar su propio programa (§60) — antes sí.
* Puntos: reversar una acumulación ya canjeada no deja el saldo negativo (§29).
* Cupones, vales (saldo del libro), sorteos (participación antes del boleto,
  reimpresión con motivo y sin duplicar), antifraude.
* Tarjetas: pliego 12 × 18, imposición, plantilla versionada con reverso,
  emisión, QR que resuelve y que deja de resolver al rotarse, lote aprobado por
  otra persona, impresión y reimpresión sin tarjetas nuevas.
* Auditoría: cada hecho deja rastro en `audit_logs`, sin token de QR.
"""

from __future__ import annotations

import json
import os
import sqlite3
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from backend.application.loyalty.queries.records_query_service import LoyaltyRecord as R  # noqa: E402
from backend.shared.ids import new_uuid  # noqa: E402


@pytest.fixture(scope="module")
def template_db():
    import migrations.m000_base_schema as base
    from backend.infrastructure.db.schema.commercial_instruments_schema import (
        create_commercial_instruments_schema,
    )
    from backend.infrastructure.db.schema.customers_crm_schema import create_customers_crm_schema
    from backend.infrastructure.db.schema.loyalty_cards_schema import create_loyalty_cards_schema
    from backend.infrastructure.db.schema.loyalty_schema import create_loyalty_schema
    from backend.infrastructure.db.schema.sweepstakes_schema import create_sweepstakes_schema

    c = sqlite3.connect(":memory:")
    base.up(c)
    for crear in (create_customers_crm_schema, create_loyalty_schema,
                  create_commercial_instruments_schema, create_sweepstakes_schema,
                  create_loyalty_cards_schema):
        crear(c)
    c.commit()
    yield c
    c.close()


@pytest.fixture
def conn(template_db):
    c = sqlite3.connect(":memory:")
    template_db.backup(c)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


class _Session:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.active_branch_id = new_uuid()
        self.is_active = True

    def tiene_permiso(self, _code) -> bool:
        return True


@pytest.fixture
def two_users(conn):
    from frontend.desktop.modules.fidelidad.composition import build_fidelidad_presenter

    return (build_fidelidad_presenter(conn, _Session(new_uuid())),
            build_fidelidad_presenter(conn, _Session(new_uuid())))


def _customer(conn, name="Ana Torres") -> str:
    from backend.application.customers.authorization import CustomerAuthorizationPolicy
    from backend.application.sales.use_cases.customer_use_cases import (
        QuickCreateCustomerForSaleUseCase,
    )
    return QuickCreateCustomerForSaleUseCase(CustomerAuthorizationPolicy.permissive_for_tests()).execute(
        conn, actor_user_id=new_uuid(), operation_id=new_uuid(), display_name=name).entity_id


def _ok(result):
    assert result.success, result.message
    return result


def _first(p, record, **kw):
    rows = p.records(record, **kw).rows
    return rows[0] if rows else None


def _active_program(a, b, code="P1"):
    _ok(a.run_command("create_program", code=code, name=f"Programa {code}", currency_name="Puntos"))
    prog = [r for r in a.records(R.PROGRAMS).rows if r["code"] == code][0]
    _ok(b.run_command("approve_program", program_id=prog["id"]))
    _ok(a.run_command("activate_program", program_id=prog["id"]))
    return prog["id"]


class TestProgramsAndPoints:
    def test_creator_cannot_approve_own_program_nor_approve_twice(self, conn, two_users):
        a, b = two_users
        _ok(a.run_command("create_program", code="P1", name="Puntos", currency_name="Puntos"))
        prog = _first(a, R.PROGRAMS)
        propio = a.run_command("approve_program", program_id=prog["id"])
        assert not propio.success
        assert "crea" in propio.message
        _ok(b.run_command("approve_program", program_id=prog["id"]))
        assert not b.run_command("approve_program", program_id=prog["id"]).success

    def test_points_balance_comes_from_ledger_and_reversal_never_goes_negative(
            self, conn, two_users):
        a, b = two_users
        programa = _active_program(a, b)
        _ok(a.run_command("enroll_membership", customer_id=_customer(conn), program_id=programa))
        cuenta = _first(a, R.ACCOUNTS)
        _ok(a.run_command("accrue_points", loyalty_account_id=cuenta["id"],
                          points_amount=Decimal("150"), reason_code="BONO"))
        _ok(a.run_command("redeem_points", loyalty_account_id=cuenta["id"],
                          points_amount=Decimal("20"), reason_code="CANJE"))
        assert _first(a, R.ACCOUNTS)["points"] == Decimal("130")
        acumulacion = _first(a, R.LEDGER, status="EARN")
        rechazo = a.run_command("reverse_transaction", transaction_id=acumulacion["id"],
                                reason_code="ERROR")
        assert not rechazo.success
        assert _first(a, R.ACCOUNTS)["points"] == Decimal("130")

    def test_overview_and_alerts_come_from_backend(self, conn, two_users):
        a, _ = two_users
        _ok(a.run_command("create_program", code="P9", name="Pendiente", currency_name="Puntos"))
        resumen = a.overview()
        assert resumen.active_members == 0
        alertas = a.alerts()
        assert any(al.route_id == "loyalty.programs" and al.count == 1 for al in alertas)


class TestInstrumentsAndSweepstakes:
    def test_voucher_balance_is_derived_from_its_ledger(self, conn, two_users):
        from backend.domain.commercial_instruments.enums import VoucherType

        a, _ = two_users
        _ok(a.run_command("create_voucher_definition", code="SAF", name="Saldo a favor",
                          voucher_type=VoucherType.STORE_CREDIT))
        _ok(a.run_command("issue_voucher", definition_id=_first(a, R.VOUCHER_DEFINITIONS)["id"],
                          customer_id=_customer(conn), amount=Decimal("75.50")))
        assert _first(a, R.VOUCHERS)["balance"] == Decimal("75.50")

    def test_entry_exists_before_ticket_and_reprint_needs_reason_and_keeps_entry(
            self, conn, two_users, monkeypatch):
        from backend.domain.sweepstakes.enums import SweepstakesEntryMethod
        from backend.infrastructure.hardware.sales_ticket_printer import SalesTicketPrinter

        impresos = []
        monkeypatch.setattr(SalesTicketPrinter, "print_raffle_ticket",
                            lambda self, datos, **_: impresos.append(datos) or "job")
        a, b = two_users
        _ok(a.run_command("create_sweepstakes_campaign", code="S1", name="Rifa"))
        campana = _first(a, R.SWEEPSTAKES_CAMPAIGNS)
        _ok(b.run_command("approve_sweepstakes_campaign", campaign_id=campana["id"]))
        _ok(a.run_command("activate_sweepstakes_campaign", campaign_id=campana["id"]))
        _ok(a.run_command("grant_sweepstakes_entry", campaign_id=campana["id"],
                          customer_id=_customer(conn), chances_granted=1, notes="Cortesía",
                          entry_method=SweepstakesEntryMethod.MANUAL_GRANT))
        participacion = _first(a, R.SWEEPSTAKES_ENTRIES)
        _ok(a.run_command("issue_sweepstakes_ticket", entry_id=participacion["id"],
                          campaign_id=participacion["campaign_id"]))
        boleto = _first(a, R.SWEEPSTAKES_TICKETS)
        _ok(a.run_command("print_sweepstakes_ticket", ticket_id=boleto["id"]))
        assert not a.run_command("print_sweepstakes_ticket", ticket_id=boleto["id"]).success
        _ok(a.run_command("print_sweepstakes_ticket", ticket_id=boleto["id"], reason="atasco"))
        assert a.records(R.SWEEPSTAKES_ENTRIES).total == 1
        assert a.records(R.SWEEPSTAKES_TICKETS).total == 1
        assert _first(a, R.SWEEPSTAKES_TICKETS)["print_count"] == 2
        assert [d["folio"].endswith("(COPIA)") for d in impresos] == [False, True]

    def test_without_a_printer_the_print_is_not_recorded(self, conn, two_users):
        from backend.domain.sweepstakes.enums import SweepstakesEntryMethod

        a, b = two_users
        _ok(a.run_command("create_sweepstakes_campaign", code="S2", name="Rifa"))
        campana = _first(a, R.SWEEPSTAKES_CAMPAIGNS)
        _ok(b.run_command("approve_sweepstakes_campaign", campaign_id=campana["id"]))
        _ok(a.run_command("activate_sweepstakes_campaign", campaign_id=campana["id"]))
        _ok(a.run_command("grant_sweepstakes_entry", campaign_id=campana["id"],
                          customer_id=_customer(conn), chances_granted=1, notes="x",
                          entry_method=SweepstakesEntryMethod.MANUAL_GRANT))
        participacion = _first(a, R.SWEEPSTAKES_ENTRIES)
        _ok(a.run_command("issue_sweepstakes_ticket", entry_id=participacion["id"],
                          campaign_id=participacion["campaign_id"]))
        boleto = _first(a, R.SWEEPSTAKES_TICKETS)
        resultado = a.run_command("print_sweepstakes_ticket", ticket_id=boleto["id"])
        assert not resultado.success and "impresora" in resultado.message.lower()
        assert _first(a, R.SWEEPSTAKES_TICKETS)["print_count"] == 0


class TestLoyaltyCards:
    def _card_setup(self, conn, a, b):
        from backend.domain.loyalty_cards.enums import LoyaltyCardTemplateTargetType, LoyaltyCardType

        programa = _active_program(a, b)
        _ok(a.run_command("enroll_membership", customer_id=_customer(conn), program_id=programa))
        membresia = _first(a, R.MEMBERSHIPS)
        _ok(a.run_command("create_card_template", code="T1", name="Clásica",
                          target_type=LoyaltyCardTemplateTargetType.PHYSICAL))
        plantilla = _first(a, R.CARD_TEMPLATES)
        _ok(b.run_command("approve_card_template", template_id=plantilla["id"]))
        diseno = {"canvas": {"width_mm": "85.6", "height_mm": "53.98"},
                  "elements": [{"type": "TEXT", "content": "{{customer_name}}", "x_mm": "5",
                                "y_mm": "40", "width_mm": "50", "height_mm": "6"},
                               {"type": "QR", "data_source": "CARD_TOKEN", "x_mm": "60",
                                "y_mm": "25", "width_mm": "20", "height_mm": "20"}],
                  "back_elements": [{"type": "BARCODE", "format": "CODE128",
                                     "data_source": "CARD_NUMBER", "x_mm": "5", "y_mm": "40",
                                     "width_mm": "45", "height_mm": "7"}]}
        _ok(a.run_command("save_card_design", template_id=plantilla["id"],
                          design_schema_json=json.dumps(diseno)))
        version = _first(a, R.CARD_TEMPLATE_VERSIONS)
        assert not a.run_command("approve_card_template_version", version_id=version["id"]).success
        _ok(b.run_command("approve_card_template_version", version_id=version["id"]))
        _ok(a.run_command("activate_card_template_version", version_id=version["id"]))
        _ok(a.run_command("issue_card", membership_id=membresia["id"],
                          card_type=LoyaltyCardType.PHYSICAL))
        return programa, plantilla, _first(a, R.CARDS)

    def test_qr_resolves_without_internal_ids_and_stops_after_rotation(self, conn, two_users):
        from backend.application.loyalty_cards.queries.card_render_data_query import (
            LoyaltyCardRenderDataQuery,
        )

        a, b = two_users
        _programa, _plantilla, tarjeta = self._card_setup(conn, a, b)
        _ok(a.run_command("activate_card", card_id=tarjeta["id"]))
        qr = LoyaltyCardRenderDataQuery(conn).placeholders_for_card(tarjeta["id"])["card_token"]
        assert qr.startswith("SPJ-CARD:")
        for interno in (tarjeta["id"], tarjeta["customer_id"], tarjeta["membership_id"]):
            assert interno not in qr
        resuelta = a.resolve_card(qr)
        assert resuelta.found and resuelta.eligible
        assert resuelta.customer_id == tarjeta["customer_id"]
        _ok(a.run_command("rotate_card_token", card_id=tarjeta["id"]))
        vieja = a.resolve_card(qr)
        assert vieja.found and not vieja.eligible

    def test_batch_needs_second_approver_and_reprint_creates_no_cards(self, conn, two_users):
        a, b = two_users
        programa, plantilla, _tarjeta = self._card_setup(conn, a, b)
        _ok(a.run_command("create_standard_sheet"))
        pliego = _first(a, R.CARD_SHEETS)
        assert Decimal(str(pliego["width_mm"])) == Decimal("304.8")
        assert Decimal(str(pliego["height_mm"])) == Decimal("457.2")
        _ok(a.run_command("create_imposition", sheet_profile_id=pliego["id"],
                          card_width_mm=Decimal("85.6"), card_height_mm=Decimal("53.98"),
                          bleed_mm=Decimal("3"), safe_area_mm=Decimal("3")))
        imposicion = _first(a, R.CARD_IMPOSITIONS)
        sin_destinatarios = a.run_command(
            "create_card_batch", program_id=programa, template_id=plantilla["id"],
            imposition_profile_id=imposicion["id"])
        assert not sin_destinatarios.success  # la única membresía ya tiene tarjeta vigente
        segundo = _active_program(a, b, code="P2")
        cliente = _first(a, R.ACCOUNTS)["customer_id"]
        _ok(a.run_command("enroll_membership", customer_id=cliente, program_id=segundo))
        _ok(a.run_command("create_card_batch", program_id=segundo, template_id=plantilla["id"],
                          imposition_profile_id=imposicion["id"]))
        lote = _first(a, R.CARD_BATCHES)
        _ok(a.run_command("submit_card_batch", batch_id=lote["id"]))
        assert not a.run_command("approve_card_batch", batch_id=lote["id"]).success
        _ok(b.run_command("approve_card_batch", batch_id=lote["id"]))
        _ok(a.run_command("start_card_batch_printing", batch_id=lote["id"]))
        _ok(a.run_command("render_card_batch", batch_id=lote["id"]))
        tarjetas = a.records(R.CARDS).total
        trabajo = _first(a, R.CARD_PRINT_JOBS)
        _ok(a.run_command("reprint_card_batch", original_job_id=trabajo["id"], reason="manchado"))
        assert a.records(R.CARDS).total == tarjetas
        assert a.records(R.CARD_REPRINTS).total == 1


class TestAudit:
    def test_every_fact_is_audited_without_qr_token(self, conn, two_users):
        a, b = two_users
        _programa, _plantilla, tarjeta = self._setup(conn, a, b)
        filas = conn.execute(
            "SELECT accion, modulo, valor_despues FROM audit_logs"
            " WHERE modulo IN ('GROWTH_ENGINE', 'TARJETAS_FIDELIDAD')").fetchall()
        acciones = {f["accion"] for f in filas}
        assert "ApproveLoyaltyProgram" in acciones  # transición sin evento canónico
        assert any(f["modulo"] == "TARJETAS_FIDELIDAD" for f in filas)
        from backend.application.loyalty_cards.queries.card_render_data_query import (
            LoyaltyCardRenderDataQuery,
        )
        qr = LoyaltyCardRenderDataQuery(conn).placeholders_for_card(tarjeta["id"])["card_token"]
        token = qr.removeprefix("SPJ-CARD:")
        assert token and not any(token in (f["valor_despues"] or "") for f in filas)
        # §32: el token tampoco vive en la tabla de tokens.
        assert not any(token in str(tuple(f)) for f in conn.execute(
            "SELECT * FROM loyalty_card_tokens").fetchall())

    def _setup(self, conn, a, b):
        return TestLoyaltyCards()._card_setup(conn, a, b)


class TestRecordsPermissions:
    def test_each_record_requires_its_own_read_permission(self, conn):
        from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
        from backend.application.loyalty.queries.records_query_service import (
            LoyaltyRecordsQueryService,
        )
        from backend.domain.loyalty.exceptions import LoyaltyDomainError

        servicio = LoyaltyRecordsQueryService(conn, authorization=LoyaltyAuthorizationPolicy())
        with pytest.raises(LoyaltyDomainError):
            servicio.page(R.PROGRAMS, actor_user_id=new_uuid())

    def test_unknown_filter_is_rejected_not_interpolated(self, conn):
        from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
        from backend.application.loyalty.queries.records_query_service import (
            LoyaltyRecordsQueryService,
        )

        servicio = LoyaltyRecordsQueryService(
            conn, authorization=LoyaltyAuthorizationPolicy.permissive_for_tests())
        with pytest.raises(ValueError):
            servicio.page(R.MEMBERSHIPS, actor_user_id=new_uuid(),
                          filters={"1=1; DROP TABLE x --": "y"})


class TestCardPrivacy:
    def test_privacy_settings_change_what_is_printed(self, conn, two_users):
        from backend.application.loyalty_cards.queries.card_render_data_query import (
            LoyaltyCardRenderDataQuery,
        )
        from backend.domain.loyalty_cards.policies.privacy_policy import CardNameMode

        a, b = two_users
        _programa, _plantilla, tarjeta = TestLoyaltyCards()._card_setup(conn, a, b)
        datos = LoyaltyCardRenderDataQuery(conn)
        assert datos.placeholders_for_card(tarjeta["id"])["customer_name"] == "Ana Torres"
        assert datos.placeholders_for_card(tarjeta["id"])["points_balance"] == ""
        _ok(a.run_command("update_card_privacy", name_mode=CardNameMode.FIRST_NAME,
                          print_points_balance=True))
        impreso = datos.placeholders_for_card(tarjeta["id"])
        assert impreso["customer_name"] == "Ana"
        assert impreso["points_balance"] == "0"
        assert "card_token" not in datos.display_fields_for_card(tarjeta["id"])


class TestAuthorizedAdjustment:
    """§60: quien ajusta puntos no aprueba su propio ajuste; el autorizador es
    OTRA persona con `puntos.ajustar` según `rol_permisos`."""

    def _usuarios(self, conn):
        ids = {}
        for rol in ("cajero", "admin"):
            uid = new_uuid()
            conn.execute("INSERT INTO usuarios (id, nombre, usuario, password_hash, rol, activo)"
                         " VALUES (?,?,?,?,?,1)", (uid, rol, f"u_{rol}", "x", rol))
            ids[rol] = uid
        conn.commit()
        return ids

    def test_second_person_authorizes_and_balance_never_goes_negative(self, conn):
        from frontend.desktop.modules.fidelidad.composition import build_fidelidad_presenter

        ids = self._usuarios(conn)
        a = build_fidelidad_presenter(conn, _Session(ids["cajero"]))
        b = build_fidelidad_presenter(conn, _Session(new_uuid()))
        programa = _active_program(a, b)
        _ok(a.run_command("enroll_membership", customer_id=_customer(conn), program_id=programa))
        cuenta = _first(a, R.ACCOUNTS)["id"]
        propio = a.run_command("adjust_points", loyalty_account_id=cuenta,
                               points_amount=Decimal("10"), reason_code="CORTESIA",
                               authorizer_user_id=ids["cajero"])
        assert not propio.success
        sin_permiso = a.run_command("adjust_points", loyalty_account_id=cuenta,
                                    points_amount=Decimal("10"), reason_code="CORTESIA",
                                    authorizer_user_id=new_uuid())
        assert not sin_permiso.success
        _ok(a.run_command("adjust_points", loyalty_account_id=cuenta, points_amount=Decimal("10"),
                          reason_code="CORTESIA", authorizer_user_id=ids["admin"]))
        assert _first(a, R.ACCOUNTS)["points"] == Decimal("10")
        assert not a.run_command("adjust_points", loyalty_account_id=cuenta,
                                 points_amount=Decimal("-11"), reason_code="ERROR",
                                 authorizer_user_id=ids["admin"]).success


class TestPreprintedCards:
    """§44-45: tarjetas preimpresas sin cliente, asignadas una sola vez."""

    def test_preprinted_batch_assign_activate_and_no_reassignment(self, conn, two_users):
        from backend.application.loyalty_cards.queries.card_render_data_query import (
            LoyaltyCardRenderDataQuery,
        )

        a, b = two_users
        programa, plantilla, _tarjeta = TestLoyaltyCards()._card_setup(conn, a, b)
        _ok(a.run_command("create_standard_sheet"))
        _ok(a.run_command("create_imposition", sheet_profile_id=_first(a, R.CARD_SHEETS)["id"],
                          card_width_mm=Decimal("85.6"), card_height_mm=Decimal("53.98")))
        _ok(a.run_command("create_preprinted_batch", blank_quantity=3,
                          template_id=plantilla["id"],
                          imposition_profile_id=_first(a, R.CARD_IMPOSITIONS)["id"]))
        sin_asignar = a.records(R.CARDS, status="UNASSIGNED").rows
        assert len(sin_asignar) == 3
        datos = LoyaltyCardRenderDataQuery(conn)
        impreso = datos.placeholders_for_card(sin_asignar[0]["id"])
        assert impreso["customer_name"] == "" and impreso["card_token"].startswith("SPJ-CARD:")
        resuelta = a.resolve_card(impreso["card_token"])
        assert resuelta.found and not resuelta.eligible
        assert any("asignada" in aviso for aviso in resuelta.warnings)

        # La única membresía ya tiene su tarjeta personalizada: no admite otra.
        membresia = _first(a, R.MEMBERSHIPS)
        assert not a.run_command("assign_card", card_id=sin_asignar[0]["id"],
                                 membership_id=membresia["id"]).success
        otro = _active_program(a, b, code="P3")
        _ok(a.run_command("enroll_membership", customer_id=membresia["customer_id"],
                          program_id=otro))
        nueva = [m for m in a.records(R.MEMBERSHIPS).rows if m["program_id"] == otro][0]
        _ok(a.run_command("assign_card", card_id=sin_asignar[0]["id"],
                          membership_id=nueva["id"], reason="Entregada en mostrador"))
        assert a.records(R.CARD_ASSIGNMENTS).total == 1
        assert not a.run_command("assign_card", card_id=sin_asignar[0]["id"],
                                 membership_id=nueva["id"]).success  # no se reasigna
        _ok(a.run_command("activate_card", card_id=sin_asignar[0]["id"]))
        assert a.resolve_card(impreso["card_token"]).eligible


class TestTemplateImport:
    """§41: importar crea una versión nueva y rechaza contenido peligroso."""

    def test_svg_import_creates_a_version_and_scripts_are_rejected(self, conn, two_users, tmp_path):
        from backend.domain.loyalty_cards.enums import LoyaltyCardTemplateTargetType

        a, _b = two_users
        _ok(a.run_command("create_card_template", code="T9", name="Importada",
                          target_type=LoyaltyCardTemplateTargetType.PHYSICAL))
        plantilla = _first(a, R.CARD_TEMPLATES)["id"]
        bueno = tmp_path / "tarjeta.svg"
        bueno.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 856 539.8">'
                         '<rect width="10" height="10"/></svg>', encoding="utf-8")
        _ok(a.run_command("import_card_design", template_id=plantilla, file_path=str(bueno)))
        assert a.records(R.CARD_TEMPLATE_VERSIONS).total == 1
        malo = tmp_path / "malo.svg"
        malo.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 856 540">'
                        '<script>alert(1)</script></svg>', encoding="utf-8")
        assert not a.run_command("import_card_design", template_id=plantilla,
                                 file_path=str(malo)).success
        otro = tmp_path / "plantilla.pdf"
        otro.write_bytes(b"%PDF-1.4")
        assert not a.run_command("import_card_design", template_id=plantilla,
                                 file_path=str(otro)).success
        assert a.records(R.CARD_TEMPLATE_VERSIONS).total == 1


class TestReplacementReason:
    def test_replacement_keeps_points_rotates_qr_and_audits_the_reason(self, conn, two_users):
        import json as _json

        from backend.application.loyalty_cards.queries.card_render_data_query import (
            LoyaltyCardRenderDataQuery,
        )
        from backend.domain.loyalty_cards.enums import CardReplacementReason

        a, b = two_users
        _programa, _plantilla, tarjeta = TestLoyaltyCards()._card_setup(conn, a, b)
        _ok(a.run_command("activate_card", card_id=tarjeta["id"]))
        qr_viejo = LoyaltyCardRenderDataQuery(conn).placeholders_for_card(tarjeta["id"])["card_token"]
        _ok(a.run_command("replace_card", card_id=tarjeta["id"],
                          reason=CardReplacementReason.STOLEN))
        assert not a.resolve_card(qr_viejo).eligible
        fila = conn.execute("SELECT valor_despues FROM audit_logs WHERE accion = ?",
                            ("LOYALTY_CARD_REPLACED",)).fetchone()
        assert _json.loads(fila["valor_despues"])["reason"] == "STOLEN"
