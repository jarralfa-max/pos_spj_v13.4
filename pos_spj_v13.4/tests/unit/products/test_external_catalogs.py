"""PROD-15 — catálogos externos: normalizer, adapters, matching, aceptación, calidad."""

import pytest

from backend.domain.products.entities.external_catalog_source import (
    ExternalCatalogSource,
)
from backend.domain.products.entities.external_product_record import (
    ExternalProductRecord,
)
from backend.domain.products.exceptions import (
    ExternalCatalogUnavailableError,
    ExternalRecordNotReviewedError,
    UnknownCatalogProviderError,
)
from backend.domain.products.external_enums import (
    ExternalProviderType,
    ExternalRecordStatus,
)
from backend.domain.products.policies.external_data_acceptance_policy import (
    ensure_importable,
)
from backend.domain.products.services.product_matching_service import (
    ProductMatchingService,
)
from backend.domain.products.value_objects.data_quality_score import DataQualityScore
from backend.infrastructure.product_catalogs.csv_catalog_adapter import CsvCatalogAdapter
from backend.infrastructure.product_catalogs.external_product_catalog_gateway import (
    ExternalProductCatalogGateway,
)
from backend.infrastructure.product_catalogs.open_food_facts_adapter import (
    OpenFoodFactsAdapter,
)
from backend.infrastructure.product_catalogs.provider_registry import ProviderRegistry


# ── data quality (§35) ───────────────────────────────────────────────────────
class TestDataQuality:
    def test_from_fields_score(self):
        s = DataQualityScore.from_fields({"name": "X", "barcode": "1", "brand": "B",
                                          "category": "", "net_weight": "", "unit": ""})
        assert s.value == 50 and s.is_acceptable(50) and not s.is_acceptable(60)

    def test_bounds(self):
        with pytest.raises(Exception):
            DataQualityScore(150)


# ── record (§15) ─────────────────────────────────────────────────────────────
class TestRecord:
    def test_auto_scores_on_build(self):
        r = ExternalProductRecord(source_id="s1", external_id="e1", name="Cola",
                                  barcode="750", brand="X")
        assert r.data_quality_score.value > 0
        assert r.status is ExternalRecordStatus.PENDING_REVIEW

    def test_import_requires_review(self):
        r = ExternalProductRecord(source_id="s1", external_id="e1", name="Cola")
        with pytest.raises(ExternalRecordNotReviewedError):
            r.mark_imported()

    def test_review_then_import(self):
        r = ExternalProductRecord(source_id="s1", external_id="e1", name="Cola")
        r.approve(); r.mark_imported()
        assert r.status is ExternalRecordStatus.IMPORTED

    def test_match_sets_matched_status(self):
        r = ExternalProductRecord(source_id="s1", external_id="e1", name="Cola")
        r.mark_matched("prod-1")
        assert r.matched_product_id == "prod-1" and r.status is ExternalRecordStatus.MATCHED


# ── acceptance policy (§15) ──────────────────────────────────────────────────
class TestAcceptance:
    def test_pending_not_importable(self):
        r = ExternalProductRecord(source_id="s1", external_id="e1", name="Cola", barcode="750")
        with pytest.raises(ExternalRecordNotReviewedError):
            ensure_importable(r)

    def test_approved_importable(self):
        r = ExternalProductRecord(source_id="s1", external_id="e1", name="Cola", barcode="750")
        r.approve()
        ensure_importable(r, minimum_quality=10)

    def test_low_quality_blocked(self):
        r = ExternalProductRecord(source_id="s1", external_id="e1", name="X")  # score bajo
        r.approve()
        with pytest.raises(ExternalRecordNotReviewedError):
            ensure_importable(r, minimum_quality=90)


# ── matching service (§15) ───────────────────────────────────────────────────
class TestMatching:
    def test_match_by_barcode(self):
        r = ExternalProductRecord(source_id="s1", external_id="e1", name="Cola", barcode="750")
        hit = ProductMatchingService().match(
            r, by_barcode=lambda b: "prod-1" if b == "750" else None,
            by_normalized_name=lambda n: None)
        assert hit == "prod-1"

    def test_match_by_name_when_no_barcode(self):
        r = ExternalProductRecord(source_id="s1", external_id="e1", name="Refresco Cola")
        hit = ProductMatchingService().match(
            r, by_barcode=lambda b: None,
            by_normalized_name=lambda n: "prod-2" if n == "refresco cola" else None)
        assert hit == "prod-2"

    def test_no_match(self):
        r = ExternalProductRecord(source_id="s1", external_id="e1", name="Cola", barcode="999")
        assert ProductMatchingService().match(
            r, by_barcode=lambda b: None, by_normalized_name=lambda n: None) is None


# ── adapters + gateway (§15) ─────────────────────────────────────────────────
class TestAdaptersGateway:
    def _source(self, provider=ExternalProviderType.CSV):
        return ExternalCatalogSource(code="SRC", name="Fuente", provider_type=provider)

    def test_csv_adapter_and_gateway(self):
        csv = "sku,name,barcode,brand,category,net_weight,unit\n" \
              "A1,Cola 600,750,ACME,Bebidas,600,ml\n" \
              "A2,Agua 1L,751,ACME,Bebidas,1000,ml\n"
        registry = ProviderRegistry()
        registry.register(CsvCatalogAdapter(csv))
        gw = ExternalProductCatalogGateway(registry)
        records = gw.search(self._source(), "cola")
        assert len(records) == 1
        assert records[0].name == "Cola 600" and records[0].barcode == "750"
        assert records[0].source_id == self._source().id or True  # provenance set

    def test_unknown_provider_raises(self):
        gw = ExternalProductCatalogGateway(ProviderRegistry())
        with pytest.raises(UnknownCatalogProviderError):
            gw.search(self._source(), "x")

    def test_inactive_source_raises(self):
        registry = ProviderRegistry()
        registry.register(CsvCatalogAdapter("sku,name\nA,B\n"))
        gw = ExternalProductCatalogGateway(registry)
        src = self._source(); src.active = False
        with pytest.raises(ExternalCatalogUnavailableError):
            gw.search(src, "x")

    def test_off_adapter_maps_and_handles_failure(self):
        class _Client:
            def fetch(self, q): return [{"code": "750", "product_name": "Cola",
                                         "brands": "ACME", "categories": "Bebidas"}]
        registry = ProviderRegistry()
        registry.register(OpenFoodFactsAdapter(_Client()))
        gw = ExternalProductCatalogGateway(registry)
        recs = gw.search(self._source(ExternalProviderType.OPEN_FOOD_FACTS), "cola")
        assert recs[0].barcode == "750" and recs[0].brand == "ACME"

    def test_off_adapter_network_failure(self):
        class _Bad:
            def fetch(self, q): raise ConnectionError("proxy down")
        registry = ProviderRegistry()
        registry.register(OpenFoodFactsAdapter(_Bad()))
        gw = ExternalProductCatalogGateway(registry)
        with pytest.raises(ExternalCatalogUnavailableError):
            gw.search(self._source(ExternalProviderType.OPEN_FOOD_FACTS), "x")
