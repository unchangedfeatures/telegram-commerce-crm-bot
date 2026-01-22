#!/bin/bash

# Fix PostgreSQL authentication - parxpress deployment
# This script fixes the "Ident authentication failed" error

echo "=========================================="
echo "  Fixing PostgreSQL Authentication"
echo "=========================================="
echo ""

# Find pg_hba.conf
PG_HBA="/var/lib/pgsql/data/pg_hba.conf"

if [ ! -f "$PG_HBA" ]; then
    echo "ERROR: pg_hba.conf not found at $PG_HBA"
    echo "Searching for pg_hba.conf..."
    PG_HBA=$(find /var -name "pg_hba.conf" 2>/dev/null | head -1)
    if [ -z "$PG_HBA" ]; then
        echo "ERROR: Could not find pg_hba.conf"
        exit 1
    fi
    echo "Found at: $PG_HBA"
fi

echo "PostgreSQL config: $PG_HBA"
echo ""

# Backup the original file
cp "$PG_HBA" "$PG_HBA.backup"
echo "✓ Backup created: $PG_HBA.backup"

# Fix the authentication method from 'ident' to 'md5' or 'scram-sha-256'
echo "Fixing authentication method..."

# For local connections (unix socket)
sed -i 's/^local.*postgres.*ident/local   all             postgres                                    md5/' "$PG_HBA"
sed -i 's/^local.*all.*all.*ident/local   all             all                                         md5/' "$PG_HBA"

# For tcp connections
sed -i 's/^host.*all.*all.*127.0.0.1.*32.*ident/host    all             all             127.0.0.1\/32            md5/' "$PG_HBA"
sed -i 's/^host.*all.*all.*::1.*128.*ident/host    all             all             ::1\/128                 md5/' "$PG_HBA"

echo "✓ Authentication method updated to md5"
echo ""

# Show the updated lines
echo "Updated pg_hba.conf entries:"
grep -E "^(local|host)" "$PG_HBA" | head -10
echo ""

# Restart PostgreSQL
echo "Restarting PostgreSQL..."
systemctl restart postgresql

sleep 2

# Check if PostgreSQL is running
if systemctl is-active --quiet postgresql; then
    echo "✓ PostgreSQL restarted successfully"
else
    echo "ERROR: PostgreSQL failed to restart"
    exit 1
fi

echo ""
echo "=========================================="
echo "  PostgreSQL Authentication Fixed!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Restart the bot service:"
echo "     systemctl restart parxpress-bot"
echo ""
echo "  2. Check bot logs:"
echo "     journalctl -u parxpress-bot -f"
echo ""
