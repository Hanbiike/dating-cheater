#!/bin/bash
# Quick fix for existing PostgreSQL installation
echo "🔧 Quick PostgreSQL Fix for Han Dating Bot"
echo "=========================================="

# Test if PostgreSQL is running
if ! systemctl is-active --quiet postgresql; then
    echo "🔄 Starting PostgreSQL..."
    systemctl start postgresql
    systemctl enable postgresql
fi

# Test if Redis is running  
if ! systemctl is-active --quiet redis-server; then
    echo "🔄 Starting Redis..."
    systemctl start redis-server
    systemctl enable redis-server
fi

# Setup database and user
echo "🗄️ Setting up database..."
su - postgres -c "
psql << 'EOF'
-- Set password for bot_user if exists, or create user
DO \$\$
BEGIN
    IF EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'bot_user') THEN
        ALTER USER bot_user WITH PASSWORD 'bot_password';
        RAISE NOTICE 'Updated password for existing user bot_user';
    ELSE
        CREATE USER bot_user WITH PASSWORD 'bot_password';
        RAISE NOTICE 'Created new user bot_user';
    END IF;
END
\$\$;

-- Ensure user can create databases
ALTER USER bot_user CREATEDB;

-- Grant all privileges
GRANT ALL PRIVILEGES ON DATABASE han_dating_bot TO bot_user;
GRANT ALL PRIVILEGES ON DATABASE dating_bot TO bot_user;

\q
EOF
"

# Find and configure pg_hba.conf
echo "🔐 Configuring authentication..."
PG_HBA_FILE=""
for config_file in /etc/postgresql/*/main/pg_hba.conf; do
    if [[ -f "$config_file" ]]; then
        PG_HBA_FILE="$config_file"
        break
    fi
done

if [[ -n "$PG_HBA_FILE" ]]; then
    echo "📁 Found config: $PG_HBA_FILE"
    
    # Backup
    cp "$PG_HBA_FILE" "$PG_HBA_FILE.backup.$(date +%Y%m%d_%H%M%S)"
    
    # Add authentication lines
    if ! grep -q "local.*bot_user.*md5" "$PG_HBA_FILE"; then
        echo "local   all             bot_user                                md5" >> "$PG_HBA_FILE"
    fi
    
    if ! grep -q "host.*bot_user.*127.0.0.1.*md5" "$PG_HBA_FILE"; then
        echo "host    all             bot_user        127.0.0.1/32            md5" >> "$PG_HBA_FILE"
        echo "host    all             bot_user        ::1/128                 md5" >> "$PG_HBA_FILE"
    fi
    
    # Restart PostgreSQL
    systemctl restart postgresql
    echo "✅ PostgreSQL restarted"
else
    echo "⚠️ Could not find pg_hba.conf"
fi

# Install Python dependencies
echo "🐍 Installing Python dependencies..."
pip3 install asyncpg psycopg2-binary redis aioredis sqlalchemy alembic

# Test connections
echo "🧪 Testing connections..."

sleep 2

# Test Redis
if redis-cli ping > /dev/null 2>&1; then
    echo "✅ Redis: Working"
else
    echo "❌ Redis: Failed"
fi

# Test PostgreSQL
if PGPASSWORD=bot_password psql -U bot_user -d postgres -h localhost -c "SELECT 'OK';" > /dev/null 2>&1; then
    echo "✅ PostgreSQL: Working"
    
    # Test specific databases
    if PGPASSWORD=bot_password psql -U bot_user -d han_dating_bot -h localhost -c "SELECT 'han_dating_bot OK';" > /dev/null 2>&1; then
        echo "✅ Database han_dating_bot: Working"
    else
        echo "⚠️ Database han_dating_bot: Not accessible"
    fi
    
    if PGPASSWORD=bot_password psql -U bot_user -d dating_bot -h localhost -c "SELECT 'dating_bot OK';" > /dev/null 2>&1; then
        echo "✅ Database dating_bot: Working"
    else
        echo "⚠️ Database dating_bot: Not accessible"
    fi
else
    echo "❌ PostgreSQL: Connection failed"
    echo "Try: PGPASSWORD=bot_password psql -U bot_user -d postgres -h localhost"
fi

echo ""
echo "🎉 Quick Fix Complete!"
echo "===================="
echo "🚀 Try running your bot now:"
echo "cd /root/dating-cheater"
echo "python3 main.py"
