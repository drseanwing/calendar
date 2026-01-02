"""
Configuration Module
Centralizes all application configuration from environment variables
Provides validation and defaults for all settings
"""

import os
import logging
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """
    Application configuration class
    Loads all settings from environment variables with sensible defaults
    """
    
    # ========================================================================
    # Flask Configuration
    # ========================================================================
    FLASK_ENV = os.getenv('FLASK_ENV', 'production')
    FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    SECRET_KEY = os.getenv('SECRET_KEY', os.urandom(32).hex())
    
    # ========================================================================
    # Database Configuration
    # ========================================================================
    DATABASE_URL = os.getenv('DATABASE_URL')
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is required")
    
    # SQLAlchemy settings
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = FLASK_DEBUG
    SQLALCHEMY_POOL_SIZE = int(os.getenv('DB_POOL_SIZE', '10'))
    SQLALCHEMY_MAX_OVERFLOW = int(os.getenv('DB_MAX_OVERFLOW', '20'))
    SQLALCHEMY_POOL_RECYCLE = int(os.getenv('DB_POOL_RECYCLE', '3600'))
    
    # ========================================================================
    # CalDAV Server Configuration
    # ========================================================================
    CALDAV_URL = os.getenv('CALDAV_URL')
    if not CALDAV_URL:
        raise ValueError("CALDAV_URL environment variable is required")
    
    CALDAV_USERNAME = os.getenv('CALDAV_USERNAME')
    if not CALDAV_USERNAME:
        raise ValueError("CALDAV_USERNAME environment variable is required")
    
    CALDAV_PASSWORD = os.getenv('CALDAV_PASSWORD')
    if not CALDAV_PASSWORD:
        raise ValueError("CALDAV_PASSWORD environment variable is required")
    
    CALDAV_CALENDAR_NAME = os.getenv('CALDAV_CALENDAR_NAME', 'All Events')
    
    # CalDAV connection settings
    CALDAV_TIMEOUT = int(os.getenv('CALDAV_TIMEOUT', '30'))
    CALDAV_RETRY_ATTEMPTS = int(os.getenv('CALDAV_RETRY_ATTEMPTS', '3'))
    CALDAV_RETRY_DELAY = int(os.getenv('CALDAV_RETRY_DELAY', '2'))
    
    # ========================================================================
    # API Security Configuration
    # ========================================================================
    API_KEY = os.getenv('API_KEY')
    if not API_KEY:
        raise ValueError("API_KEY environment variable is required")
    
    # Allow multiple API keys (comma-separated for different sources)
    API_KEYS = [key.strip() for key in API_KEY.split(',')]
    
    # ========================================================================
    # Logging Configuration
    # ========================================================================
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
    LOG_FILE = os.getenv('LOG_FILE', '/app/logs/middleware.log')
    LOG_FORMAT = os.getenv(
        'LOG_FORMAT',
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    )
    LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
    
    # Create logs directory if it doesn't exist
    log_dir = Path(LOG_FILE).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Maximum log file size before rotation (in bytes)
    LOG_MAX_BYTES = int(os.getenv('LOG_MAX_BYTES', str(10 * 1024 * 1024)))  # 10MB
    LOG_BACKUP_COUNT = int(os.getenv('LOG_BACKUP_COUNT', '5'))
    
    # Console logging
    LOG_TO_CONSOLE = os.getenv('LOG_TO_CONSOLE', 'true').lower() == 'true'
    
    # ========================================================================
    # Sync Configuration
    # ========================================================================
    SYNC_BATCH_SIZE = int(os.getenv('SYNC_BATCH_SIZE', '50'))
    WEBHOOK_TIMEOUT = int(os.getenv('WEBHOOK_TIMEOUT', '30'))
    MAX_SYNC_RETRIES = int(os.getenv('MAX_SYNC_RETRIES', '3'))
    SYNC_RETRY_DELAY = int(os.getenv('SYNC_RETRY_DELAY', '5'))
    
    # Conflict resolution strategy
    CONFLICT_RESOLUTION = os.getenv('CONFLICT_RESOLUTION', 'last_write_wins')
    VALID_CONFLICT_STRATEGIES = ['last_write_wins', 'priority_based', 'manual']
    
    if CONFLICT_RESOLUTION not in VALID_CONFLICT_STRATEGIES:
        raise ValueError(
            f"Invalid CONFLICT_RESOLUTION: {CONFLICT_RESOLUTION}. "
            f"Must be one of {VALID_CONFLICT_STRATEGIES}"
        )
    
    # Event deduplication
    ENABLE_DEDUPLICATION = os.getenv('ENABLE_DEDUPLICATION', 'true').lower() == 'true'
    
    # Maximum event age to sync (0 = no limit)
    MAX_EVENT_AGE_DAYS = int(os.getenv('MAX_EVENT_AGE_DAYS', '0'))
    
    # ========================================================================
    # Source Calendar Priorities (for conflict resolution)
    # ========================================================================
    SOURCE_PRIORITY_M365_TENANT1 = int(os.getenv('SOURCE_PRIORITY_M365_TENANT1', '5'))
    SOURCE_PRIORITY_M365_TENANT2 = int(os.getenv('SOURCE_PRIORITY_M365_TENANT2', '5'))
    SOURCE_PRIORITY_ICLOUD = int(os.getenv('SOURCE_PRIORITY_ICLOUD', '3'))
    
    @classmethod
    def get_source_priority(cls, source_id: str) -> int:
        """
        Get priority for a given source calendar ID
        
        Args:
            source_id: Source calendar identifier
            
        Returns:
            Priority value (1-10, higher = higher priority)
        """
        priority_map = {
            'm365-tenant1': cls.SOURCE_PRIORITY_M365_TENANT1,
            'm365-tenant2': cls.SOURCE_PRIORITY_M365_TENANT2,
            'icloud': cls.SOURCE_PRIORITY_ICLOUD,
        }
        return priority_map.get(source_id, 5)  # Default priority: 5
    
    # ========================================================================
    # Timezone Configuration
    # ========================================================================
    TIMEZONE = os.getenv('TZ', 'Australia/Brisbane')
    
    # ========================================================================
    # Performance and Resource Limits
    # ========================================================================
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', str(16 * 1024 * 1024)))  # 16MB
    REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', '60'))
    
    # ========================================================================
    # Monitoring and Alerts
    # ========================================================================
    ENABLE_METRICS = os.getenv('ENABLE_METRICS', 'false').lower() == 'true'
    ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', '')
    
    # SMTP configuration for alerts
    SMTP_HOST = os.getenv('SMTP_HOST', '')
    SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
    SMTP_USERNAME = os.getenv('SMTP_USERNAME', '')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
    SMTP_USE_TLS = os.getenv('SMTP_USE_TLS', 'true').lower() == 'true'
    
    # ========================================================================
    # Development and Testing
    # ========================================================================
    RECREATE_DB = os.getenv('RECREATE_DB', 'false').lower() == 'true'
    
    @classmethod
    def validate(cls) -> bool:
        """
        Validate all configuration settings
        
        Returns:
            True if configuration is valid
            
        Raises:
            ValueError: If any required configuration is invalid
        """
        # Validate database URL
        if not cls.DATABASE_URL.startswith('postgresql'):
            raise ValueError("DATABASE_URL must be a PostgreSQL connection string")
        
        # Validate CalDAV URL
        if not (cls.CALDAV_URL.startswith('http://') or cls.CALDAV_URL.startswith('https://')):
            raise ValueError("CALDAV_URL must be a valid HTTP/HTTPS URL")
        
        # Validate log level
        valid_log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if cls.LOG_LEVEL not in valid_log_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_log_levels}")
        
        # Validate numeric ranges
        if not (1 <= cls.SYNC_BATCH_SIZE <= 1000):
            raise ValueError("SYNC_BATCH_SIZE must be between 1 and 1000")
        
        if not (1 <= cls.WEBHOOK_TIMEOUT <= 300):
            raise ValueError("WEBHOOK_TIMEOUT must be between 1 and 300 seconds")
        
        # Validate priorities
        for source_id in ['m365-tenant1', 'm365-tenant2', 'icloud']:
            priority = cls.get_source_priority(source_id)
            if not (1 <= priority <= 10):
                raise ValueError(f"Priority for {source_id} must be between 1 and 10")
        
        return True
    
    @classmethod
    def get_logging_config(cls) -> dict:
        """
        Generate logging configuration dictionary
        
        Returns:
            Dictionary suitable for logging.config.dictConfig()
        """
        return {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'default': {
                    'format': cls.LOG_FORMAT,
                    'datefmt': cls.LOG_DATE_FORMAT,
                },
                'json': {
                    '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
                    'format': '%(asctime)s %(name)s %(levelname)s %(message)s',
                },
            },
            'handlers': {
                'console': {
                    'class': 'logging.StreamHandler',
                    'level': cls.LOG_LEVEL,
                    'formatter': 'default',
                    'stream': 'ext://sys.stdout',
                },
                'file': {
                    'class': 'logging.handlers.RotatingFileHandler',
                    'level': cls.LOG_LEVEL,
                    'formatter': 'json',
                    'filename': cls.LOG_FILE,
                    'maxBytes': cls.LOG_MAX_BYTES,
                    'backupCount': cls.LOG_BACKUP_COUNT,
                },
            },
            'root': {
                'level': cls.LOG_LEVEL,
                'handlers': ['console', 'file'] if cls.LOG_TO_CONSOLE else ['file'],
            },
            'loggers': {
                'werkzeug': {
                    'level': 'WARNING',
                },
                'sqlalchemy.engine': {
                    'level': 'WARNING',
                },
            },
        }


# Validate configuration on import
try:
    Config.validate()
except ValueError as e:
    print(f"Configuration Error: {e}")
    raise
