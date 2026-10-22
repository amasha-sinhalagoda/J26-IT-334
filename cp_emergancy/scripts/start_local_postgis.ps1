$ErrorActionPreference = "Stop"

$root = Join-Path $env:LOCALAPPDATA "J26-IT-334"
$pgRoot = Join-Path $root "postgresql17\pgsql"
$postgisRoot = Join-Path $root "postgis-stage\postgis-bundle-pg17-3.6.2x64"
$dataDir = Join-Path $root "pgdata"
$logFile = Join-Path $root "postgresql.log"
$port = 55432

$postgres = Join-Path $pgRoot "bin\postgres.exe"
$pgCtl = Join-Path $pgRoot "bin\pg_ctl.exe"
if (-not (Test-Path $postgres) -or -not (Test-Path $pgCtl)) {
    throw "User-local PostgreSQL binaries were not found under $pgRoot"
}
if (-not (Test-Path (Join-Path $postgisRoot "bin\libgeos_c.dll"))) {
    throw "PostGIS runtime libraries were not found under $postgisRoot"
}
if (-not (Test-Path (Join-Path $dataDir "PG_VERSION"))) {
    throw "PostgreSQL cluster is not initialized. Run scripts\setup_local_postgis.ps1 first."
}

$env:PATH = "$(Join-Path $postgisRoot 'bin');$(Join-Path $pgRoot 'bin');$env:PATH"
$env:GDAL_DATA = Join-Path $postgisRoot "gdal-data"
$env:PROJ_LIB = Join-Path $postgisRoot "share\contrib\postgis-3.6\proj"
if (-not (Test-Path (Join-Path $env:GDAL_DATA "gdalvrt.xsd"))) {
    throw "PostGIS GDAL data directory is incomplete"
}
if (-not (Test-Path (Join-Path $env:PROJ_LIB "proj.db"))) {
    throw "PostGIS PROJ data directory is incomplete"
}

& $pgCtl status -D $dataDir *> $null
if ($LASTEXITCODE -eq 0) {
    Write-Output "Local PostGIS database is already running on 127.0.0.1:$port"
    exit 0
}

& $pgCtl start -D $dataDir -l $logFile -o "-p $port -c listen_addresses=localhost"
if ($LASTEXITCODE -ne 0) {
    throw "PostgreSQL failed to start. Review $logFile"
}
Write-Output "Local PostgreSQL is running on localhost:$port"
