#!/bin/bash
# Ultra-simple PostgreSQL fix
echo "🚀 Ultra-Simple PostgreSQL Fix"

# Set passwords for both users
su - postgres -c "
psql << 'EOF'
ALTER USER postgres PASSWORD 'bot_password';
ALTER USER bot_user PASSWORD 'bot_password';
ALTER USER bot_user SUPERUSER;
\q
EOF
"

# Allow password authentication
echo "host all all 127.0.0.1/32 md5" >> /etc/postgresql/12/main/pg_hba.conf
echo "host all all ::1/128 md5" >> /etc/postgresql/12/main/pg_hba.conf

# Restart PostgreSQL
systemctl restart postgresql

echo "✅ Done! Both 'postgres' and 'bot_user' now have password 'bot_password'"
echo "Test: PGPASSWORD=bot_password psql -U bot_user -d han_dating_bot -h localhost"
