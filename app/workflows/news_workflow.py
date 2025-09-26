from datetime import timedelta
from temporalio import workflow, activity
from temporalio.common import RetryPolicy
from typing import List, Dict, Any


@workflow.defn
class NewsWorkflow:
    """
    Main workflow for news summarization process.
    """
    
    @workflow.run
    async def run(self, job_id: str, target_date: str = None) -> Dict[str, Any]:
        """
        Run the complete news workflow.
        
        Args:
            job_id: Unique job identifier
            target_date: Target date for scraping in YYYY-MM-DD format
        """
        workflow.logger.info(f"Starting news workflow for job {job_id}")
        
        try:
            # Step 1: Scrape news articles
            workflow.logger.info("Starting scraping step", extra={"target_date": target_date})
            scraper_result = await workflow.execute_activity(
                scrape_news,
                args=[job_id, target_date],
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=1),
                    maximum_interval=timedelta(seconds=30),
                    maximum_attempts=3
                )
            )
            
            # Check if we got any articles
            if not scraper_result.get("articles"):
                workflow.logger.warning("No articles found")
                return {"status": "completed", "articles_count": 0}
            
            # Step 2: Summarize articles
            workflow.logger.info(f"Starting summarization step, articles_count={len(scraper_result['articles'])}")
            summary_result = await workflow.execute_activity(
                summarize_news,
                args=[job_id, scraper_result["articles"]],
                start_to_close_timeout=timedelta(minutes=15),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=2),
                    maximum_interval=timedelta(seconds=60),
                    maximum_attempts=3
                )
            )
            
            # Step 3: Critique and improve summaries
            workflow.logger.info("Starting critique step")
            critique_result = await workflow.execute_activity(
                critique_summaries,
                args=[job_id, summary_result["summaries"]],
                start_to_close_timeout=timedelta(minutes=12),  # Slightly longer for review process
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=2),
                    maximum_interval=timedelta(seconds=60),
                    maximum_attempts=2  # Fewer retries since this is optional improvement
                )
            )
            
            # Step 4: Analyze improved summaries
            workflow.logger.info("Starting analysis step")
            analysis_result = await workflow.execute_activity(
                analyze_news,
                args=[job_id, critique_result["improved_summaries"]],
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=2),
                    maximum_interval=timedelta(seconds=60),
                    maximum_attempts=3
                )
            )
            
            # Step 5: Mark job as completed in database
            await workflow.execute_activity(
                mark_job_completed,
                args=[job_id],
                start_to_close_timeout=timedelta(minutes=2)
            )
            
            # Step 6: Return final result
            final_result = {
                "job_id": job_id,
                "status": "completed",
                "articles": scraper_result["articles"],
                "summaries": summary_result["summaries"],
                "improved_summaries": critique_result["improved_summaries"],
                "critiques": critique_result["critiques"],
                "analyses": analysis_result["analyses"],
                "processing_time": analysis_result.get("total_processing_time", 0),
                "critique_processing_time": critique_result.get("total_processing_time", 0),
                "completed_at": workflow.now().isoformat()
            }
            
            workflow.logger.info("News workflow completed successfully")
            return final_result
            
        except Exception as e:
            workflow.logger.error(f"News workflow failed: {str(e)}")
            
            # Mark job as failed
            await workflow.execute_activity(
                mark_job_failed,
                args=[job_id, str(e)],
                start_to_close_timeout=timedelta(minutes=2)
            )
            
            return {
                "job_id": job_id,
                "status": "failed",
                "error": str(e),
                "failed_at": workflow.now().isoformat()
            }


# Activity functions
@activity.defn
async def scrape_news(job_id: str, target_date: str = None) -> Dict[str, Any]:
    """Scrape news articles from configured RSS feeds."""
    from app.agents.scraper_agent import ScraperAgent
    
    agent = ScraperAgent(job_id)
    result = await agent.run(target_date)
    
    return result


@activity.defn
async def summarize_news(job_id: str, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarize news articles using LLM."""
    from app.agents.summarizer_agent import SummarizerAgent
    
    agent = SummarizerAgent(job_id)
    result = await agent.run(articles)
    
    return result


@activity.defn
async def critique_summaries(job_id: str, summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Review and improve summaries using quality critique."""
    from app.agents.critic_agent import CriticAgent
    
    agent = CriticAgent(job_id)
    result = await agent.run(summaries)
    
    return result


@activity.defn
async def analyze_news(job_id: str, summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze news summaries for trends and insights."""
    from app.agents.analyst_agent import AnalystAgent
    
    agent = AnalystAgent(job_id)
    result = await agent.run(summaries)
    
    return result


@activity.defn
async def mark_job_completed(job_id: str) -> None:
    """Mark a job as completed in the database."""
    from app.config.database import SessionLocal
    from app.models.news import NewsJob
    from datetime import datetime
    
    db = SessionLocal()
    try:
        job = db.query(NewsJob).filter(NewsJob.job_id == job_id).first()
        if job:
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


@activity.defn
async def mark_job_failed(job_id: str, error_message: str) -> None:
    """Mark a job as failed in the database."""
    from app.config.database import SessionLocal
    from app.models.news import NewsJob
    from datetime import datetime
    from prometheus_client import Counter
    
    # Prometheus error metrics
    WORKFLOW_ERRORS = Counter('news_workflow_errors_total', 'Total workflow errors', ['error_type'])
    
    # Determine error type from message
    error_type = "unknown"
    if "temporal" in error_message.lower():
        error_type = "temporal"
    elif "ollama" in error_message.lower() or "llm" in error_message.lower():
        error_type = "llm"
    elif "database" in error_message.lower():
        error_type = "database"
    elif "scraping" in error_message.lower() or "rss" in error_message.lower():
        error_type = "scraping"
    
    # Update error metrics
    WORKFLOW_ERRORS.labels(error_type=error_type).inc()
    
    db = SessionLocal()
    try:
        job = db.query(NewsJob).filter(NewsJob.job_id == job_id).first()
        if job:
            job.status = "failed"
            job.error_message = error_message
            job.completed_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()