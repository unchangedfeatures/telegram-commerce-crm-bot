# ParXpress - Upload folders to VPS via SCP
# PowerShell version (Windows)
# Usage: .\upload-folders-to-vps.ps1 79.143.90.63 parxpress "C:\Users\Sevav\.ssh\id_rsa_parxpress"

param(
    [string]$VPS_IP = "",
    [string]$SSH_USER = "root",
    [string]$SSH_KEY = ""
)

if ([string]::IsNullOrEmpty($VPS_IP)) {
    Write-Host "Usage: .\upload-folders-to-vps.ps1 <VPS_IP> [SSH_USER] [SSH_KEY]" -ForegroundColor Yellow
    exit 1
}

# Default folders to upload
$folders = @("handlers", "database", "keyboards", "middleware", "templates", "texts", "static")

# Get script directory (assume script in C:\Users\Sevav\Desktop\requiem\ParXpress)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# Prepare SSH key argument
$sshKeyArg = @()
if (-not [string]::IsNullOrEmpty($SSH_KEY) -and (Test-Path $SSH_KEY)) {
    $sshKeyArg = @("-i", $SSH_KEY)
} else {
    $defaultKey = "$env:USERPROFILE\.ssh\id_rsa_parxpress"
    if (Test-Path $defaultKey) { $sshKeyArg = @("-i", $defaultKey) }
}

# Create destination directory on VPS
$destPath = if ($SSH_USER -eq "root") { "/root/app/" } else { "/home/${SSH_USER}/app/" }
& ssh $sshKeyArg "${SSH_USER}@${VPS_IP}" "mkdir -p $destPath && chmod 755 $destPath"

# Upload each folder recursively
foreach ($folder in $folders) {
    if (Test-Path $folder) {
        Write-Host "Uploading folder: $folder ..." -ForegroundColor Cyan
        & scp $sshKeyArg -r "$folder" "${SSH_USER}@${VPS_IP}:$destPath"
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  OK: $folder uploaded" -ForegroundColor Green
        } else {
            Write-Host "  ERROR: $folder failed to upload" -ForegroundColor Red
        }
    } else {
        Write-Host "  SKIP: $folder not found locally" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "Upload completed!" -ForegroundColor Cyan
Write-Host "Destination on VPS: $destPath"
