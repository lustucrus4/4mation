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
$errLog = Join-Path $dataDir "train_stderr.log"
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
$argString = "--cores $Cores --self-play-games $SelfPlayGames --eval-every $EvalEvery --data-dir `"$dataDir`""
if ($Resume) { $argString += " --resume" }

$env:PYTHONPATH = "$root;$root\script"
$env:RUST_LOG = "formation_rl=info"

# Start-Process détaché : le shell parent peut se fermer sans couper train.exe
$proc = Start-Process -FilePath $trainExe `
    -ArgumentList $argString `
    -WorkingDirectory $root `
    -RedirectStandardOutput $log `
    -RedirectStandardError $errLog `
    -PassThru `
    -WindowStyle Hidden

@"
PID=$($proc.Id)
LOG=$log
ERR=$errLog
START=$(Get-Date -Format o)
CMD=$trainExe $($argList -join ' ')
"@ | Set-Content -Path $pidFile -Encoding UTF8

Write-Host "Entrainement RL demarre PID=$($proc.Id)"
Write-Host "Log: $log"
Write-Host "Dashboard: /analyze/rl"
