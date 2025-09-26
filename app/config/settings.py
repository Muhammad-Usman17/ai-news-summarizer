from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    # Environment
    environment: str = "development"
    debug: bool = True
    
    # Database
    database_url: str = "postgresql://newsuser:newspassword@localhost:5432/newsdb"
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_stream_key: str = "news_updates"
    
    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    
    # Scheduling - Enhanced configuration
    news_processing_schedule_hours: int = 1  # Run every X hours
    news_processing_enabled: bool = True
    news_processing_schedule_type: str = "hourly"  # "hourly", "daily", "custom"
    news_processing_custom_cron: str = "0 */1 * * *"  # Custom cron expression
    news_processing_daily_time: int = 9  # Hour for daily processing (24-hour format)
    
    # Temporal (keeping for migration compatibility)
    temporal_host: str = "localhost:7233"
    
    # LLM Services
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = "llama3-8b-8192"  # Fast model for summarization
    
    # News Sources - Updated with reliable RSS feeds
    rss_feeds: str = os.getenv("RSS_FEEDS", 
        "https://feeds.bbci.co.uk/news/technology/rss.xml,"
        "https://feeds.arstechnica.com/arstechnica/index,"
        "https://rss.slashdot.org/Slashdot/slashdot,"
        "https://feeds.feedburner.com/TechCrunch,"
        "https://www.wired.com/feed/rss"
    )
    
    # Observability
    jaeger_endpoint: str = "http://localhost:14268/api/traces"
    prometheus_port: int = 8001
    
    # Security
    secret_key: str = "your-secret-key-here"
    api_key_header: str = "X-API-Key"
    
    # Logging
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings():
    return Settings()