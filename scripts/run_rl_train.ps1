# Lance l'entraînement RL Rust en arrière-plan (Windows).
# Usage: .\scripts\run_rl_train.ps1 [-Cores 16] [-Resume]

param(
    [int]$Cores = 16,
    [int]$SelfPlayGames = 1000,
    [int]$EvalEvery = 5000,
    [switch]$Resume
)

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$rlDir = Join-Path $root "script\rl_rust"
$dataDir = Join-Path $rlDir "data"
$log = Join-Path $dataDir "train.log"
$pidFile = Join-Path $dataDir "_train.pid"

New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

Push-Location $rlDir
try {
    Write-Host "Compilation release..."
    cargo build --release --bin train
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}

$trainExe = Join-Path $rlDir "target\release\train.exe"
$argList = @(
    "--cores", $Cores,
    "--self-play-games", $SelfPlayGames,
    "--eval-every", $EvalEvery,
    "--data-dir", $dataDir
)
if ($Resume) { $argList += "--resume" }

$env:PYTHONPATH = "$root;$root\script"
$env:RUST_LOG = "formation_rl=info"

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $trainExe
$psi.Arguments = ($argList -join " ")
$psi.WorkingDirectory = $root
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
foreach ($key in @("PYTHONPATH", "RUST_LOG")) {
    if (Test-Path "env:$key") {
        $psi.EnvironmentVariables[$key] = (Get-Item "env:$key").Value
    }
}

$proc = New-Object System.Diagnostics.Process
$proc.StartInfo = $psi
$null = $proc.Start()

@"
PID=$($proc.Id)
LOG=$log
START=$(Get-Date -Format o)
CMD=$trainExe $($psi.Arguments)
"@ | Set-Content -Path $pidFile -Encoding UTF8

$outWriter = [System.IO.StreamWriter]::new($log, $false, [System.Text.UTF8Encoding]::new($false))
$proc.add_OutputDataReceived({ param($s, $e) if ($null -ne $e.Data) { $outWriter.WriteLine($e.Data); $outWriter.Flush() } })
$proc.add_ErrorDataReceived({ param($s, $e) if ($null -ne $e.Data) { $outWriter.WriteLine($e.Data); $outWriter.Flush() } })
$proc.BeginOutputReadLine()
$proc.BeginErrorReadLine()

Write-Host "Entrainement RL demarre PID=$($proc.Id)"
Write-Host "Log: $log"
Write-Host "Dashboard: /analyze/rl"
