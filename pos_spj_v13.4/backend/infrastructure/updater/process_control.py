"""External processes the updater coordinates — never through a shell.

Every command is an argument LIST passed to `CreateProcess`/`ShellExecuteEx`;
no `os.system`, no `shell=True`, no string built from a URL or a path. The
only elevated program is the installer itself, started with the `runas` verb
so Windows shows the UAC prompt with the installer's publisher.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Sequence


class ProcessControlError(RuntimeError):
    installer_started = True


class InstallerNotStartedError(ProcessControlError):
    """UAC declined or the executable could not be started: nothing changed."""

    installer_started = False


# ── waiting for the desktop to exit ────────────────────────────────────────
def wait_for_process_exit(pid: int, *, timeout_seconds: float) -> bool:
    """True when `pid` is gone within the timeout."""
    if pid <= 0:
        return True
    if sys.platform == "win32":
        return _win_wait_pid(pid, timeout_seconds)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            pass
        time.sleep(0.25)
    return False


def _win_wait_pid(pid: int, timeout_seconds: float) -> bool:
    import ctypes
    from ctypes import wintypes

    SYNCHRONIZE = 0x00100000
    WAIT_OBJECT_0 = 0x0
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        return True  # no such process (or already gone)
    try:
        result = kernel32.WaitForSingleObject(handle, int(timeout_seconds * 1000))
        return result == WAIT_OBJECT_0
    finally:
        kernel32.CloseHandle(handle)


# ── running the installer ──────────────────────────────────────────────────
def inno_silent_arguments(log_path: Path) -> list[str]:
    """`/SILENT` (not `/VERYSILENT`): Inno shows its own progress bar, so the
    person at the till sees that an update is running. No questions asked."""
    return ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOCANCEL",
            "/CLOSEAPPLICATIONS", f"/LOG={log_path}", "/SPJUPDATER=1"]


class InstallerRunner:
    """`elevate=False` for per-user installations (`install_mode: user`): the
    installer runs as the same user, with `/CURRENTUSER`, and no UAC prompt."""

    def __init__(self, *, elevate: bool = True) -> None:
        self._elevate = elevate

    def run(self, installer: Path, arguments: Sequence[str], *, timeout_seconds: float) -> int:
        installer = Path(installer)
        if sys.platform == "win32" and self._elevate:
            return _win_run_elevated(installer, list(arguments), timeout_seconds)
        completed = subprocess.run([str(installer), *arguments], timeout=timeout_seconds,
                                   check=False)
        return completed.returncode


def _quote_argument(argument: str) -> str:
    # CommandLineToArgvW rules — the same quoting subprocess.list2cmdline uses.
    return subprocess.list2cmdline([argument])


def _win_run_elevated(installer: Path, arguments: list[str], timeout_seconds: float) -> int:
    import ctypes
    from ctypes import wintypes

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR), ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HKEY), ("dwHotKey", wintypes.DWORD),
            ("hIconOrMonitor", wintypes.HANDLE), ("hProcess", wintypes.HANDLE),
        ]

    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    SEE_MASK_NOASYNC = 0x00000100
    SW_SHOWNORMAL = 1
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NOASYNC
    info.lpVerb = "runas"
    info.lpFile = str(installer)
    info.lpParameters = " ".join(_quote_argument(a) for a in arguments)
    info.lpDirectory = str(installer.parent)
    info.nShow = SW_SHOWNORMAL
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        error = ctypes.get_last_error()
        if error == 1223:  # ERROR_CANCELLED — UAC prompt declined
            raise InstallerNotStartedError("Se canceló la autorización de administrador (UAC).")
        raise InstallerNotStartedError(f"No se pudo iniciar el instalador (error {error}).")
    try:
        if kernel32.WaitForSingleObject(info.hProcess, int(timeout_seconds * 1000)) != 0:
            raise ProcessControlError("El instalador no terminó en el tiempo esperado.")
        code = wintypes.DWORD()
        kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
        return int(code.value)
    finally:
        kernel32.CloseHandle(info.hProcess)


# ── self-test of the installed application ─────────────────────────────────
@dataclass(frozen=True)
class SelfTestReport:
    ok: bool
    version: str
    schema_version: int | None
    detail: str
    raw: dict


class SelfTestProbe:
    """Runs `<app> --self-test --json`: resolves paths, relocates if needed,
    integrity → migrations → schema/UUID validation, then exits."""

    def __init__(self, app_command: Sequence[str], *, environment: dict | None = None) -> None:
        self._command = list(app_command)
        self._environment = environment

    def run(self, *, timeout_seconds: float) -> SelfTestReport:
        import tempfile

        handle, report_path = tempfile.mkstemp(prefix="spj-selftest-", suffix=".json")
        os.close(handle)
        try:
            try:
                completed = subprocess.run(
                    [*self._command, "--self-test", "--json", "--report", report_path],
                    capture_output=True, text=True, timeout=timeout_seconds, check=False,
                    env=self._environment,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                return SelfTestReport(False, "", None, f"No se pudo ejecutar la prueba: {exc}", {})
            try:
                written = Path(report_path).read_text(encoding="utf-8")
            except OSError:
                written = ""
        finally:
            Path(report_path).unlink(missing_ok=True)
        report = _last_json_object(written) or _last_json_object(completed.stdout)
        if report is None:
            tail = (completed.stderr or completed.stdout or "")[-800:]
            return SelfTestReport(False, "", None,
                                  f"La prueba no devolvió resultado (código {completed.returncode}). {tail}",
                                  {})
        return SelfTestReport(
            ok=bool(report.get("ok")) and completed.returncode == 0,
            version=str(report.get("version") or ""),
            schema_version=report.get("schema_version"),
            detail=str(report.get("detail") or ""), raw=report)


def _last_json_object(text: str) -> dict | None:
    for line in reversed((text or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict):
                return value
    return None


# ── launching detached processes ───────────────────────────────────────────
def launch_detached(command: Sequence[str], *, working_directory: Path | None = None) -> int:
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    process = subprocess.Popen(
        list(command), cwd=str(working_directory) if working_directory else None,
        close_fds=True, creationflags=flags,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return process.pid
