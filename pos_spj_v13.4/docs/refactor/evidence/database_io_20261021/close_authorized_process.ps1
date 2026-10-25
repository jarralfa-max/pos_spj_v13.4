$ErrorActionPreference = 'Stop'
$resultPath = Join-Path $PSScriptRoot 'process_close_result.txt'
try {
    $expectedStart = [long](Get-Content -LiteralPath (Join-Path $PSScriptRoot 'authorized_process_start.txt'))
    $targetProcess = Get-Process -Id 15480 -ErrorAction SilentlyContinue
    if ($null -eq $targetProcess) {
        'Already exited; no process terminated.' | Set-Content -LiteralPath $resultPath
        exit 0
    }
    if ($targetProcess.ProcessName -ne 'python' -or $targetProcess.StartTime.ToUniversalTime().ToFileTimeUtc() -ne $expectedStart) {
        throw 'Process identity differs from the authorized database holder. No process terminated.'
    }
    Stop-Process -InputObject $targetProcess -Force -ErrorAction Stop
    if (-not $targetProcess.WaitForExit(10000)) { throw 'Timed out waiting for authorized process to exit.' }
    'Authorized database holder PID 15480 terminated and exited.' | Set-Content -LiteralPath $resultPath
} catch {
    $_.Exception.Message | Set-Content -LiteralPath $resultPath
    exit 1
}
