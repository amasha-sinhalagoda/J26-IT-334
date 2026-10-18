$ErrorActionPreference = "Stop"

$root = Join-Path $env:LOCALAPPDATA "J26-IT-334"
$pgRoot = Join-Path $root "postgresql17\pgsql"
$postgisRoot = Join-Path $root "postgis-stage\postgis-bundle-pg17-3.6.2x64"
$dataDir = Join-Path $root "pgdata"
$pgBin = Join-Path $pgRoot "bin"
$pgShare = Join-Path $pgRoot "share"
$postgisLib = Join-Path $postgisRoot "lib"
$postgisShare = Join-Path $postgisRoot "share"

foreach ($required in @(
    (Join-Path $pgBin "initdb.exe"),
    (Join-Path $pgBin "pg_ctl.exe"),
    (Join-Path $postgisLib "postgis-3.dll"),
    (Join-Path $postgisShare "extension\postgis.control"),
    (Join-Path $postgisShare "contrib\postgis-3.6\proj\proj.db")
)) {
    if (-not (Test-Path $required)) {
        throw "Required local PostgreSQL/PostGIS file not found: $required"
    }
}

if (Test-Path (Join-Path $dataDir "PG_VERSION")) {
    throw "A PostgreSQL cluster already exists at $dataDir; setup will not overwrite it"
}
if (Test-Path $dataDir) {
    throw "The PostgreSQL data path exists but is not initialized: $dataDir"
}

$env:PATH = "$(Join-Path $postgisRoot 'bin');$pgBin;$env:PATH"
$env:GDAL_DATA = Join-Path $postgisRoot "gdal-data"
$env:PROJ_LIB = Join-Path $postgisShare "contrib\postgis-3.6\proj"

New-Item -ItemType Directory -Path (Join-Path $pgRoot "lib"),(Join-Path $pgShare "extension"),(Join-Path $pgShare "contrib") -Force | Out-Null
Get-ChildItem $postgisLib -File -Filter "postgis*.dll" |
    Copy-Item -Destination (Join-Path $pgRoot "lib") -Force
Get-ChildItem (Join-Path $postgisShare "extension") -File -Filter "postgis*" |
    Copy-Item -Destination (Join-Path $pgShare "extension") -Force
Copy-Item `
    -LiteralPath (Join-Path $postgisShare "contrib\postgis-3.6") `
    -Destination (Join-Path $pgShare "contrib\postgis-3.6") `
    -Recurse `
    -Force

& (Join-Path $pgBin "initdb.exe") `
    -D $dataDir `
    -U dual_route `
    --encoding=UTF8 `
    --auth-local=trust `
    --auth-host=trust
if ($LASTEXITCODE -ne 0) {
    throw "initdb failed to create the local PostGIS cluster"
}

$config = Join-Path $dataDir "postgresql.conf"
Add-Content -LiteralPath $config -Value "`nlisten_addresses = 'localhost'`nport = 55432`n"
$hba = Join-Path $dataDir "pg_hba.conf"
@"
# This user-local development database accepts connections only from loopback.
host all all 127.0.0.1/32 trust
host all all ::1/128 trust
"@ | Set-Content -LiteralPath $hba -Encoding ASCII

Write-Output "Initialized user-local PostgreSQL 17 and installed PostGIS 3.6 extension files."
Write-Output "Run scripts\start_local_postgis.ps1 to start it on localhost:55432."
