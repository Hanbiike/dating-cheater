#!/usr/bin/env python3
"""
Database Management CLI
Provides command-line interface for database operations.
"""

import argparse
import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from database.migrate import DatabaseMigrator, DataMigrator
from config import get_database_url

async def migrate_schema(args):
    """Run schema migrations."""
    print("🔄 Running schema migrations...")
    
    migrator = DatabaseMigrator(get_database_url())
    success = await migrator.run_migrations(dry_run=args.dry_run)
    
    if success:
        print("✅ Schema migrations completed successfully")
    else:
        print("❌ Schema migrations failed")
        return False
    
    return True

async def migrate_data(args):
    """Run data migration from JSON files."""
    print("🔄 Running data migration...")
    
    data_migrator = DataMigrator(get_database_url(), Path(project_root))
    
    if args.dry_run:
        print("🔍 DRY RUN - Would migrate JSON data to database")
        return True
    
    success = await data_migrator.run_data_migration()
    
    if success:
        print("✅ Data migration completed successfully")
    else:
        print("❌ Data migration failed")
        return False
    
    return True

async def rollback_migration(args):
    """Rollback a specific migration."""
    print(f"🔄 Rolling back migration {args.migration_id}...")
    
    migrator = DatabaseMigrator(get_database_url())
    success = await migrator.rollback_migration(args.migration_id)
    
    if success:
        print(f"✅ Migration {args.migration_id} rolled back successfully")
    else:
        print(f"❌ Failed to rollback migration {args.migration_id}")
        return False
    
    return True

async def verify_migration(args):
    """Verify migration completeness."""
    import asyncpg
    
    print("🔍 Verifying migration...")
    
    conn = await asyncpg.connect(get_database_url())
    
    try:
        # Get bot_id from args or find first bot
        bot_id = args.bot_id
        if not bot_id:
            row = await conn.fetchrow("SELECT bot_id FROM bots LIMIT 1")
            if row:
                bot_id = row['bot_id']
            else:
                print("❌ No bots found in database")
                return False
        
        # Run verification
        print(f"Verifying migration for bot: {bot_id}")
        
        # Check completeness
        completeness_rows = await conn.fetch(
            "SELECT * FROM verify_migration_completeness($1)", bot_id
        )
        
        print("\n📊 Migration Completeness:")
        for row in completeness_rows:
            status_emoji = "✅" if row['status'] == 'OK' else "⚠️" if row['status'] == 'WARNING' else "❌"
            print(f"  {status_emoji} {row['category']}: {row['actual_count']} ({row['status']})")
        
        # Check integrity
        integrity_rows = await conn.fetch(
            "SELECT * FROM check_migration_integrity($1)", bot_id
        )
        
        print("\n🔍 Data Integrity:")
        for row in integrity_rows:
            status_emoji = "✅" if row['status'] == 'OK' else "⚠️" if row['status'] == 'WARNING' else "❌"
            print(f"  {status_emoji} {row['check_name']}: {row['issue_count']} issues ({row['status']})")
        
        # Generate report
        report_rows = await conn.fetch(
            "SELECT * FROM generate_migration_report($1)", bot_id
        )
        
        print("\n📋 Migration Report:")
        current_section = None
        for row in report_rows:
            if row['section'] != current_section:
                current_section = row['section']
                print(f"\n{current_section}:")
            print(f"  {row['metric']}: {row['value']}")
        
        print("\n✅ Migration verification completed")
        
    finally:
        await conn.close()
    
    return True

async def status(args):
    """Show database status."""
    import asyncpg
    
    print("📊 Database Status")
    print("=" * 50)
    
    try:
        conn = await asyncpg.connect(get_database_url())
        
        # Check connection
        print("✅ Database connection: OK")
        
        # Check tables
        tables = await conn.fetch("""
            SELECT table_name, 
                   (SELECT COUNT(*) FROM information_schema.columns 
                    WHERE table_name = t.table_name AND table_schema = 'public') as column_count
            FROM information_schema.tables t
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        
        print(f"\n📋 Tables ({len(tables)}):")
        for table in tables:
            print(f"  • {table['table_name']} ({table['column_count']} columns)")
        
        # Check migrations
        try:
            migrations = await conn.fetch("""
                SELECT migration_id, description, applied_at
                FROM migration_log
                ORDER BY id
            """)
            
            print(f"\n🔄 Applied Migrations ({len(migrations)}):")
            for migration in migrations:
                print(f"  • {migration['migration_id']}: {migration['description']}")
                print(f"    Applied: {migration['applied_at'].strftime('%Y-%m-%d %H:%M:%S')}")
        except:
            print("\n⚠️  Migration log table not found")
        
        # Check bots
        try:
            bots = await conn.fetch("SELECT bot_id, name, status FROM bots")
            print(f"\n🤖 Bots ({len(bots)}):")
            for bot in bots:
                print(f"  • {bot['bot_id']}: {bot['name']} ({bot['status']})")
        except:
            print("\n⚠️  Bots table not found")
        
        await conn.close()
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False
    
    return True

async def handle_multibot_command(args):
    """Handle multi-bot management commands."""
    from multibot_manager import MultiBotManager, BotConfiguration
    from config import Config
    
    if args.multibot_command == 'start':
        return await start_multibot_manager(args)
    elif args.multibot_command == 'stop':
        return await stop_multibot_manager(args)
    elif args.multibot_command == 'status':
        return await multibot_status(args)
    elif args.multibot_command == 'list':
        return await list_bots(args)
    elif args.multibot_command == 'bot':
        return await handle_bot_command(args)
    else:
        print(f"Unknown multibot command: {args.multibot_command}")
        return False

async def start_multibot_manager(args):
    """Start Multi-Bot ProcessSupervisor."""
    print("🚀 Starting Multi-Bot ProcessSupervisor...")
    
    try:
        config = Config()
        manager = MultiBotManager(config)
        
        print("✅ Multi-Bot ProcessSupervisor started successfully")
        print("📊 Use 'python database/cli.py multibot status' to check status")
        
        # Start manager (this will run until interrupted)
        await manager.start()
        
    except KeyboardInterrupt:
        print("\n⏹️ Multi-Bot ProcessSupervisor stopped by user")
        return True
    except Exception as e:
        print(f"❌ Error starting Multi-Bot ProcessSupervisor: {e}")
        return False

async def stop_multibot_manager(args):
    """Stop Multi-Bot ProcessSupervisor."""
    print("⏹️ Stopping Multi-Bot ProcessSupervisor...")
    
    # TODO: Implement IPC communication to stop manager
    print("⚠️  Stop command not yet implemented - use Ctrl+C to stop")
    return True

async def multibot_status(args):
    """Show Multi-Bot Manager status."""
    print("📊 Multi-Bot Manager Status")
    print("=" * 50)
    
    # TODO: Implement IPC communication to get status
    print("⚠️  Status command not yet implemented")
    return True

async def list_bots(args):
    """List all bots."""
    print("🤖 Bot List")
    print("=" * 50)
    
    # TODO: Implement IPC communication to list bots
    print("⚠️  List command not yet implemented")
    return True

async def handle_bot_command(args):
    """Handle individual bot commands."""
    if args.bot_command == 'create':
        return await create_bot(args)
    elif args.bot_command == 'start':
        return await start_bot(args)
    elif args.bot_command == 'stop':
        return await stop_bot(args)
    elif args.bot_command == 'restart':
        return await restart_bot(args)
    else:
        print(f"Unknown bot command: {args.bot_command}")
        return False

async def create_bot(args):
    """Create new bot."""
    print(f"🤖 Creating bot: {args.bot_id}")
    
    # TODO: Implement IPC communication to create bot
    print("⚠️  Create bot command not yet implemented")
    return True

async def start_bot(args):
    """Start bot."""
    print(f"▶️ Starting bot: {args.bot_id}")
    
    # TODO: Implement IPC communication to start bot
    print("⚠️  Start bot command not yet implemented")
    return True

async def stop_bot(args):
    """Stop bot."""
    print(f"⏹️ Stopping bot: {args.bot_id}")
    
    # TODO: Implement IPC communication to stop bot
    print("⚠️  Stop bot command not yet implemented")
    return True

async def restart_bot(args):
    """Restart bot."""
    print(f"🔄 Restarting bot: {args.bot_id}")
    
    # TODO: Implement IPC communication to restart bot
    print("⚠️  Restart bot command not yet implemented")
    return True

async def setup_env(args):
    """Setup environment file with database configuration."""
    env_file = Path(project_root) / ".env"
    
    print("🔧 Setting up database environment...")
    
    # Read existing .env if it exists
    existing_vars = {}
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    existing_vars[key] = value
    
    # Database configuration prompts
    db_config = {
        'DATABASE_HOST': input(f"Database host [{existing_vars.get('DATABASE_HOST', 'localhost')}]: ").strip() or existing_vars.get('DATABASE_HOST', 'localhost'),
        'DATABASE_PORT': input(f"Database port [{existing_vars.get('DATABASE_PORT', '5432')}]: ").strip() or existing_vars.get('DATABASE_PORT', '5432'),
        'DATABASE_NAME': input(f"Database name [{existing_vars.get('DATABASE_NAME', 'han_dating_bot')}]: ").strip() or existing_vars.get('DATABASE_NAME', 'han_dating_bot'),
        'DATABASE_USER': input(f"Database user [{existing_vars.get('DATABASE_USER', 'postgres')}]: ").strip() or existing_vars.get('DATABASE_USER', 'postgres'),
        'DATABASE_PASSWORD': input(f"Database password [{existing_vars.get('DATABASE_PASSWORD', '')}]: ").strip() or existing_vars.get('DATABASE_PASSWORD', ''),
        'MULTI_BOT_ENABLED': input(f"Enable multi-bot support [y/N]: ").strip().lower().startswith('y'),
    }
    
    # Update existing vars
    existing_vars.update(db_config)
    existing_vars['MULTI_BOT_ENABLED'] = 'true' if db_config['MULTI_BOT_ENABLED'] else 'false'
    
    # Write updated .env
    with open(env_file, 'w') as f:
        f.write("# Han Dating Bot Configuration\n\n")
        f.write("# Database Configuration\n")
        for key, value in db_config.items():
            if key != 'MULTI_BOT_ENABLED':
                f.write(f"{key}={value}\n")
        f.write(f"MULTI_BOT_ENABLED={existing_vars['MULTI_BOT_ENABLED']}\n")
        
        f.write("\n# Other Configuration\n")
        for key, value in existing_vars.items():
            if not key.startswith('DATABASE_') and key != 'MULTI_BOT_ENABLED':
                f.write(f"{key}={value}\n")
    
    print(f"✅ Environment configuration saved to {env_file}")
    return True

def main():
    parser = argparse.ArgumentParser(description='Database Management CLI')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Migration commands
    migrate_parser = subparsers.add_parser('migrate', help='Run database migrations')
    migrate_parser.add_argument('--dry-run', action='store_true', help='Show what would be migrated without applying')
    migrate_parser.add_argument('--schema-only', action='store_true', help='Run only schema migrations')
    migrate_parser.add_argument('--data-only', action='store_true', help='Run only data migrations')
    
    # Rollback command
    rollback_parser = subparsers.add_parser('rollback', help='Rollback a migration')
    rollback_parser.add_argument('migration_id', help='Migration ID to rollback')
    
    # Verify command
    verify_parser = subparsers.add_parser('verify', help='Verify migration completeness')
    verify_parser.add_argument('--bot-id', help='Bot ID to verify (optional)')
    
    # Status command
    subparsers.add_parser('status', help='Show database status')
    
    # Setup command
    subparsers.add_parser('setup', help='Setup database environment configuration')
    
    # Multi-Bot Manager commands
    multibot_parser = subparsers.add_parser('multibot', help='Multi-Bot Manager operations')
    multibot_subparsers = multibot_parser.add_subparsers(dest='multibot_command', help='Multi-bot commands')
    
    # Start ProcessSupervisor
    multibot_subparsers.add_parser('start', help='Start Multi-Bot ProcessSupervisor')
    
    # Stop ProcessSupervisor
    stop_parser = multibot_subparsers.add_parser('stop', help='Stop Multi-Bot ProcessSupervisor')
    stop_parser.add_argument('--graceful', action='store_true', default=True, help='Graceful shutdown')
    
    # Status of ProcessSupervisor
    multibot_subparsers.add_parser('status', help='Show Multi-Bot Manager status')
    
    # Bot management commands
    bot_parser = multibot_subparsers.add_parser('bot', help='Individual bot management')
    bot_subparsers = bot_parser.add_subparsers(dest='bot_command', help='Bot operations')
    
    # Create bot
    create_bot_parser = bot_subparsers.add_parser('create', help='Create new bot')
    create_bot_parser.add_argument('bot_id', help='Unique bot identifier')
    create_bot_parser.add_argument('--token', required=True, help='Bot token')
    create_bot_parser.add_argument('--memory-limit', type=int, default=512, help='Memory limit in MB')
    
    # Start bot
    start_bot_parser = bot_subparsers.add_parser('start', help='Start bot')
    start_bot_parser.add_argument('bot_id', help='Bot identifier')
    
    # Stop bot
    stop_bot_parser = bot_subparsers.add_parser('stop', help='Stop bot')
    stop_bot_parser.add_argument('bot_id', help='Bot identifier')
    stop_bot_parser.add_argument('--force', action='store_true', help='Force stop')
    
    # Restart bot
    restart_bot_parser = bot_subparsers.add_parser('restart', help='Restart bot')
    restart_bot_parser.add_argument('bot_id', help='Bot identifier')
    
    # List bots
    multibot_subparsers.add_parser('list', help='List all bots')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Run the appropriate command
    try:
        if args.command == 'migrate':
            success = True
            if not args.data_only:
                success = asyncio.run(migrate_schema(args))
            if success and not args.schema_only:
                success = asyncio.run(migrate_data(args))
        elif args.command == 'rollback':
            success = asyncio.run(rollback_migration(args))
        elif args.command == 'verify':
            success = asyncio.run(verify_migration(args))
        elif args.command == 'status':
            success = asyncio.run(status(args))
        elif args.command == 'setup':
            success = asyncio.run(setup_env(args))
        elif args.command == 'multibot':
            success = asyncio.run(handle_multibot_command(args))
        else:
            print(f"Unknown command: {args.command}")
            success = False
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n⏹️  Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
