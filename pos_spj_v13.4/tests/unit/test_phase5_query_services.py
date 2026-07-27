from backend.application.queries import (
    BranchQueryService,
    BusinessIntelligenceQueryService,
    CashRegisterQueryService,
    CustomerQueryService,
    ProductQueryService,
    QueryFilters,
    SearchResult,
    TableRow,
    KpiMetric,
)


class FakeQueryDataSource:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []

    def search(self, scope: str, query: str, filters: QueryFilters | None = None) -> list[SearchResult]:
        self.calls.append(("search", scope, filters))
        return [SearchResult(id=f"{scope}-1", label=f"{scope}:{query}")]

    def list_rows(self, scope: str, filters: QueryFilters | None = None) -> list[TableRow]:
        self.calls.append(("list_rows", scope, filters))
        return [TableRow(id=f"{scope}-row", values={"scope": scope})]

    def metrics(self, scope: str, filters: QueryFilters | None = None) -> list[KpiMetric]:
        self.calls.append(("metrics", scope, filters))
        return [KpiMetric(key=f"{scope}.total", label="Total", value=0)]


def test_entity_query_service_delegates_search_table_and_kpis_to_data_source() -> None:
    data_source = FakeQueryDataSource()
    service = ProductQueryService(data_source)

    assert service.search_products("  res  ") == [SearchResult(id="products-1", label="products:res")]
    assert service.list_for_table() == [TableRow(id="products-row", values={"scope": "products"})]
    assert service.get_kpis() == [KpiMetric(key="products.total", label="Total", value=0)]
    assert data_source.calls == [
        ("search", "products", None),
        ("list_rows", "products", None),
        ("metrics", "products", None),
    ]


def test_query_services_expose_expected_scopes_for_ui_read_models() -> None:
    expected_scopes = {
        CustomerQueryService: "customers",
        ProductQueryService: "products",
        BranchQueryService: "branches",
        CashRegisterQueryService: "cash_register",
        BusinessIntelligenceQueryService: "business_intelligence",
    }

    assert {service_class: service_class().scope for service_class in expected_scopes} == expected_scopes


def test_empty_query_service_is_safe_for_unwired_adapters() -> None:
    service = CustomerQueryService()

    assert service.search_customers("cliente") == []
    assert service.list_for_table() == []
    assert service.get_kpis() == []
