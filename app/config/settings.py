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
    
    # Temporal
    temporal_host: str = "localhost:7233"
    
    # LLM Services
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = "llama3-8b-8192"  # Fast model for summarization
    
    # News Sources
    rss_feeds: str = "https://feeds.bbci.co.uk/news/rss.xml,https://techcrunch.com/feed/"
    
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