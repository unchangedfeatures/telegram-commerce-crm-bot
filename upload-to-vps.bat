@echo off
REM ============================================================
REM ParXpress - File upload to VPS via SCP
REM For Windows 10+
REM ============================================================

setlocal enabledelayedexpansion

echo.
echo ============================================================
echo   ParXpress - Upload files to VPS
echo ============================================================
echo.

REM Check parameters
if "%~1"=="" (
    echo.
    echo Usage: upload-to-vps.bat ^<VPS_IP^> [SSH_USERNAME]
    echo.
    echo Example: upload-to-vps.bat 79.143.90.63 parxpress
    echo Example: upload-to-vps.bat 192.168.1.100 root
    echo.
    echo Parameters:
    echo   VPS_IP - IP address of your VPS server
    echo   SSH_USERNAME - username for connection (default: root)
    echo.
    exit /b 1
)

set VPS_IP=%~1
set SSH_USER=%~2
if "%SSH_USER%"=="" set SSH_USER=root

echo Connection parameters:
echo   VPS IP: %VPS_IP%
echo   SSH User: %SSH_USER%
echo.

REM Check SSH
where ssh > nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: SSH not found!
    echo.
    echo Solution: Install OpenSSH (built-in Windows 10+)
    echo   Or use PuTTY/WinSCP to upload files manually
    echo.
    exit /b 1
)

echo OK: SSH found
echo.

REM Get current project directory
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo Uploading files to VPS...
echo.

REM List of files and folders to upload
set FILES=admin_app.py bot.py config.py bot_instance.py cache_helpers.py cache_manager.py helpers.py monitoring.py notification_queue.py notifications.py states.py requirements.txt requirements_admin.txt .env.example

REM Upload files
for %%F in (%FILES%) do (
    if exist "%%F" (
        echo Uploading %%F...
        scp -q "%%F" "%SSH_USER%@%VPS_IP%:/home/%SSH_USER%/app/" 2>nul
        if !ERRORLEVEL! EQU 0 (
            echo   OK: %%F
        ) else (
            echo   ERROR: %%F
        )
    ) else (
        echo   SKIP: %%F not found
    )
)

echo.
echo Uploading folders...
echo.

REM Upload folders
for %%D in (handlers database keyboards middleware templates texts static) do (
    if exist "%%D\" (
        echo Uploading %%D...
        scp -rq "%%D\" "%SSH_USER%@%VPS_IP%:/home/%SSH_USER%/app/" 2>nul
        if !ERRORLEVEL! EQU 0 (
            echo   OK: %%D/
        ) else (
            echo   ERROR: %%D/
        )
    )
)

echo.
echo ============================================================
echo   Upload completed!
echo ============================================================
echo.
echo Next steps on VPS:
echo   1. Connect to VPS:
echo      ssh %SSH_USER%@%VPS_IP%
echo.
echo   2. Go to folder:
echo      cd /home/%SSH_USER%/app
echo.
echo   3. Run deployment:
echo      sudo bash deploy-almalinux.sh
echo.
pause
