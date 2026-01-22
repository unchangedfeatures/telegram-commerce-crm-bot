@echo off
REM Script to initialize ParXpress project for deployment on Windows

echo Initializing ParXpress for deployment...

REM Check if .env exists
if not exist .env (
    echo .env file not found!
    echo Creating .env from .env.example...
    copy .env.example .env
    echo Please edit .env with your configuration
    exit /b 1
)

echo Checking environment variables...
findstr /R "^TOKEN=" .env >nul || (echo Missing TOKEN in .env & exit /b 1)
findstr /R "^ADMIN_ID=" .env >nul || (echo Missing ADMIN_ID in .env & exit /b 1)
findstr /R "^CHAT_ID=" .env >nul || (echo Missing CHAT_ID in .env & exit /b 1)
findstr /R "^ORDERS_CHAT_ID=" .env >nul || (echo Missing ORDERS_CHAT_ID in .env & exit /b 1)
findstr /R "^USERNAME=" .env >nul || (echo Missing USERNAME in .env & exit /b 1)
findstr /R "^SUPPORT=" .env >nul || (echo Missing SUPPORT in .env & exit /b 1)

echo All required environment variables found

REM Create uploads directory
if not exist static\uploads mkdir static\uploads

echo Created uploads directory

REM Check Python version
python --version

echo Installing dependencies...
pip install -r requirements.txt

echo.
echo ParXpress is ready for deployment!
echo.
echo Next steps:
echo 1. Run bot.py to start the Telegram bot
echo 2. Run admin_app.py to start the web admin panel
echo.
pause
