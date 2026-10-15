"""In-app use cases of «Configuración → Acerca de y actualizaciones».

The desktop checks, downloads, verifies and SCHEDULES; it never installs. The
install transaction runs in the external updater (`update_transaction.py`)
after the desktop has closed.

Authorization: `CONFIGURACION.actualizacion.ver` (status, history, check),
`.administrar` (download, offline import, install, cancel) and `.canal`
(channel and maintenance window) through `ConfiguracionAuthorizationPolicy`
— the same `require()` every Configuración use case uses. Every action is
recorded in `software_update_events`; channel/window changes also in
`configuracion_audit_log`.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
import json
import logging
import os
from pathlib import Path
from typing import Callable, Protocol

from backend.application.configuracion.permissions import ConfiguracionPermissions as P
from backend.application.software_updates.installation import SoftwareInstallation
from backend.domain.software_distribution.eligibility import (
    EligibilityDecision,
    EligibilityOutcome,
    StationIdentity,
    UpdateEligibilityPolicy,
)
from backend.domain.software_distribution.operations import (
    ActiveOperationsSnapshot,
    DeferralDecision,
    MaintenanceWindow,
    UpdateDeferralPolicy,
)
from backend.domain.software_distribution.release_manifest import (
    ManifestValidationError,
    ReleaseChannel,
    ReleaseManifest,
)
from backend.domain.software_distribution.semantic_version import SemanticVersion
from backend.domain.software_distribution.update_job import UpdateJob, UpdateJobState
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.software_updates")

HISTORY_LIMIT = 30


class SoftwareUpdateError(RuntimeError):
    """Expected, user-facing failure (message in Spanish)."""


class UpdateDeferredError(SoftwareUpdateError):
    def __init__(self, decision: DeferralDecision) -> None:
        super().__init__("No se puede actualizar ahora: " + " ".join(decision.reasons))
        self.decision = decision


# ── ports ──────────────────────────────────────────────────────────────────
class Authorization(Protocol):
    def require(self, user_id: str, permission_code: str) -> None: ...
    def has_permission(self, user_id: str, permission_code: str) -> bool: ...


class StationRepository(Protocol):
    def get(self, workstation_key: str): ...
    def record_start(self, **kwargs) -> None: ...
    def set_channel(self, workstation_key: str, channel: str, *, user_id: str) -> None: ...
    def set_maintenance_window(self, workstation_key: str, window, *, user_id: str) -> None: ...
    def set_last_check(self, workstation_key: str, result: str) -> None: ...
    def record_event(self, **kwargs) -> str: ...
    def has_event(self, job_id: str, event_type: str) -> bool: ...
    def list_events(self, workstation_key: str, limit: int) -> list[dict]: ...


class ManifestReader(Protocol):
    def read(self, raw: bytes): ...  # -> AuthenticatedManifest


class Downloader(Protocol):
    def fetch_manifest(self, url: str) -> bytes: ...
    def download(self, artifact, *, progress=None, cancelled=None) -> Path: ...
    def target_path(self, artifact) -> Path: ...


class JobStorePort(Protocol):
    def load(self) -> UpdateJob | None: ...
    def save(self, job: UpdateJob) -> UpdateJob: ...
    def archive(self, job: UpdateJob) -> Path: ...


class AuditLog(Protocol):
    def record(self, **kwargs) -> None: ...


@dataclass(frozen=True)
class StationContext:
    workstation_key: str
    branch_id: str
    user_id: str


@dataclass
class SoftwareUpdateDependencies:
    """Everything the use cases share; built once by the composition."""

    connection: object
    installation: SoftwareInstallation
    station: StationContext
    authorization: Authorization
    repository: StationRepository
    reader: ManifestReader
    downloader: Downloader
    job_store: JobStorePort
    probe: object  # .snapshot() -> ActiveOperationsSnapshot
    audit: AuditLog | None = None
    verify_package: Callable[[Path, object], None] | None = None
    schema_version: Callable[[], int | None] = lambda: None
    signing_configured: bool = True
    clock: Callable[[], datetime] = field(default=lambda: datetime.now())

    @property
    def manifests_dir(self) -> Path:
        return self.installation.paths.manifests_dir

    def channel(self) -> ReleaseChannel:
        settings = self.repository.get(self.station.workstation_key)
        value = settings.channel if settings else self.installation.default_channel
        return ReleaseChannel.parse(value)

    def station_identity(self) -> StationIdentity:
        return StationIdentity(
            installed_version=self.installation.version, channel=self.channel(),
            platform=self.installation.platform,
            database_schema_version=self.schema_version() or 0,
            workstation_id=self.station.workstation_key, branch_id=self.station.branch_id)

    def policy(self) -> UpdateEligibilityPolicy:
        return UpdateEligibilityPolicy(allowed_hosts=self.installation.allowed_hosts)

    def event(self, event_type: str, **kwargs) -> None:
        self.repository.record_event(
            workstation_key=self.station.workstation_key, branch_id=self.station.branch_id,
            actor_user_id=kwargs.pop("actor_user_id", self.station.user_id),
            event_type=event_type, **kwargs)

    def commit(self) -> None:
        commit = getattr(self.connection, "commit", None)
        if commit:
            commit()


# ── status ─────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SoftwareStatus:
    app_version: str
    build_label: str
    signed_build: bool
    channel: ReleaseChannel
    maintenance_window: str
    install_profile: str
    enabled_capabilities: tuple[str, ...]
    layout: str
    data_dir: str
    database_path: str
    schema_version: int | None
    feed_configured: bool
    signing_configured: bool
    whatsapp_mode: str
    last_check_at: str
    last_check_result: str
    pending_job: UpdateJob | None
    available: "AvailableUpdate | None"
    history: tuple[dict, ...]
    can_administer: bool
    can_change_channel: bool


@dataclass(frozen=True)
class AvailableUpdate:
    manifest: ReleaseManifest
    downloaded: bool
    package_path: str


class GetSoftwareStatusQuery:
    def __init__(self, deps: SoftwareUpdateDependencies) -> None:
        self._d = deps

    def execute(self) -> SoftwareStatus:
        d = self._d
        d.authorization.require(d.station.user_id, P.ACTUALIZACIONES_VIEW)
        settings = d.repository.get(d.station.workstation_key)
        installation = d.installation
        available = _load_offered(d)
        return SoftwareStatus(
            app_version=str(installation.version),
            build_label=installation.build.label,
            signed_build=installation.build.signed,
            channel=d.channel(),
            maintenance_window=(settings.maintenance_window if settings else ""),
            install_profile=installation.capabilities.profile.label,
            enabled_capabilities=tuple(sorted(installation.capabilities.enabled)),
            layout=installation.paths.effective_layout,
            data_dir=str(installation.paths.user_data_dir),
            database_path=str(installation.paths.database_path),
            schema_version=d.schema_version(),
            feed_configured=bool(installation.feed_url_template),
            signing_configured=d.signing_configured,
            whatsapp_mode=installation.whatsapp_mode,
            last_check_at=(settings.last_check_at if settings else ""),
            last_check_result=(settings.last_check_result if settings else ""),
            pending_job=_pending_job(d),
            available=available,
            history=tuple(d.repository.list_events(d.station.workstation_key, HISTORY_LIMIT)),
            can_administer=d.authorization.has_permission(
                d.station.user_id, P.ACTUALIZACIONES_ADMINISTRAR),
            can_change_channel=d.authorization.has_permission(
                d.station.user_id, P.ACTUALIZACIONES_CANAL),
        )


def _pending_job(d: SoftwareUpdateDependencies) -> UpdateJob | None:
    try:
        job = d.job_store.load()
    except (OSError, ValueError):
        return None
    return job if job is not None and not job.state.is_terminal else None


def _offered_path(d: SoftwareUpdateDependencies, channel: ReleaseChannel) -> Path:
    return d.manifests_dir / f"offered-{channel.value}.json"


def _load_offered(d: SoftwareUpdateDependencies) -> AvailableUpdate | None:
    """The last offered manifest, RE-VERIFIED (signature and eligibility):
    the file sits in a user-writable folder."""
    path = _offered_path(d, d.channel())
    if not path.exists():
        return None
    try:
        authenticated = d.reader.read(path.read_bytes())
    except Exception as exc:
        logger.warning("Manifiesto guardado descartado: %s", exc)
        path.unlink(missing_ok=True)
        return None
    manifest = authenticated.manifest
    offline = path.with_suffix(".offline").exists()
    decision = d.policy().evaluate(d.station_identity(), manifest, offline=offline)
    if not decision.offered:
        return None
    package = d.downloader.target_path(manifest.artifact)
    downloaded = False
    if package.exists() and d.verify_package is not None:
        try:
            d.verify_package(package, manifest.artifact)
            downloaded = True
        except Exception:
            downloaded = False
    return AvailableUpdate(manifest=manifest, downloaded=downloaded, package_path=str(package))


# ── check ──────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class UpdateCheckResult:
    decision: EligibilityDecision | None
    manifest: ReleaseManifest | None
    error: str = ""

    @property
    def message(self) -> str:
        return self.error or (self.decision.message if self.decision else "")


class CheckForUpdatesUseCase:
    def __init__(self, deps: SoftwareUpdateDependencies) -> None:
        self._d = deps

    def execute(self) -> UpdateCheckResult:
        d = self._d
        d.authorization.require(d.station.user_id, P.ACTUALIZACIONES_VIEW)
        channel = d.channel()
        if not d.installation.feed_url_template:
            return self._finish(UpdateCheckResult(None, None, error=(
                "Esta instalación no tiene servidor de actualizaciones configurado. "
                "Use «Importar paquete offline».")), channel)
        try:
            raw = d.downloader.fetch_manifest(d.installation.feed_url(channel.value))
            authenticated = d.reader.read(raw)
        except (ManifestValidationError, ValueError, RuntimeError, OSError) as exc:
            result = UpdateCheckResult(None, None, error=f"Manifiesto rechazado: {exc}")
            d.event("REJECTED", channel=channel.value, detail=result.error)
            return self._finish(result, channel)
        manifest = authenticated.manifest
        decision = d.policy().evaluate(d.station_identity(), manifest)
        event = {EligibilityOutcome.OFFERED: "OFFERED",
                 EligibilityOutcome.NOT_OFFERED: "NOT_OFFERED",
                 EligibilityOutcome.REJECTED: "REJECTED"}[decision.outcome]
        d.event(event, channel=channel.value, from_version=str(d.installation.version),
                to_version=str(manifest.version), detail=f"{decision.reason.value}: {decision.message}")
        path = _offered_path(d, channel)
        if decision.offered:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(authenticated.raw)
            path.with_suffix(".offline").unlink(missing_ok=True)
        else:
            path.unlink(missing_ok=True)
        return self._finish(UpdateCheckResult(decision, manifest), channel)

    def _finish(self, result: UpdateCheckResult, channel: ReleaseChannel) -> UpdateCheckResult:
        d = self._d
        d.repository.set_last_check(d.station.workstation_key, result.message)
        d.commit()
        return result


# ── download / offline import ──────────────────────────────────────────────
@dataclass(frozen=True)
class PreparedDownload:
    """The network part of a download, safe to run in a worker thread: it
    never touches the database (the desktop's connection is thread-bound)."""

    manifest: ReleaseManifest
    downloader: Downloader

    def run(self, *, progress=None, cancelled=None) -> Path:
        return self.downloader.download(self.manifest.artifact, progress=progress,
                                        cancelled=cancelled)


class DownloadUpdateUseCase:
    """`prepare()` and `record()` on the UI thread, `PreparedDownload.run()`
    wherever the caller wants (the page uses a worker thread)."""

    def __init__(self, deps: SoftwareUpdateDependencies) -> None:
        self._d = deps

    def prepare(self) -> PreparedDownload:
        d = self._d
        d.authorization.require(d.station.user_id, P.ACTUALIZACIONES_ADMINISTRAR)
        available = _load_offered(d)
        if available is None:
            raise SoftwareUpdateError("No hay una actualización disponible; busque primero.")
        return PreparedDownload(manifest=available.manifest, downloader=d.downloader)

    def record(self, prepared: PreparedDownload, *, error: BaseException | None) -> None:
        d = self._d
        manifest = prepared.manifest
        if error is not None:
            d.event("DOWNLOAD_FAILED", channel=manifest.channel.value,
                    to_version=str(manifest.version), detail=str(error))
        else:
            d.event("DOWNLOADED", channel=manifest.channel.value,
                    from_version=str(d.installation.version), to_version=str(manifest.version),
                    detail=f"{manifest.artifact.file_name} verificado (tamaño y SHA-256).")
        d.commit()

    def execute(self, *, progress=None, cancelled=None) -> Path:
        prepared = self.prepare()
        try:
            path = prepared.run(progress=progress, cancelled=cancelled)
        except Exception as exc:
            self.record(prepared, error=exc)
            raise SoftwareUpdateError(str(exc)) from exc
        self.record(prepared, error=None)
        return path


class ImportOfflineUpdateUseCase:
    """A USB/removable-media package: the signed `manifest.json` and the
    installer named in it, side by side. Same signature, hash and safety
    rules as an online update; only the download host and the staged
    rollout do not apply."""

    MANIFEST_NAME = "manifest.json"

    def __init__(self, deps: SoftwareUpdateDependencies,
                 copy_file: Callable[[Path, Path], None]) -> None:
        self._d = deps
        self._copy = copy_file

    def execute(self, manifest_file: Path) -> ReleaseManifest:
        d = self._d
        d.authorization.require(d.station.user_id, P.ACTUALIZACIONES_ADMINISTRAR)
        manifest_file = Path(manifest_file)
        if manifest_file.is_dir():
            manifest_file = manifest_file / self.MANIFEST_NAME
        try:
            raw = manifest_file.read_bytes()
            authenticated = d.reader.read(raw)
        except Exception as exc:
            d.event("REJECTED", detail=f"Paquete offline rechazado: {exc}")
            d.commit()
            raise SoftwareUpdateError(f"Paquete offline rechazado: {exc}") from exc
        manifest = authenticated.manifest
        decision = d.policy().evaluate(d.station_identity(), manifest, offline=True)
        if not decision.offered:
            d.event("REJECTED", channel=manifest.channel.value,
                    to_version=str(manifest.version), detail=decision.message)
            d.commit()
            raise SoftwareUpdateError(decision.message)
        source = manifest_file.parent / manifest.artifact.file_name
        target = d.downloader.target_path(manifest.artifact)
        partial = target.with_name(target.name + ".part")
        try:
            d.verify_package(source, manifest.artifact)
            target.parent.mkdir(parents=True, exist_ok=True)
            self._copy(source, partial)
            d.verify_package(partial, manifest.artifact)  # what landed on disk
            os.replace(partial, target)
        except Exception as exc:
            partial.unlink(missing_ok=True)
            d.event("REJECTED", channel=manifest.channel.value,
                    to_version=str(manifest.version), detail=f"Paquete offline: {exc}")
            d.commit()
            raise SoftwareUpdateError(f"El instalador del paquete offline no es válido: {exc}") from exc
        offered = _offered_path(d, manifest.channel)
        offered.parent.mkdir(parents=True, exist_ok=True)
        offered.write_bytes(authenticated.raw)
        offered.with_suffix(".offline").write_text("offline", encoding="utf-8")
        d.event("OFFLINE_IMPORTED", channel=manifest.channel.value,
                from_version=str(d.installation.version), to_version=str(manifest.version),
                detail=f"Importado desde {manifest_file.parent}")
        d.commit()
        return manifest


# ── schedule / install ─────────────────────────────────────────────────────
class InstallTiming(str, Enum):
    NOW = "NOW"
    MAINTENANCE_WINDOW = "MAINTENANCE_WINDOW"


@dataclass(frozen=True)
class LaunchRequest:
    """Ask the desktop to close cleanly and hand over to the updater."""

    job: UpdateJob
    job_path: Path
    warnings: tuple[str, ...] = ()


class ScheduleUpdateInstallUseCase:
    def __init__(self, deps: SoftwareUpdateDependencies) -> None:
        self._d = deps

    def execute(self, timing: InstallTiming) -> LaunchRequest | UpdateJob:
        """NOW → a LaunchRequest (the desktop must close now).
        MAINTENANCE_WINDOW → the staged job; `RunScheduledUpdateIfDueUseCase`
        launches it inside the window when nothing is in progress."""
        d = self._d
        d.authorization.require(d.station.user_id, P.ACTUALIZACIONES_ADMINISTRAR)
        if _pending_job(d) is not None:
            raise SoftwareUpdateError("Ya hay una actualización programada o en curso.")
        available = _load_offered(d)
        if available is None or not available.downloaded:
            raise SoftwareUpdateError("Descargue (o importe) y verifique la actualización primero.")
        window = ""
        if timing is InstallTiming.MAINTENANCE_WINDOW:
            settings = d.repository.get(d.station.workstation_key)
            window = settings.maintenance_window if settings else ""
            if not window:
                raise SoftwareUpdateError("Defina primero la ventana de mantenimiento de la estación.")
        else:
            deferral = UpdateDeferralPolicy().decide(d.probe.snapshot())
            if deferral.blocked:
                d.event("DEFERRED", to_version=str(available.manifest.version),
                        detail=" ".join(deferral.reasons))
                d.commit()
                raise UpdateDeferredError(deferral)
        manifest = available.manifest
        job = UpdateJob(
            job_id=new_uuid(), operation_id=new_uuid(),
            from_version=str(d.installation.version), to_version=str(manifest.version),
            channel=manifest.channel.value, installer_path=available.package_path,
            installer_sha256=manifest.artifact.sha256, installer_size=manifest.artifact.size,
            database_path=str(d.installation.paths.database_path),
            workstation_id=d.station.workstation_key, branch_id=d.station.branch_id,
            requested_by=d.station.user_id, offline=_offered_path(
                d, manifest.channel).with_suffix(".offline").exists(),
            scheduled_window=window,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        d.job_store.save(job)
        d.event("SCHEDULED", operation_id=job.operation_id, job_id=job.job_id,
                channel=job.channel, from_version=job.from_version, to_version=job.to_version,
                detail=("Instalación inmediata." if not window
                        else f"Instalación en la ventana {window}."))
        d.commit()
        if window:
            return job
        return LaunchRequest(job=job, job_path=_job_path(d),
                             warnings=UpdateDeferralPolicy().decide(d.probe.snapshot()).warnings)


def _job_path(d: SoftwareUpdateDependencies) -> Path:
    return getattr(d.job_store, "path", d.installation.paths.update_job_path)


class RunScheduledUpdateIfDueUseCase:
    """Background tick (no user): a job a person scheduled for the
    maintenance window is launched only inside the window and only when no
    sale, payment or cash cut is in progress — otherwise it waits."""

    def __init__(self, deps: SoftwareUpdateDependencies) -> None:
        self._d = deps

    def execute(self) -> LaunchRequest | None:
        d = self._d
        job = _pending_job(d)
        if job is None or job.state is not UpdateJobState.STAGED or not job.scheduled_window:
            return None
        try:
            window = MaintenanceWindow.parse(job.scheduled_window)
        except ValueError:
            return None
        if not window.contains(d.clock()):
            return None
        deferral = UpdateDeferralPolicy().decide(d.probe.snapshot())
        if deferral.blocked:
            return None
        return LaunchRequest(job=job, job_path=_job_path(d), warnings=deferral.warnings)


class CancelScheduledUpdateUseCase:
    def __init__(self, deps: SoftwareUpdateDependencies) -> None:
        self._d = deps

    def execute(self) -> None:
        d = self._d
        d.authorization.require(d.station.user_id, P.ACTUALIZACIONES_ADMINISTRAR)
        job = _pending_job(d)
        if job is None or job.state is not UpdateJobState.STAGED:
            raise SoftwareUpdateError("No hay una actualización programada que cancelar.")
        job = job.transition(UpdateJobState.CANCELLED, "Cancelada por el usuario.")
        d.job_store.save(job)
        d.event("CANCELLED", operation_id=job.operation_id, job_id=job.job_id,
                to_version=job.to_version, detail=job.last_detail)
        d.job_store.archive(job)
        d.commit()


# ── channel and maintenance window ─────────────────────────────────────────
class ChangeUpdateChannelUseCase:
    def __init__(self, deps: SoftwareUpdateDependencies) -> None:
        self._d = deps

    def execute(self, channel: str) -> ReleaseChannel:
        d = self._d
        d.authorization.require(d.station.user_id, P.ACTUALIZACIONES_CANAL)
        new = ReleaseChannel.parse(channel)
        old = d.channel()
        if new is old:
            return new
        _ensure_station_row(d)
        d.repository.set_channel(d.station.workstation_key, new.value, user_id=d.station.user_id)
        # An offer from the other channel is no longer valid for this station.
        _offered_path(d, old).unlink(missing_ok=True)
        d.event("CHANNEL_CHANGED", channel=new.value, detail=f"{old.label} → {new.label}")
        if d.audit is not None:
            d.audit.record(entity_type="software_station", entity_id=d.station.workstation_key,
                           action="CHANNEL_CHANGED", user_id=d.station.user_id,
                           before_json=json.dumps({"channel": old.value}),
                           after_json=json.dumps({"channel": new.value}),
                           branch_id=d.station.branch_id)
        d.commit()
        return new


class SetMaintenanceWindowUseCase:
    def __init__(self, deps: SoftwareUpdateDependencies) -> None:
        self._d = deps

    def execute(self, window: str) -> str:
        d = self._d
        d.authorization.require(d.station.user_id, P.ACTUALIZACIONES_CANAL)
        text = (window or "").strip()
        value = str(MaintenanceWindow.parse(text)) if text else None
        _ensure_station_row(d)
        before = d.repository.get(d.station.workstation_key)
        d.repository.set_maintenance_window(d.station.workstation_key, value,
                                            user_id=d.station.user_id)
        d.event("WINDOW_CHANGED", detail=value or "Sin ventana")
        if d.audit is not None:
            d.audit.record(entity_type="software_station", entity_id=d.station.workstation_key,
                           action="MAINTENANCE_WINDOW_CHANGED", user_id=d.station.user_id,
                           before_json=json.dumps({"window": before.maintenance_window if before else ""}),
                           after_json=json.dumps({"window": value or ""}),
                           branch_id=d.station.branch_id)
        d.commit()
        return value or ""


def _ensure_station_row(d: SoftwareUpdateDependencies) -> None:
    if d.repository.get(d.station.workstation_key) is None:
        RecordStationStartUseCase(d).record_heartbeat()


# ── startup: version inventory + outcome of the last update ───────────────
@dataclass(frozen=True)
class StartupUpdateNotice:
    state: UpdateJobState
    title: str
    message: str


_OUTCOME_EVENT = {
    UpdateJobState.COMPLETED: "INSTALL_COMPLETED",
    UpdateJobState.ROLLED_BACK: "INSTALL_ROLLED_BACK",
    UpdateJobState.NEEDS_RECOVERY: "INSTALL_NEEDS_RECOVERY",
    UpdateJobState.RECOVERED: "INSTALL_RECOVERED",
    UpdateJobState.CANCELLED: "INSTALL_CANCELLED",
}


class RecordStationStartUseCase:
    """Runs after the database bootstrap, before the login: refreshes this
    station's version row and records the outcome of a finished update job
    (exactly once — `ux_software_update_events_job_outcome`)."""

    def __init__(self, deps: SoftwareUpdateDependencies) -> None:
        self._d = deps

    def record_heartbeat(self) -> None:
        d = self._d
        caps = d.installation.capabilities
        d.repository.record_start(
            workstation_key=d.station.workstation_key, branch_id=d.station.branch_id,
            installed_version=str(d.installation.version), schema_version=d.schema_version(),
            install_profile=caps.profile.value, enabled_capabilities=",".join(sorted(caps.enabled)),
            default_channel=ReleaseChannel.parse(d.installation.default_channel).value)

    def execute(self) -> StartupUpdateNotice | None:
        d = self._d
        self.record_heartbeat()
        notice = None
        try:
            job = d.job_store.load()
        except (OSError, ValueError) as exc:
            logger.warning("No se pudo leer el diario de actualización: %s", exc)
            job = None
        if job is not None and job.state.is_terminal:
            event = _OUTCOME_EVENT[job.state]
            if not d.repository.has_event(job.job_id, event):
                d.event(event, operation_id=job.operation_id, job_id=job.job_id,
                        channel=job.channel, from_version=job.from_version,
                        to_version=job.to_version, actor_user_id=job.requested_by,
                        detail=" | ".join(f"{s.state.value}: {s.detail}" for s in job.history)[-2000:])
            notice = _notice_for(job)
            if job.state is not UpdateJobState.NEEDS_RECOVERY:
                d.job_store.archive(job)
        d.commit()
        return notice


def _notice_for(job: UpdateJob) -> StartupUpdateNotice | None:
    if job.state is UpdateJobState.COMPLETED:
        return StartupUpdateNotice(job.state, "Actualización completada",
                                   f"SPJ se actualizó a la versión {job.to_version}.")
    if job.state is UpdateJobState.ROLLED_BACK:
        return StartupUpdateNotice(job.state, "Actualización revertida", job.last_detail)
    if job.state is UpdateJobState.RECOVERED:
        return StartupUpdateNotice(job.state, "Recuperación terminada", job.last_detail)
    if job.state is UpdateJobState.CANCELLED and job.history and len(job.history) > 1:
        return StartupUpdateNotice(job.state, "Actualización no aplicada", job.last_detail)
    return None
