# ParXpress - Setup SSH keys for password-less login
# Removes need to enter password every time

param(
    [string]$VPS_IP = "",
    [string]$SSH_USER = "root",
    [string]$SSH_PASSWORD = ""
)

if ([string]::IsNullOrEmpty($VPS_IP)) {
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  ParXpress - Setup SSH Key Authentication" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "This script sets up SSH keys so you don't need to enter password" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Usage: .\setup-ssh-key.ps1 <VPS_IP> [SSH_USERNAME] [PASSWORD]" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Yellow
    Write-Host "  .\setup-ssh-key.ps1 79.143.90.63 root rootpasswordeasy"
    Write-Host "  .\setup-ssh-key.ps1 79.143.90.63 parxpress"
    Write-Host ""
    Write-Host "If you don't provide password, you'll be prompted to enter it" -ForegroundColor Gray
    Write-Host ""
    exit 1
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  ParXpress - SSH Key Setup" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# SSH folder
$sshDir = "$env:USERPROFILE\.ssh"
$keyPath = "$sshDir\id_rsa_parxpress"
$pubKeyPath = "$keyPath.pub"

# Create .ssh directory if it doesn't exist
if (-not (Test-Path $sshDir)) {
    Write-Host "Creating .ssh directory..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $sshDir -Force | Out-Null
    Write-Host "  OK: Directory created" -ForegroundColor Green
}

# Check if key already exists
if (Test-Path $keyPath) {
    Write-Host "SSH key already exists at: $keyPath" -ForegroundColor Yellow
    $response = Read-Host "Regenerate? (y/n)"
    if ($response -ne "y") {
        Write-Host "Using existing key" -ForegroundColor Gray
    } else {
        Remove-Item $keyPath -Force
        Remove-Item $pubKeyPath -Force
    }
}

# Generate key if doesn't exist
if (-not (Test-Path $keyPath)) {
    Write-Host "Generating SSH key..." -ForegroundColor Yellow
    
    # Generate key without passphrase
    # Use echo to pipe empty line for passphrase prompt
    $env:DISPLAY = ''
    echo '' | & ssh-keygen -t rsa -b 4096 -f "$keyPath" -N "" -C "parxpress@$VPS_IP" 2>$null
    
    if ($LASTEXITCODE -eq 0 -or (Test-Path $keyPath)) {
        Write-Host "  OK: Key generated" -ForegroundColor Green
        Write-Host "    Public key: $pubKeyPath" -ForegroundColor Gray
    } else {
        Write-Host "  ERROR: Could not generate key" -ForegroundColor Red
        Write-Host "  Trying alternative method..." -ForegroundColor Yellow
        
        # Alternative: use absolute path and simpler syntax
        & ssh-keygen -t rsa -b 4096 -f $keyPath -N '""' -C "parxpress@$VPS_IP" 2>$null
        
        if (-not (Test-Path $keyPath)) {
            Write-Host "  ERROR: Key generation failed" -ForegroundColor Red
            exit 1
        }
    }
}

Write-Host ""
Write-Host "Copying public key to VPS..." -ForegroundColor Cyan

# Get password if not provided
if ([string]::IsNullOrEmpty($SSH_PASSWORD)) {
    $credential = Get-Credential -UserName $SSH_USER -Message "Enter password for $SSH_USER@$VPS_IP"
    $SSH_PASSWORD = $credential.GetNetworkCredential().Password
}

# Use ssh-copy-id equivalent with scp
# First, try ssh-copy-id if available
$sshCopyIdCheck = cmd /c "where ssh-copy-id 2>nul"
if ($LASTEXITCODE -eq 0) {
    Write-Host "Using ssh-copy-id..." -ForegroundColor Yellow
    & ssh-copy-id -i "$pubKeyPath" "${SSH_USER}@${VPS_IP}" 2>$null
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  OK: Key copied" -ForegroundColor Green
    } else {
        Write-Host "  ERROR: Could not copy key" -ForegroundColor Red
        exit 1
    }
} else {
    # Fallback: use scp and ssh to append key manually
    Write-Host "Using manual method (scp + ssh)..." -ForegroundColor Yellow
    
    # Copy public key to VPS temp location
    Write-Host "Uploading key..." -ForegroundColor Gray
    & scp -q "$pubKeyPath" "${SSH_USER}@${VPS_IP}:/tmp/id_rsa_new.pub" 2>$null
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ERROR: Could not upload key" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "Setting up on VPS..." -ForegroundColor Gray
    # Create .ssh directory and add key
    & ssh "${SSH_USER}@${VPS_IP}" "mkdir -p ~/.ssh && cat /tmp/id_rsa_new.pub >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys && rm /tmp/id_rsa_new.pub" 2>$null
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  OK: Key configured" -ForegroundColor Green
    } else {
        Write-Host "  ERROR: Could not configure key on VPS" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "Testing connection..." -ForegroundColor Cyan

# Test SSH connection
& ssh -o StrictHostKeyChecking=no -o PasswordAuthentication=no -i "$keyPath" "${SSH_USER}@${VPS_IP}" "echo 'Connection successful'" 2>$null

if ($LASTEXITCODE -eq 0) {
    Write-Host "  OK: SSH key authentication working!" -ForegroundColor Green
} else {
    Write-Host "  WARNING: Connection test failed" -ForegroundColor Yellow
    Write-Host "  Try manually: ssh -i `"$keyPath`" ${SSH_USER}@${VPS_IP}" -ForegroundColor Gray
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  SSH Key Setup Complete!" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Now you can use upload without password:" -ForegroundColor Yellow
Write-Host "  .\upload-to-vps.ps1 $VPS_IP $SSH_USER"
Write-Host ""
Write-Host "Your private key is stored at:" -ForegroundColor Gray
Write-Host "  $keyPath"
Write-Host ""
Write-Host "IMPORTANT: Keep this file safe! Do NOT share it!" -ForegroundColor Red
Write-Host ""
