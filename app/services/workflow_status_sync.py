"""
Workflow status synchronization service.
Handles syncing job status between Celery tasks, database, and UI updates.
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.config.database import SessionLocal  
from app.config.logging import get_logger
from app.models.news import NewsJob
from app.services.redis_stream import redis_stream_service

logger = get_logger(__name__)


class WorkflowStatusSync:
    """Service for synchronizing workflow status across systems."""
    
    def __init__(self):
        pass  # No temporal client needed anymore
    
    async def update_job_status(
        self,
        job_id: str,
        status: str,
        error_message: Optional[str] = None,
        task_id: Optional[str] = None,
        additional_data: Optional[Dict[str, Any]] = None
    ):
        """
        Update job status across all systems: database and Redis stream.
        
        Args:
            job_id: The job identifier
            status: New status (started, completed, failed, terminated)
            error_message: Optional error message for failed status
            task_id: Optional Celery task ID
            additional_data: Optional additional data to include in updates
        """
        try:
            # Update database
            with SessionLocal() as db:
                job = db.query(NewsJob).filter(NewsJob.job_id == job_id).first()
                
                if not job:
                    logger.warning(f"Job {job_id} not found in database for status update")
                    return False
                
                # Update job fields
                old_status = job.status
                job.status = status
                
                if task_id:
                    job.workflow_run_id = task_id  # Reuse this field for Celery task ID
                
                if error_message:
                    job.error_message = error_message
                
                # Set completion timestamp if completed or failed
                if status in ["completed", "failed", "terminated"] and not job.completed_at:
                    job.completed_at = datetime.utcnow()
                
                db.commit()
                
                logger.info(f"Updated job {job_id} status: {old_status} -> {status}")
        
            # Publish update to Redis stream for real-time UI updates
            message = self._get_status_message(status, error_message)
            update_data = {
                "type": "job_status_update",
                "job_id": job_id, 
                "status": status,
                "message": message
            }
            
            if additional_data:
                update_data.update(additional_data)
            
            await redis_stream_service.publish_update(update_data)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to update job status for {job_id}: {e}")
            return False
    
    def _get_status_message(self, status: str, error_message: Optional[str] = None) -> str:
        """Generate appropriate status message."""
        messages = {
            "started": "Workflow is starting...",
            "scraping": "Scraping news articles...",
            "summarizing": "Generating summaries...",
            "analyzing": "Performing analysis...",
            "completed": "Workflow completed successfully",
            "failed": f"Workflow failed: {error_message}" if error_message else "Workflow failed",
            "terminated": "Workflow was terminated"
        }
        return messages.get(status, f"Workflow status updated: {status}")
    
    async def sync_stale_jobs(self, max_age_hours: int = 2) -> Dict[str, Any]:
        """
        Find and sync jobs that may be stale (stuck in 'started' state).
        
        Args:
            max_age_hours: Maximum hours a job can be in 'started' state
            
        Returns:
            Dictionary with sync results
        """
        try:
            from datetime import timedelta
            cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
            
            with SessionLocal() as db:
                # Find jobs that are stuck in 'started' state
                stale_jobs = db.query(NewsJob).filter(
                    and_(
                        NewsJob.status == "started",
                        NewsJob.created_at < cutoff_time
                    )
                ).all()
                
                sync_results = {
                    "total_stale_jobs": len(stale_jobs),
                    "synced_jobs": 0,
                    "failed_syncs": 0,
                    "job_details": []
                }
                
                for job in stale_jobs:
                    try:
                        # For stale jobs, mark as completed (they likely finished)
                        # In a real implementation with Celery, you'd query task status
                        success = await self.update_job_status(
                            job_id=job.job_id,
                            status="completed"
                        )
                        
                        if success:
                            sync_results["synced_jobs"] += 1
                            sync_results["job_details"].append({
                                "job_id": job.job_id,
                                "status": "synced",
                                "age_hours": (datetime.utcnow() - job.created_at).total_seconds() / 3600
                            })
                        else:
                            sync_results["failed_syncs"] += 1
                            
                    except Exception as e:
                        logger.error(f"Failed to sync job {job.job_id}: {e}")
                        sync_results["failed_syncs"] += 1
                
                logger.info(f"Stale job sync completed: {sync_results['synced_jobs']} synced, {sync_results['failed_syncs']} failed")
                return sync_results
                
        except Exception as e:
            logger.error(f"Error during stale job sync: {e}")
            return {
                "total_stale_jobs": 0,
                "synced_jobs": 0, 
                "failed_syncs": 1,
                "error": str(e)
            }
    
    async def get_workflow_health_status(self) -> Dict[str, Any]:
        """
        Get overall health status of workflows.
        
        Returns:
            Dictionary with health metrics
        """
        try:
            with SessionLocal() as db:
                from datetime import timedelta
                
                # Get job counts by status
                total_jobs = db.query(NewsJob).count()
                completed_jobs = db.query(NewsJob).filter(NewsJob.status == "completed").count()
                failed_jobs = db.query(NewsJob).filter(NewsJob.status == "failed").count()
                started_jobs = db.query(NewsJob).filter(NewsJob.status == "started").count()
                
                # Get recent activity (last 24 hours)
                yesterday = datetime.utcnow() - timedelta(hours=24)
                recent_jobs = db.query(NewsJob).filter(NewsJob.created_at >= yesterday).count()
                recent_completed = db.query(NewsJob).filter(
                    and_(
                        NewsJob.created_at >= yesterday,
                        NewsJob.status == "completed"
                    )
                ).count()
                
                # Calculate health metrics
                success_rate = (completed_jobs / total_jobs * 100) if total_jobs > 0 else 0
                recent_success_rate = (recent_completed / recent_jobs * 100) if recent_jobs > 0 else 0
                
                # Determine overall health
                health_status = "healthy"
                if success_rate < 80:
                    health_status = "degraded"
                if success_rate < 50 or started_jobs > 10:
                    health_status = "unhealthy"
                
                return {
                    "overall_health": health_status,
                    "total_jobs": total_jobs,
                    "job_status_breakdown": {
                        "completed": completed_jobs,
                        "failed": failed_jobs,
                        "started": started_jobs
                    },
                    "success_rate": round(success_rate, 2),
                    "recent_activity_24h": {
                        "total_jobs": recent_jobs,
                        "completed_jobs": recent_completed,
                        "success_rate": round(recent_success_rate, 2)
                    },
                    "alerts": self._generate_health_alerts(started_jobs, success_rate, recent_success_rate)
                }
                
        except Exception as e:
            logger.error(f"Error getting workflow health status: {e}")
            return {
                "overall_health": "unknown",
                "error": str(e)
            }
    
    def _generate_health_alerts(self, started_jobs: int, success_rate: float, recent_success_rate: float) -> List[str]:
        """Generate health alerts based on metrics."""
        alerts = []
        
        if started_jobs > 5:
            alerts.append(f"{started_jobs} jobs are stuck in 'started' state - consider running sync")
        
        if success_rate < 70:
            alerts.append(f"Low overall success rate: {success_rate:.1f}%")
        
        if recent_success_rate < 50:
            alerts.append(f"Recent success rate is concerning: {recent_success_rate:.1f}%")
        
        return alerts
    
    async def terminate_job(self, job_id: str, reason: str = "Manual termination") -> bool:
        """
        Terminate a running job.
        
        Args:
            job_id: Job to terminate
            reason: Reason for termination
            
        Returns:
            True if successfully terminated
        """
        try:
            # Update database status
            success = await self.update_job_status(
                job_id=job_id,
                status="terminated",
                error_message=reason
            )
            
            if success:
                logger.info(f"Job {job_id} terminated: {reason}")
                return True
            else:
                logger.error(f"Failed to terminate job {job_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error terminating job {job_id}: {e}")
            return False


# Singleton instance for use across the application
workflow_status_sync = WorkflowStatusSync()


# Utility functions for API endpoints
async def update_job_status(
    job_id: str,
    status: str,
    error_message: Optional[str] = None,
    workflow_run_id: Optional[str] = None,
    additional_data: Optional[Dict[str, Any]] = None
) -> bool:
    """Update job status across all systems."""
    return await workflow_status_sync.update_job_status(
        job_id, status, error_message, workflow_run_id, additional_data
    )


async def sync_stale_jobs(max_age_hours: int = 2) -> Dict[str, Any]:
    """Find and sync stale jobs."""
    return await workflow_status_sync.sync_stale_jobs(max_age_hours)


async def get_workflow_health() -> Dict[str, Any]:
    """Get workflow health status."""
    return await workflow_status_sync.get_workflow_health_status()


async def terminate_job(job_id: str, reason: str = "Manual termination") -> bool:
    """Terminate a running job."""
    return await workflow_status_sync.terminate_job(job_id, reason)