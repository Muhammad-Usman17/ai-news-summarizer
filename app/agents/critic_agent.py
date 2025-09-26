import time
import asyncio
from typing import List, Dict, Any
from datetime import datetime
from prometheus_client import Counter
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()

from app.config.settings import get_settings
from app.config.logging import get_logger, LogContext
from app.config.database import SessionLocal
from app.models.news import NewsSummary
from app.services.redis_stream import RedisStreamService
from app.services.groq_client import GroqClient
from app.agents.news_processing_core import NewsProcessingCore

logger = get_logger(__name__)
settings = get_settings()

# Prometheus Metrics
CRITIQUES_GENERATED = Counter('news_critiques_generated_total', 'Total critiques generated')


class CriticAgent:
    """Agent responsible for reviewing and improving news summaries through quality critique."""
    
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.redis_stream = RedisStreamService()
        self.groq_client = GroqClient()
        
    async def run(self, summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Execute the critic agent to review and improve summaries.
        
        Args:
            summaries: List of summary dictionaries to review
            
        Returns:
            Dict containing improved summaries and critique feedback
        """
        with LogContext(job_id=self.job_id, agent="CriticAgent"):
            logger.info("Starting summary critique and improvement", summaries_count=len(summaries))
            
            # Send status update
            await self.redis_stream.publish_update(
                job_id=self.job_id,
                status="critique_started",
                message=f"Starting quality review of {len(summaries)} summaries"
            )
            
            start_time = time.time()
            
            # Process summaries in parallel with concurrency limit
            MAX_CONCURRENT = 3  # Limit to avoid overwhelming API
            semaphore = asyncio.Semaphore(MAX_CONCURRENT)
            
            # Create tasks for parallel processing
            tasks = []
            for i, summary in enumerate(summaries):
                task = self._critique_summary_with_semaphore(semaphore, i, summary)
                tasks.append(task)
            
            # Wait for all tasks with progress updates
            improved_summaries = []
            critiques = []
            completed = 0
            
            # Process tasks as they complete
            for task in asyncio.as_completed(tasks):
                try:
                    result = await task
                    if result:
                        improved_summaries.append(result["improved_summary"])
                        critiques.append(result["critique"])
                    completed += 1
                    
                    # Send progress update every few completions
                    if completed % 2 == 0 or completed == len(summaries):
                        await self.redis_stream.publish_update(
                            job_id=self.job_id,
                            status="critique_progress",
                            message=f"Reviewed {completed}/{len(summaries)} summaries",
                            data={"completed": completed, "total": len(summaries)}
                        )
                        
                except Exception as e:
                    logger.error("Critique task failed", error=str(e))
                    completed += 1
            
            total_processing_time = time.time() - start_time
            
            # Update summaries in database with improvements
            await self._update_summaries_with_improvements(improved_summaries)
            
            # Send completion update
            await self.redis_stream.publish_update(
                job_id=self.job_id,
                status="critique_completed",
                message=f"Quality review completed. Improved {len(improved_summaries)} summaries in {total_processing_time:.2f}s",
                data={
                    "improved_count": len(improved_summaries),
                    "total_processing_time": total_processing_time
                }
            )
            
            logger.info("Summary critique and improvement completed", 
                       improved_count=len(improved_summaries),
                       total_time=total_processing_time)
            
            return {
                "improved_summaries": improved_summaries,
                "critiques": critiques,
                "total_processing_time": total_processing_time,
                "success_count": len(improved_summaries)
            }
    
    async def _critique_summary_with_semaphore(self, semaphore: asyncio.Semaphore, index: int, summary: Dict[str, Any]) -> Dict[str, Any]:
        """
        Critique and improve a single summary with concurrency control.
        
        Args:
            semaphore: Concurrency control
            index: Summary index
            summary: Summary dictionary
            
        Returns:
            Dict with improved summary and critique or None if failed
        """
        async with semaphore:
            try:
                logger.info("Reviewing summary", 
                          summary_index=index+1, 
                          title=summary.get("article_title", "")[:100])
                
                start_time = time.time()
                
                # Add timeout to prevent hanging
                critique_result = await asyncio.wait_for(
                    self._critique_and_improve_summary(summary), 
                    timeout=45.0  # 45 second timeout per summary (longer than summarization)
                )
                
                processing_time = time.time() - start_time
                
                # Prepare improved summary data
                improved_summary = {
                    **summary,  # Keep original data
                    "summary": critique_result["improved_summary"],
                    "bullet_points": critique_result["improved_bullet_points"],
                    "critique_processing_time": processing_time,
                    "quality_score": critique_result.get("quality_score", 0),
                    "improvements_made": critique_result.get("improvements", [])
                }
                
                critique_data = {
                    "summary_id": summary.get("id") or summary.get("db_id"),
                    "article_id": summary.get("article_id"),
                    "original_summary": summary.get("summary", ""),
                    "improved_summary": critique_result["improved_summary"],
                    "critique_feedback": critique_result["critique"],
                    "quality_score": critique_result.get("quality_score", 0),
                    "improvements": critique_result.get("improvements", []),
                    "processing_time": processing_time
                }
                
                return {
                    "improved_summary": improved_summary,
                    "critique": critique_data
                }
                
            except asyncio.TimeoutError:
                logger.warning("Summary critique timed out", 
                             summary_index=index+1, 
                             title=summary.get("article_title", "")[:50])
                return None
                
            except Exception as e:
                logger.error("Failed to critique summary", 
                           summary_index=index+1, 
                           error=str(e))
                return None
    
    async def _critique_and_improve_summary(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        """
        Critique and improve a summary using NewsProcessingCore.
        
        Args:
            summary: Summary dictionary
            
        Returns:
            Dict containing improved summary, bullet points, and critique
        """
        original_summary = summary.get("summary", "")
        original_points = summary.get("bullet_points", [])
        article_title = summary.get("article_title", "")
        article_url = summary.get("article_url", "")
        
        # Use shared core logic
        return await NewsProcessingCore.quality_critique(
            title=article_title,
            summary=original_summary,
            bullet_points=original_points,
            groq_client=self.groq_client,
            article_url=article_url
        )
    
    
    async def _update_summaries_with_improvements(self, improved_summaries: List[Dict[str, Any]]):
        """
        Update summaries in the database with improvements.
        
        Args:
            improved_summaries: List of improved summary dictionaries
        """
        db = SessionLocal()
        try:
            updated_count = 0
            for summary_data in improved_summaries:
                summary_id = summary_data.get("id") or summary_data.get("db_id")
                if not summary_id:
                    continue
                    
                # Find existing summary
                summary = db.query(NewsSummary).filter(NewsSummary.id == summary_id).first()
                if summary:
                    # Update with improved content
                    summary.summary = summary_data["summary"]
                    summary.bullet_points = summary_data["bullet_points"]
                    summary.quality_score = summary_data.get("quality_score", 7)
                    
                    updated_count += 1
                    
                    # Update Prometheus metrics
                    CRITIQUES_GENERATED.inc()
            
            db.commit()
            logger.info("Summaries updated with improvements", count=updated_count)
            
        except Exception as e:
            db.rollback()
            logger.error("Failed to update summaries with improvements", error=str(e))
            raise
        finally:
            db.close()