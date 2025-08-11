#!/bin/bash
# Fix PostgreSQL authentication issues for Han Dating Bot
echo "🔧 Fixing PostgreSQL Authentication Issues"
echo "========================================"

# Step 1: Fix the bot_user password
echo "🔐 Step 1: Setting up bot_user with correct password..."
su - postgres -c "
psql << 'EOF'
-- Drop and recreate user with correct password
DROP USER IF EXISTS bot_user;
CREATE USER bot_user WITH PASSWORD 'bot_password';
ALTER USER bot_user CREATEDB;
ALTER USER bot_user SUPERUSER;

-- Ensure databases exist and are owned by bot_user
DROP DATABASE IF EXISTS han_dating_bot;
DROP DATABASE IF EXISTS dating_bot;
CREATE DATABASE han_dating_bot OWNER bot_user;
CREATE DATABASE dating_bot OWNER bot_user;

-- Grant all privileges
GRANT ALL PRIVILEGES ON DATABASE han_dating_bot TO bot_user;
GRANT ALL PRIVILEGES ON DATABASE dating_bot TO bot_user;

\q
EOF
"

# Step 2: Fix pg_hba.conf authentication
echo "🔐 Step 2: Configuring PostgreSQL authentication..."

# Find pg_hba.conf
PG_HBA_FILE=""
for config_file in /etc/postgresql/*/main/pg_hba.conf; do
    if [[ -f "\$config_file" ]]; then
        PG_HBA_FILE="\$config_file"
        break
    fi
done

if [[ -n "\$PG_HBA_FILE" ]]; then
    echo "📁 Found config: \$PG_HBA_FILE"
    
    # Backup current config
    cp "\$PG_HBA_FILE" "\$PG_HBA_FILE.backup.$(date +%Y%m%d_%H%M%S)"
    
    # Remove old bot_user entries
    grep -v "bot_user" "\$PG_HBA_FILE" > "\$PG_HBA_FILE.tmp"
    mv "\$PG_HBA_FILE.tmp" "\$PG_HBA_FILE"
    
    # Add new authentication entries for bot_user
    cat >> "\$PG_HBA_FILE" << 'EOF'

# Han Dating Bot authentication
local   all             bot_user                                md5
host    all             bot_user        127.0.0.1/32            md5
host    all             bot_user        ::1/128                 md5
EOF

    echo "✅ Updated pg_hba.conf authentication"
else
    echo "❌ Could not find pg_hba.conf file"
fi

# Step 3: Also setup postgres user password (fallback)
echo "🔐 Step 3: Setting up postgres user as fallback..."
su - postgres -c "
psql << 'EOF'
ALTER USER postgres PASSWORD 'bot_password';
\q
EOF
"

# Step 4: Restart PostgreSQL
echo "🔄 Step 4: Restarting PostgreSQL..."
systemctl restart postgresql

# Step 5: Verify connections
echo "🧪 Step 5: Testing connections..."

sleep 3

# Test with bot_user
echo "Testing bot_user connection..."
if PGPASSWORD=bot_password psql -U bot_user -d han_dating_bot -h localhost -c "SELECT 'bot_user connection OK' as test;" 2>/dev/null; then
    echo "✅ bot_user connection: SUCCESS"
else
    echo "❌ bot_user connection: FAILED"
fi

# Test with postgres user (fallback)
echo "Testing postgres user connection..."
if PGPASSWORD=bot_password psql -U postgres -d postgres -h localhost -c "SELECT 'postgres connection OK' as test;" 2>/dev/null; then
    echo "✅ postgres user connection: SUCCESS"
else
    echo "❌ postgres user connection: FAILED"
fi

# Step 6: Update environment variables if needed
echo "📝 Step 6: Environment variables check..."
echo "Current database environment variables:"
echo "DB_USER=\${DB_USER:-'not set'}"
echo "DB_PASSWORD=\${DB_PASSWORD:-'not set'}"
echo "DATABASE_USER=\${DATABASE_USER:-'not set'}"
echo "DATABASE_PASSWORD=\${DATABASE_PASSWORD:-'not set'}"

echo ""
echo "🎉 PostgreSQL Authentication Fix Complete!"
echo "========================================"
echo "✅ bot_user created with password 'bot_password'"
echo "✅ postgres user password set to 'bot_password'"
echo "✅ Databases: han_dating_bot, dating_bot"
echo "✅ Authentication configured"
echo ""
echo "🚀 Try running your bot now:"
echo "cd /root/dating-cheater"
echo "python3 main.py"
echo ""
echo "🔍 Manual test commands:"
echo "PGPASSWORD=bot_password psql -U bot_user -d han_dating_bot -h localhost"
echo "PGPASSWORD=bot_password psql -U postgres -d postgres -h localhost"
