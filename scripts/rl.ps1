# Entraînement RL 4mation — commande unique

Param(
    [ValidateSet("train", "eval", "stop", "status")]
    [string]$Action = "train",
    [int]$Cores = 16,
    [switch]$Resume,
    [switch]$Fresh,
    [switch]$Imitate,
    [int]$EvalGames = 12,
    [int]$EvalEveryL5 = 10000,
    [int]$EvalEveryL3 = 25000,
    [int]$MctsSims = 36,
    [int]$EvalMctsSims = 16,
    [int]$SelfPlayGames = 1200,
    [int]$CheckpointEvery = 25,
    [ValidateSet("auto", "vs_level5", "self_play")]
    [string]$TrainingPhase = "self_play",
    [double]$Phase2WinThreshold = 0.50,
    [int]$PhaseTransitionGames = 20
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$rlDir = Join-Path $root "script\rl_rust"
$dataDir = Join-Path $rlDir "data"
$trainExe = Join-Path $rlDir "target\release\train.exe"
$evalExe = Join-Path $rlDir "target\release\eval.exe"

function Show-Status {
    $statusFile = Join-Path $dataDir "status.json"
    if (-not (Test-Path $statusFile)) {
        Write-Host "Aucun entrainement detecte ($statusFile)"
        return
    }
    Get-Content $statusFile -Raw | ConvertFrom-Json | Format-List
    try {
        Invoke-RestMethod "http://127.0.0.1:5000/api/rl/status" -TimeoutSec 2 | Format-List
    } catch { }
}

switch ($Action) {
    "stop" {
        Get-Process train -ErrorAction SilentlyContinue | ForEach-Object {
            Write-Host "Arret train PID=$($_.Id)"
            Stop-Process -Id $_.Id -Force
        }
        if (-not (Get-Process train -ErrorAction SilentlyContinue)) {
            Write-Host "Aucun train.exe actif."
        }
    }
    "status" {
        Show-Status
        if (Test-Path (Join-Path $dataDir "train.log")) {
            Write-Host "`n--- train.log (10 dernieres lignes) ---"
            Get-Content (Join-Path $dataDir "train.log") -Tail 10
        }
    }
    "eval" {
        Push-Location $rlDir
        try {
            cargo build --release --bin eval
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        } finally { Pop-Location }
        $env:PYTHONPATH = "$root;$root\script"
        & $evalExe --games $EvalGames --data-dir $dataDir
    }
    "train" {
        Get-Process train -ErrorAction SilentlyContinue | ForEach-Object {
            Write-Host "Arret ancien train PID=$($_.Id)"
            Stop-Process -Id $_.Id -Force
        }
        New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
        Push-Location $rlDir
        try {
            Write-Host "Compilation release..."
            cargo build --release --bin train
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        } finally { Pop-Location }

        $argString = @(
            "--cores $Cores",
            "--self-play-games $SelfPlayGames",
            "--eval-every-l5 $EvalEveryL5",
            "--eval-every-l3 $EvalEveryL3",
            "--eval-games $EvalGames",
            "--mcts-sims $MctsSims",
            "--eval-mcts-sims $EvalMctsSims",
            "--checkpoint-every $CheckpointEvery",
            "--training-phase $TrainingPhase",
            "--phase2-win-threshold $Phase2WinThreshold",
            "--phase-transition-games $PhaseTransitionGames",
            "--data-dir `"$dataDir`""
        ) -join " "
        if ($Resume) { $argString += " --resume" }
        if ($Fresh) { $argString += " --fresh" }
        if ($Imitate) { $argString += " --imitate" }

        $env:PYTHONPATH = "$root;$root\script"
        $env:RUST_LOG = "formation_rl=info"
        $log = Join-Path $dataDir "train.log"
        $errLog = Join-Path $dataDir "train_stderr.log"

        $proc = Start-Process -FilePath $trainExe `
            -ArgumentList $argString `
            -WorkingDirectory $root `
            -RedirectStandardOutput $log `
            -RedirectStandardError $errLog `
            -PassThru -WindowStyle Hidden

        @"
PID=$($proc.Id)
LOG=$log
START=$(Get-Date -Format o)
"@ | Set-Content (Join-Path $dataDir "_train.pid") -Encoding UTF8

        Write-Host "Entrainement RL demarre PID=$($proc.Id)"
        Write-Host "Donnees: $dataDir"
        Write-Host "Dashboard: http://127.0.0.1:5173/analyze/rl"
        Write-Host "Commandes: .\scripts\rl.ps1 status | eval | stop"
    }
}
