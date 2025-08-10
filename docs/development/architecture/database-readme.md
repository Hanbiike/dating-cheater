# Database Migration System

This directory contains the database migration system for the Han Dating Bot multi-bot support feature.

## Overview

The migration system converts the bot from JSON file storage to PostgreSQL database with multi-bot support, including:

- **Schema Migration**: Creates tables, indexes, partitions, and security policies
- **Data Migration**: Converts existing JSON data to PostgreSQL format
- **Security System**: Row Level Security (RLS) with role-based access control
- **Audit System**: Comprehensive logging and monitoring
- **Performance Optimization**: Hash partitioning and indexes

## Quick Start

### 1. Setup Environment

```bash
# Setup database configuration
python database/cli.py setup

# Or manually create .env file with:
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=han_dating_bot
DATABASE_USER=postgres
DATABASE_PASSWORD=your_password
MULTI_BOT_ENABLED=true
```

### 2. Install Dependencies

```bash
pip install asyncpg psycopg2-binary
```

### 3. Run Migration

```bash
# Check database status
python database/cli.py status

# Run complete migration (schema + data)
python database/cli.py migrate

# Or run dry-run first
python database/cli.py migrate --dry-run
```

### 4. Verify Migration

```bash
# Verify migration completeness
python database/cli.py verify

# Check database status
python database/cli.py status
```

## Migration Scripts

The migration system consists of 5 SQL scripts that must be executed in order:

1. **001_create_base_schema.sql** - Creates core tables with hash partitioning
2. **002_create_security_roles.sql** - Sets up RLS and database roles
3. **003_create_audit_system.sql** - Creates audit logging system
4. **004_partitioning_optimization.sql** - Adds performance indexes and views
5. **005_json_data_migration.sql** - Creates data migration utilities

## Command Line Interface

### Migration Commands

```bash
# Run all migrations
python database/cli.py migrate

# Schema only
python database/cli.py migrate --schema-only

# Data only  
python database/cli.py migrate --data-only

# Dry run
python database/cli.py migrate --dry-run
```

### Verification Commands

```bash
# Check migration status
python database/cli.py verify

# Show database status
python database/cli.py status

# Verify specific bot
python database/cli.py verify --bot-id <bot_id>
```

### Rollback Commands

```bash
# Rollback specific migration
python database/cli.py rollback 001
```

## Python Migration Tools

### DatabaseMigrator Class

Handles SQL schema migrations:

```python
from database.migrate import DatabaseMigrator

migrator = DatabaseMigrator(database_url)
await migrator.run_migrations(dry_run=False)
```

### DataMigrator Class

Handles JSON to PostgreSQL data migration:

```python
from database.migrate import DataMigrator

data_migrator = DataMigrator(database_url, data_directory)
await data_migrator.run_data_migration()
```

## Database Schema

### Core Tables

- **bots** - Bot configurations and metadata
- **girls_profiles** - User profiles (partitioned by bot_id)
- **conversations** - Conversation metadata (partitioned by bot_id)
- **messages** - Individual messages (partitioned by bot_id)
- **bot_metrics** - Performance metrics (partitioned by bot_id)
- **security_audit_log** - Security and audit events

### Partitioning Strategy

All user data tables are hash partitioned by `bot_id` with 10 partitions:

```sql
-- Example partition
CREATE TABLE girls_profiles_0 PARTITION OF girls_profiles 
FOR VALUES WITH (MODULUS 10, REMAINDER 0);
```

### Security Model

Row Level Security (RLS) isolates data between bots:

```sql
-- Bot can only access their own data
CREATE POLICY bot_isolation ON girls_profiles 
FOR ALL TO bot_role 
USING (bot_id = current_setting('app.current_bot_id'));
```

### Database Roles

- **super_admin_role** - Full database access
- **admin_role** - Cross-bot administration
- **bot_role** - Single bot access (RLS enforced)
- **app_base_role** - Base permissions

## Migration Process

### Phase 1: Schema Setup

1. Create base tables with partitioning
2. Setup security roles and RLS policies  
3. Create audit system with triggers
4. Add performance indexes and views
5. Create migration utility functions

### Phase 2: Data Migration

1. Create default bot entry
2. Migrate girls_data/*.json to girls_profiles
3. Migrate conversations/*.json to conversations/messages
4. Verify data integrity
5. Generate migration report

### Phase 3: Verification

1. Check migration completeness
2. Verify data integrity
3. Test security policies
4. Generate final report

## Monitoring and Maintenance

### Built-in Functions

```sql
-- Cleanup old audit logs (90 days)
SELECT cleanup_old_audit_logs(90);

-- Update table statistics
SELECT update_table_statistics();

-- Check partition health
SELECT * FROM check_partition_health();

-- Security health check
SELECT * FROM security_health_check();

-- Maintenance reminders
SELECT * FROM maintenance_reminder();
```

### Performance Views

```sql
-- Bot activity overview
SELECT * FROM bot_activity_summary;

-- Daily metrics
SELECT * FROM daily_metrics_summary;

-- Recent activity
SELECT * FROM recent_activity LIMIT 50;
```

## Troubleshooting

### Common Issues

1. **Connection Failed**
   ```bash
   # Check database is running
   systemctl status postgresql
   
   # Verify connection settings
   psql -h localhost -U postgres -d han_dating_bot
   ```

2. **Migration Failed**
   ```bash
   # Check migration logs
   python database/cli.py status
   
   # Rollback if needed
   python database/cli.py rollback <migration_id>
   ```

3. **Data Migration Issues**
   ```bash
   # Run verification
   python database/cli.py verify
   
   # Check specific bot data
   python database/cli.py verify --bot-id <bot_id>
   ```

### Recovery

```bash
# Reset database (DANGER: DELETES ALL DATA)
dropdb han_dating_bot
createdb han_dating_bot

# Re-run migrations
python database/cli.py migrate
```

## Development

### Adding New Migrations

1. Create new SQL file: `006_your_migration.sql`
2. Add description header: `-- Description: Your migration description`
3. Test with dry-run: `python database/cli.py migrate --dry-run`
4. Apply: `python database/cli.py migrate`

### Testing

```bash
# Test on development database
DATABASE_NAME=han_dating_bot_test python database/cli.py migrate

# Verify test migration
DATABASE_NAME=han_dating_bot_test python database/cli.py verify
```

## Production Deployment

1. **Backup existing data**
   ```bash
   cp -r girls_data/ backups/
   cp -r conversations/ backups/
   ```

2. **Setup production database**
   ```bash
   createdb han_dating_bot_prod
   ```

3. **Run migration**
   ```bash
   DATABASE_NAME=han_dating_bot_prod python database/cli.py migrate
   ```

4. **Verify and monitor**
   ```bash
   DATABASE_NAME=han_dating_bot_prod python database/cli.py verify
   ```

For more information, see the main project documentation.
