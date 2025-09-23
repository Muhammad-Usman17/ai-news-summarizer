from datetime import timedelta, datetime
from temporalio import workflow, activity
from temporalio.common import RetryPolicy
from typing import List, Dict, Any
import asyncio
from app.models.news import NewsStreamUpdate


@workflow.defn
class NewsWorkflow:
    """Main workflow for processing news articles."""
    
    @workflow.run
    async def process_news(self, job_id: str) -> Dict[str, Any]:
        """
        Process news articles through scraping, summarization, and analysis.
        
        Args:
            job_id: Unique identifier for this job
            
        Returns:
            Complete results including articles, summaries, and analyses
        """
        # Stream initial status
        await workflow.execute_activity(
            stream_update,
            NewsStreamUpdate(
                job_id=job_id,
                status="started",
                message="Job started",
                progress=0.0
            ),
            start_to_close_timeout=timedelta(seconds=10)
        )
        
        try:
            # Step 1: Scrape news articles
            await workflow.execute_activity(
                stream_update,
                NewsStreamUpdate(
                    job_id=job_id,
                    status="scraping",
                    message="Scraping news articles...",
                    progress=0.1
                ),
                start_to_close_timeout=timedelta(seconds=10)
            )
            
            scrape_result = await workflow.execute_activity(
                scrape_news_simple,
                job_id,
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3)
            )
            
            if not scrape_result.get("articles"):
                return {"status": "completed", "message": "No articles found", "data": {}}
            
            # Step 2: Summarize articles
            await workflow.execute_activity(
                stream_update,
                NewsStreamUpdate(
                    job_id=job_id,
                    status="summarizing", 
                    message="Summarizing articles...",
                    progress=0.4
                ),
                start_to_close_timeout=timedelta(seconds=10)
            )
            
            summary_result = await workflow.execute_activity(
                summarize_news_simple,
                scrape_result["articles"],
                job_id,
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=RetryPolicy(maximum_attempts=2)
            )
            
            # Step 3: Analyze summaries
            await workflow.execute_activity(
                stream_update,
                NewsStreamUpdate(
                    job_id=job_id,
                    status="analyzing",
                    message="Analyzing summaries...",
                    progress=0.7
                ),
                start_to_close_timeout=timedelta(seconds=10)
            )
            
            analysis_result = await workflow.execute_activity(
                analyze_news_simple,
                summary_result["summaries"],
                job_id,
                start_to_close_timeout=timedelta(minutes=8),
                retry_policy=RetryPolicy(maximum_attempts=2)
            )
            
            # Final status update
            await workflow.execute_activity(
                stream_update,
                NewsStreamUpdate(
                    job_id=job_id,
                    status="completed",
                    message="Job completed successfully",
                    progress=1.0
                ),
                start_to_close_timeout=timedelta(seconds=10)
            )
            
            return {
                "status": "completed",
                "data": {
                    "articles": scrape_result["articles"],
                    "summaries": summary_result["summaries"],
                    "analyses": analysis_result["analyses"]
                }
            }
            
        except Exception as e:
            await workflow.execute_activity(
                stream_update,
                NewsStreamUpdate(
                    job_id=job_id,
                    status="failed",
                    message=f"Job failed: {str(e)}",
                    progress=0.0
                ),
                start_to_close_timeout=timedelta(seconds=10)
            )
            raise


@workflow.defn
class DailyNewsWorkflow:
    """Daily scheduled workflow for processing news."""
    
    @workflow.run  
    async def process_daily_news(self, schedule_date: str) -> Dict[str, Any]:
        """
        Process daily news with scheduled execution.
        
        Args:
            schedule_date: Date for this scheduled run
            
        Returns:
            Result of daily processing
        """
        # Generate job ID for daily run
        job_id = f"daily_{schedule_date}_{datetime.now().strftime('%H%M%S')}"
        
        # Wait for scheduled time (9 AM)
        now = datetime.now()
        target_time = datetime.combine(now.date(), datetime.min.time().replace(hour=9))
        if now < target_time:
            await asyncio.sleep((target_time - now).total_seconds())
        
        # Execute main news workflow
        result = await workflow.execute_child_workflow(
            NewsWorkflow.process_news,
            job_id,
            id=f"daily_child_{job_id}",
            task_queue="news-task-queue"
        )
        
        return result


# Activities (executed by workers, can access external dependencies)

@activity.defn
async def scrape_news_simple(job_id: str) -> Dict[str, Any]:
    """
    Scrape news articles from various sources.
    
    Args:
        job_id: Job identifier
        
    Returns:
        Scraped articles data
    """
    from app.agents.scraper_agent import ScraperAgent
    agent = ScraperAgent()
    result = await agent.scrape_all_sources(job_id)
    return result


@activity.defn
async def summarize_news_simple(articles: List[Dict[str, Any]], job_id: str) -> Dict[str, Any]:
    """
    Summarize news articles using AI agents.
    
    Args:
        articles: List of articles to summarize
        job_id: Job identifier
        
    Returns:
        Summarization results
    """
    from app.agents.summarizer_agent import SummarizerAgent
    agent = SummarizerAgent(job_id)
    result = await agent.run(articles)
    return result


@activity.defn
async def analyze_news_simple(summaries: List[Dict[str, Any]], job_id: str) -> Dict[str, Any]:
    """
    Analyze news summaries for impact and insights.
    
    Args:
        summaries: List of summaries to analyze
        job_id: Job identifier
        
    Returns:
        Analysis results
    """
    from app.agents.analyst_agent import AnalystAgent
    agent = AnalystAgent(job_id)
    result = await agent.run(summaries)
    return result


@activity.defn
async def stream_update(update: NewsStreamUpdate) -> None:
    """
    Stream status updates to Redis for real-time monitoring.
    
    Args:
        update: Status update to stream
    """
    from app.services.redis_client import RedisStreamClient
    
    client = RedisStreamClient()
    await client.publish_update(update)