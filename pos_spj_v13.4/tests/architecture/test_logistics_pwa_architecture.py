from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PWA = ROOT / "frontend" / "web" / "logistics"


def test_mobile_origin_loading_is_an_installable_offline_shell():
    required = {
        "index.html", "manifest.webmanifest", "sw.js", "app.js", "api.js",
        "store.js", "sync.js", "uuidv7.js", "styles.css",
    }
    assert required <= {path.name for path in PWA.iterdir()}
    page = (PWA / "index.html").read_text(encoding="utf-8")
    assert 'rel="manifest"' in page
    assert "Carga en origen" in page
    assert 'capture="environment"' in page


def test_sync_contract_is_idempotent_versioned_and_not_last_write_wins():
    api = (PWA / "api.js").read_text(encoding="utf-8")
    sync = (PWA / "sync.js").read_text(encoding="utf-8")
    worker = (PWA / "sw.js").read_text(encoding="utf-8")
    assert '"Idempotency-Key"' in api
    assert '"If-Match"' in api
    assert '"CONFLICT"' in sync and "Never last-write-wins" in sync
    assert 'url.pathname.startsWith("/api/")' in worker


def test_mobile_token_is_not_persisted_in_durable_browser_storage():
    app = (PWA / "app.js").read_text(encoding="utf-8")
    assert 'sessionStorage.getItem("spj-mobile-token")' in app
    assert 'localStorage.getItem("spj-mobile-token")' not in app


<<<<<<< HEAD
def test_offline_commands_carry_identity_and_conflicts_are_user_resolvable():
    store = (PWA / "store.js").read_text(encoding="utf-8")
    sync = (PWA / "sync.js").read_text(encoding="utf-8")
    page = (PWA / "index.html").read_text(encoding="utf-8")
    for field in ("clientOperationId", "deviceId", "userId", "createdAt", "payloadVersion"):
        assert field in store
    assert "retryConflict" in sync and "getAggregate" in sync
    assert 'id="syncIssues"' in page


def test_photo_evidence_is_linked_by_registered_migration():
    migration = ROOT / "migrations/standalone/173_logistics_shipment_photos.py"
    assert migration.exists() and "logistics_shipment_photos" in migration.read_text()
    engine = (ROOT / "migrations/engine.py").read_text()
    assert '"173",  "migrations.standalone.173_logistics_shipment_photos"' in engine


=======
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2
def test_mobile_controller_contains_no_sql_or_repository_imports():
    router = (ROOT / "backend" / "api" / "routers" / "mobile_logistics.py").read_text(
        encoding="utf-8")
    assert "SELECT " not in router.upper()
    assert "repositories" not in router
