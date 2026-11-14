# Build a release zip that can be handed to other people (no venv, no generated tracks).
# ASCII only on purpose: Windows PowerShell 5.1 reads BOM-less files as ANSI.
param([string]$Version = "v0.8")

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$dist = Join-Path $root "dist"
$stage = Join-Path $dist "campus-run-planner-$Version"
$zip = Join-Path $dist "campus-run-planner-$Version.zip"

if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
if (Test-Path $zip)   { Remove-Item $zip -Force }
New-Item -ItemType Directory -Path $stage -Force | Out-Null

$files = @(
    "README.md", "LICENSE", "requirements.txt",
    "outputs\README.md", "outputs\TEST_REPORT.md", "outputs\check_gpx.py", "outputs\clear_location.py",
    "outputs\run-planner\run_planner.py", "outputs\run-planner\road_network.py",
    "outputs\run-planner\auto_route.py", "outputs\run-planner\checkpoint_reader.py",
    "outputs\run-planner\locate_checkpoints.py", "outputs\run-planner\location_sim.py",
    "outputs\run-planner\phone_screen.py", "outputs\run-planner\sim_now.py",
    "outputs\run-planner\run_from_phone.py", "outputs\run-planner\campus_map.json"
)
foreach ($item in $files) {
    $source = Join-Path $root $item
    if (-not (Test-Path $source)) { throw "missing: $item" }
    $target = Join-Path $stage $item
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    Copy-Item $source $target -Force
}

# the launchers have Chinese filenames, so find them instead of spelling them
$bats = Get-ChildItem -Path $root -Filter *.bat -File
if (-not $bats) { throw "no .bat launcher in project root" }
foreach ($bat in $bats) { Copy-Item $bat.FullName (Join-Path $stage $bat.Name) -Force }

Copy-Item (Join-Path $root "outputs\run-planner\tests") (Join-Path $stage "outputs\run-planner\tests") -Recurse -Force
New-Item -ItemType Directory -Path (Join-Path $stage "outputs\run-planner\generated") -Force | Out-Null
Set-Content -Path (Join-Path $stage "outputs\run-planner\generated\.gitkeep") -Value ""

# second front end: the obstacle-aware planner with automatic start + replay
Copy-Item (Join-Path $root "outputs\real-run-planner") (Join-Path $stage "outputs") -Recurse -Force
$published = Join-Path $stage "outputs\real-run-planner"
New-Item -ItemType Directory -Path (Join-Path $published "generated") -Force | Out-Null
Set-Content -Path (Join-Path $published "generated\.gitkeep") -Value ""
Get-ChildItem -Path $published -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -Path (Join-Path $published "generated") -Filter "*.gpx" | Remove-Item -Force

Compress-Archive -Path $stage -DestinationPath $zip -CompressionLevel Optimal
Write-Host "built: $zip"