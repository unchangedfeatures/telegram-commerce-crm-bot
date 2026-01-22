#!/bin/bash

# Script to initialize ParXpress project for deployment
set -e

echo "🚀 Initializing ParXpress for deployment..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    echo "📋 Creating .env from .env.example..."
    cp .env.example .env
    echo "⚠️  Please edit .env with your configuration"
    exit 1
fi

# Check required environment variables
required_vars=("TOKEN" "ADMIN_ID" "CHAT_ID" "ORDERS_CHAT_ID" "USERNAME" "SUPPORT")

echo "✅ Checking environment variables..."
for var in "${required_vars[@]}"; do
    if ! grep -q "^${var}=" .env; then
        echo "❌ Missing $var in .env"
        exit 1
    fi
done

echo "✅ All required environment variables found"

# Create uploads directory
mkdir -p static/uploads
chmod 755 static/uploads

echo "✅ Created uploads directory"

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✅ Python version: $python_version"

# Install dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt

echo "✅ Dependencies installed"

# Run migrations (if using Alembic)
# alembic upgrade head

echo "🎉 ParXpress is ready for deployment!"
echo ""
echo "📝 Next steps:"
echo "1. Start with Docker Compose: docker-compose up -d"
echo "2. Or run manually: python bot.py & python -m flask run -h 0.0.0.0"
echo ""
