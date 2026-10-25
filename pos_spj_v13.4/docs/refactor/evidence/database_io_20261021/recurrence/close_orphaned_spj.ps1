$ErrorActionPreference = 'Stop'
$resultPath = Join-Path $PSScriptRoot 'process_close_result.txt'
try {
    $targetProcess = Get-Process -Id 17568 -ErrorAction SilentlyContinue
    if ($null -eq $targetProcess) {
        'Already exited; no process terminated.' | Set-Content -LiteralPath $resultPath
        exit 0
    }
    if ($targetProcess.ProcessName -ne 'python' -or $targetProcess.StartTime.ToUniversalTime().ToFileTimeUtc() -ne 134371030632578829) {
        throw 'Process identity changed; no process terminated.'
    }
    $details = Get-CimInstance Win32_Process -Filter 'ProcessId = 17568'
    if ($details.CommandLine -ne '"C:\Users\Diego Rodriguez\Downloads\pos_spj_v13.4\.venv\Scripts\python.exe" main.py') {
        throw 'Process is not the verified SPJ instance; no process terminated.'
    }
    $parentProcess = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $details.ParentProcessId)
    if ($null -ne $parentProcess) { throw 'Parent is present; no process terminated.' }
    $requestedClose = $targetProcess.CloseMainWindow()
    if (-not $requestedClose -or -not $targetProcess.WaitForExit(5000)) {
        Stop-Process -InputObject $targetProcess -Force -ErrorAction Stop
    }
    if (-not $targetProcess.WaitForExit(10000)) { throw 'Process did not exit.' }
    'Verified orphaned SPJ PID 17568 exited.' | Set-Content -LiteralPath $resultPath
} catch {
    $_.Exception.Message | Set-Content -LiteralPath $resultPath
    exit 1
}
