# ParXpress - Upload files to VPS via SCP
# PowerShell version (recommended for Windows)
# Usage: .\upload-to-vps.ps1 79.143.90.63 root
# With SSH key: .\upload-to-vps.ps1 79.143.90.63 root "C:\Users\YourName\.ssh\id_rsa_parxpress"

param(
    [string]$VPS_IP = "",
    [string]$SSH_USER = "root",
    [string]$SSH_KEY = ""
)

if ([string]::IsNullOrEmpty($VPS_IP)) {
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  ParXpress - Upload files to VPS" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Usage: .\upload-to-vps.ps1 <VPS_IP> [SSH_USERNAME]" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Yellow
    Write-Host "  .\upload-to-vps.ps1 79.143.90.63 parxpress"
    Write-Host "  .\upload-to-vps.ps1 192.168.1.100 root"
    Write-Host ""
    exit 1
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  ParXpress - Upload files to VPS" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Connection parameters:" -ForegroundColor Yellow
Write-Host "  VPS IP: $VPS_IP"
Write-Host "  SSH User: $SSH_USER"
Write-Host ""

# Check if SSH is available
$sshCheck = cmd /c "where ssh 2>nul"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: SSH not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Solution:" -ForegroundColor Yellow
    Write-Host "  - Install OpenSSH (built-in Windows 10+)"
    Write-Host "  - Or use PuTTY/WinSCP to upload files manually"
    Write-Host ""
    exit 1
}

Write-Host "OK: SSH found" -ForegroundColor Green
Write-Host ""

# Get script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "Setting up VPS..." -ForegroundColor Cyan
Write-Host ""

# First, create the destination directory on VPS
Write-Host "Creating /root/app directory on VPS..." -ForegroundColor Yellow
$sshKeyArg_early = @()
$defaultKey = "$env:USERPROFILE\.ssh\id_rsa_parxpress"
if (Test-Path $defaultKey) {
    $sshKeyArg_early = @("-i", $defaultKey)
}

& ssh $sshKeyArg_early "${SSH_USER}@${VPS_IP}" "mkdir -p /root/app && chmod 755 /root/app && echo 'Directory ready'" 2>$null
Write-Host "  OK: /root/app created" -ForegroundColor Green
Write-Host ""

Write-Host "Uploading files to VPS..." -ForegroundColor Cyan
Write-Host ""

# Prepare SSH key argument if provided
$sshKeyArg = @()
if (-not [string]::IsNullOrEmpty($SSH_KEY) -and (Test-Path $SSH_KEY)) {
    $sshKeyArg = @("-i", $SSH_KEY)
    Write-Host "Using SSH key: $SSH_KEY" -ForegroundColor Green
} else {
    # Try default key location
    $defaultKey = "$env:USERPROFILE\.ssh\id_rsa_parxpress"
    if (Test-Path $defaultKey) {
        $sshKeyArg = @("-i", $defaultKey)
        Write-Host "Using SSH key: $defaultKey" -ForegroundColor Green
    } else {
        Write-Host "No SSH key found - will use password authentication" -ForegroundColor Yellow
        Write-Host "To setup SSH key run: .\setup-ssh-key.ps1 $VPS_IP $SSH_USER" -ForegroundColor Gray
    }
}
Write-Host ""

# Files to upload
$files = @(
    "admin_app.py",
    "bot.py",
    "config.py",
    "bot_instance.py",
    "cache_helpers.py",
    "cache_manager.py",
    "helpers.py",
    "monitoring.py",
    "notification_queue.py",
    "notifications.py",
    "states.py",
    "requirements.txt",
    "requirements_admin.txt",
    ".env.example",
    ".env",
    "deploy-almalinux.sh"
)

# Upload files
foreach ($file in $files) {
    if (Test-Path $file) {
        Write-Host "Uploading $file..." -ForegroundColor Yellow
        # Use /root/app for root user
        $destPath = if ($SSH_USER -eq "root") { "/root/app/" } else { "/home/${SSH_USER}/app/" }
        & scp $sshKeyArg -q "$file" "${SSH_USER}@${VPS_IP}:${destPath}" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  OK: $file" -ForegroundColor Green
        } else {
            Write-Host "  ERROR: $file" -ForegroundColor Red
        }
    } else {
        Write-Host "  SKIP: $file not found" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "Uploading folders..." -ForegroundColor Cyan
Write-Host ""

# Folders to upload
$folders = @("handlers", "database", "keyboards", "middleware", "templates", "texts", "static")

foreach ($folder in $folders) {
    if (Test-Path $folder) {
        Write-Host "Uploading $folder..." -ForegroundColor Yellow
        # Use /root/app for root user
        $destPath = if ($SSH_USER -eq "root") { "/root/app/" } else { "/home/${SSH_USER}/app/" }
        & scp $sshKeyArg -rq "$folder\" "${SSH_USER}@${VPS_IP}:${destPath}" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  OK: $folder/" -ForegroundColor Green
        } else {
            Write-Host "  WARNING: $folder/ - will be created if missing" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  SKIP: $folder not found locally" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Upload completed!" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps on VPS:" -ForegroundColor Yellow
Write-Host "  1. Connect to VPS:"
Write-Host "     ssh ${SSH_USER}@${VPS_IP}"
Write-Host ""
Write-Host "  2. Go to folder:"
Write-Host "     cd /home/${SSH_USER}/app"
Write-Host ""
Write-Host "  3. Run deployment:"
Write-Host "     sudo bash deploy-almalinux.sh"
Write-Host ""
