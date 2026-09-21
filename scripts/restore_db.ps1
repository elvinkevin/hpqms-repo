$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackupDir = Join-Path $ProjectRoot "backups"

Write-Host "========================================"
Write-Host "HPQMS PostgreSQL Restore"
Write-Host "========================================"
Write-Host ""

# Find available backup files
$Backups = Get-ChildItem $BackupDir -Filter "*.dump" |
    Sort-Object LastWriteTime -Descending

if ($Backups.Count -eq 0) {
    throw "No .dump backup files found in $BackupDir"
}

Write-Host "Available backups:"
Write-Host ""

for ($i = 0; $i -lt $Backups.Count; $i++) {
    Write-Host "[$($i + 1)] $($Backups[$i].Name) - $($Backups[$i].Length) bytes"
}

Write-Host ""

$Selection = Read-Host "Enter backup number"

if (-not [int]::TryParse($Selection, [ref]$null)) {
    throw "Invalid backup selection."
}

$Index = [int]$Selection - 1

if ($Index -lt 0 -or $Index -ge $Backups.Count) {
    throw "Backup selection is out of range."
}

$BackupFile = $Backups[$Index]

Write-Host ""
Write-Host "Selected backup:"
Write-Host $BackupFile.FullName
Write-Host ""

$DatabaseName = Read-Host "Enter the target database name"

if ([string]::IsNullOrWhiteSpace($DatabaseName)) {
    throw "Database name cannot be empty."
}

if ($DatabaseName -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
    throw "Invalid database name. Use only letters, numbers, and underscores, starting with a letter or underscore."
}

if ($DatabaseName -eq "hpqms") {
    throw "For safety, this script will not restore directly into the live 'hpqms' database."
}

Write-Host ""
Write-Host "Target database: $DatabaseName"
Write-Host ""
Write-Host "WARNING: The target database will be recreated."
$Confirmation = Read-Host "Type RESTORE to continue"

if ($Confirmation -ne "RESTORE") {
    Write-Host "Restore cancelled."
    exit 0
}

Write-Host ""
Write-Host "Creating target database..."

# Drop the target database if it already exists
docker compose exec postgres psql -U hpqms -d postgres -c "DROP DATABASE IF EXISTS $DatabaseName;"

if ($LASTEXITCODE -ne 0) {
    throw "Failed to remove existing target database."
}

# Create a clean target database
docker compose exec postgres psql -U hpqms -d postgres -c "CREATE DATABASE $DatabaseName;"

if ($LASTEXITCODE -ne 0) {
    throw "Failed to create target database."
}

Write-Host "Target database created."

# Copy backup into the PostgreSQL container
Write-Host ""
Write-Host "Copying backup into PostgreSQL container..."

docker compose cp $BackupFile.FullName postgres:/tmp/hpqms_restore.dump

if ($LASTEXITCODE -ne 0) {
    throw "Failed to copy backup into PostgreSQL container."
}

# Restore
Write-Host ""
Write-Host "Restoring database..."

docker compose exec postgres pg_restore `
    -U hpqms `
    -d $DatabaseName `
    --clean `
    --if-exists `
    /tmp/hpqms_restore.dump

if ($LASTEXITCODE -ne 0) {
    throw "Database restore failed."
}

# Remove temporary container copy
docker compose exec postgres rm -f /tmp/hpqms_restore.dump

if ($LASTEXITCODE -ne 0) {
    Write-Warning "Restore succeeded, but the temporary container file could not be removed."
}

Write-Host ""
Write-Host "========================================"
Write-Host "Restore completed successfully."
Write-Host "========================================"
Write-Host ""
Write-Host "Restored database: $DatabaseName"
Write-Host ""