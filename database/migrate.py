#!/usr/bin/env python3
"""
Database Migration Runner
Manages the execution of database migrations for multi-bot support.
"""

import os
import sys
import asyncio
import asyncpg
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from config import load_config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DatabaseMigrator:
    """Handles database migrations with rollback support."""
    
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.migrations_dir = Path(__file__).parent / "migrations"
        
    async def connect(self) -> asyncpg.Connection:
        """Create database connection."""
        try:
            conn = await asyncpg.connect(self.db_url)
            logger.info("Connected to database successfully")
            return conn
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
            
    async def ensure_migration_table(self, conn: asyncpg.Connection):
        """Ensure migration tracking table exists."""
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS migration_log (
                id SERIAL PRIMARY KEY,
                migration_id VARCHAR(10) UNIQUE NOT NULL,
                description TEXT,
                applied_at TIMESTAMP DEFAULT NOW(),
                rollback_sql TEXT
            )
        """)
        logger.info("Migration tracking table ready")
        
    async def get_applied_migrations(self, conn: asyncpg.Connection) -> List[str]:
        """Get list of already applied migrations."""
        rows = await conn.fetch("SELECT migration_id FROM migration_log ORDER BY id")
        return [row['migration_id'] for row in rows]
        
    async def get_available_migrations(self) -> List[Dict[str, str]]:
        """Get list of available migration files."""
        migrations = []
        for file_path in sorted(self.migrations_dir.glob("*.sql")):
            migration_id = file_path.stem.split('_')[0]
            migrations.append({
                'id': migration_id,
                'file': str(file_path),
                'description': self._extract_description(file_path)
            })
        return migrations
        
    def _extract_description(self, file_path: Path) -> str:
        """Extract description from migration file header."""
        try:
            with open(file_path, 'r') as f:
                lines = f.readlines()[:10]  # Check first 10 lines
                for line in lines:
                    if line.strip().startswith('-- Description:'):
                        return line.strip().replace('-- Description:', '').strip()
        except Exception:
            pass
        return f"Migration from {file_path.name}"
        
    async def apply_migration(self, conn: asyncpg.Connection, migration: Dict[str, str]) -> bool:
        """Apply a single migration."""
        try:
            logger.info(f"Applying migration {migration['id']}: {migration['description']}")
            
            # Read migration file
            with open(migration['file'], 'r') as f:
                sql_content = f.read()
                
            # Execute migration in transaction
            async with conn.transaction():
                await conn.execute(sql_content)
                
            logger.info(f"Migration {migration['id']} applied successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to apply migration {migration['id']}: {e}")
            return False
            
    async def run_migrations(self, dry_run: bool = False) -> bool:
        """Run all pending migrations."""
        conn = await self.connect()
        
        try:
            await self.ensure_migration_table(conn)
            
            applied = await self.get_applied_migrations(conn)
            available = await self.get_available_migrations()
            
            pending = [m for m in available if m['id'] not in applied]
            
            if not pending:
                logger.info("No pending migrations")
                return True
                
            logger.info(f"Found {len(pending)} pending migrations")
            
            if dry_run:
                logger.info("DRY RUN - Would apply the following migrations:")
                for migration in pending:
                    logger.info(f"  {migration['id']}: {migration['description']}")
                return True
                
            # Apply migrations
            for migration in pending:
                success = await self.apply_migration(conn, migration)
                if not success:
                    logger.error(f"Migration {migration['id']} failed - stopping")
                    return False
                    
            logger.info("All migrations applied successfully")
            return True
            
        finally:
            await conn.close()
            
    async def rollback_migration(self, migration_id: str) -> bool:
        """Rollback a specific migration (if rollback SQL exists)."""
        conn = await self.connect()
        
        try:
            # Get rollback SQL
            row = await conn.fetchrow(
                "SELECT rollback_sql FROM migration_log WHERE migration_id = $1",
                migration_id
            )
            
            if not row or not row['rollback_sql']:
                logger.error(f"No rollback SQL found for migration {migration_id}")
                return False
                
            logger.info(f"Rolling back migration {migration_id}")
            
            async with conn.transaction():
                await conn.execute(row['rollback_sql'])
                await conn.execute(
                    "DELETE FROM migration_log WHERE migration_id = $1",
                    migration_id
                )
                
            logger.info(f"Migration {migration_id} rolled back successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to rollback migration {migration_id}: {e}")
            return False
        finally:
            await conn.close()

class DataMigrator:
    """Handles data migration from JSON files to PostgreSQL."""
    
    def __init__(self, db_url: str, data_dir: Path):
        self.db_url = db_url
        self.data_dir = data_dir
        
    async def create_default_bot(self, conn: asyncpg.Connection) -> str:
        """Create default bot entry for existing data."""
        # Read current config to get bot info
        config = load_config()
        
        bot_data = {
            'name': 'Han Dating Bot (Migrated)',
            'telegram_token': config.bot_token,
            'telegram_bot_username': getattr(config, 'bot_username', None),
            'owner_telegram_id': getattr(config, 'admin_id', None),
            'status': 'active',
            'config': json.dumps({
                'migrated_from': 'json_files',
                'migration_date': datetime.now().isoformat(),
                'original_data_location': str(self.data_dir)
            })
        }
        
        # Insert bot and return bot_id
        bot_id = await conn.fetchval("""
            INSERT INTO bots (name, telegram_token, telegram_bot_username, owner_telegram_id, status, config)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING bot_id
        """, *bot_data.values())
        
        logger.info(f"Created default bot with ID: {bot_id}")
        return str(bot_id)
        
    async def migrate_girls_data(self, conn: asyncpg.Connection, bot_id: str) -> int:
        """Migrate girls_data/*.json files to girls_profiles table."""
        girls_dir = self.data_dir / "girls_data"
        if not girls_dir.exists():
            logger.warning("No girls_data directory found")
            return 0
            
        migrated_count = 0
        
        for json_file in girls_dir.glob("*.json"):
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                    
                # Map JSON structure to database schema
                profile_data = {
                    'bot_id': bot_id,
                    'telegram_id': data.get('chat_id'),
                    'chat_id': data.get('chat_id'),
                    'name': data.get('name', ''),
                    'last_activity': data.get('last_activity'),
                    'message_count': data.get('message_count', 0),
                    'summary': json.dumps(data.get('summary', {})),
                    'profile': json.dumps(data.get('profile', {})),
                    'previous_response_id': data.get('previous_response_id'),
                    'additional_data': json.dumps({
                        'source_file': json_file.name,
                        'migrated_at': datetime.now().isoformat()
                    })
                }
                
                # Insert into database
                await conn.execute("""
                    INSERT INTO girls_profiles 
                    (bot_id, telegram_id, chat_id, name, last_activity, message_count, 
                     summary, profile, previous_response_id, additional_data)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (bot_id, telegram_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        last_activity = EXCLUDED.last_activity,
                        message_count = EXCLUDED.message_count,
                        summary = EXCLUDED.summary,
                        profile = EXCLUDED.profile,
                        previous_response_id = EXCLUDED.previous_response_id,
                        additional_data = EXCLUDED.additional_data,
                        updated_at = NOW()
                """, *profile_data.values())
                
                migrated_count += 1
                logger.debug(f"Migrated profile from {json_file.name}")
                
            except Exception as e:
                logger.error(f"Failed to migrate {json_file.name}: {e}")
                
        logger.info(f"Migrated {migrated_count} girl profiles")
        return migrated_count
        
    async def migrate_conversations(self, conn: asyncpg.Connection, bot_id: str) -> int:
        """Migrate conversations/*.json files to conversations and messages tables."""
        conversations_dir = self.data_dir / "conversations"
        if not conversations_dir.exists():
            logger.warning("No conversations directory found")
            return 0
            
        migrated_conversations = 0
        migrated_messages = 0
        
        for json_file in conversations_dir.glob("*.json"):
            try:
                with open(json_file, 'r') as f:
                    messages_data = json.load(f)
                    
                if not messages_data:
                    continue
                    
                # Extract chat_id from filename
                chat_id = int(json_file.stem)
                
                # Create conversation entry
                conversation_id = await conn.fetchval("""
                    INSERT INTO conversations (bot_id, chat_id, title, message_count)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (bot_id, chat_id) DO UPDATE SET
                        message_count = EXCLUDED.message_count,
                        updated_at = NOW()
                    RETURNING id
                """, bot_id, chat_id, f"Conversation {chat_id}", len(messages_data))
                
                # Link to girl profile if exists
                await conn.execute("""
                    UPDATE conversations SET girl_profile_id = (
                        SELECT id FROM girls_profiles 
                        WHERE bot_id = $1 AND chat_id = $2 
                        LIMIT 1
                    )
                    WHERE id = $3
                """, bot_id, chat_id, conversation_id)
                
                # Migrate messages
                for i, msg in enumerate(messages_data):
                    message_data = {
                        'conversation_id': conversation_id,
                        'bot_id': bot_id,
                        'sender_type': 'bot' if msg.get('direction') == 'out' else 'user',
                        'content': msg.get('text', ''),
                        'direction': msg.get('direction', 'in'),
                        'timestamp': msg.get('ts'),
                        'metadata': json.dumps({
                            'original_index': i,
                            'source_file': json_file.name
                        })
                    }
                    
                    await conn.execute("""
                        INSERT INTO messages 
                        (conversation_id, bot_id, sender_type, content, direction, timestamp, metadata)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """, *message_data.values())
                    
                    migrated_messages += 1
                    
                migrated_conversations += 1
                logger.debug(f"Migrated conversation from {json_file.name}")
                
            except Exception as e:
                logger.error(f"Failed to migrate conversation {json_file.name}: {e}")
                
        logger.info(f"Migrated {migrated_conversations} conversations with {migrated_messages} messages")
        return migrated_conversations
        
    async def run_data_migration(self) -> bool:
        """Run complete data migration from JSON files."""
        conn = await asyncpg.connect(self.db_url)
        
        try:
            logger.info("Starting data migration from JSON files")
            
            # Create default bot
            bot_id = await self.create_default_bot(conn)
            
            # Migrate data
            async with conn.transaction():
                girls_count = await self.migrate_girls_data(conn, bot_id)
                conversations_count = await self.migrate_conversations(conn, bot_id)
                
            logger.info(f"Data migration completed: {girls_count} profiles, {conversations_count} conversations")
            return True
            
        except Exception as e:
            logger.error(f"Data migration failed: {e}")
            return False
        finally:
            await conn.close()

async def main():
    """Main migration runner."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Database Migration Runner')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be migrated without applying')
    parser.add_argument('--data-only', action='store_true', help='Run only data migration')
    parser.add_argument('--schema-only', action='store_true', help='Run only schema migration')
    parser.add_argument('--rollback', type=str, help='Rollback specific migration ID')
    
    args = parser.parse_args()
    
    # Load database URL from config
    config = load_config()
    db_url = getattr(config, 'database_url', None)
    
    if not db_url:
        logger.error("DATABASE_URL not found in configuration")
        return False
        
    success = True
    
    # Handle rollback
    if args.rollback:
        migrator = DatabaseMigrator(db_url)
        success = await migrator.rollback_migration(args.rollback)
        return success
        
    # Run schema migrations
    if not args.data_only:
        logger.info("Running schema migrations...")
        migrator = DatabaseMigrator(db_url)
        success = await migrator.run_migrations(dry_run=args.dry_run)
        
    # Run data migrations
    if success and not args.schema_only:
        logger.info("Running data migrations...")
        data_migrator = DataMigrator(db_url, Path(__file__).parent.parent)
        if not args.dry_run:
            success = await data_migrator.run_data_migration()
        else:
            logger.info("DRY RUN - Would migrate JSON data to database")
            
    if success:
        logger.info("✅ All migrations completed successfully")
    else:
        logger.error("❌ Migration failed")
        
    return success

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
