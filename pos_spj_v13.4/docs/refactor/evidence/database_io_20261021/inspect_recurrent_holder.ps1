$ErrorActionPreference = 'Stop'
$process = Get-CimInstance Win32_Process -Filter 'ProcessId = 17568'
$parent = if ($process) { Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $process.ParentProcessId) }
@($process, $parent) | Where-Object { $null -ne $_ } | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine,CreationDate | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'recurrent_holder.json') -Encoding UTF8
