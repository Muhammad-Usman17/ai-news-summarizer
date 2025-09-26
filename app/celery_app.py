from celery import Celery
from app.config.settings import get_settings

settings = get_settings()

# Create Celery app
celery_app = Celery(
    "news_agents",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.agents.scraper_agent",
        "app.agents.summarizer_agent", 
        "app.agents.analyst_agent",
        "app.services.scheduler"  # Include scheduler tasks
    ]
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    worker_concurrency=2,  # Handle 2 jobs simultaneously
    worker_pool='threads',  # Use thread pool for better I/O concurrency
    # Beat scheduler configuration
    beat_schedule={},
    beat_schedule_filename='celerybeat-schedule',
)