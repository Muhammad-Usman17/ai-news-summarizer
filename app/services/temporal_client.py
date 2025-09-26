from temporalio.client import Client
from app.config.settings import get_settings
from app.config.logging import get_logger
from app.workflows.temporal_worker import TemporalService

logger = get_logger(__name__)
settings = get_settings()


class TemporalClient:
    """Wrapper for Temporal client operations."""
    
    def __init__(self):
        self.service = TemporalService()
    
    async def connect(self):
        """Connect to Temporal server."""
        await self.service.connect()
    
    async def close(self):
        """Close Temporal client."""
        await self.service.close()
    
    async def start_news_workflow(self, job_id: str, target_date: str = None) -> str:
        """
        Start a traditional news workflow.
        
        Args:
            job_id: Unique job identifier
            target_date: Target date for scraping (YYYY-MM-DD format)
            
        Returns:
            Workflow ID
        """
        return await self.service.start_news_workflow(job_id, target_date)
    
    async def get_workflow_result(self, workflow_id: str):
        """
        Get workflow result.
        
        Args:
            workflow_id: Workflow identifier
            
        Returns:
            Workflow result
        """
        if not self.service.client:
            await self.connect()
        
        handle = self.service.client.get_workflow_handle(workflow_id)
        return await handle.result()
    
    async def get_workflow_status(self, workflow_id: str):
        """
        Get workflow status.
        
        Args:
            workflow_id: Workflow identifier
            
        Returns:
            Workflow status information
        """
        if not self.service.client:
            await self.connect()
        
        handle = self.service.client.get_workflow_handle(workflow_id)
        return await handle.describe()


# Global instance
temporal_client = TemporalClient()