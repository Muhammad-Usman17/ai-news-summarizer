"""OpenTelemetry configuration for tracing and metrics."""

import os
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from prometheus_client import start_http_server
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import Resource

from app.config.logging import get_logger

logger = get_logger(__name__)


def setup_telemetry(app_name: str = "ai-news-summarizer"):
    """
    Set up OpenTelemetry instrumentation for tracing and metrics.
    
    Args:
        app_name: Name of the application for telemetry identification
    """
    
    # Create resource
    resource = Resource.create({
        "service.name": app_name,
        "service.version": "1.0.0",
        "deployment.environment": os.getenv("ENVIRONMENT", "development")
    })
    
    # Set up tracing
    setup_tracing(resource)
    
    # Set up metrics
    setup_metrics(resource)
    
    # Instrument libraries
    instrument_libraries()
    
    logger.info("OpenTelemetry telemetry configured successfully")


def setup_tracing(resource: Resource):
    """Configure tracing with Jaeger exporter."""
    
    # Configure tracer provider
    tracer_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(tracer_provider)
    
    # Configure Jaeger exporter
    jaeger_exporter = JaegerExporter(
        agent_host_name=os.getenv("JAEGER_HOST", "localhost"),
        agent_port=int(os.getenv("JAEGER_AGENT_PORT", "6831")),
        collector_endpoint=f"http://{os.getenv('JAEGER_HOST', 'localhost')}:14268/api/traces",
    )
    
    # Add batch span processor
    span_processor = BatchSpanProcessor(jaeger_exporter)
    tracer_provider.add_span_processor(span_processor)
    
    logger.info("Tracing configured with Jaeger exporter")


def setup_metrics(resource: Resource):
    """Configure metrics with Prometheus exporter."""
    
    # Create Prometheus metric reader
    prometheus_reader = PrometheusMetricReader()
    
    # Configure meter provider
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[prometheus_reader]
    )
    metrics.set_meter_provider(meter_provider)
    
    logger.info("Metrics configured with Prometheus exporter")


def instrument_libraries():
    """Instrument common libraries for automatic tracing."""
    
    # Instrument FastAPI (will be called later in main.py)
    # FastAPIInstrumentor().instrument_app(app)
    
    # Instrument SQLAlchemy
    SQLAlchemyInstrumentor().instrument()
    
    # Instrument Redis
    RedisInstrumentor().instrument()
    
    # Instrument HTTP requests
    RequestsInstrumentor().instrument()
    
    logger.info("Library instrumentation configured")


def get_tracer(name: str):
    """
    Get a tracer instance.
    
    Args:
        name: Name of the tracer (usually __name__)
        
    Returns:
        Tracer instance
    """
    return trace.get_tracer(name)


def get_meter(name: str):
    """
    Get a meter instance.
    
    Args:
        name: Name of the meter (usually __name__)
        
    Returns:
        Meter instance
    """
    return metrics.get_meter(name)