# Envoie la tablebase locale (script\solver\data\tablebase.db) sur le VPS de production.
#
# La base de production ne contient qu'une petite partie des positions resolues en local :
# le niveau 6 et l'analyse sont donc plus faibles en ligne. Ce script remplace la base du
# volume Docker de l'API par un instantane coherent de la base locale.
#
# Etapes :
#   1. instantane local coherent (API de sauvegarde SQLite, meme si le solveur tourne) ;
#   2. controle d'integrite rapide de l'instantane ;
#   3. verification de l'espace disque sur le VPS, puis envoi par scp ;
#   4. arret des conteneurs qui ecrivent dans la base, sauvegarde de l'ancienne base,
#      remplacement, redemarrage ;
#   5. controle de /api/health.
#
# L'ancienne base est conservee sur le VPS (tablebase.db.avant-sync-<date>) : en cas de
# probleme, il suffit de la remettre en place. Les positions resolues uniquement par le
# solveur du VPS depuis la derniere synchro ne sont PAS fusionnees : elles restent dans
# cette sauvegarde.
#
# Usage (PowerShell, depuis la racine du projet) :
#   .\scripts\sync_tablebase_vps.ps1
#   .\scripts\sync_tablebase_vps.ps1 -VpsHost root@72.61.96.171 -WhatIf
#   .\scripts\sync_tablebase_vps.ps1 -SshKey $HOME\.ssh\cursor_hostinger_ed25519

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$VpsHost = "root@72.61.96.171",
    # Cle privee passee a ssh et scp (-i) ; vide = cle par defaut / agent.
    [string]$SshKey = "",
    [string]$LocalDb = "script\solver\data\tablebase.db",
    [string]$Snapshot = "$env:TEMP\4mation_tablebase_snapshot.db",
    [string]$RemoteTmp = "/opt/4mation/tablebase.db.upload",
    [string]$ApiContainer = "4mation-api",
    [string[]]$WriterContainers = @("4mation-solver", "4mation-solver-filler", "4mation-realtime", "4mation-api"),
    [string]$HealthUrl = "https://api-4mation.lab211.fr/api/health"
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$sshOpts = @()
if ($SshKey) {
    if (-not (Test-Path $SshKey)) { throw "Cle SSH introuvable : $SshKey" }
    $sshOpts = @("-i", $SshKey, "-o", "IdentitiesOnly=yes")
}

$python = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }

if (-not (Test-Path $LocalDb)) { throw "Base locale introuvable : $LocalDb" }

Write-Host "== 1. Instantane local de $LocalDb"
$snapshotCode = @'
import sqlite3, sys
src = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
dst = sqlite3.connect(sys.argv[2])
src.backup(dst, pages=65536)
dst.execute("PRAGMA journal_mode=DELETE")
row = dst.execute("PRAGMA quick_check").fetchone()[0]
pos = dst.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
book = dst.execute("SELECT COUNT(*) FROM opening_book").fetchone()[0]
dst.close(); src.close()
print(f"quick_check={row} positions={pos} opening_book={book}")
sys.exit(0 if row == "ok" else 1)
'@
if (Test-Path $Snapshot) { Remove-Item $Snapshot }
# Fichier plutot que -c : Windows PowerShell 5.1 retire les guillemets doubles
# des arguments passes a un programme natif, ce qui cassait le code Python.
$snapshotPy = Join-Path $env:TEMP "4mation_snapshot.py"
Set-Content -Path $snapshotPy -Value $snapshotCode -Encoding ASCII
& $python $snapshotPy $LocalDb $Snapshot
Remove-Item $snapshotPy
if ($LASTEXITCODE -ne 0) { throw "Instantane invalide (quick_check en echec)" }
$sizeGb = [math]::Round((Get-Item $Snapshot).Length / 1GB, 2)
Write-Host "   instantane : $Snapshot ($sizeGb Go)"

Write-Host "== 2. Espace disque sur le VPS"
$needKb = [math]::Ceiling((Get-Item $Snapshot).Length / 1KB * 1.1)
$freeKb = ssh @sshOpts $VpsHost "mkdir -p /opt/4mation && df -Pk /opt/4mation /var/lib/docker | awk 'NR>1 {print `$4}' | sort -n | head -1"
if ([int64]$freeKb -lt $needKb) {
    throw "Espace insuffisant sur le VPS : $([math]::Round($freeKb/1MB,1)) Go libres, $([math]::Round($needKb/1MB,1)) Go necessaires"
}
Write-Host "   $([math]::Round($freeKb/1MB,1)) Go libres"

if (-not $PSCmdlet.ShouldProcess($VpsHost, "Remplacer la tablebase de production")) { return }

Write-Host "== 3. Envoi ($sizeGb Go, peut etre long)"
scp @sshOpts $Snapshot "${VpsHost}:$RemoteTmp"
if ($LASTEXITCODE -ne 0) { throw "Echec de l'envoi scp" }

Write-Host "== 4. Remplacement sur le VPS"
$writers = $WriterContainers -join " "
$remote = @"
set -eu
DATA=`$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/app/data"}}{{.Source}}{{end}}{{end}}' $ApiContainer)
test -n "`$DATA"
STAMP=`$(date +%Y%m%d-%H%M%S)
docker stop $writers
if [ -f "`$DATA/tablebase.db" ]; then mv "`$DATA/tablebase.db" "`$DATA/tablebase.db.avant-sync-`$STAMP"; fi
rm -f "`$DATA/tablebase.db-wal" "`$DATA/tablebase.db-shm"
mv $RemoteTmp "`$DATA/tablebase.db"
docker start $writers
echo "ancienne base : `$DATA/tablebase.db.avant-sync-`$STAMP"
"@
$remote = $remote -replace "`r", ""
$remote | ssh @sshOpts $VpsHost "sh -s"
if ($LASTEXITCODE -ne 0) { throw "Echec du remplacement sur le VPS (les conteneurs sont peut-etre arretes : docker start $writers)" }

Write-Host "== 5. Controle de sante"
Start-Sleep -Seconds 60
try {
    $health = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 30
    $health | ConvertTo-Json -Depth 4
} catch {
    Write-Warning "L'API ne repond pas encore ; reessayer : $HealthUrl"
}

Remove-Item $Snapshot
Write-Host "Termine."
