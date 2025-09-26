import time
import asyncio
import uuid
from typing import List, Dict, Any
from datetime import datetime
from prometheus_client import Counter
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()

from app.config.settings import get_settings
from app.config.logging import get_logger, LogContext
from app.config.database import SessionLocal
from app.models.news import NewsAnalysis
from app.services.redis_stream import RedisStreamService
from app.services.groq_client import GroqClient


def ensure_json_serializable(obj):
    """
    Recursively convert UUID objects to strings to ensure JSON serializability.
    """
    if isinstance(obj, uuid.UUID):
        return str(obj)
    elif isinstance(obj, dict):
        return {k: ensure_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [ensure_json_serializable(item) for item in obj]
    else:
        return obj
from app.agents.news_processing_core import NewsProcessingCore

logger = get_logger(__name__)
settings = get_settings()

# Prometheus Metrics
ANALYSES_GENERATED = Counter('news_analyses_generated_total', 'Total analyses generated')


class AnalystAgent:
    """Agent responsible for analyzing news summaries and providing insights."""
    
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.redis_stream = RedisStreamService()
        self.groq_client = GroqClient()
        
    async def run(self, summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Execute the analyst agent.
        
        Args:
            summaries: List of summary dictionaries
            
        Returns:
            Dict containing analyses
        """
        with LogContext(job_id=self.job_id, agent="AnalystAgent"):
            logger.info("Starting news analysis", summaries_count=len(summaries))
            
            # Send status update
            await self.redis_stream.publish_update(
                job_id=self.job_id,
                status="analysis_started",
                message=f"Starting fast parallel analysis of {len(summaries)} summaries"
            )
            
            start_time = time.time()
            
            # Process summaries in parallel with concurrency limit
            MAX_CONCURRENT = 3  # Limit to avoid overwhelming Groq
            semaphore = asyncio.Semaphore(MAX_CONCURRENT)
            
            # Create tasks for parallel processing
            tasks = []
            for i, summary in enumerate(summaries):
                task = self._analyze_summary_with_semaphore(semaphore, i, summary)
                tasks.append(task)
            
            # Wait for all tasks with progress updates
            analyses = []
            completed = 0
            
            # Process tasks as they complete
            for task in asyncio.as_completed(tasks):
                try:
                    analysis_data = await task
                    if analysis_data:
                        analyses.append(analysis_data)
                    completed += 1
                    
                    # Send progress update every few completions
                    if completed % 2 == 0 or completed == len(summaries):
                        await self.redis_stream.publish_update(
                            job_id=self.job_id,
                            status="analysis_progress",
                            message=f"Completed {completed}/{len(summaries)} analyses",
                            data={"completed": completed, "total": len(summaries)}
                        )
                        
                except Exception as e:
                    logger.error("Analysis task failed", error=str(e))
                    completed += 1
            
            total_processing_time = time.time() - start_time
            
            # Generate overall trend analysis
            if analyses:
                try:
                    overall_analysis = await self._generate_overall_trends_analysis(summaries, analyses)
                    analyses.append(overall_analysis)
                except Exception as e:
                    logger.error("Failed to generate overall analysis", error=str(e))
            
            # Save analyses to database
            await self._save_analyses(analyses)
            
            # Send completion update
            await self.redis_stream.publish_update(
                job_id=self.job_id,
                status="analysis_completed",
                message=f"Analysis completed. Generated {len(analyses)} analyses",
                data={
                    "analyses_count": len(analyses),
                    "total_processing_time": total_processing_time
                }
            )
            
            logger.info("News analysis completed", 
                       analyses_count=len(analyses),
                       total_time=total_processing_time)
            
            return {
                "analyses": analyses,
                "total_processing_time": total_processing_time,
                "success_count": len(analyses)
            }
    
    async def _analyze_summary(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a single summary using NewsProcessingCore.
        
        Args:
            summary: Summary dictionary
            
        Returns:
            Dict containing analysis, insights, and impact assessment
        """
        article_title = summary.get("article_title", "")
        summary_text = summary.get("summary", "")
        bullet_points = summary.get("bullet_points", [])
        
        # Use shared core logic
        return await NewsProcessingCore.deep_analyze(
            title=article_title,
            summary=summary_text,
            bullet_points=bullet_points,
            groq_client=self.groq_client
        )
    
    async def _analyze_summary_with_semaphore(self, semaphore: asyncio.Semaphore, index: int, summary: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a single summary with concurrency control and timeout.
        
        Args:
            semaphore: Concurrency control
            index: Summary index
            summary: Summary dictionary
            
        Returns:
            Analysis data or None if failed
        """
        async with semaphore:
            try:
                logger.info("Analyzing summary", 
                          summary_index=index+1, 
                          title=summary.get("article_title", "")[:100])
                
                start_time = time.time()
                
                # Add timeout to prevent hanging
                analysis_result = await asyncio.wait_for(
                    self._analyze_summary(summary), 
                    timeout=25.0  # 25 second timeout per analysis
                )
                
                processing_time = time.time() - start_time
                
                # Use the actual database UUID ID from the summary
                summary_id = summary.get("id") or summary.get("db_id")
                if not summary_id:
                    logger.error("Missing summary ID - cannot create analysis", 
                               article_title=summary.get("article_title", "")[:50])
                    return None
                
                # Convert UUID to string for JSON serialization
                summary_id_str = str(summary_id) if summary_id else None
                
                # Prepare analysis data
                analysis_data = {
                    "summary_id": summary_id_str,
                    "analysis": analysis_result["analysis"],
                    "insights": analysis_result["insights"],
                    "impact_assessment": analysis_result["impact_assessment"],
                    "processing_time": processing_time,
                    "article_title": summary.get("article_title", ""),
                    "article_url": summary.get("article_url", "")
                }
                
                return analysis_data
                
            except asyncio.TimeoutError:
                logger.warning("Summary analysis timed out", 
                             summary_index=index+1, 
                             title=summary.get("article_title", "")[:50])
                return None
                
            except Exception as e:
                logger.error("Failed to analyze summary", 
                           summary_index=index+1, 
                           error=str(e))
                return None
    
    
    async def _save_analyses(self, analyses: List[Dict[str, Any]]):
        """
        Save analyses to the database.
        
        Args:
            analyses: List of analysis dictionaries
        """
        import uuid
        from app.models.news import NewsJob
        
        db = SessionLocal()
        try:
            # Get the actual job UUID from the job_id string
            job = db.query(NewsJob).filter(NewsJob.job_id == self.job_id).first()
            if not job:
                logger.error(f"Job not found in database: {self.job_id}")
                raise ValueError(f"Job not found: {self.job_id}")
            
            job_uuid = job.id  # This is the UUID primary key
            logger.info(f"Found job UUID: {job_uuid} for job_id: {self.job_id}")
            
            for analysis_data in analyses:
                # Ensure JSON serializable data
                insights_safe = ensure_json_serializable(analysis_data["insights"])
                summary_ids_safe = ensure_json_serializable([analysis_data["summary_id"]])
                
                logger.debug(f"Creating NewsAnalysis with job_id type: {type(job_uuid)}")
                logger.debug(f"Summary ID types: {[type(sid) for sid in summary_ids_safe]}")
                
                analysis = NewsAnalysis(
                    job_id=job_uuid,  # Use the UUID, not the string
                    summary_ids=summary_ids_safe,  # Store as a list to match the model
                    analysis=analysis_data["analysis"],
                    insights=insights_safe,
                    impact_assessment=analysis_data["impact_assessment"],
                    processing_time=analysis_data["processing_time"],
                    created_at=datetime.utcnow()
                )
                db.add(analysis)
                
                # Update Prometheus metrics
                ANALYSES_GENERATED.inc()
            
            db.commit()
            logger.info("Analyses saved to database", count=len(analyses))
            
        except Exception as e:
            db.rollback()
            logger.error("Failed to save analyses", error=str(e))
            raise
        finally:
            db.close()

    async def _generate_overall_trends_analysis(self, summaries: List[Dict], analyses: List[Dict]) -> Dict[str, Any]:
        """
        Generate overall trends analysis using NewsProcessingCore.
        
        Args:
            summaries: List of processed summaries
            analyses: List of individual analyses
            
        Returns:
            Overall trends analysis dictionary
        """
        try:
            # Extract titles and summary texts from the dictionaries
            titles = [s.get("article_title", "") for s in summaries]
            summary_texts = [s.get("summary", "") for s in summaries]
            
            trends_result = await NewsProcessingCore.generate_overall_trends(
                titles=titles,
                summaries=summary_texts,
                groq_client=self.groq_client
            )
            
            return {
                "summary_id": "overall_trends",
                "analysis": trends_result["trends"],
                "insights": trends_result["insights"],
                "impact_assessment": trends_result["impact_assessment"],
                "processing_time": 0.0,  # Will be calculated elsewhere
                "article_title": "Overall Market Trends Analysis",
                "article_url": ""
            }
            
        except Exception as e:
            logger.error("Failed to generate overall trends analysis", error=str(e))
            # Return fallback analysis
            return {
                "summary_id": "overall_trends",
                "analysis": "Overall trends analysis not available",
                "insights": ["Analysis generation failed"],
                "impact_assessment": "Unable to assess overall impact",
                "processing_time": 0.0,
                "article_title": "Overall Market Trends Analysis",
                "article_url": ""
            }