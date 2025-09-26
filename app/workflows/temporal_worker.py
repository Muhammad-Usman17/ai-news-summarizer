import asyncio
import os
from datetime import timedelta, datetime
from dotenv import load_dotenv
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.common import RetryPolicy

# Load environment variables from .env file
load_dotenv()

from app.config.settings import get_settings
from app.config.logging import get_logger, setup_logging
from app.workflows.news_workflow import (
    NewsWorkflow, 
    scrape_news,
    summarize_news,
    critique_summaries,  # Added missing import
    analyze_news,
    mark_job_completed,
    mark_job_failed
)

setup_logging()
logger = get_logger(__name__)
settings = get_settings()

TASK_QUEUE = "news-processing"


class TemporalService:
    """Service for managing Temporal client and workers."""
    
    def __init__(self):
        self.client: Client = None
        self.worker: Worker = None
        
    async def connect(self):
        """Connect to Temporal server."""
        logger.info("Connecting to Temporal server", host=settings.temporal_host)
        
        try:
            self.client = await Client.connect(settings.temporal_host)
            logger.info("Connected to Temporal server successfully")
        except Exception as e:
            logger.error("Failed to connect to Temporal server", error=str(e))
            raise
    
    async def close(self):
        """Close Temporal client."""
        if self.client:
            # Temporal client doesn't need explicit close
            logger.info("Temporal client closed")
    
    async def start_news_workflow(self, job_id: str, target_date: str = None) -> str:
        """
        Start a news workflow.
        
        Args:
            job_id: Unique job identifier
            target_date: Target date for scraping (YYYY-MM-DD format)
            
        Returns:
            Workflow ID
        """
        if not self.client:
            await self.connect()
        
        logger.info("Starting news workflow", job_id=job_id, target_date=target_date)
        
        handle = await self.client.start_workflow(
            NewsWorkflow.run,
            args=[job_id, target_date],
            id=f"news_workflow_{job_id}",
            task_queue=TASK_QUEUE,
            execution_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=30),
                maximum_attempts=2
            )
        )
        
        logger.info("News workflow started", workflow_id=handle.id)
        return handle.id
    
    async def setup_daily_schedule(self):
        """Set up daily news workflow schedule - DEPRECATED: Using external hourly service instead."""
        logger.info("Daily schedule setup skipped - using external hourly service instead")
        pass


async def run_worker():
    """Run Temporal worker for processing workflows and activities."""
    logger.info("Starting Temporal worker")
    
    # Connect to Temporal
    client = await Client.connect(settings.temporal_host)
    
    # Create worker with workflows and activities
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[
            NewsWorkflow
        ],
        activities=[
            scrape_news,
            summarize_news,
            critique_summaries,  # Added missing critique activity
            analyze_news,
            mark_job_completed,
            mark_job_failed
        ]
    )
    
    logger.info("Temporal worker configured", task_queue=TASK_QUEUE)
    
    # Run worker
    logger.info("Starting worker execution")
    await worker.run()


async def main():
    """Main entry point for running the Temporal worker."""
    try:
        await run_worker()
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception as e:
        logger.error("Worker failed", error=str(e))
        raise


if __name__ == "__main__":
    asyncio.run(main())