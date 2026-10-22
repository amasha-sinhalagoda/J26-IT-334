$ErrorActionPreference = "Stop"

$root = Join-Path $env:LOCALAPPDATA "J26-IT-334"
$pgRoot = Join-Path $root "postgresql17\pgsql"
$dataDir = Join-Path $root "pgdata"
$pgCtl = Join-Path $pgRoot "bin\pg_ctl.exe"

if (-not (Test-Path $pgCtl) -or -not (Test-Path (Join-Path $dataDir "PG_VERSION"))) {
    throw "User-local PostgreSQL installation or cluster was not found"
}

& $pgCtl stop -D $dataDir -m fast
if ($LASTEXITCODE -ne 0) {
    throw "PostgreSQL failed to stop cleanly"
}
Write-Output "Local PostgreSQL stopped"
