#!/bin/bash
# Complete Ubuntu Database Setup for Han Dating Bot
set -e

echo "🚀 Han Dating Bot - Ubuntu Database Setup"
echo "========================================="

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo "❌ Don't run this script as root. Run as regular user with sudo access."
   exit 1
fi

# Update system
echo "📋 Step 1: Updating package list..."
sudo apt update

# Install PostgreSQL and Redis
echo "📦 Step 2: Installing PostgreSQL and Redis..."
sudo apt install -y postgresql postgresql-contrib redis-server

# Start services
echo "🔄 Step 3: Starting services..."
sudo systemctl start postgresql
sudo systemctl enable postgresql
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Setup PostgreSQL
echo "🗄️ Step 4: Setting up PostgreSQL databases and user..."
sudo -u postgres psql << EOF
CREATE USER bot_user WITH PASSWORD 'bot_password';
CREATE DATABASE han_dating_bot OWNER bot_user;
CREATE DATABASE dating_bot OWNER bot_user;
GRANT ALL PRIVILEGES ON DATABASE han_dating_bot TO bot_user;
GRANT ALL PRIVILEGES ON DATABASE dating_bot TO bot_user;
\q
EOF

# Configure PostgreSQL authentication
echo "🔐 Step 5: Configuring PostgreSQL authentication..."
PG_VERSION=$(sudo -u postgres psql -t -c "SELECT version();" | grep -oP '\d+\.\d+' | head -1)
PG_HBA_FILE="/etc/postgresql/${PG_VERSION}/main/pg_hba.conf"

# Backup original config
sudo cp "$PG_HBA_FILE" "$PG_HBA_FILE.backup"

# Add bot_user authentication line
if ! sudo grep -q "local.*bot_user.*md5" "$PG_HBA_FILE"; then
    echo "local   all             bot_user                                md5" | sudo tee -a "$PG_HBA_FILE"
fi

# Restart PostgreSQL
echo "🔄 Step 6: Restarting PostgreSQL..."
sudo systemctl restart postgresql

# Install Python dependencies
echo "🐍 Step 7: Installing Python dependencies..."
pip install asyncpg psycopg2-binary redis aioredis sqlalchemy alembic

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
sudo systemctl status postgresql --no-pager -l
echo ""
sudo systemctl status redis-server --no-pager -l

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
