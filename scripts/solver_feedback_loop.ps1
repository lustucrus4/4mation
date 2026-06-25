# Boucle de retroaction du solveur 4mation-local
#
# Compile, lance le solveur sur une fenetre de test, echantillonne la base
# toutes les N secondes et valide que :
#   - la base grossit (positions/s > seuil)
#   - la file reste alimentee (pending > 0 = le solveur a du travail)
#   - le CPU est utilise
#
# Tant que le critere "a fond" n'est pas atteint, le round est marque a ameliorer.
# La boucle s'arrete au premier round reussi (ou apres MaxRounds).
#
# Usage : cd 4mation ; .\scripts\solver_feedback_loop.ps1
param(
    [int]$MaxRounds = 3,
    [int]$RunSeconds = 180,
    [int]$SampleSeconds = 10,
    [double]$MinRate = 5.0,
    [int]$Threads = 0,
    [int]$MaxEmpty = 20,
    [int]$SolveBatch = 2000,
    [int]$MinPending = 800
)

$ErrorActionPreference = "Stop"
if ($Threads -le 0) { $Threads = [int]$env:NUMBER_OF_PROCESSORS }
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Bin = Join-Path $Root "script\solver_rust\target\release\4mation-local.exe"
$Db = Join-Path $Root "script\solver\data\tablebase.db"
$SnapPy = Join-Path $Root "scripts\_db_snapshot.py"
$ResetPy = Join-Path $Root "scripts\_wq_reset_in_progress.py"

function Get-Snapshot {
    $lines = python $SnapPy $Db
    if (-not $lines) { throw "Lecture base impossible : $Db" }
    return @{
        positions   = [int]$lines[0]
        pending     = [int]$lines[1]
        failed      = [int]$lines[2]
        in_progress = [int]$lines[3]
    }
}

Write-Host "========================================"
Write-Host " 4mation - Boucle retroaction solveur"
Write-Host "========================================"
Write-Host "Critere 'a fond' : >$MinRate positions/s ET file alimentee (pending>0)"

for ($round = 1; $round -le $MaxRounds; $round++) {
    Write-Host ""
    Write-Host "--- Round $round / $MaxRounds ---"

    Stop-Process -Name "4mation-local" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    $recycled = python $ResetPy $Db
    if ([int]$recycled -gt 0) { Write-Host "  Recycle: $recycled in_progress -> pending" }

    Write-Host "Compilation..."
    Push-Location (Join-Path $Root "script\solver_rust")
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & cargo build --release --bin 4mation-local 2>&1 | Out-Null
    $buildOk = $LASTEXITCODE -eq 0
    $ErrorActionPreference = $prevEap
    Pop-Location
    if (-not $buildOk) { throw "Echec compilation" }

    $log = Join-Path $env:TEMP "4mation_fb_$round.log"
    $err = Join-Path $env:TEMP "4mation_fb_err_$round.log"
    if (Test-Path $log) { Remove-Item $log -Force }
    if (Test-Path $err) { Remove-Item $err -Force }

    $argLine = "--db `"$Db`" --threads $Threads --max-empty $MaxEmpty --solve-batch $SolveBatch --min-pending $MinPending"
    Write-Host "Test ${RunSeconds}s (max-empty=$MaxEmpty, solve-batch=$SolveBatch, min-pending=$MinPending)"
    $p = Start-Process -FilePath $Bin -ArgumentList $argLine -PassThru -RedirectStandardOutput $log -RedirectStandardError $err -WorkingDirectory $Root

    Start-Sleep -Seconds 4
    if ($p.HasExited) {
        $bootErr = (Get-Content $err -Raw -ErrorAction SilentlyContinue)
        Write-Host "  Le solveur s'est arrete au demarrage. Stderr:"
        if ($bootErr) { Write-Host "    $($bootErr.Trim())" }
        Write-Host "  Round $round : ECHEC demarrage"
        continue
    }

    $start = Get-Snapshot
    $startPos = $start.positions
    $samples = [int]([math]::Ceiling($RunSeconds / $SampleSeconds))
    $pendingNonZero = 0
    $maxPending = 0
    $prevPos = $startPos

    Write-Host ("  {0,6}  {1,10}  {2,8}  {3,8}  {4,10}" -f "t(s)", "positions", "pending", "inprog", "delta/s")
    for ($i = 1; $i -le $samples; $i++) {
        Start-Sleep -Seconds $SampleSeconds
        $s = Get-Snapshot
        $rate = [math]::Round(($s.positions - $prevPos) / $SampleSeconds, 1)
        $prevPos = $s.positions
        if ($s.pending -gt 0) { $pendingNonZero++ }
        if ($s.pending -gt $maxPending) { $maxPending = $s.pending }
        Write-Host ("  {0,6}  {1,10}  {2,8}  {3,8}  {4,10}" -f ($i * $SampleSeconds), $s.positions, $s.pending, $s.in_progress, $rate)
    }

    $end = Get-Snapshot
    if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }

    $delta = $end.positions - $startPos
    $avgRate = [math]::Round($delta / $RunSeconds, 2)
    $pendingRatio = [math]::Round(100 * $pendingNonZero / $samples)

    Write-Host ""
    Write-Host "  Bilan : +$delta positions en ${RunSeconds}s (~$avgRate/s)"
    Write-Host "  File alimentee : $pendingRatio% des echantillons (pic pending=$maxPending)"
    Write-Host "  Failed : $($end.failed)"

    $rateOk = $avgRate -ge $MinRate
    $fedOk = $pendingRatio -ge 50

    if ($rateOk -and $fedOk) {
        Write-Host "  Round $round : OK - le solveur tourne a fond"
        Write-Host ""
        Write-Host "Boucle terminee avec succes."
        exit 0
    }

    Write-Host "  Round $round : a ameliorer (rate=$avgRate/s, file alimentee=$pendingRatio%)"
    if (-not $fedOk) {
        Write-Host "  -> File peu alimentee : l'explorateur ne genere pas assez de positions."
    }
    if (-not $rateOk -and $fedOk) {
        Write-Host "  -> File alimentee mais resolution lente (positions dures, normal au-dela de empty=16)."
    }
    Write-Host "  Derniers logs :"
    if (Test-Path $log) { Get-Content $log -Tail 6 | ForEach-Object { Write-Host "    $_" } }
}

Write-Host ""
Write-Host "Boucle terminee apres $MaxRounds rounds."
Write-Host "Logs: $env:TEMP\4mation_fb_*.log"
exit 1
