from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
import asyncio
from functools import wraps
from typing import Callable, Any

from app.config.settings import get_settings
from app.config.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


def setup_tracing():
    """Set up OpenTelemetry tracing with Jaeger."""
    logger.info("Setting up distributed tracing")
    
    # Create resource
    resource = Resource(attributes={
        ResourceAttributes.SERVICE_NAME: "ai-news-summarizer",
        ResourceAttributes.SERVICE_VERSION: "1.0.0",
        ResourceAttributes.DEPLOYMENT_ENVIRONMENT: settings.environment
    })
    
    # Configure tracer provider
    trace.set_tracer_provider(TracerProvider(resource=resource))
    tracer_provider = trace.get_tracer_provider()
    
    # Configure Jaeger exporter
    jaeger_exporter = JaegerExporter(
        agent_host_name="localhost",
        agent_port=6831,
        collector_endpoint=settings.jaeger_endpoint,
    )
    
    # Add span processor
    span_processor = BatchSpanProcessor(jaeger_exporter)
    tracer_provider.add_span_processor(span_processor)
    
    logger.info("Distributed tracing configured with Jaeger")


def get_tracer(name: str):
    """Get a tracer instance."""
    return trace.get_tracer(name)


def trace_async_function(operation_name: str = None):
    """Decorator to trace async functions."""
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = get_tracer(__name__)
            span_name = operation_name or f"{func.__module__}.{func.__name__}"
            
            with tracer.start_as_current_span(span_name) as span:
                try:
                    # Add function parameters as attributes
                    if args:
                        span.set_attribute("function.args_count", len(args))
                    if kwargs:
                        for key, value in kwargs.items():
                            if isinstance(value, (str, int, float, bool)):
                                span.set_attribute(f"function.arg.{key}", value)
                    
                    result = await func(*args, **kwargs)
                    span.set_attribute("function.success", True)
                    return result
                    
                except Exception as e:
                    span.set_attribute("function.success", False)
                    span.set_attribute("function.error", str(e))
                    span.record_exception(e)
                    raise
        
        return wrapper
    return decorator


def trace_function(operation_name: str = None):
    """Decorator to trace synchronous functions."""
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            tracer = get_tracer(__name__)
            span_name = operation_name or f"{func.__module__}.{func.__name__}"
            
            with tracer.start_as_current_span(span_name) as span:
                try:
                    # Add function parameters as attributes
                    if args:
                        span.set_attribute("function.args_count", len(args))
                    if kwargs:
                        for key, value in kwargs.items():
                            if isinstance(value, (str, int, float, bool)):
                                span.set_attribute(f"function.arg.{key}", value)
                    
                    result = func(*args, **kwargs)
                    span.set_attribute("function.success", True)
                    return result
                    
                except Exception as e:
                    span.set_attribute("function.success", False)
                    span.set_attribute("function.error", str(e))
                    span.record_exception(e)
                    raise
        
        return wrapper
    return decorator


class TracingContext:
    """Context manager for manual tracing."""
    
    def __init__(self, operation_name: str, **attributes):
        self.tracer = get_tracer(__name__)
        self.operation_name = operation_name
        self.attributes = attributes
        self.span = None
    
    def __enter__(self):
        self.span = self.tracer.start_span(self.operation_name)
        
        # Set initial attributes
        for key, value in self.attributes.items():
            if isinstance(value, (str, int, float, bool)):
                self.span.set_attribute(key, value)
        
        return self.span
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.span.set_attribute("error", True)
            self.span.set_attribute("error_message", str(exc_val))
            self.span.record_exception(exc_val)
        else:
            self.span.set_attribute("success", True)
        
        self.span.end()


def instrument_fastapi(app):
    """Instrument FastAPI application."""
    logger.info("Instrumenting FastAPI for tracing")
    FastAPIInstrumentor.instrument_app(app)


def instrument_sqlalchemy(engine):
    """Instrument SQLAlchemy for tracing."""
    logger.info("Instrumenting SQLAlchemy for tracing")
    SQLAlchemyInstrumentor().instrument(engine=engine)


def instrument_redis():
    """Instrument Redis for tracing."""
    logger.info("Instrumenting Redis for tracing")
    RedisInstrumentor().instrument()