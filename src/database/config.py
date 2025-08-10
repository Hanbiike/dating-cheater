"""
Database Configuration Management

Centralizes database configuration with support for multiple environments
and secure credential management. Integrates with existing Config system.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from pathlib import Path

from src.config.config import Config


@dataclass
class DatabaseConfig:
    """Database configuration with environment support"""
    
    # PostgreSQL connection settings
    host: str = field(default="localhost")
    port: int = field(default=5432)
    database: str = field(default="dating_bot")
    username: str = field(default="bot_user")
    password: str = field(default="")
    
    # Connection pool settings
    min_pool_size: int = field(default=5)
    max_pool_size: int = field(default=20)
    pool_timeout: int = field(default=30)
    pool_recycle: int = field(default=3600)
    pool_pre_ping: bool = field(default=True)
    
    # Performance settings
    command_timeout: int = field(default=30)
    server_side_cursors: bool = field(default=True)
    prepared_statement_cache_size: int = field(default=100)
    
    # SSL settings
    ssl_mode: str = field(default="prefer")  # disable, allow, prefer, require
    ssl_cert_file: Optional[str] = field(default=None)
    ssl_key_file: Optional[str] = field(default=None)
    ssl_ca_file: Optional[str] = field(default=None)
    
    # Migration settings
    migration_timeout: int = field(default=300)
    migration_lock_timeout: int = field(default=60)
    migration_table: str = field(default="alembic_version")
    
    # Environment-specific overrides
    environment: str = field(default="development")
    
    def __post_init__(self):
        """Load configuration from environment and config files"""
        self._load_from_config()
        self._load_from_environment()
        self._validate_configuration()
    
    def _load_from_config(self):
        """Load database settings from main config"""
        try:
            config = Config()
            
            # Load basic connection settings
            if hasattr(config, 'DATABASE_HOST'):
                self.host = config.DATABASE_HOST
            if hasattr(config, 'DATABASE_PORT'):
                self.port = int(config.DATABASE_PORT)
            if hasattr(config, 'DATABASE_NAME'):
                self.database = config.DATABASE_NAME
            if hasattr(config, 'DATABASE_USER'):
                self.username = config.DATABASE_USER
            if hasattr(config, 'DATABASE_PASSWORD'):
                self.password = config.DATABASE_PASSWORD
                
            # Load environment
            if hasattr(config, 'ENVIRONMENT'):
                self.environment = config.ENVIRONMENT
                
        except Exception as e:
            print(f"Warning: Could not load database config from main config: {e}")
    
    def _load_from_environment(self):
        """Load configuration from environment variables"""
        
        # Connection settings
        self.host = os.getenv('DB_HOST', self.host)
        self.port = int(os.getenv('DB_PORT', str(self.port)))
        self.database = os.getenv('DB_NAME', self.database)
        self.username = os.getenv('DB_USER', self.username)
        self.password = os.getenv('DB_PASSWORD', self.password)
        
        # Pool settings
        self.min_pool_size = int(os.getenv('DB_MIN_POOL_SIZE', str(self.min_pool_size)))
        self.max_pool_size = int(os.getenv('DB_MAX_POOL_SIZE', str(self.max_pool_size)))
        self.pool_timeout = int(os.getenv('DB_POOL_TIMEOUT', str(self.pool_timeout)))
        
        # Performance settings
        self.command_timeout = int(os.getenv('DB_COMMAND_TIMEOUT', str(self.command_timeout)))
        
        # SSL settings
        self.ssl_mode = os.getenv('DB_SSL_MODE', self.ssl_mode)
        self.ssl_cert_file = os.getenv('DB_SSL_CERT_FILE', self.ssl_cert_file)
        self.ssl_key_file = os.getenv('DB_SSL_KEY_FILE', self.ssl_key_file)
        self.ssl_ca_file = os.getenv('DB_SSL_CA_FILE', self.ssl_ca_file)
        
        # Environment
        self.environment = os.getenv('ENVIRONMENT', self.environment)
    
    def _validate_configuration(self):
        """Validate configuration settings"""
        if not self.host:
            raise ValueError("Database host cannot be empty")
        
        if not (1 <= self.port <= 65535):
            raise ValueError(f"Invalid database port: {self.port}")
        
        if not self.database:
            raise ValueError("Database name cannot be empty")
        
        if not self.username:
            raise ValueError("Database username cannot be empty")
        
        if self.min_pool_size <= 0:
            raise ValueError("Minimum pool size must be positive")
        
        if self.max_pool_size <= self.min_pool_size:
            raise ValueError("Maximum pool size must be greater than minimum")
        
        if self.ssl_mode not in ['disable', 'allow', 'prefer', 'require']:
            raise ValueError(f"Invalid SSL mode: {self.ssl_mode}")
    
    def get_dsn(self, async_driver: bool = True) -> str:
        """
        Generate database connection string
        
        Args:
            async_driver: If True, use asyncpg format; if False, use psycopg2 format
        """
        if async_driver:
            # asyncpg format
            protocol = "postgresql+asyncpg" if self._needs_sqlalchemy_protocol() else "postgresql"
        else:
            # psycopg2 format
            protocol = "postgresql+psycopg2" if self._needs_sqlalchemy_protocol() else "postgresql"
        
        # Build basic DSN
        dsn = f"{protocol}://{self.username}"
        
        if self.password:
            dsn += f":{self.password}"
        
        dsn += f"@{self.host}:{self.port}/{self.database}"
        
        # Add SSL parameters if needed
        if self.ssl_mode != "prefer":  # prefer is default
            dsn += f"?sslmode={self.ssl_mode}"
            
            if self.ssl_cert_file:
                dsn += f"&sslcert={self.ssl_cert_file}"
            if self.ssl_key_file:
                dsn += f"&sslkey={self.ssl_key_file}"
            if self.ssl_ca_file:
                dsn += f"&sslrootcert={self.ssl_ca_file}"
        
        return dsn
    
    def _needs_sqlalchemy_protocol(self) -> bool:
        """Check if SQLAlchemy protocol specification is needed"""
        # This can be expanded based on usage context
        return False
    
    def get_asyncpg_config(self) -> Dict[str, Any]:
        """Get configuration dictionary for asyncpg.create_pool()"""
        config = {
            'host': self.host,
            'port': self.port,
            'database': self.database,
            'user': self.username,
            'command_timeout': self.command_timeout,
            'server_settings': {
                'application_name': f'dating_bot_{self.environment}'
            }
        }
        
        if self.password:
            config['password'] = self.password
            
        # SSL configuration
        if self.ssl_mode != "disable":
            ssl_context = self._build_ssl_context()
            if ssl_context:
                config['ssl'] = ssl_context
        
        return config
    
    def get_sqlalchemy_config(self) -> Dict[str, Any]:
        """Get configuration dictionary for SQLAlchemy engine"""
        return {
            'url': self.get_dsn(async_driver=True),
            'pool_size': self.max_pool_size,
            'max_overflow': 0,  # Don't allow overflow connections
            'pool_timeout': self.pool_timeout,
            'pool_recycle': self.pool_recycle,
            'pool_pre_ping': self.pool_pre_ping,
            'echo': self.environment == "development",  # Log SQL in development
            'future': True  # Use SQLAlchemy 2.0 style
        }
    
    def _build_ssl_context(self):
        """Build SSL context if SSL files are provided"""
        if not any([self.ssl_cert_file, self.ssl_key_file, self.ssl_ca_file]):
            return None
            
        import ssl
        
        context = ssl.create_default_context()
        
        # Set SSL mode
        if self.ssl_mode == "require":
            context.check_hostname = False
            context.verify_mode = ssl.CERT_REQUIRED
        elif self.ssl_mode == "prefer":
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        
        # Load certificates
        if self.ssl_cert_file and self.ssl_key_file:
            if Path(self.ssl_cert_file).exists() and Path(self.ssl_key_file).exists():
                context.load_cert_chain(self.ssl_cert_file, self.ssl_key_file)
        
        if self.ssl_ca_file and Path(self.ssl_ca_file).exists():
            context.load_verify_locations(self.ssl_ca_file)
        
        return context
    
    def get_environment_config(self) -> Dict[str, Any]:
        """Get environment-specific configuration overrides"""
        configs = {
            'development': {
                'pool_size': 5,
                'echo': True,
                'auto_commit': True
            },
            'testing': {
                'pool_size': 2,
                'echo': False,
                'auto_commit': True,
                'isolation_level': 'AUTOCOMMIT'
            },
            'staging': {
                'pool_size': 10,
                'echo': False,
                'pool_pre_ping': True
            },
            'production': {
                'pool_size': 20,
                'echo': False,
                'pool_pre_ping': True,
                'pool_recycle': 3600
            }
        }
        
        return configs.get(self.environment, configs['development'])
    
    def __repr__(self) -> str:
        """Safe string representation without password"""
        return (f"DatabaseConfig(host='{self.host}', port={self.port}, "
                f"database='{self.database}', username='{self.username}', "
                f"environment='{self.environment}')")


@dataclass 
class RedisConfig:
    """Redis caching configuration"""
    
    host: str = field(default="localhost")
    port: int = field(default=6379)
    db: int = field(default=0)
    password: Optional[str] = field(default=None)
    
    # Connection pool settings
    max_connections: int = field(default=50)
    retry_on_timeout: bool = field(default=True)
    health_check_interval: int = field(default=30)
    
    # Performance settings
    socket_keepalive: bool = field(default=True)
    socket_keepalive_options: Dict[str, int] = field(default_factory=lambda: {})
    
    # Cache TTL settings (seconds)
    default_ttl: int = field(default=3600)  # 1 hour
    user_cache_ttl: int = field(default=1800)  # 30 minutes
    config_cache_ttl: int = field(default=7200)  # 2 hours
    analytics_cache_ttl: int = field(default=300)  # 5 minutes
    
    def __post_init__(self):
        """Load Redis configuration from environment"""
        self._load_from_environment()
    
    def _load_from_environment(self):
        """Load Redis settings from environment variables"""
        self.host = os.getenv('REDIS_HOST', self.host)
        self.port = int(os.getenv('REDIS_PORT', str(self.port)))
        self.db = int(os.getenv('REDIS_DB', str(self.db)))
        self.password = os.getenv('REDIS_PASSWORD', self.password)
        
        self.max_connections = int(os.getenv('REDIS_MAX_CONNECTIONS', str(self.max_connections)))
        self.default_ttl = int(os.getenv('REDIS_DEFAULT_TTL', str(self.default_ttl)))
    
    def get_redis_url(self) -> str:
        """Generate Redis connection URL"""
        url = f"redis://"
        
        if self.password:
            url += f":{self.password}@"
        
        url += f"{self.host}:{self.port}/{self.db}"
        
        return url
    
    def get_aioredis_config(self) -> Dict[str, Any]:
        """Get configuration for aioredis connection"""
        config = {
            'host': self.host,
            'port': self.port,
            'db': self.db,
            'max_connections': self.max_connections,
            'retry_on_timeout': self.retry_on_timeout,
            'health_check_interval': self.health_check_interval,
            'socket_keepalive': self.socket_keepalive
        }
        
        if self.password:
            config['password'] = self.password
            
        if self.socket_keepalive_options:
            config['socket_keepalive_options'] = self.socket_keepalive_options
        
        return config


def load_database_config() -> DatabaseConfig:
    """
    Factory function to load database configuration
    with environment detection and validation
    """
    return DatabaseConfig()


def load_redis_config() -> RedisConfig:
    """
    Factory function to load Redis configuration
    with environment detection and validation
    """
    return RedisConfig()


def get_alembic_config(db_config: DatabaseConfig) -> Dict[str, Any]:
    """
    Generate Alembic configuration for database migrations
    
    Args:
        db_config: Database configuration instance
        
    Returns:
        Dictionary with Alembic configuration
    """
    return {
        'script_location': 'database/migrations',
        'sqlalchemy.url': db_config.get_dsn(async_driver=False),  # Alembic uses sync
        'version_table': db_config.migration_table,
        'version_table_schema': None,
        'compare_type': True,
        'compare_server_default': True,
        'render_as_batch': True,  # For SQLite compatibility during testing
        'transaction_per_migration': True,
        'target_metadata': None  # Will be set by migration environment
    }
