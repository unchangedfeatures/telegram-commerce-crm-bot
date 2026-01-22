#!/bin/bash

# Fix PostgreSQL permissions for parxpress_user
# Uses sudo to connect as postgres user (no password needed)

echo "=========================================="
echo "  Fixing PostgreSQL Permissions"
echo "=========================================="
echo ""

DB_USER="parxpress_user"
DB_NAME="parxpress_db"

echo "Database: $DB_NAME"
echo "User: $DB_USER"
echo ""

# Connect as postgres superuser (sudo) and grant permissions
echo "Setting permissions on all tables..."

sudo -u postgres psql -d "$DB_NAME" <<'EOSQL'
-- Grant schema usage and creation
GRANT USAGE ON SCHEMA public TO "parxpress_user";
GRANT CREATE ON SCHEMA public TO "parxpress_user";

-- Grant all privileges on existing tables
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO "parxpress_user";

-- Grant all privileges on existing sequences (for auto-increment)
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO "parxpress_user";

-- Grant all privileges on existing functions
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO "parxpress_user";

-- Set default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO "parxpress_user";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO "parxpress_user";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO "parxpress_user";

-- Show what tables exist
\dt public.*;

EOSQL

echo ""
echo "✓ Permissions applied successfully"
echo ""
echo "=========================================="
echo "  PostgreSQL Permissions Fixed!"
echo "=========================================="
echo ""
echo "Restart the bot with:"
echo "  sudo systemctl restart parxpress-bot"
echo ""
