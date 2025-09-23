"""
Enhanced news workflow with multi-agent processing option.
"""

from datetime import timedelta
from temporalio import workflow, activity
from temporalio.common import RetryPolicy
from typing import List, Dict, Any
import asyncio

# Import activities from main workflow
from app.workflows.news_workflow import mark_job_completed, mark_job_failed, scrape_news


@workflow.defn
class NewsWorkflowMultiAgent:
    """
    Enhanced news workflow with multi-agent collaborative processing.
    """
    
    @workflow.run
    async def run(self, job_id: str, use_multi_agent: bool = True, target_date: str = None) -> Dict[str, Any]:
        """
        Run the complete news workflow with optional multi-agent processing.
        
        Args:
            job_id: Unique job identifier
            use_multi_agent: Whether to use collaborative multi-agent processing
            target_date: Target date for scraping in YYYY-MM-DD format
        """
        workflow.logger.info(f"Starting news workflow for job {job_id}, multi_agent={use_multi_agent}", extra={"target_date": target_date})
        
        try:
            # Step 1: Scrape news articles
            workflow.logger.info("Starting scraping step", extra={"target_date": target_date})
            # 1. Scrape News Articles
            articles_result = await workflow.execute_activity(
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
            if not articles_result.get("articles"):
                workflow.logger.warning("No articles found")
                return {"status": "completed", "articles_count": 0}
            
            articles = articles_result["articles"]
            workflow.logger.info(f"Found {len(articles)} articles to process")
            
            # Choose processing path based on multi_agent flag
            if use_multi_agent:
                # Step 2: Multi-agent collaborative processing
                workflow.logger.info("Starting multi-agent collaborative processing")
                multi_agent_result = await workflow.execute_activity(
                    process_with_multi_agents,
                    args=[job_id, articles],
                    start_to_close_timeout=timedelta(minutes=20),  # Longer timeout for collaboration
                    retry_policy=RetryPolicy(
                        initial_interval=timedelta(seconds=2),
                        maximum_interval=timedelta(seconds=60),
                        maximum_attempts=2  # Fewer retries for complex processing
                    )
                )
                
                # Mark job as completed in database
                await workflow.execute_activity(
                    mark_job_completed,
                    args=[job_id],
                    start_to_close_timeout=timedelta(minutes=2)
                )
                
                final_result = {
                    "job_id": job_id,
                    "status": "completed",
                    "processing_mode": "multi_agent",
                    "articles": articles,
                    "multi_agent_results": multi_agent_result["results"],
                    "processing_time": multi_agent_result.get("processing_time", 0),
                    "agents_used": ["SummarizerAgent", "AnalystAgent", "CriticAgent", "CoordinatorAgent"],
                    "completed_at": workflow.now().isoformat()
                }
                
            else:
                # Step 2: Traditional summarization
                workflow.logger.info("Starting traditional summarization step")
                summary_result = await workflow.execute_activity(
                    summarize_news,
                    args=[job_id, articles],
                    start_to_close_timeout=timedelta(minutes=15),
                    retry_policy=RetryPolicy(
                        initial_interval=timedelta(seconds=2),
                        maximum_interval=timedelta(seconds=60),
                        maximum_attempts=3
                    )
                )
                
                # Step 3: Analysis
                workflow.logger.info("Starting analysis step")
                analysis_result = await workflow.execute_activity(
                    analyze_news,
                    args=[job_id, summary_result["summaries"]],
                    start_to_close_timeout=timedelta(minutes=10),
                    retry_policy=RetryPolicy(
                        initial_interval=timedelta(seconds=2),
                        maximum_interval=timedelta(seconds=60),
                        maximum_attempts=3
                    )
                )
                
                # Mark job as completed in database
                await workflow.execute_activity(
                    mark_job_completed,
                    args=[job_id],
                    start_to_close_timeout=timedelta(minutes=2)
                )
                
                final_result = {
                    "job_id": job_id,
                    "status": "completed",
                    "processing_mode": "traditional",
                    "articles": articles,
                    "summaries": summary_result["summaries"],
                    "analyses": analysis_result["analyses"],
                    "processing_time": analysis_result.get("total_processing_time", 0),
                    "completed_at": workflow.now().isoformat()
                }
            
            workflow.logger.info(f"News workflow completed successfully, mode={final_result['processing_mode']}")
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


@workflow.defn
class DailyNewsWorkflowMultiAgent:
    """
    Enhanced daily workflow with multi-agent option.
    """
    
    @workflow.run
    async def run(self, use_multi_agent: bool = True) -> Dict[str, Any]:
        """
        Run the daily news workflow with multi-agent processing.
        
        Args:
            use_multi_agent: Whether to use collaborative multi-agent processing
        """
        import uuid
        job_id = f"daily_multi_agent_{workflow.now().strftime('%Y%m%d')}_{str(uuid.uuid4())[:8]}"
        
        workflow.logger.info(f"Starting daily news workflow for job {job_id}, multi_agent={use_multi_agent}")
        
        # Execute the enhanced news workflow
        result = await workflow.execute_child_workflow(
            NewsWorkflowMultiAgent.run,
            args=[job_id, use_multi_agent],
            id=f"news_workflow_{job_id}"
        )
        
        workflow.logger.info(f"Daily news workflow completed, status={result.get('status')}")
        return result


# Enhanced activity functions
@activity.defn
async def process_with_multi_agents(job_id: str, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Process articles using multi-agent collaboration system.
    
    Args:
        job_id: Job identifier
        articles: List of articles to process
        
    Returns:
        Multi-agent processing results
    """
    from app.agents.multi_agent_processor import MultiAgentNewsProcessor
    from datetime import datetime
    import time
    
    start_time = time.time()
    
    # Initialize multi-agent processor
    processor = MultiAgentNewsProcessor(job_id)
    
    # Process articles through agent collaboration
    result = await processor.process_articles(articles)
    
    processing_time = time.time() - start_time
    result["processing_time"] = processing_time
    
    return result



@activity.defn
async def summarize_news(job_id: str, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarize news articles using LLM."""
    from app.agents.summarizer_agent import SummarizerAgent
    
    agent = SummarizerAgent(job_id)
    result = await agent.run(articles)
    
    return result


@activity.defn
async def analyze_news(job_id: str, summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze news summaries for trends and insights."""
    from app.agents.analyst_agent import AnalystAgent
    
    agent = AnalystAgent(job_id)
    result = await agent.run(summaries)
    
    return result


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
    elif "groq" in error_message.lower() or "llm" in error_message.lower():
        error_type = "llm"
    elif "autogen" in error_message.lower():
        error_type = "multi_agent"
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