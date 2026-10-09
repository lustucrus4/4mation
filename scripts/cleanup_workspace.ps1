# Range les fichiers temporaires et de diagnostic du projet dans _archive\<date>\.
#
# Par defaut le script ne fait que LISTER ce qu'il deplacerait. Avec -Apply, il deplace
# (rien n'est supprime : _archive\ est ignore par git et peut etre efface a la main
# une fois verifie). Les grosses sauvegardes de la tablebase sont seulement signalees.
#
# Usage (PowerShell, depuis la racine du projet) :
#   .\scripts\cleanup_workspace.ps1          # liste
#   .\scripts\cleanup_workspace.ps1 -Apply   # deplace

param([switch]$Apply)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

$patterns = @(
    "scripts\_tmp_*",
    "scripts\_*diag*.py",
    "scripts\_repro_*.py",
    "scripts\_test_*.py",
    "scripts\_blob_check.py",
    "scripts\_db_*.py",
    "scripts\_empty_*.py",
    "scripts\_layer_stats.py",
    "scripts\_lesson_*.py",
    "scripts\_pending_empty_dist.py",
    "scripts\_wq_*.py",
    "script\solver\_tmp_*.py",
    "script\solver\data\_*.log",
    "script\solver_rust\*.log",
    "script\rl_rust\data\_test_*",
    "script\rl_rust\data\_tmp_*",
    "script\rl_rust\data\*.pid",
    "script\logs\*.pid",
    "script\game_tree\tree_visualization_*.html",
    "4mation_dashboard_dev\src\main.js"
)

$files = foreach ($p in $patterns) { Get-ChildItem -Path $p -File -ErrorAction SilentlyContinue }
$files = $files | Sort-Object FullName -Unique

$dest = Join-Path $root ("_archive\" + (Get-Date -Format "yyyy-MM-dd"))
$total = 0
foreach ($f in $files) {
    $rel = $f.FullName.Substring($root.Path.Length + 1)
    $total += $f.Length
    "{0,10:N1} Mo  {1}" -f ($f.Length / 1MB), $rel
    if ($Apply) {
        $target = Join-Path $dest $rel
        New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
        Move-Item -LiteralPath $f.FullName -Destination $target
    }
}
"{0} fichier(s), {1:N1} Mo" -f @($files).Count, ($total / 1MB)

$ckpt = Get-ChildItem "script\rl_rust\data\checkpoints" -File -ErrorAction SilentlyContinue
if ($ckpt) {
    "`nCheckpoints RL : {0} fichiers, {1:N1} Mo (script\rl_rust\data\checkpoints) - a archiver si l'entrainement est termine." -f $ckpt.Count, (($ckpt | Measure-Object Length -Sum).Sum / 1MB)
}

$backups = Get-ChildItem "script\solver\data" -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "tablebase*.db" -and $_.Name -ne "tablebase.db" }
if ($backups) {
    "`nSauvegardes de tablebase (non touchees, a supprimer a la main si inutiles) :"
    foreach ($b in $backups) { "{0,10:N1} Go  {1}" -f ($b.Length / 1GB), $b.Name }
}

if (-not $Apply) { "`nRien n'a ete deplace. Relancer avec -Apply pour ranger dans $dest" }
