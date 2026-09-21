<#
.SYNOPSIS
    HPQMS PostgreSQL backup: pg_dump (custom format) -> backups/ with
    integrity verification and retention pruning.

.EXAMPLE
    .\scripts\backup_db.ps1                  # default: keep last 7 dumps
    .\scripts\backup_db.ps1 -KeepCount 30    # keep last 30 dumps
    .\scripts\backup_db.ps1 -NoPrune         # never delete old dumps
#>
param(
    # How many most-recent dumps to retain.
    [int]$KeepCount = 7,

    # Disable retention pruning entirely (e.g. for archival runs).
    [switch]$NoPrune
)

$ErrorActionPreference = "Stop"

# Docker Desktop is commonly not on the PATH of spawned/Task Scheduler
# sessions; resolve it explicitly.
$DockerCmd = Get-Command docker -ErrorAction SilentlyContinue
if (-not $DockerCmd) {
    $DockerExe = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
    if (-not (Test-Path $DockerExe)) {
        throw "docker not found on PATH or at $DockerExe."
    }
    Set-Alias docker $DockerExe
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackupDir = Join-Path $ProjectRoot "backups"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupFile = Join-Path $BackupDir "hpqms_backup_$Timestamp.dump"

Write-Host "========================================"
Write-Host "HPQMS PostgreSQL Backup"
Write-Host "========================================"

# Ensure backup directory exists
New-Item -ItemType Directory -Force $BackupDir | Out-Null

Write-Host "Creating database backup..."

# Create the custom-format dump inside the PostgreSQL container
docker compose exec postgres sh -c "pg_dump -U hpqms -Fc hpqms > /tmp/hpqms_backup.dump"

if ($LASTEXITCODE -ne 0) {
    throw "pg_dump failed."
}

# Copy the binary dump from the container to the host
docker compose cp postgres:/tmp/hpqms_backup.dump $BackupFile

if ($LASTEXITCODE -ne 0) {
    throw "Failed to copy backup from PostgreSQL container."
}

# Remove temporary container copy
docker compose exec postgres rm -f /tmp/hpqms_backup.dump

if ($LASTEXITCODE -ne 0) {
    Write-Warning "Backup succeeded, but the temporary container file could not be removed."
}

# Verify backup exists and isn't empty
if (!(Test-Path $BackupFile)) {
    throw "Backup file was not created."
}

$Size = (Get-Item $BackupFile).Length

if ($Size -le 0) {
    throw "Backup file is empty."
}

# --------------------------------------------------------------------
# Integrity verification: a pg_dump -Fc file can be non-empty yet
# truncated/corrupt and would only fail mid-restore (possibly AFTER the
# target database was dropped). pg_restore --list parses the archive's
# table of contents without touching any database, so it proves the
# file is a complete, readable archive.
# --------------------------------------------------------------------
Write-Host "Verifying archive integrity..."

docker compose cp $BackupFile postgres:/tmp/hpqms_verify.dump

if ($LASTEXITCODE -ne 0) {
    Remove-Item $BackupFile
    throw "Could not copy backup back into container for verification."
}

docker compose exec postgres pg_restore --list /tmp/hpqms_verify.dump > $null

$IntegrityExit = $LASTEXITCODE

docker compose exec postgres rm -f /tmp/hpqms_verify.dump | Out-Null

if ($IntegrityExit -ne 0) {
    Remove-Item $BackupFile
    throw "Backup archive FAILED integrity verification and was deleted. Do NOT trust earlier unverified dumps."
}

Write-Host "Integrity verification passed."

# --------------------------------------------------------------------
# Retention: prune oldest dumps beyond -KeepCount. Never fails the
# backup itself; deletion problems are warnings only.
# --------------------------------------------------------------------
if (-not $NoPrune) {

    if ($KeepCount -lt 1) {
        Write-Warning "-KeepCount must be >= 1 (got $KeepCount). Skipping retention prune."
    }
    else {
        $Dumps = Get-ChildItem $BackupDir -Filter "hpqms_backup_*.dump" |
            Sort-Object LastWriteTime -Descending

        if ($Dumps.Count -gt $KeepCount) {
            $Stale = $Dumps | Select-Object -Skip $KeepCount

            Write-Host ""
            Write-Host "Retention: keeping $KeepCount most recent dump(s), pruning $($Stale.Count)..."

            foreach ($File in $Stale) {
                try {
                    Remove-Item $File.FullName
                    Write-Host "  pruned: $($File.Name)"
                }
                catch {
                    Write-Warning "  could not delete $($File.Name): $($_.Exception.Message)"
                }
            }
        }
    }
}

Write-Host ""
Write-Host "Backup successful."
Write-Host "File: $BackupFile"
Write-Host "Size: $Size bytes"
Write-Host ""