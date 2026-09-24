"""Record validated brand infrastructure separately from absent official art."""
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
out = root / "docs/refactor/evidence/brand_asset_provider_phase_6"
out.mkdir(parents=True, exist_ok=True)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
cases, results = {}, []
for name in ("brand-phase6-regression", "qss-global-visuals"):
    path = root / ".test_tmp" / f"{name}.xml"
    counts = dict(passed=0, failed=0, errors=0, skipped=0)
    for case in ET.parse(path).iter("testcase"):
        status = "failed" if case.find("failure") is not None else "errors" if case.find("error") is not None else "skipped" if case.find("skipped") is not None else "passed"
        cases[(case.get("classname"), case.get("name"))] = status
        counts[status] += 1
    results.append(dict(name=name, **counts))
    shutil.copy2(path, out / path.name)
    raw = path.with_suffix(".log").read_bytes()
    text = raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
    (out / path.with_suffix(".log").name).write_text(text, encoding="utf-8")
asset_names = ("logo_horizontal_light", "logo_horizontal_dark", "isotype_light", "isotype_dark", "app_icon", "window_icon")
directory = root / "assets/branding"
payload = {
    "phase": "6. BrandAssetProvider", "date": "2026-09-21",
    "status": "Official artwork supplied and infrastructure validated; operational visual acceptance pending",
    "results": results,
    "distinct_totals": {status: list(cases.values()).count(status) for status in ("passed", "failed", "errors", "skipped")},
    "official_assets": {name: [p.relative_to(root).as_posix() for p in directory.glob(name + ".*") if p.suffix in (".svg", ".png", ".ico")] for name in asset_names},
    "original_files_sha256": {p.name: sha(p) for p in sorted(directory.iterdir()) if p.suffix in (".svg", ".png", ".ico")},
    "shared_captures": [{"file": "../qss_global_phase_4/" + p.name, "sha256": sha(p)}
                        for p in sorted((root / "docs/refactor/evidence/qss_global_phase_4").glob("*.png"))
                        if not p.name.startswith("qss-states-")],
    "fixture_artwork": "Temporary synthetic geometry only; no fixture is installed as JUANIS artwork",
    "packaging": "AppPaths resource resolution simulated; no executable build performed",
    "source_sha256": {name: sha(root / name) for name in (
        "frontend/desktop/components/branding.py", "backend/shared/app_paths.py",
        "frontend/desktop/app.py", "frontend/desktop/auth/login_window.py",
        "frontend/desktop/shell/sidebar/global_sidebar.py",
        "frontend/desktop/components/standard_window.py", "frontend/desktop/components/dialogs.py",
        "tests/ui/test_brand_asset_provider.py", "tests/ui/test_brand_official_assets.py",
        "tests/unit/test_app_paths_resources.py")},
}
original_hashes = json.loads((root / ".test_tmp/brand-official-hash-review.json").read_text(encoding="utf-8"))
assert all(item["sha256"] == payload["original_files_sha256"][name] for name, item in original_hashes.items()), "Reassess modified artwork before reporting"
payload["originals_unchanged_since_audit"] = True
for name in ("brand-svg2-before", "brand-official-before", "brand-svg-local-before"):
    path = root / ".test_tmp" / f"{name}.xml"
    shutil.copy2(path, out / path.name)
shutil.copy2(root / ".test_tmp/brand-official-assets.json", out / "original_assets_inspection_before_svg_fix.json")
(out / "validation.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"totals": payload["distinct_totals"], "official_assets": payload["official_assets"]}))
