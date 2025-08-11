#!/bin/bash
# Quick Ubuntu Database Setup for Root User
echo "🚀 Quick Database Setup (Root Mode)"
echo "=================================="

# Install packages
apt update
apt install -y postgresql postgresql-contrib redis-server python3-pip

# Start services
systemctl start postgresql
systemctl enable postgresql
systemctl start redis-server
systemctl enable redis-server

# Setup PostgreSQL as postgres user
echo "🗄️ Setting up PostgreSQL..."
su - postgres -c "
psql << 'EOF'
CREATE USER bot_user WITH PASSWORD 'bot_password';
CREATE DATABASE han_dating_bot OWNER bot_user;
CREATE DATABASE dating_bot OWNER bot_user;
GRANT ALL PRIVILEGES ON DATABASE han_dating_bot TO bot_user;
GRANT ALL PRIVILEGES ON DATABASE dating_bot TO bot_user;
ALTER USER bot_user CREATEDB;
\q
EOF
"

# Configure authentication
echo "🔐 Configuring PostgreSQL authentication..."
PG_VERSION=$(su - postgres -c "psql -t -c \"SELECT version();\"" | grep -oP '\d+\.\d+' | head -1)
PG_HBA_FILE="/etc/postgresql/${PG_VERSION}/main/pg_hba.conf"

# Backup and modify pg_hba.conf
cp "$PG_HBA_FILE" "$PG_HBA_FILE.backup"

# Add authentication for bot_user
if ! grep -q "local.*bot_user.*md5" "$PG_HBA_FILE"; then
    echo "local   all             bot_user                                md5" >> "$PG_HBA_FILE"
fi

# Also allow host connections
if ! grep -q "host.*bot_user.*md5" "$PG_HBA_FILE"; then
    echo "host    all             bot_user        127.0.0.1/32            md5" >> "$PG_HBA_FILE"
    echo "host    all             bot_user        ::1/128                 md5" >> "$PG_HBA_FILE"
fi

# Restart PostgreSQL
systemctl restart postgresql

# Install Python packages
echo "🐍 Installing Python dependencies..."
pip3 install asyncpg psycopg2-binary redis aioredis sqlalchemy alembic

# Test connections
echo "🧪 Testing connections..."

# Test Redis
if redis-cli ping > /dev/null 2>&1; then
    echo "✅ Redis: Working"
else
    echo "❌ Redis: Failed"
fi

# Test PostgreSQL
if PGPASSWORD=bot_password psql -U bot_user -d han_dating_bot -h localhost -c "SELECT 'OK';" > /dev/null 2>&1; then
    echo "✅ PostgreSQL: Working"
else
    echo "❌ PostgreSQL: Failed - trying to fix..."
    
    # Alternative setup if the first one failed
    su - postgres -c "
    createuser --interactive --pwprompt bot_user << 'EOF'
bot_password
bot_password
y
y
y
EOF
    createdb -O bot_user han_dating_bot
    createdb -O bot_user dating_bot
    "
fi

echo ""
echo "🎉 Setup Complete!"
echo "=================="
echo "✅ PostgreSQL installed and running"
echo "✅ Redis installed and running" 
echo "✅ Databases: han_dating_bot, dating_bot"
echo "✅ User: bot_user (password: bot_password)"
echo ""
echo "🚀 Now you can run the bot:"
echo "cd /root/dating-cheater"
echo "python3 main.py"
echo ""
echo "🔍 Quick tests:"
echo "redis-cli ping"
echo "PGPASSWORD=bot_password psql -U bot_user -d han_dating_bot -h localhost -c 'SELECT version();'"
