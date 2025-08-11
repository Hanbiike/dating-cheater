#!/bin/bash
# Complete Ubuntu Database Setup for Han Dating Bot
set -e

echo "🚀 Han Dating Bot - Ubuntu Database Setup"
echo "========================================="

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo "⚠️ Running as root. This is not recommended but will proceed..."
   echo "🔧 Note: Python packages will be installed system-wide"
   sleep 3
   SUDO_CMD=""
   PIP_CMD="pip3"
else
   echo "✅ Running as regular user with sudo access"
   SUDO_CMD="sudo"
   PIP_CMD="pip"
fi

# Update system
echo "📋 Step 1: Updating package list..."
${SUDO_CMD} apt update

# Install PostgreSQL and Redis
echo "📦 Step 2: Installing PostgreSQL and Redis..."
${SUDO_CMD} apt install -y postgresql postgresql-contrib redis-server

# Start services
echo "🔄 Step 3: Starting services..."
${SUDO_CMD} systemctl start postgresql
${SUDO_CMD} systemctl enable postgresql
${SUDO_CMD} systemctl start redis-server
${SUDO_CMD} systemctl enable redis-server

# Setup PostgreSQL
echo "🗄️ Step 4: Setting up PostgreSQL databases and user..."
if [[ $EUID -eq 0 ]]; then
    # Running as root - use su to switch to postgres user
    su - postgres -c "psql << 'EOF'
-- Create user if not exists
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'bot_user') THEN
        CREATE USER bot_user WITH PASSWORD 'bot_password';
    END IF;
END
\$\$;

-- Create databases if not exist
SELECT 'CREATE DATABASE han_dating_bot OWNER bot_user' 
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'han_dating_bot')\gexec

SELECT 'CREATE DATABASE dating_bot OWNER bot_user' 
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'dating_bot')\gexec

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE han_dating_bot TO bot_user;
GRANT ALL PRIVILEGES ON DATABASE dating_bot TO bot_user;
ALTER USER bot_user CREATEDB;
\q
EOF"
else
    # Running as regular user
    sudo -u postgres psql << EOF
-- Create user if not exists
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'bot_user') THEN
        CREATE USER bot_user WITH PASSWORD 'bot_password';
    END IF;
END
\$\$;

-- Create databases if not exist
SELECT 'CREATE DATABASE han_dating_bot OWNER bot_user' 
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'han_dating_bot')\gexec

SELECT 'CREATE DATABASE dating_bot OWNER bot_user' 
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'dating_bot')\gexec

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE han_dating_bot TO bot_user;
GRANT ALL PRIVILEGES ON DATABASE dating_bot TO bot_user;
ALTER USER bot_user CREATEDB;
\q
EOF
fi

# Configure PostgreSQL authentication
echo "🔐 Step 5: Configuring PostgreSQL authentication..."

# Find the correct PostgreSQL version and config path
if [[ $EUID -eq 0 ]]; then
    PG_VERSION=$(su - postgres -c "psql -t -c \"SHOW server_version;\"" | grep -oP '\d+\.\d+' | head -1)
else
    PG_VERSION=$(sudo -u postgres psql -t -c "SHOW server_version;" | grep -oP '\d+\.\d+' | head -1)
fi

# Find the actual config file
PG_HBA_FILE=""
for version_dir in /etc/postgresql/*/main/; do
    if [[ -f "${version_dir}pg_hba.conf" ]]; then
        PG_HBA_FILE="${version_dir}pg_hba.conf"
        break
    fi
done

# Fallback: try common locations
if [[ -z "$PG_HBA_FILE" ]]; then
    for possible_path in \
        "/etc/postgresql/12/main/pg_hba.conf" \
        "/etc/postgresql/13/main/pg_hba.conf" \
        "/etc/postgresql/14/main/pg_hba.conf" \
        "/etc/postgresql/15/main/pg_hba.conf" \
        "/var/lib/pgsql/data/pg_hba.conf"; do
        if [[ -f "$possible_path" ]]; then
            PG_HBA_FILE="$possible_path"
            break
        fi
    done
fi

if [[ -z "$PG_HBA_FILE" ]]; then
    echo "⚠️ Could not find pg_hba.conf file. Skipping authentication configuration."
    echo "PostgreSQL should still work with default authentication."
else
    echo "📁 Found PostgreSQL config: $PG_HBA_FILE"
    
    # Backup original config
    ${SUDO_CMD} cp "$PG_HBA_FILE" "$PG_HBA_FILE.backup.$(date +%Y%m%d_%H%M%S)"

    # Add bot_user authentication line if not exists
    if ! ${SUDO_CMD} grep -q "local.*bot_user.*md5" "$PG_HBA_FILE"; then
        echo "local   all             bot_user                                md5" | ${SUDO_CMD} tee -a "$PG_HBA_FILE"
        echo "✅ Added local authentication for bot_user"
    else
        echo "✅ Local authentication for bot_user already configured"
    fi
    
    # Add host authentication lines if not exists
    if ! ${SUDO_CMD} grep -q "host.*bot_user.*127.0.0.1.*md5" "$PG_HBA_FILE"; then
        echo "host    all             bot_user        127.0.0.1/32            md5" | ${SUDO_CMD} tee -a "$PG_HBA_FILE"
        echo "✅ Added IPv4 host authentication for bot_user"
    fi
    
    if ! ${SUDO_CMD} grep -q "host.*bot_user.*::1.*md5" "$PG_HBA_FILE"; then
        echo "host    all             bot_user        ::1/128                 md5" | ${SUDO_CMD} tee -a "$PG_HBA_FILE"
        echo "✅ Added IPv6 host authentication for bot_user"
    fi
fi

# Restart PostgreSQL
echo "🔄 Step 6: Restarting PostgreSQL..."
${SUDO_CMD} systemctl restart postgresql

# Install Python dependencies
echo "🐍 Step 7: Installing Python dependencies..."
${PIP_CMD} install asyncpg psycopg2-binary redis aioredis sqlalchemy alembic

# Test connections
echo "🧪 Step 8: Testing connections..."

# Test PostgreSQL
echo "Testing PostgreSQL connection..."
if PGPASSWORD=bot_password psql -U bot_user -d han_dating_bot -h localhost -c "SELECT 'PostgreSQL connection successful!' as status;" 2>/dev/null; then
    echo "✅ PostgreSQL connection: SUCCESS"
else
    echo "❌ PostgreSQL connection: FAILED"
    echo "You may need to configure authentication manually"
fi

# Test Redis
echo "Testing Redis connection..."
if redis-cli ping > /dev/null 2>&1; then
    echo "✅ Redis connection: SUCCESS"
else
    echo "❌ Redis connection: FAILED"
fi

# Display status
echo ""
echo "📊 Service Status:"
echo "=================="
${SUDO_CMD} systemctl status postgresql --no-pager -l
echo ""
${SUDO_CMD} systemctl status redis-server --no-pager -l

echo ""
echo "🎉 Ubuntu Database Setup Complete!"
echo "=================================="
echo "✅ PostgreSQL installed and configured"
echo "✅ Redis installed and running"
echo "✅ Databases created: han_dating_bot, dating_bot"
echo "✅ User created: bot_user"
echo "✅ Python dependencies installed"
echo ""
echo "🚀 You can now run your bot:"
echo "cd /path/to/gpt-5-dater"
echo "python main.py"
echo ""
echo "🔍 Troubleshooting:"
echo "- Check logs: tail -f bot.log"
echo "- Test PostgreSQL: PGPASSWORD=bot_password psql -U bot_user -d han_dating_bot -h localhost"
echo "- Test Redis: redis-cli ping"
