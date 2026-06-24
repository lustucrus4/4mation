param(
    [Parameter(Position = 0)]
    [int]$Port = 8765
)

$connections = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
if ($connections.Count -eq 0) {
    exit 0
}

$processIds = $connections | ForEach-Object { $_.OwningProcess } | Sort-Object -Unique
foreach ($procId in $processIds) {
    try {
        $proc = Get-Process -Id $procId -ErrorAction Stop
        Stop-Process -Id $procId -Force -ErrorAction Stop
        Write-Host "Port $Port : processus $($proc.ProcessName) (PID $procId) arrete."
    }
    catch {
        Write-Host "Port $Port : impossible d'arreter PID $procId ($($_.Exception.Message))."
    }
}
