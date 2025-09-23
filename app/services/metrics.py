from prometheus_client import Counter, Histogram, Gauge, generate_latest
from prometheus_client.core import CollectorRegistry
from fastapi import Response
import time
from functools import wraps
from typing import Callable, Any

from app.config.logging import get_logger

logger = get_logger(__name__)

# Create custom registry
REGISTRY = CollectorRegistry()

# Define metrics
REQUEST_COUNT = Counter(
    'news_api_requests_total',
    'Total number of API requests',
    ['method', 'endpoint', 'status'],
    registry=REGISTRY
)

REQUEST_DURATION = Histogram(
    'news_api_request_duration_seconds',
    'Request duration in seconds',
    ['method', 'endpoint'],
    registry=REGISTRY
)

ACTIVE_JOBS = Gauge(
    'news_active_jobs_total',
    'Number of active news processing jobs',
    registry=REGISTRY
)

ARTICLES_SCRAPED = Counter(
    'news_articles_scraped_total',
    'Total number of articles scraped',
    ['source'],
    registry=REGISTRY
)

SUMMARIES_GENERATED = Counter(
    'news_summaries_generated_total',
    'Total number of summaries generated',
    registry=REGISTRY
)

ANALYSES_COMPLETED = Counter(
    'news_analyses_completed_total',
    'Total number of analyses completed',
    registry=REGISTRY
)

PROCESSING_TIME = Histogram(
    'news_processing_duration_seconds',
    'Time taken for news processing steps',
    ['step'],
    registry=REGISTRY
)

LLM_REQUESTS = Counter(
    'news_llm_requests_total',
    'Total number of LLM requests',
    ['model', 'agent_type', 'status'],
    registry=REGISTRY
)

LLM_RESPONSE_TIME = Histogram(
    'news_llm_response_duration_seconds',
    'LLM response time in seconds',
    ['model', 'agent_type'],
    registry=REGISTRY
)


class MetricsCollector:
    """Collector for application-specific metrics."""
    
    @staticmethod
    def record_request(method: str, endpoint: str, status: int, duration: float):
        """Record API request metrics."""
        REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status).inc()
        REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)
    
    @staticmethod
    def record_job_started():
        """Record when a job starts."""
        ACTIVE_JOBS.inc()
    
    @staticmethod
    def record_job_completed():
        """Record when a job completes."""
        ACTIVE_JOBS.dec()
    
    @staticmethod
    def record_articles_scraped(source: str, count: int):
        """Record articles scraped from a source."""
        ARTICLES_SCRAPED.labels(source=source).inc(count)
    
    @staticmethod
    def record_summary_generated():
        """Record a summary generation."""
        SUMMARIES_GENERATED.inc()
    
    @staticmethod
    def record_analysis_completed():
        """Record an analysis completion."""
        ANALYSES_COMPLETED.inc()
    
    @staticmethod
    def record_processing_time(step: str, duration: float):
        """Record processing time for a step."""
        PROCESSING_TIME.labels(step=step).observe(duration)
    
    @staticmethod
    def record_llm_request(model: str, agent_type: str, status: str, duration: float):
        """Record LLM request metrics."""
        LLM_REQUESTS.labels(model=model, agent_type=agent_type, status=status).inc()
        LLM_RESPONSE_TIME.labels(model=model, agent_type=agent_type).observe(duration)


def metrics_middleware(request_func: Callable) -> Callable:
    """Middleware to collect request metrics."""
    
    @wraps(request_func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        
        try:
            response = await request_func(*args, **kwargs)
            status = getattr(response, 'status_code', 200)
            
        except Exception as e:
            status = 500
            raise
        finally:
            duration = time.time() - start_time
            
            # Extract request info (simplified)
            method = "GET"  # Default, would need to extract from request
            endpoint = request_func.__name__
            
            MetricsCollector.record_request(method, endpoint, status, duration)
        
        return response
    
    return wrapper


def get_metrics() -> Response:
    """Get Prometheus metrics."""
    metrics_data = generate_latest(REGISTRY)
    return Response(
        content=metrics_data,
        media_type="text/plain; charset=utf-8"
    )