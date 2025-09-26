from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.orm import Session
from sqlalchemy import cast, String, or_, and_
from datetime import datetime, timedelta
import asyncio
import json
import uuid
from typing import AsyncGenerator, Optional, List, Dict, Any
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app.config.database import get_db, get_redis, create_tables
from app.config.logging import setup_logging, get_logger, LogContext
from app.config.settings import get_settings
from app.config.telemetry import setup_telemetry, get_tracer
from app.models.news import (
    NewsJob, NewsArticle, NewsSummary, NewsAnalysis,
    NewsJobResponse, NewsArticleResponse, NewsSummaryResponse, NewsAnalysisResponse,
    NewsStreamUpdate, NewsJobResult
)
from app.services.redis_stream import redis_stream_service
from app.services.scheduler import (
    trigger_manual_news_processing,
    start_scheduled_processing,
    stop_scheduled_processing,
    get_schedule_status
)
from app.services.temporal_client import temporal_client
from app.services.workflow_status_sync import (
    sync_stale_jobs,
    get_workflow_health,
    terminate_job
)


class ScheduleRequest(BaseModel):
    """Request model for schedule configuration."""
    schedule_type: str = "hourly"
    hours: int = 1
    daily_time: int = 9
    custom_cron: str = "0 */1 * * *"


# Prometheus Metrics
REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint'])
REQUEST_DURATION = Histogram('http_request_duration_seconds', 'HTTP request duration')
ACTIVE_JOBS = Gauge('news_jobs_active_total', 'Number of active news jobs')
ARTICLES_SCRAPED = Counter('news_articles_scraped_total', 'Total articles scraped', ['source'])
SUMMARIES_GENERATED = Counter('news_summaries_generated_total', 'Total summaries generated')
WORKFLOW_ERRORS = Counter('news_workflow_errors_total', 'Total workflow errors', ['error_type'])

# Initialize logging
setup_logging()
logger = get_logger(__name__)

# Get settings
settings = get_settings()

# Setup telemetry (must be done before app creation)
setup_telemetry()

# Initialize FastAPI app
app = FastAPI(
    title="AI News Summarizer",
    description="An AI-powered news summarization service with expert agents",
    version="1.0.0",
    debug=settings.debug
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4000",  # React development server
        "http://localhost:3000",  # Alternative React port
        "http://127.0.0.1:4000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Instrument FastAPI with OpenTelemetry
FastAPIInstrumentor.instrument_app(app)

# Get tracer for this module
tracer = get_tracer(__name__)


@app.on_event("startup")
async def startup_event():
    """Initialize application on startup."""
    with LogContext(event="startup"):
        logger.info("Starting AI News Summarizer service")
        
        # Create database tables
        create_tables()
        logger.info("Database tables created")
        
        # Initialize Temporal client
        await temporal_client.connect()
        logger.info("Temporal client connected")
        
        logger.info("AI News Summarizer service started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    with LogContext(event="shutdown"):
        logger.info("Shutting down AI News Summarizer service")
        
        # Close Temporal client
        await temporal_client.close()
        logger.info("Temporal client closed")
        
        # Close Redis connections if needed
        await redis_stream_service.close()
        logger.info("Redis connections closed")
        
        logger.info("AI News Summarizer service shutdown complete")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    REQUEST_COUNT.labels(method="GET", endpoint="/health").inc()
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "ai-news-summarizer"
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    # Update active jobs gauge
    db = next(get_db())
    active_jobs = db.query(NewsJob).filter(NewsJob.status == "started").count()
    ACTIVE_JOBS.set(active_jobs)
    db.close()
    
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/news/run", response_model=dict)
async def trigger_news_workflow(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Manually trigger the traditional news summarization workflow for current date.
    Note: Date selection has been removed - use historical endpoints for older dates.
    
    Returns:
        dict: Job information with job_id for tracking
    """
    # Use current date only - no date selection for manual triggers
    parsed_date = datetime.now().date()
    
    # Create job ID with date info and UUID
    job_id = str(uuid.uuid4())
    
    with tracer.start_as_current_span("trigger_news_workflow") as span:
        span.set_attribute("job_id", job_id)
        span.set_attribute("endpoint", "trigger_news_workflow") 
        span.set_attribute("target_date", str(parsed_date))
        
        with LogContext(job_id=job_id, endpoint="trigger_news_workflow", target_date=str(parsed_date)):
            logger.info("Triggering manual news summarization workflow", target_date=str(parsed_date))
        
        # Track request metrics
        REQUEST_COUNT.labels(method="POST", endpoint="/news/run").inc()
        
        # Track request duration
        with REQUEST_DURATION.time():
            try:
                # Create job record in database with UUID and new fields
                with tracer.start_as_current_span("create_job_record"):
                    # Explicitly generate UUID for the job
                    job_uuid = uuid.uuid4()
                    
                    db_job = NewsJob(
                        id=job_uuid,  # Explicitly set the ID
                        job_id=job_id,
                        job_type="manual",  # New field
                        processed_date=parsed_date,  # New field
                        status="started",
                        created_at=datetime.utcnow()
                    )
                    db.add(db_job)
                    db.commit()
                    db.refresh(db_job)
                
                # Send initial update to Redis stream
                with tracer.start_as_current_span("publish_redis_update"):
                    await redis_stream_service.publish_update(
                        job_id=job_id,
                        status="started",
                        message=f"Manual news workflow initiated for {parsed_date}",
                        data={
                            "type": "job_started",
                            "target_date": str(parsed_date),
                            "job_type": "manual"
                        }
                    )
                
                # Trigger Celery task for news processing
                with tracer.start_as_current_span("trigger_celery_task"):
                    result = trigger_manual_news_processing.delay(
                        job_id=job_id,
                        target_date=str(parsed_date)
                    )
                
                span.set_attribute("status", "success")
                logger.info("Manual news workflow started successfully")
                
                return {
                    "job_id": job_id,
                    "status": "started",
                    "job_type": "manual",
                    "message": f"Manual news workflow initiated for {parsed_date}",
                    "target_date": str(parsed_date),
                    "stream_url": f"/news/stream/{job_id}"
                }
                
            except Exception as e:
                span.set_attribute("status", "error")
                span.set_attribute("error", str(e))
                logger.error("Failed to start manual news workflow", error=str(e))
                
                # Update job status in database
                if 'db_job' in locals():
                    db_job.status = "failed"
                    db_job.error_message = str(e)
                    db.commit()
                
                # Send error update to Redis stream
                await redis_stream_service.publish_update(
                    job_id=job_id,
                    status="failed",
                    message=f"Failed to start workflow: {str(e)}",
                    data={
                        "type": "job_failed"
                    }
                )
                
                raise HTTPException(status_code=500, detail=str(e))


@app.get("/news/stream/{job_id}")
async def stream_news_updates(job_id: str):
    """
    Stream real-time updates for a specific news job.
    
    Args:
        job_id: The unique job identifier
        
    Returns:
        StreamingResponse: Server-sent events with job updates
    """
    
    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate server-sent events for job updates."""
        
        with LogContext(job_id=job_id, endpoint="stream_news_updates"):
            logger.info("Starting news update stream")
            
            try:
                # Subscribe to Redis pub/sub for real-time updates
                async for update in redis_stream_service.subscribe_to_updates():
                    # Filter updates for this specific job
                    if update.get('job_id') == job_id:
                        # Format as server-sent event
                        event_data = json.dumps(update)
                        yield f"data: {event_data}\n\n"
                        
                        # Break the stream if job is completed or failed
                        if update.get('status') in ["completed", "failed"]:
                            logger.info("Job finished, ending stream", status=update.get('status'))
                            break
                        
            except Exception as e:
                logger.error("Error in stream generator", error=str(e))
                error_update = NewsStreamUpdate(
                    job_id=job_id,
                    status="error",
                    message=f"Stream error: {str(e)}",
                    timestamp=datetime.utcnow()
                )
                yield f"data: {json.dumps(error_update.dict())}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control"
        }
    )


@app.get("/news/jobs/{job_id}", response_model=NewsJobResponse)
async def get_job_status(job_id: str, db: Session = Depends(get_db)):
    """
    Get the current status of a news job.
    
    Args:
        job_id: The unique job identifier
        
    Returns:
        NewsJobResponse: Current job status and details
    """
    REQUEST_COUNT.labels(method="GET", endpoint="/news/jobs").inc()
    
    with LogContext(job_id=job_id, endpoint="get_job_status"):
        logger.info("Retrieving job status")
        
        job = db.query(NewsJob).filter(NewsJob.job_id == job_id).first()
        
        if not job:
            logger.warning("Job not found")
            raise HTTPException(status_code=404, detail="Job not found")
        
        logger.info("Job status retrieved", status=job.status)
        
        # Create response with proper UUID handling
        job_dict = {
            "id": str(job.id),  # Convert UUID to string
            "job_id": job.job_id,
            "job_type": job.job_type,
            "workflow_run_id": job.workflow_run_id,
            "status": job.status,
            "processed_date": job.processed_date,
            "created_at": job.created_at,
            "completed_at": job.completed_at,
            "error_message": job.error_message
        }
        return NewsJobResponse(**job_dict)


@app.get("/news/jobs/{job_id}/result", response_model=NewsJobResult)
async def get_job_result(job_id: str, db: Session = Depends(get_db)):
    """
    Get the complete result of a finished news job.
    
    Args:
        job_id: The unique job identifier
        
    Returns:
        NewsJobResult: Complete job results including summaries and analyses
    """
    with LogContext(job_id=job_id, endpoint="get_job_result"):
        logger.info("Retrieving job result")
        
        job = db.query(NewsJob).filter(NewsJob.job_id == job_id).first()
        
        if not job:
            logger.warning("Job not found")
            raise HTTPException(status_code=404, detail="Job not found")
        
        if job.status not in ["completed", "failed"]:
            logger.warning("Job not finished", status=job.status)
            raise HTTPException(
                status_code=400, 
                detail=f"Job is not finished. Current status: {job.status}"
            )
        
        # Calculate processing time
        processing_time = 0.0
        if job.completed_at and job.created_at:
            processing_time = (job.completed_at - job.created_at).total_seconds()
        
        result = NewsJobResult(
            job_id=job.job_id,
            status=job.status,
            articles_count=len(job.articles),
            summaries=[s for s in job.summaries],
            analyses=[a for a in job.analyses],
            processing_time=processing_time,
            created_at=job.created_at,
            completed_at=job.completed_at
        )
        
        logger.info("Job result retrieved", articles_count=result.articles_count)
        return result


@app.get("/news/jobs", response_model=list[NewsJobResponse])
async def list_jobs(
    limit: int = 10, 
    offset: int = 0, 
    db: Session = Depends(get_db)
):
    """
    List recent news jobs.
    
    Args:
        limit: Maximum number of jobs to return (default: 10)
        offset: Number of jobs to skip (default: 0)
        
    Returns:
        list[NewsJobResponse]: List of recent jobs
    """
    with LogContext(endpoint="list_jobs", limit=limit, offset=offset):
        logger.info("Listing jobs")
        
        jobs = (
            db.query(NewsJob)
            .order_by(NewsJob.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        
        logger.info("Jobs retrieved", count=len(jobs))
        
        # Convert jobs to response models with proper UUID handling
        job_responses = []
        for job in jobs:
            job_dict = {
                "id": str(job.id),  # Convert UUID to string
                "job_id": job.job_id,
                "job_type": job.job_type,
                "workflow_run_id": job.workflow_run_id,
                "status": job.status,
                "processed_date": job.processed_date,
                "created_at": job.created_at,
                "completed_at": job.completed_at,
                "error_message": job.error_message
            }
            job_responses.append(NewsJobResponse(**job_dict))
        
        return job_responses


@app.get("/news/articles", response_model=list[NewsArticleResponse])
async def get_articles(
    limit: int = 10,
    offset: int = 0,
    date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get news articles with optional date filtering.
    
    Args:
        limit: Maximum number of articles to return
        offset: Number of articles to skip
        date: Optional date filter (YYYY-MM-DD format)
        
    Returns:
        list[NewsArticleResponse]: List of news articles
    """
    query = db.query(NewsArticle).order_by(NewsArticle.scraped_at.desc())
    
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
            query = query.filter(
                NewsArticle.scraped_at >= target_date,
                NewsArticle.scraped_at < datetime.combine(target_date, datetime.min.time()) + timedelta(days=1)
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    articles = query.offset(offset).limit(limit).all()
    
    # Convert articles with proper UUID handling
    article_responses = []
    for article in articles:
        article_dict = {
            "id": str(article.id),
            "job_id": str(article.job_id),
            "title": article.title,
            "url": article.url,
            "content": article.content,
            "source": article.source,
            "published_at": article.published_at,
            "scraped_at": article.scraped_at
        }
        article_responses.append(NewsArticleResponse(**article_dict))
    
    return article_responses


@app.get("/news/summaries", response_model=list[NewsSummaryResponse])
async def get_summaries(
    limit: int = 10,
    offset: int = 0,
    date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get news summaries with optional date filtering.
    
    Args:
        limit: Maximum number of summaries to return
        offset: Number of summaries to skip
        date: Optional date filter (YYYY-MM-DD format)
        
    Returns:
        list[NewsSummaryResponse]: List of news summaries
    """
    query = db.query(NewsSummary).order_by(NewsSummary.created_at.desc())
    
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
            query = query.filter(
                NewsSummary.created_at >= target_date,
                NewsSummary.created_at < datetime.combine(target_date, datetime.min.time()) + timedelta(days=1)
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    summaries = query.offset(offset).limit(limit).all()
    
    # Convert summaries with proper UUID handling
    summary_responses = []
    for summary in summaries:
        summary_dict = {
            "id": str(summary.id),
            "job_id": str(summary.job_id),
            "article_id": str(summary.article_id),
            "summary": summary.summary,
            "bullet_points": summary.bullet_points or [],
            "processing_time": summary.processing_time or 0.0,
            "quality_score": summary.quality_score,
            "created_at": summary.created_at
        }
        summary_responses.append(NewsSummaryResponse(**summary_dict))
    
    return summary_responses


@app.get("/news/analyses", response_model=list[NewsAnalysisResponse])
async def get_analyses(
    limit: int = 10,
    offset: int = 0,
    date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get news analyses with optional date filtering.
    
    Args:
        limit: Maximum number of analyses to return
        offset: Number of analyses to skip
        date: Optional date filter (YYYY-MM-DD format)
        
    Returns:
        list[NewsAnalysisResponse]: List of news analyses
    """
    query = db.query(NewsAnalysis).order_by(NewsAnalysis.created_at.desc())
    
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
            query = query.filter(
                NewsAnalysis.created_at >= target_date,
                NewsAnalysis.created_at < datetime.combine(target_date, datetime.min.time()) + timedelta(days=1)
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    analyses = query.offset(offset).limit(limit).all()
    
    # Convert analyses with proper UUID handling
    analysis_responses = []
    for analysis in analyses:
        # Convert summary_ids list (if it exists) to string UUIDs
        summary_ids = []
        if analysis.summary_ids:
            summary_ids = [str(sid) if isinstance(sid, uuid.UUID) else str(sid) for sid in analysis.summary_ids]
        
        analysis_dict = {
            "id": str(analysis.id),
            "job_id": str(analysis.job_id),
            "summary_ids": summary_ids,
            "analysis": analysis.analysis,
            "insights": analysis.insights or [],
            "impact_assessment": analysis.impact_assessment or "",
            "processing_time": analysis.processing_time or 0.0,
            "created_at": analysis.created_at
        }
        analysis_responses.append(NewsAnalysisResponse(**analysis_dict))
    
    return analysis_responses


@app.get("/news/timeline")
async def get_news_timeline(
    limit: int = 20,
    offset: int = 0,
    date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get a combined timeline of news articles, summaries, and analyses.
    
    Args:
        limit: Maximum number of items to return
        offset: Number of items to skip
        date: Optional date filter (YYYY-MM-DD format). If not provided, uses current date
        
    Returns:
        dict: Combined timeline with articles, summaries, and analyses
    """
    timeline_items = []
    
    # Parse date filter - use current date if not provided
    target_date = None
    apply_date_filter = True  # Always apply date filtering
    
    if date:
        try:
            from datetime import timedelta
            # Handle both ISO 8601 format and simple YYYY-MM-DD format
            if 'T' in date:
                # ISO 8601 format: 2025-09-22T00:00:00.000Z
                target_date = datetime.fromisoformat(date.replace('Z', '+00:00')).date()
            else:
                # Simple format: 2025-09-22
                target_date = datetime.strptime(date, "%Y-%m-%d").date()
        except (ValueError, OSError):
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD or ISO 8601 format")
    else:
        # If no date provided, use current date
        target_date = datetime.now().date()
        logger.info("No date provided, using current date for timeline", current_date=str(target_date))

    # Get articles - filter by published_at first, fallback to scraped_at
    articles_query = db.query(NewsArticle).order_by(NewsArticle.published_at.desc().nullslast(), NewsArticle.scraped_at.desc())
    
    # Apply date filter (always applies now - either provided date or current date)
    if target_date:
        from datetime import timedelta
        start_of_day = datetime.combine(target_date, datetime.min.time())
        end_of_day = start_of_day + timedelta(days=1)
        
        logger.info("Timeline date filter applied", 
                   target_date=str(target_date), 
                   start_of_day=start_of_day.isoformat(), 
                   end_of_day=end_of_day.isoformat())
        
        articles_query = articles_query.filter(
            or_(
                # Filter by published_at if available
                and_(
                    NewsArticle.published_at.isnot(None),
                    NewsArticle.published_at >= start_of_day,
                    NewsArticle.published_at < end_of_day
                ),
                # Fallback to scraped_at if published_at is null
                and_(
                    NewsArticle.published_at.is_(None),
                    NewsArticle.scraped_at >= start_of_day,
                    NewsArticle.scraped_at < end_of_day
                )
            )
        )

    articles = articles_query.limit(limit//2).all()
    
    logger.info("Articles found for timeline", 
               articles_count=len(articles),
               target_date=str(target_date))
    
    for article in articles:
        # Use published_at if available, otherwise fall back to scraped_at
        display_timestamp = article.published_at if article.published_at else article.scraped_at
        timeline_items.append({
            "id": f"article-{article.id}",
            "type": "article",
            "timestamp": display_timestamp.isoformat(),
            "title": article.title,
            "content": article.content[:500] + "..." if len(article.content) > 500 else article.content,
            "url": article.url,
            "source": article.source,
            "published_at": article.published_at.isoformat() if article.published_at else None,
            "scraped_at": article.scraped_at.isoformat()
        })
    
    # Get comprehensive news data by joining summaries with articles and analyses
    summaries_query = (
        db.query(NewsSummary)
        .join(NewsArticle)
        .order_by(NewsArticle.published_at.desc().nullslast(), NewsSummary.created_at.desc())
    )
    
    # Apply date filter (always applies now - either provided date or current date)
    if target_date:
        from datetime import timedelta
        start_of_day = datetime.combine(target_date, datetime.min.time())
        end_of_day = start_of_day + timedelta(days=1)
        
        summaries_query = summaries_query.filter(
            or_(
                # Filter by article's published_at if available
                and_(
                    NewsArticle.published_at.isnot(None),
                    NewsArticle.published_at >= start_of_day,
                    NewsArticle.published_at < end_of_day
                ),
                # Fallback to article's scraped_at if published_at is null
                and_(
                    NewsArticle.published_at.is_(None),
                    NewsArticle.scraped_at >= start_of_day,
                    NewsArticle.scraped_at < end_of_day
                )
            )
        )

    summaries = summaries_query.limit(limit).all()
    
    logger.info("Summaries found for timeline", 
               summaries_count=len(summaries),
               target_date=str(target_date) if target_date else "recent")
    
    # Create unified news items with all available information
    news_items_map = {}  # Use dict to avoid duplicates based on article
    
    for summary in summaries:
        article = summary.article
        if not article:
            continue
            
        # Use article URL as unique key to avoid duplicates
        item_key = article.url
        
        if item_key not in news_items_map:
            # Find related analysis for this summary using text search in JSON
            analysis = db.query(NewsAnalysis).filter(
                cast(NewsAnalysis.summary_ids, String).contains(f'"{summary.id}"')
            ).first()
            
            # Use published_at for timestamp if available, otherwise use scraped_at, finally fallback to created_at
            display_timestamp = article.published_at if article.published_at else (article.scraped_at if hasattr(article, 'scraped_at') else summary.created_at)
            
            news_items_map[item_key] = {
                "id": f"news-{article.id}",
                "type": "news_item", 
                "timestamp": display_timestamp.isoformat(),
                "title": article.title,
                "summary": summary.summary,
                "bullet_points": summary.bullet_points or [],
                "insights": analysis.insights if analysis and analysis.insights else [],
                "impact_assessment": analysis.impact_assessment if analysis else None,
                "source": article.source,
                "url": article.url,
                "published_at": article.published_at.isoformat() if article.published_at else None,
                "scraped_at": article.scraped_at.isoformat() if hasattr(article, 'scraped_at') and article.scraped_at else None,
                "created_at": summary.created_at.isoformat()
            }
    
    # Convert to list and sort by timestamp
    timeline_items = list(news_items_map.values())
    timeline_items.sort(key=lambda x: x["timestamp"], reverse=True)
    
    # Generate overall summary from the news items
    # Format date for better display in summary
    formatted_date = None
    if date:
        try:
            if 'T' in date:
                parsed_date = datetime.fromisoformat(date.replace('Z', '+00:00'))
            else:
                parsed_date = datetime.strptime(date, "%Y-%m-%d")
            formatted_date = parsed_date.strftime("%B %d, %Y")
        except (ValueError, OSError):
            formatted_date = date
    
    overall_summary = await _generate_timeline_summary(timeline_items, formatted_date)
    
    return {
        "items": timeline_items[:limit],
        "total": len(timeline_items),
        "overall_summary": overall_summary,
        "date_filter": date
    }


async def _generate_timeline_summary(news_items: List[Dict], date_filter: str = None) -> Dict[str, Any]:
    """
    Generate an overall summary of the news timeline.
    
    Args:
        news_items: List of news items
        date_filter: Optional date filter
        
    Returns:
        Dict containing overall summary and key insights
    """
    try:
        if not news_items:
            return {
                "summary": "No news items available for the selected period.",
                "key_themes": [],
                "impact_overview": "No significant developments to report."
            }
        
        # Extract key information for summary
        titles = [item.get("title", "") for item in news_items[:10]]  # Top 10 items
        all_insights = []
        
        for item in news_items[:5]:  # Use top 5 for analysis
            if item.get("insights"):
                all_insights.extend(item["insights"])
        
        # Create a brief summary using the Groq client
        from app.services.groq_client import GroqClient
        groq_client = GroqClient()
        
        date_context = f" on {date_filter}" if date_filter else " today"
        
        prompt = f"""
        Based on these news headlines{date_context}, provide a brief overall summary:
        
        Headlines:
        {chr(10).join([f"• {title}" for title in titles[:8]])}
        
        Key Insights Available:
        {chr(10).join([f"• {insight}" for insight in all_insights[:6]])}
        
        Provide a response in this exact format:
        SUMMARY: [2-3 sentence overview of main developments and trends]
        
        THEMES:
        • [Key theme 1]
        • [Key theme 2] 
        • [Key theme 3]
        
        IMPACT: [1-2 sentences about overall significance and potential implications]
        """
        
        response = await groq_client.generate(
            prompt=prompt,
            model=groq_client.get_fast_model(),
            max_tokens=300,
            temperature=0.3
        )
        
        # Parse the response
        lines = response.strip().split('\n')
        summary = ""
        themes = []
        impact = ""
        
        current_section = None
        for line in lines:
            line = line.strip()
            if line.upper().startswith('SUMMARY:'):
                summary = line[8:].strip()
                current_section = "summary"
            elif line.upper().startswith('THEMES:'):
                current_section = "themes"
            elif line.upper().startswith('IMPACT:'):
                impact = line[7:].strip()
                current_section = "impact"
            elif line.startswith('•') and current_section == "themes":
                themes.append(line[1:].strip())
            elif current_section == "summary" and not summary:
                summary = line
            elif current_section == "impact" and not impact:
                impact = line
        
        return {
            "summary": summary or "Multiple technology developments reported.",
            "key_themes": themes[:4],  # Limit to 4 themes
            "impact_overview": impact or "Various impacts on technology sector.",
            "news_count": len(news_items)
        }
        
    except Exception as e:
        logger.error("Failed to generate timeline summary", error=str(e))
        return {
            "summary": f"Found {len(news_items)} news items{' for ' + date_filter if date_filter else ''}.",
            "key_themes": ["Technology Updates", "Industry News", "Market Developments"],
            "impact_overview": "Multiple developments with potential market implications.",
            "news_count": len(news_items)
        }


@app.post("/news/sync-job-status/{job_id}")
async def sync_job_status(job_id: str, db: Session = Depends(get_db)):
    """
    Manually sync job status with Celery task status.
    Useful for jobs that completed in Celery but are stuck in 'started' state in DB.
    
    Args:
        job_id: The job ID to sync
        
    Returns:
        dict: Updated job status
    """
    try:
        # Get job from database
        job = db.query(NewsJob).filter(NewsJob.job_id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # If job is not in started state, no need to sync
        if job.status != "started":
            return {"job_id": job_id, "status": job.status, "message": "Job already completed or failed"}
        
        # For now, we'll mark long-running jobs as completed
        # In a real implementation, you'd query Celery to get actual status
        from datetime import datetime, timedelta
        
        # If job is older than 1 hour and still "started", likely completed
        if job.created_at < datetime.utcnow() - timedelta(hours=1):
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            db.commit()
            
            return {
                "job_id": job_id, 
                "status": "completed", 
                "message": "Job marked as completed (was likely finished in Celery)"
            }
        
        return {
            "job_id": job_id, 
            "status": job.status, 
            "message": "Job is recent, keeping current status"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/news/sync-all-jobs")
async def sync_all_job_statuses(db: Session = Depends(get_db)):
    """
    Sync all 'started' jobs that are likely completed.
    
    Returns:
        dict: Summary of sync operation
    """
    try:
        from datetime import datetime, timedelta
        
        # Get all jobs that are "started" and older than 30 minutes
        old_started_jobs = db.query(NewsJob).filter(
            NewsJob.status == "started",
            NewsJob.created_at < datetime.utcnow() - timedelta(minutes=30)
        ).all()
        
        synced_count = 0
        for job in old_started_jobs:
            job.status = "completed" 
            job.completed_at = datetime.utcnow()
            synced_count += 1
        
        db.commit()
        
        return {
            "synced_jobs": synced_count,
            "message": f"Marked {synced_count} old 'started' jobs as completed"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/news/sync-data")
async def sync_data_with_db(db: Session = Depends(get_db)):
    """
    Synchronize UI with database to get latest data without triggering new workflows.
    This is useful for refreshing the UI when data might have been updated externally.
    
    Returns:
        dict: Current data counts and sync timestamp
    """
    try:
        # Get current counts
        articles_count = db.query(NewsArticle).count()
        summaries_count = db.query(NewsSummary).count()
        analyses_count = db.query(NewsAnalysis).count()
        jobs_count = db.query(NewsJob).count()
        
        # Get latest entries
        latest_article = db.query(NewsArticle).order_by(NewsArticle.scraped_at.desc()).first()
        latest_summary = db.query(NewsSummary).order_by(NewsSummary.created_at.desc()).first()
        latest_analysis = db.query(NewsAnalysis).order_by(NewsAnalysis.created_at.desc()).first()
        
        sync_info = {
            "sync_timestamp": datetime.utcnow().isoformat(),
            "data_counts": {
                "articles": articles_count,
                "summaries": summaries_count,
                "analyses": analyses_count,
                "jobs": jobs_count
            },
            "latest_entries": {
                "latest_article_at": latest_article.scraped_at.isoformat() if latest_article else None,
                "latest_summary_at": latest_summary.created_at.isoformat() if latest_summary else None,
                "latest_analysis_at": latest_analysis.created_at.isoformat() if latest_analysis else None
            },
            "message": "Data synchronized successfully"
        }
        
        return sync_info
        
    except Exception as e:
        logger.error(f"Error syncing data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error syncing data: {str(e)}")


async def _get_news_processing_stats(days: int, db: Session) -> Dict[str, Any]:
    """
    Get processing statistics for the last N days.
    
    Args:
        days: Number of days to analyze
        db: Database session
        
    Returns:
        Dictionary with processing stats
    """
    try:
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)
        
        # Get jobs in date range
        jobs = db.query(NewsJob).filter(
            and_(
                NewsJob.processed_date >= start_date,
                NewsJob.processed_date <= end_date
            )
        ).all()
        
        stats = {
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "days": days
            },
            "total_jobs": len(jobs),
            "completed_jobs": 0,
            "failed_jobs": 0,
            "in_progress_jobs": 0,
            "total_articles": 0,
            "job_types": {"hourly": 0, "manual": 0},
            "daily_breakdown": []
        }
        
        # Process jobs
        daily_stats = {}
        for job in jobs:
            # Count by status
            if job.status == "completed":
                stats["completed_jobs"] += 1
            elif job.status == "failed":
                stats["failed_jobs"] += 1
            else:
                stats["in_progress_jobs"] += 1
            
            # Count by job type
            if job.job_type in stats["job_types"]:
                stats["job_types"][job.job_type] += 1
            
            # Count articles for completed jobs
            if job.status == "completed":
                articles_count = db.query(NewsArticle).filter(
                    NewsArticle.job_id == job.id
                ).count()
                stats["total_articles"] += articles_count
                
                # Daily breakdown
                job_date = job.processed_date or job.created_at.date()
                date_str = job_date.isoformat()
                
                if date_str not in daily_stats:
                    daily_stats[date_str] = {"date": date_str, "articles": 0, "jobs": 0}
                daily_stats[date_str]["articles"] += articles_count
                daily_stats[date_str]["jobs"] += 1
        
        stats["daily_breakdown"] = list(daily_stats.values())
        stats["daily_breakdown"].sort(key=lambda x: x["date"], reverse=True)
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting processing stats: {e}")
        raise


@app.get("/news/processing/stats")
async def get_processing_statistics(days: int = 30, db: Session = Depends(get_db)):
    """
    Get news processing statistics for the last N days.
    
    Args:
        days: Number of days to analyze (default: 30, max: 90)
        
    Returns:
        dict: Processing statistics and insights
    """
    # Limit days to reasonable range
    days = min(max(days, 1), 90)
    
    try:
        stats = await _get_news_processing_stats(days, db)
        
        return {
            "statistics": stats,
            "insights": {
                "success_rate": (
                    stats["completed_jobs"] / stats["total_jobs"] * 100 
                    if stats["total_jobs"] > 0 else 0
                ),
                "avg_articles_per_job": (
                    stats["total_articles"] / stats["completed_jobs"] 
                    if stats["completed_jobs"] > 0 else 0
                ),
                "most_active_job_type": max(
                    stats["job_types"].items(), 
                    key=lambda x: x[1], 
                    default=("none", 0)
                )[0]
            }
        }
        
    except Exception as e:
        logger.error(f"Error retrieving processing stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/news/hourly/start")
async def start_hourly_processing(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Start the hourly automated news processing.
    Note: Hourly processing is now handled by the external hourly service.
    
    Returns:
        dict: Information about hourly processing
    """
    return {
        "status": "info",
        "message": "Hourly processing is handled by the external hourly service. Use 'make dev-run-hourly' or 'python3 start_hourly_service.py' to start it.",
        "service": "external",
        "command": "python3 start_hourly_service.py"
    }


@app.get("/news/hourly/status")
async def get_hourly_processing_status(db: Session = Depends(get_db)):
    """
    Get the status of hourly automated processing.
    
    Returns:
        dict: Current status of hourly processing
    """
    try:
        # Check recent hourly jobs
        from datetime import timedelta
        recent_hourly_jobs = db.query(NewsJob).filter(
            and_(
                NewsJob.job_type == "hourly",
                NewsJob.created_at >= datetime.utcnow() - timedelta(hours=2)
            )
        ).order_by(NewsJob.created_at.desc()).all()
        
        status = {
            "hourly_processing_active": len(recent_hourly_jobs) > 0,
            "recent_hourly_jobs": len(recent_hourly_jobs),
            "last_hourly_run": None,
            "next_scheduled_run": "within next hour"
        }
        
        if recent_hourly_jobs:
            latest_job = recent_hourly_jobs[0]
            status["last_hourly_run"] = {
                "job_id": latest_job.job_id,
                "status": latest_job.status,
                "created_at": latest_job.created_at.isoformat(),
                "completed_at": latest_job.completed_at.isoformat() if latest_job.completed_at else None
            }
        
        return status
        
    except Exception as e:
        logger.error(f"Error getting hourly status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/news/schedule/start")
async def start_news_schedule(request: ScheduleRequest):
    """
    Start or update the news processing schedule.
    
    Args:
        request: Schedule configuration request
        
    Returns:
        dict: Schedule configuration and status
    """
    try:
        # Validate inputs
        if request.schedule_type not in ["hourly", "daily", "custom"]:
            raise HTTPException(status_code=400, detail="schedule_type must be 'hourly', 'daily', or 'custom'")
        
        if request.schedule_type == "hourly" and not (1 <= request.hours <= 24):
            raise HTTPException(status_code=400, detail="hours must be between 1 and 24")
        
        if request.schedule_type == "daily" and not (0 <= request.daily_time <= 23):
            raise HTTPException(status_code=400, detail="daily_time must be between 0 and 23")
        
        if request.schedule_type == "custom" and len(request.custom_cron.split()) != 5:
            raise HTTPException(status_code=400, detail="custom_cron must be a valid 5-part cron expression")
        
        # Start the schedule
        result = start_scheduled_processing(
            schedule_type=request.schedule_type,
            hours=request.hours,
            daily_time=request.daily_time,
            custom_cron=request.custom_cron
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting news schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/news/schedule/stop")
async def stop_news_schedule():
    """
    Stop the news processing schedule.
    
    Returns:
        dict: Status of schedule stop operation
    """
    try:
        result = stop_scheduled_processing()
        return result
        
    except Exception as e:
        logger.error(f"Error stopping news schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/news/schedule/status")
async def get_news_schedule_status():
    """
    Get current news processing schedule status and configuration.
    
    Returns:
        dict: Current schedule configuration and status
    """
    try:
        status = get_schedule_status()
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "schedule": status
        }
        
    except Exception as e:
        logger.error(f"Error getting schedule status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/news/schedule/reload")
async def reload_schedule():
    """
    Force reload the Celery Beat schedule configuration.
    Useful for testing and ensuring schedule changes are picked up immediately.
    Also restarts the Celery Beat process to apply new schedule.
    
    Returns:
        dict: Reload operation result
    """
    try:
        from app.services.scheduler import update_schedule
        update_schedule(restart_beat=True)
        
        return {
            "success": True,
            "message": "Schedule reloaded successfully with Celery Beat restart initiated",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error reloading schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/news/workflow/sync-stale")
async def sync_stale_workflows(max_age_hours: int = 2):
    """
    Sync workflows that are stuck in 'started' state.
    
    Args:
        max_age_hours: Maximum hours a job can be in 'started' state (default: 2)
        
    Returns:
        dict: Sync operation results
    """
    try:
        results = await sync_stale_jobs(max_age_hours)
        return {
            "success": True,
            "sync_results": results
        }
        
    except Exception as e:
        logger.error(f"Error syncing stale workflows: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/news/workflow/health")
async def get_workflow_health_status():
    """
    Get overall workflow system health status.
    
    Returns:
        dict: Health status and metrics
    """
    try:
        health_status = await get_workflow_health()
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "health": health_status
        }
        
    except Exception as e:
        logger.error(f"Error getting workflow health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/news/workflow/terminate/{job_id}")
async def terminate_workflow(job_id: str, reason: str = "Manual termination"):
    """
    Terminate a running workflow.
    
    Args:
        job_id: ID of the job to terminate
        reason: Reason for termination
        
    Returns:
        dict: Termination result
    """
    try:
        success = await terminate_job(job_id, reason)
        
        if success:
            return {
                "success": True,
                "job_id": job_id,
                "message": f"Job terminated: {reason}"
            }
        else:
            return {
                "success": False,
                "job_id": job_id,
                "message": "Failed to terminate job"
            }
            
    except Exception as e:
        logger.error(f"Error terminating workflow {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=settings.debug
    )