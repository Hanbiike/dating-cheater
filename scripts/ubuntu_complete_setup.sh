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
CREATE USER bot_user WITH PASSWORD 'bot_password';
CREATE DATABASE han_dating_bot OWNER bot_user;
CREATE DATABASE dating_bot OWNER bot_user;
GRANT ALL PRIVILEGES ON DATABASE han_dating_bot TO bot_user;
GRANT ALL PRIVILEGES ON DATABASE dating_bot TO bot_user;
\q
EOF"
else
    # Running as regular user
    sudo -u postgres psql << EOF
CREATE USER bot_user WITH PASSWORD 'bot_password';
CREATE DATABASE han_dating_bot OWNER bot_user;
CREATE DATABASE dating_bot OWNER bot_user;
GRANT ALL PRIVILEGES ON DATABASE han_dating_bot TO bot_user;
GRANT ALL PRIVILEGES ON DATABASE dating_bot TO bot_user;
\q
EOF
fi

# Configure PostgreSQL authentication
echo "🔐 Step 5: Configuring PostgreSQL authentication..."
if [[ $EUID -eq 0 ]]; then
    PG_VERSION=$(su - postgres -c "psql -t -c \"SELECT version();\"" | grep -oP '\d+\.\d+' | head -1)
else
    PG_VERSION=$(sudo -u postgres psql -t -c "SELECT version();" | grep -oP '\d+\.\d+' | head -1)
fi

PG_HBA_FILE="/etc/postgresql/${PG_VERSION}/main/pg_hba.conf"

# Backup original config
${SUDO_CMD} cp "$PG_HBA_FILE" "$PG_HBA_FILE.backup"

# Add bot_user authentication line
if ! ${SUDO_CMD} grep -q "local.*bot_user.*md5" "$PG_HBA_FILE"; then
    echo "local   all             bot_user                                md5" | ${SUDO_CMD} tee -a "$PG_HBA_FILE"
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
