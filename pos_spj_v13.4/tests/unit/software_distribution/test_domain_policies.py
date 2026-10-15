"""Domain rules of software distribution: versions, manifests, eligibility,
rollout, deferral, maintenance window, install profiles, update job."""
from __future__ import annotations

from datetime import datetime

import pytest

from backend.domain.software_distribution.eligibility import (
    EligibilityOutcome,
    EligibilityReason,
    StationIdentity,
    UpdateEligibilityPolicy,
    rollout_bucket,
)
from backend.domain.software_distribution.install_profile import (
    ALL_CAPABILITIES,
    CORE_CAPABILITIES,
    EnabledCapabilities,
    InstallProfile,
    UnknownCapabilityError,
)
from backend.domain.software_distribution.operations import (
    ActiveOperationsSnapshot,
    InvalidMaintenanceWindowError,
    MaintenanceWindow,
    UpdateDeferralPolicy,
)
from backend.domain.software_distribution.release_manifest import (
    ManifestValidationError,
    ReleaseChannel,
    ReleaseManifest,
    TargetPlatform,
)
from backend.domain.software_distribution.semantic_version import (
    InvalidVersionError,
    SemanticVersion,
)
from backend.domain.software_distribution.update_job import (
    IllegalUpdateTransitionError,
    UpdateJob,
    UpdateJobState,
)

V = SemanticVersion.parse
HASH = "a" * 64


def payload(**overrides):
    data = {
        "format": "spj-release/1",
        "product": "spj-erp-pos",
        "version": "13.5.0",
        "channel": "stable",
        "published_at": "2026-10-14T00:00:00Z",
        "platform": {"os": "windows", "arch": "x64"},
        "minimum_installed_version": "13.4.0",
        "database_schema": {"requires_at_least": 300, "migrates_to": 340},
        "artifact": {
            "kind": "inno-setup", "file_name": "SPJ-Setup-13.5.0-x64.exe",
            "url": "https://updates.example.test/stable/SPJ-Setup-13.5.0-x64.exe",
            "size": 1000, "sha256": HASH,
        },
        "release_notes": "Notas",
        "mandatory": False,
        "mandatory_deadline": None,
        "rollout": {"percent": 100, "branch_ids": [], "workstation_ids": []},
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            data[key] = {**data[key], **value}
        else:
            data[key] = value
    return data


def station(**overrides):
    values = dict(
        installed_version=V("13.4.0"), channel=ReleaseChannel.STABLE,
        platform=TargetPlatform("windows", "x64"), database_schema_version=337,
        workstation_id="ws-1", branch_id="br-1",
    )
    values.update(overrides)
    return StationIdentity(**values)


POLICY = UpdateEligibilityPolicy(allowed_hosts=frozenset({"updates.example.test"}))


# ── semantic versions ──────────────────────────────────────────────────────
@pytest.mark.parametrize("lower, higher", [
    ("13.4.0-rc1", "13.4.0"),           # the old comparator ranked this ABOVE 13.4.0
    ("13.4.0-alpha", "13.4.0-alpha.1"),
    ("13.4.0-alpha.1", "13.4.0-alpha.beta"),
    ("13.4.0-alpha.beta", "13.4.0-beta"),
    ("13.4.0-beta.2", "13.4.0-beta.11"),
    ("13.4.0-beta.11", "13.4.0-rc.1"),
    ("13.4.0", "13.4.1"),
    ("13.9.0", "13.10.0"),
    ("1.99.99", "2.0.0"),
])
def test_semver_precedence(lower, higher):
    assert V(lower) < V(higher)
    assert V(higher) > V(lower)


def test_build_metadata_is_ignored_for_precedence():
    assert V("13.4.0+build.7") == V("13.4.0+other")
    assert hash(V("13.4.0+a")) == hash(V("13.4.0"))


@pytest.mark.parametrize("text", ["13.4", "13.4.0.1", "01.2.3", "13.4.0-", "13.4.0-01", "abc", ""])
def test_invalid_versions_are_rejected(text):
    with pytest.raises(InvalidVersionError):
        V(text)


def test_windows_file_version_drops_prerelease():
    assert V("13.5.0-rc.2").windows_file_version() == "13.5.0.0"
    assert str(V("v13.5.0-rc.2+b9")) == "13.5.0-rc.2+b9"


# ── manifest validation ────────────────────────────────────────────────────
def test_manifest_round_trip():
    manifest = ReleaseManifest.from_payload(payload())
    assert ReleaseManifest.from_payload(manifest.to_payload()) == manifest


@pytest.mark.parametrize("overrides", [
    {"format": "other/1"},
    {"artifact": {"url": "http://updates.example.test/stable/SPJ-Setup-13.5.0-x64.exe"}},
    {"artifact": {"url": "https://user:pw@updates.example.test/stable/SPJ-Setup-13.5.0-x64.exe"}},
    {"artifact": {"sha256": "ABC"}},
    {"artifact": {"size": 0}},
    {"artifact": {"size": True}},
    {"artifact": {"file_name": "..\\evil.exe"}},
    {"artifact": {"file_name": "SPJ-Setup.zip",
                  "url": "https://updates.example.test/SPJ-Setup.zip"}},
    {"artifact": {"file_name": "other.exe"}},  # name differs from the URL
    {"platform": {"arch": "mips"}},
    {"channel": "nightly"},
    {"database_schema": {"requires_at_least": 400, "migrates_to": 340}},
    {"published_at": "2026-10-14T00:00:00"},  # no timezone
    {"rollout": {"percent": 101}},
    {"version": "13.5"},
])
def test_malformed_manifest_is_rejected(overrides):
    with pytest.raises(ManifestValidationError):
        ReleaseManifest.from_payload(payload(**overrides))


def test_missing_field_is_rejected():
    data = payload()
    del data["artifact"]
    with pytest.raises(ManifestValidationError):
        ReleaseManifest.from_payload(data)


# ── eligibility ────────────────────────────────────────────────────────────
def decide(station_overrides=None, **manifest_overrides):
    manifest = ReleaseManifest.from_payload(payload(**manifest_overrides))
    return POLICY.evaluate(station(**(station_overrides or {})), manifest)


def test_newer_release_is_offered():
    decision = decide()
    assert decision.outcome is EligibilityOutcome.OFFERED


@pytest.mark.parametrize("station_overrides, manifest_overrides, reason", [
    ({"installed_version": V("13.6.0")}, {}, EligibilityReason.DOWNGRADE_REJECTED),
    ({}, {"channel": "pilot"}, EligibilityReason.CHANNEL_MISMATCH),
    ({}, {"platform": {"arch": "x86"}}, EligibilityReason.PLATFORM_MISMATCH),
    ({}, {"product": "otro"}, EligibilityReason.PRODUCT_MISMATCH),
    ({"installed_version": V("13.3.0")}, {}, EligibilityReason.INSTALLED_TOO_OLD),
    ({"database_schema_version": 250}, {}, EligibilityReason.SCHEMA_TOO_OLD),
    ({"database_schema_version": 350}, {}, EligibilityReason.SCHEMA_DOWNGRADE),
    ({}, {"artifact": {"url": "https://evil.example/SPJ-Setup-13.5.0-x64.exe"}},
     EligibilityReason.HOST_NOT_ALLOWED),
])
def test_unacceptable_release_is_rejected(station_overrides, manifest_overrides, reason):
    decision = decide(station_overrides, **manifest_overrides)
    assert decision.outcome is EligibilityOutcome.REJECTED
    assert decision.reason is reason


def test_prerelease_of_installed_final_is_a_downgrade():
    decision = decide({"installed_version": V("13.5.0")}, version="13.5.0-rc.1")
    assert decision.reason is EligibilityReason.DOWNGRADE_REJECTED


def test_same_version_is_not_offered_but_not_an_error():
    decision = decide({"installed_version": V("13.5.0")})
    assert decision.outcome is EligibilityOutcome.NOT_OFFERED
    assert decision.reason is EligibilityReason.UP_TO_DATE


def test_rollout_percent_zero_holds_every_station_except_named_ones():
    held = decide(rollout={"percent": 0})
    assert held.reason is EligibilityReason.NOT_IN_ROLLOUT
    named = decide(rollout={"percent": 0, "workstation_ids": ["ws-1"]})
    assert named.offered


def test_rollout_branch_allowlist():
    assert decide(rollout={"branch_ids": ["br-2"]}).reason is EligibilityReason.NOT_IN_ROLLOUT
    assert decide(rollout={"branch_ids": ["br-1"]}).offered


def test_rollout_bucket_is_stable_and_spread():
    version = V("13.5.0")
    assert rollout_bucket(version, "ws-1") == rollout_bucket(version, "ws-1")
    buckets = {rollout_bucket(version, f"ws-{i}") for i in range(300)}
    assert len(buckets) > 80


def test_offline_package_skips_host_and_rollout_but_not_safety_rules():
    manifest = ReleaseManifest.from_payload(payload(
        rollout={"percent": 0},
        artifact={"url": "https://not-allowed.example/SPJ-Setup-13.5.0-x64.exe"}))
    assert POLICY.evaluate(station(), manifest, offline=True).offered
    downgrade = POLICY.evaluate(station(installed_version=V("14.0.0")), manifest, offline=True)
    assert downgrade.rejected


# ── deferral and maintenance window ───────────────────────────────────────
def test_active_operations_block_the_update():
    policy = UpdateDeferralPolicy()
    assert not policy.decide(ActiveOperationsSnapshot()).blocked
    decision = policy.decide(ActiveOperationsSnapshot(
        sales_in_capture=1, payments_pending=2, cash_cuts_in_progress=1,
        pending_outbox_messages=5))
    assert decision.blocked and len(decision.reasons) == 3
    assert decision.warnings  # outbox only warns
    assert not policy.decide(ActiveOperationsSnapshot(pending_outbox_messages=9)).blocked


@pytest.mark.parametrize("window, moment, inside", [
    ("22:00-06:00", datetime(2026, 1, 1, 23, 30), True),
    ("22:00-06:00", datetime(2026, 1, 1, 5, 59), True),
    ("22:00-06:00", datetime(2026, 1, 1, 6, 0), False),
    ("22:00-06:00", datetime(2026, 1, 1, 12, 0), False),
    ("01:00-03:00", datetime(2026, 1, 1, 2, 0), True),
    ("01:00-03:00", datetime(2026, 1, 1, 3, 0), False),
])
def test_maintenance_window(window, moment, inside):
    assert MaintenanceWindow.parse(window).contains(moment) is inside


@pytest.mark.parametrize("text", ["", "25:00-01:00", "10:00-10:00", "10-12"])
def test_invalid_maintenance_window(text):
    with pytest.raises(InvalidMaintenanceWindowError):
        MaintenanceWindow.parse(text)


# ── install profiles ───────────────────────────────────────────────────────
def test_profiles_always_include_core_and_close_dependencies():
    essential = EnabledCapabilities.resolve(InstallProfile.POS_ESSENTIAL)
    assert CORE_CAPABILITIES <= essential.enabled
    assert "finance" not in essential.enabled
    full = EnabledCapabilities.resolve(InstallProfile.ERP_FULL)
    assert full.enabled == ALL_CAPABILITIES and not full.disabled
    custom = EnabledCapabilities.resolve(InstallProfile.CUSTOM, ["hr"])
    assert {"hr", "finance"} <= custom.enabled  # hr requires finance
    assert CORE_CAPABILITIES <= custom.enabled


def test_unknown_capability_is_rejected():
    with pytest.raises(UnknownCapabilityError):
        EnabledCapabilities.resolve(InstallProfile.CUSTOM, ["nope"])


def test_disabled_capability_blocks_its_permission_families_only():
    essential = EnabledCapabilities.resolve(InstallProfile.POS_ESSENTIAL)
    assert essential.permission_blocked("RRHH.NOMINA.GENERAR")
    assert essential.permission_blocked("LOSSES_VIEW")
    assert not essential.permission_blocked("POS.VER")
    assert not essential.permission_blocked("GROWTH_ENGINE.PUNTOS.CANJEAR")
    assert not essential.is_enabled("hr") and essential.is_enabled("sales_pos")
    assert essential.is_enabled("not_in_catalog")


# ── update job state machine ───────────────────────────────────────────────
def _job():
    return UpdateJob(
        job_id="j", operation_id="o", from_version="13.4.0", to_version="13.5.0",
        channel="stable", installer_path="x.exe", installer_sha256=HASH, installer_size=1,
        database_path="db", workstation_id="ws", branch_id="br", requested_by="u")


def test_update_job_legal_path_and_serialization():
    job = _job()
    for state in (UpdateJobState.WAITING_FOR_APP_EXIT, UpdateJobState.BACKING_UP,
                  UpdateJobState.INSTALLING, UpdateJobState.VERIFYING,
                  UpdateJobState.COMPLETED):
        job = job.transition(state, detail=state.value)
    assert job.state.is_terminal and len(job.history) == 5
    assert UpdateJob.from_dict(job.to_dict()) == job


def test_update_job_rejects_illegal_transition():
    with pytest.raises(IllegalUpdateTransitionError):
        _job().transition(UpdateJobState.INSTALLING)
    with pytest.raises(IllegalUpdateTransitionError):
        _job().transition(UpdateJobState.CANCELLED).transition(UpdateJobState.STAGED)
