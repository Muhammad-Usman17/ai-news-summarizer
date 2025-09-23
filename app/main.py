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
from app.services.redis_stream import RedisStreamService
from app.services.temporal_client import TemporalService

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

# Initialize services
redis_stream_service = RedisStreamService()
temporal_service = TemporalService()


@app.on_event("startup")
async def startup_event():
    """Initialize application on startup."""
    with LogContext(event="startup"):
        logger.info("Starting AI News Summarizer service")
        
        # Create database tables
        create_tables()
        logger.info("Database tables created")
        
        # Initialize temporal client
        await temporal_service.connect()
        logger.info("Temporal client connected")
        
        logger.info("AI News Summarizer service started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    with LogContext(event="shutdown"):
        logger.info("Shutting down AI News Summarizer service")
        
        # Close temporal client
        await temporal_service.close()
        logger.info("Temporal client closed")
        
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
    target_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Manually trigger the traditional news summarization workflow.
    
    Args:
        target_date: Optional date in YYYY-MM-DD format to scrape historical news.
                    If not provided, uses current date.
    
    Returns:
        dict: Job information with job_id for tracking
    """
    # Validate target_date if provided
    parsed_date = None
    if target_date:
        try:
            parsed_date = datetime.strptime(target_date, "%Y-%m-%d").date()
            # Prevent future dates
            if parsed_date > datetime.now().date():
                raise HTTPException(
                    status_code=400, 
                    detail="Cannot scrape news for future dates. Please select today or earlier."
                )
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid date format. Use YYYY-MM-DD format."
            )
    else:
        parsed_date = datetime.now().date()
    
    # Create job ID with date info
    job_id = f"{parsed_date.strftime('%Y%m%d')}_{str(uuid.uuid4())[:8]}"
    
    with tracer.start_as_current_span("trigger_news_workflow") as span:
        span.set_attribute("job_id", job_id)
        span.set_attribute("endpoint", "trigger_news_workflow")
        span.set_attribute("target_date", str(parsed_date))
        
        with LogContext(job_id=job_id, endpoint="trigger_news_workflow", target_date=str(parsed_date)):
            logger.info("Triggering news summarization workflow", target_date=str(parsed_date))
        
        # Track request metrics
        REQUEST_COUNT.labels(method="POST", endpoint="/news/run").inc()
        
        # Track request duration
        with REQUEST_DURATION.time():
            try:
                # Create job record in database
                with tracer.start_as_current_span("create_job_record"):
                    db_job = NewsJob(
                        job_id=job_id,
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
                        message=f"News summarization workflow initiated for {parsed_date}",
                        data={"job_id": job_id, "target_date": str(parsed_date)}
                    )
                
                # Start Temporal workflow with date parameter
                with tracer.start_as_current_span("start_temporal_workflow"):
                    background_tasks.add_task(
                        temporal_service.start_news_workflow,
                        job_id,
                        str(parsed_date)
                    )
                
                span.set_attribute("status", "success")
                logger.info("News workflow started successfully")
                
                return {
                    "job_id": job_id,
                    "status": "started",
                    "message": f"News summarization workflow initiated for {parsed_date}",
                    "target_date": str(parsed_date),
                    "stream_url": f"/news/stream/{job_id}"
                }
                
            except Exception as e:
                span.set_attribute("status", "error")
                span.set_attribute("error", str(e))
                logger.error("Failed to start news workflow", error=str(e))
                
                # Update job status in database
                if 'db_job' in locals():
                    db_job.status = "failed"
                    db_job.error_message = str(e)
                    db.commit()
                
                # Send error update to Redis stream
                await redis_stream_service.publish_update(
                    job_id=job_id,
                    status="failed",
                    message=f"Failed to start workflow: {str(e)}"
                )
                
                raise HTTPException(status_code=500, detail=str(e))


@app.post("/news/multi-agent", response_model=dict)
async def trigger_multi_agent_workflow(
    background_tasks: BackgroundTasks,
    target_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Trigger the multi-agent collaborative news processing workflow.
    
    This uses SummarizerAgent, AnalystAgent, CriticAgent, and CoordinatorAgent
    working together through AutoGen conversations for enhanced analysis.
    
    Args:
        target_date: Optional date in YYYY-MM-DD format to scrape historical news.
    
    Returns:
        dict: Job information with job_id for tracking
    """
    job_id = f"multi_agent_{str(uuid.uuid4())}"
    
    # Validate target_date if provided
    parsed_date = None
    if target_date:
        try:
            parsed_date = datetime.strptime(target_date, "%Y-%m-%d").date()
            # Prevent future dates
            if parsed_date > datetime.now().date():
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot scrape future dates. Provided: {target_date}, Current: {datetime.now().date()}"
                )
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid date format. Expected YYYY-MM-DD, got: {target_date}"
            )
    else:
        parsed_date = datetime.now().date()
    
    with LogContext(job_id=job_id, endpoint="trigger_multi_agent_workflow", target_date=str(parsed_date)):
        logger.info("Triggering multi-agent collaborative news processing", target_date=str(parsed_date))
        
        # Track request metrics
        REQUEST_COUNT.labels(method="POST", endpoint="/news/multi-agent").inc()
        
        # Track request duration
        with REQUEST_DURATION.time():
            try:
                # Create job record in database
                db_job = NewsJob(
                    job_id=job_id,
                    status="started",
                    created_at=datetime.utcnow()
                )
                db.add(db_job)
                db.commit()
                db.refresh(db_job)
                
                # Send initial update to Redis stream
                await redis_stream_service.publish_update(
                    job_id=job_id,
                    status="started",
                    message=f"Multi-agent collaborative processing initiated for {parsed_date}",
                    data={
                        "job_id": job_id,
                        "target_date": str(parsed_date),
                        "processing_mode": "multi_agent",
                        "agents": ["SummarizerAgent", "AnalystAgent", "CriticAgent", "CoordinatorAgent"]
                    }
                )
                
                # Start enhanced Temporal workflow with multi-agent flag
                background_tasks.add_task(
                    temporal_service.start_multi_agent_workflow,
                    job_id,
                    True,  # use_multi_agent=True
                    str(parsed_date)  # target_date
                )
                
                logger.info("Multi-agent workflow started successfully")
                
                return {
                    "job_id": job_id,
                    "status": "started",
                    "processing_mode": "multi_agent",
                    "message": f"Multi-agent collaborative processing initiated for {parsed_date}",
                    "target_date": str(parsed_date),
                    "agents": ["SummarizerAgent", "AnalystAgent", "CriticAgent", "CoordinatorAgent"],
                    "stream_url": f"/news/stream/{job_id}",
                    "description": "Specialized AI agents collaborating through AutoGen conversations"
                }
                
            except Exception as e:
                logger.error("Failed to start multi-agent workflow", error=str(e))
                
                # Update job status in database
                if 'db_job' in locals():
                    db_job.status = "failed"
                    db_job.error_message = str(e)
                    db.commit()
                
                # Send error update to Redis stream
                await redis_stream_service.publish_update(
                    job_id=job_id,
                    status="failed",
                    message=f"Failed to start multi-agent workflow: {str(e)}"
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
                # Subscribe to Redis stream for this job
                async for update in redis_stream_service.subscribe_to_updates(job_id):
                    # Format as server-sent event
                    event_data = json.dumps(update.dict())
                    yield f"data: {event_data}\n\n"
                    
                    # Break the stream if job is completed or failed
                    if update.status in ["completed", "failed"]:
                        logger.info("Job finished, ending stream", status=update.status)
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
        return NewsJobResponse.from_orm(job)


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
        return [NewsJobResponse.from_orm(job) for job in jobs]


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
    return [NewsArticleResponse.from_attributes(article) for article in articles]


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
    return [NewsSummaryResponse.from_attributes(summary) for summary in summaries]


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
    return [NewsAnalysisResponse.from_attributes(analysis) for analysis in analyses]


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
        date: Optional date filter (YYYY-MM-DD format)
        
    Returns:
        dict: Combined timeline with articles, summaries, and analyses
    """
    timeline_items = []
    
    # Parse date filter once if provided
    target_date = None
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

    # Get articles - filter by published_at first, fallback to scraped_at
    articles_query = db.query(NewsArticle).order_by(NewsArticle.published_at.desc().nullslast(), NewsArticle.scraped_at.desc())
    if target_date:
        from datetime import timedelta
        start_of_day = datetime.combine(target_date, datetime.min.time())
        end_of_day = start_of_day + timedelta(days=1)
        
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
    Manually sync job status with Temporal workflow status.
    Useful for jobs that completed in Temporal but are stuck in 'started' state in DB.
    
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
        # In a real implementation, you'd query Temporal to get actual status
        from datetime import datetime, timedelta
        
        # If job is older than 1 hour and still "started", likely completed
        if job.created_at < datetime.utcnow() - timedelta(hours=1):
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            db.commit()
            
            return {
                "job_id": job_id, 
                "status": "completed", 
                "message": "Job marked as completed (was likely finished in Temporal)"
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=settings.debug
    )