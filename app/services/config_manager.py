"""
Configuration management service for persistent application settings.
Provides database-backed configuration storage to ensure settings persist across application restarts.
"""

import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.config.database import get_db
from app.models.news import AppConfig

logger = logging.getLogger(__name__)

from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import Column, String, Boolean, Integer, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import json

from app.config.database import get_db, engine
from app.config.logging import get_logger
from app.config.settings import get_settings

logger = get_logger(__name__)
settings = get_settings()

# Configuration table
Base = declarative_base()

class AppConfig(Base):
    __tablename__ = 'app_config'
    
    key = Column(String, primary_key=True)
    value = Column(String)  # JSON string for complex values
    updated_at = Column(DateTime, default=datetime.utcnow)

# Create table if it doesn't exist
Base.metadata.create_all(bind=engine)


class ConfigManager:
    """Persistent configuration manager."""
    
    def __init__(self):
        self.db: Optional[Session] = None
    
    def get_db(self) -> Session:
        """Get database session."""
        if not self.db:
            self.db = next(get_db())
        return self.db
    
    def close(self):
        """Close database connection."""
        if self.db:
            self.db.close()
            self.db = None
    
    def set_config(self, key: str, value: Any) -> bool:
        """Set a configuration value."""
        try:
            db = self.get_db()
            
            # Convert value to JSON string
            json_value = json.dumps(value) if not isinstance(value, str) else value
            
            # Update or create config entry
            config = db.query(AppConfig).filter(AppConfig.key == key).first()
            if config:
                config.value = json_value
                config.updated_at = datetime.utcnow()
            else:
                config = AppConfig(key=key, value=json_value)
                db.add(config)
            
            db.commit()
            logger.info(f"Config updated: {key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set config {key}: {e}")
            if self.db:
                self.db.rollback()
            return False
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        try:
            db = self.get_db()
            
            config = db.query(AppConfig).filter(AppConfig.key == key).first()
            if config:
                # Try to parse as JSON, fallback to string
                try:
                    return json.loads(config.value)
                except (json.JSONDecodeError, TypeError):
                    return config.value
            
            return default
            
        except Exception as e:
            logger.error(f"Failed to get config {key}: {e}")
            return default
    
    def get_schedule_config(self) -> Dict[str, Any]:
        """Get current schedule configuration."""
        return {
            'enabled': self.get_config('news_processing_enabled', True),
            'schedule_type': self.get_config('news_processing_schedule_type', 'hourly'),
            'hours': self.get_config('news_processing_schedule_hours', 1),
            'daily_time': self.get_config('news_processing_daily_time', 9),
            'custom_cron': self.get_config('news_processing_custom_cron', '0 */1 * * *')
        }
    
    def save_schedule_config(self, config: Dict[str, Any]) -> bool:
        """Save schedule configuration."""
        try:
            success = True
            success &= self.set_config('news_processing_enabled', config.get('enabled', True))
            success &= self.set_config('news_processing_schedule_type', config.get('schedule_type', 'hourly'))
            success &= self.set_config('news_processing_schedule_hours', config.get('hours', 1))
            success &= self.set_config('news_processing_daily_time', config.get('daily_time', 9))
            success &= self.set_config('news_processing_custom_cron', config.get('custom_cron', '0 */1 * * *'))
            
            if success:
                logger.info("Schedule configuration saved successfully")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to save schedule config: {e}")
            return False


# Global config manager instance
config_manager = ConfigManager()