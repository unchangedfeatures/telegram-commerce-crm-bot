#!/bin/bash

# Reset PostgreSQL user password for parxpress
# This ensures the password in .env matches the database user password

echo "=========================================="
echo "  Resetting PostgreSQL User Password"
echo "=========================================="
echo ""

# Get the password from .env file
if [ -f /home/parxpress/app/.env ]; then
    DB_PASSWORD=$(grep "^DB_PASSWORD=" /home/parxpress/app/.env | cut -d '=' -f 2)
    DB_USER=$(grep "^DB_USER=" /home/parxpress/app/.env | cut -d '=' -f 2)
    DB_NAME=$(grep "^DB_NAME=" /home/parxpress/app/.env | cut -d '=' -f 2)
else
    echo "ERROR: .env file not found at /home/parxpress/app/.env"
    exit 1
fi

if [ -z "$DB_PASSWORD" ] || [ -z "$DB_USER" ] || [ -z "$DB_NAME" ]; then
    echo "ERROR: Could not read database configuration from .env"
    echo "Make sure DB_PASSWORD, DB_USER, and DB_NAME are set"
    exit 1
fi

echo "Database Configuration:"
echo "  User: $DB_USER"
echo "  Database: $DB_NAME"
echo "  Password: [hidden]"
echo ""

# Reset the user password and permissions
echo "Setting up PostgreSQL user..."

sudo -u postgres psql <<EOF
-- Drop user if exists to start fresh
DROP USER IF EXISTS "$DB_USER";

-- Create user with password
CREATE USER "$DB_USER" WITH PASSWORD '$DB_PASSWORD';

-- Grant necessary permissions
ALTER ROLE "$DB_USER" WITH CREATEDB;
GRANT CONNECT ON DATABASE "$DB_NAME" TO "$DB_USER";
GRANT USAGE ON SCHEMA public TO "$DB_USER";
GRANT CREATE ON SCHEMA public TO "$DB_USER";
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO "$DB_USER";
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO "$DB_USER";
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO "$DB_USER";

-- Default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO "$DB_USER";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO "$DB_USER";

EOF

if [ $? -eq 0 ]; then
    echo "✓ User '$DB_USER' created/updated successfully"
else
    echo "ERROR: Failed to create/update database user"
    exit 1
fi

echo ""
echo "Testing connection..."

# Test the connection
sudo -u postgres psql -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1;" 2>/dev/null

if [ $? -eq 0 ]; then
    echo "✓ Connection test passed"
else
    echo "WARNING: Connection test failed - check password and permissions"
fi

echo ""
echo "=========================================="
echo "  PostgreSQL User Reset Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Restart the bot:"
echo "     sudo systemctl restart parxpress-bot"
echo ""
echo "  2. Check logs:"
echo "     sudo journalctl -u parxpress-bot -f"
echo ""
