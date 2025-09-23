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

logger = get_logger(__name__)
settings = get_settings()

# Prometheus Metrics
SUMMARIES_GENERATED = Counter('news_summaries_generated_total', 'Total summaries generated')


class SummarizerAgent:
    """Agent responsible for summarizing news articles using Ollama and Autogen."""
    
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.redis_stream = RedisStreamService()
        self.groq_client = GroqClient()
        
    async def run(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Execute the summarizer agent with parallel processing for speed.
        
        Args:
            articles: List of article dictionaries
            
        Returns:
            Dict containing summaries
        """
        with LogContext(job_id=self.job_id, agent="SummarizerAgent"):
            logger.info("Starting parallel news summarization", articles_count=len(articles))
            
            # Send status update
            await self.redis_stream.publish_update(
                job_id=self.job_id,
                status="summarization_started",
                message=f"Starting fast parallel summarization of {len(articles)} articles"
            )
            
            start_time = time.time()
            
            # Process articles in parallel with concurrency limit
            MAX_CONCURRENT = 3  # Limit to avoid overwhelming Ollama
            semaphore = asyncio.Semaphore(MAX_CONCURRENT)
            
            # Create tasks for parallel processing
            tasks = []
            for i, article in enumerate(articles):
                task = self._summarize_article_with_semaphore(semaphore, i, article)
                tasks.append(task)
            
            # Wait for all tasks with progress updates
            summaries = []
            completed = 0
            
            # Process tasks as they complete
            for task in asyncio.as_completed(tasks):
                try:
                    summary_data = await task
                    if summary_data:
                        summaries.append(summary_data)
                    completed += 1
                    
                    # Send progress update every few completions
                    if completed % 2 == 0 or completed == len(articles):
                        await self.redis_stream.publish_update(
                            job_id=self.job_id,
                            status="summarization_progress",
                            message=f"Completed {completed}/{len(articles)} summaries",
                            data={"completed": completed, "total": len(articles)}
                        )
                        
                except Exception as e:
                    logger.error("Task failed", error=str(e))
                    completed += 1
            
            total_processing_time = time.time() - start_time
            
            # Save summaries to database
            await self._save_summaries(summaries)
            
            # Send completion update
            await self.redis_stream.publish_update(
                job_id=self.job_id,
                status="summarization_completed",
                message=f"Fast summarization completed. Generated {len(summaries)} summaries in {total_processing_time:.2f}s",
                data={
                    "summaries_count": len(summaries),
                    "total_processing_time": total_processing_time
                }
            )
            
            logger.info("Parallel news summarization completed", 
                       summaries_count=len(summaries),
                       total_time=total_processing_time)
            
            return {
                "summaries": summaries,
                "total_processing_time": total_processing_time,
                "success_count": len(summaries)
            }
    
    async def _summarize_article_with_semaphore(self, semaphore: asyncio.Semaphore, index: int, article: Dict[str, Any]) -> Dict[str, Any]:
        """
        Summarize a single article with concurrency control and timeout.
        
        Args:
            semaphore: Concurrency control
            index: Article index
            article: Article dictionary
            
        Returns:
            Summary data or None if failed
        """
        async with semaphore:
            try:
                logger.info("Summarizing article", 
                          article_index=index+1, 
                          title=article.get("title", "")[:100])
                
                start_time = time.time()
                
                # Add timeout to prevent hanging
                summary_result = await asyncio.wait_for(
                    self._summarize_article_fast(article), 
                    timeout=30.0  # 30 second timeout per article
                )
                
                processing_time = time.time() - start_time
                
                # Use the actual database ID from the article
                article_id = article.get("id") or article.get("db_id") or (index + 1)
                
                # Prepare summary data
                summary_data = {
                    "article_id": article_id,
                    "summary": summary_result["summary"],
                    "bullet_points": summary_result["bullet_points"],
                    "processing_time": processing_time,
                    "article_title": article.get("title", ""),
                    "article_url": article.get("url", "")
                }
                
                return summary_data
                
            except asyncio.TimeoutError:
                logger.warning("Article summarization timed out", 
                             article_index=index+1, 
                             title=article.get("title", "")[:50])
                return None
                
            except Exception as e:
                logger.error("Failed to summarize article", 
                           article_index=index+1, 
                           error=str(e))
                return None
    
    async def _summarize_article_fast(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fast summarization method using direct Ollama with optimized prompts.
        
        Args:
            article: Article dictionary
            
        Returns:
            Dict containing summary and bullet points
        """
        title = article.get("title", "")
        content = article.get("content", "")
        
        # Truncate content for faster processing (first 2000 chars)
        truncated_content = content[:2000] if content else title
        
        # Use fast Groq API call for rapid summarization
        return await self._direct_groq_summarize(title, truncated_content)
    
    async def _summarize_article(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """
        Legacy method - kept for backward compatibility.
        Now redirects to fast method.
        """
        return await self._summarize_article_fast(article)
    
    async def _direct_groq_summarize(self, title: str, content: str) -> Dict[str, Any]:
        """
        Fast Groq API summarization for rapid processing.
        
        Args:
            title: Article title
            content: Article content (already truncated)
            
        Returns:
            Dict containing summary and bullet points
        """
        # Optimized prompt for Groq's fast inference
        prompt = f"""Summarize this tech article quickly:

Title: {title}
Content: {content}

Respond exactly in this format:
SUMMARY: [2 clear sentences about the main story]
KEY POINTS:
• [key point 1]
• [key point 2] 
• [key point 3]"""
        
        try:
            response = await self.groq_client.generate(
                prompt=prompt,
                model=self.groq_client.get_fast_model(),  # Use fastest model
                max_tokens=250,  # Sufficient for structured output
                temperature=0.1  # Low temperature for consistent format
            )
            
            # Parse the response
            return self._parse_summary_response(response)
            
        except Exception as e:
            logger.error("Groq summarization failed", error=str(e))
            
            # Fast fallback without LLM
            return {
                "summary": f"Breaking: {title}",
                "bullet_points": ["Full article available at source", "AI summary temporarily unavailable", "Check original link for details"]
            }


    
    def _parse_summary_response(self, response: str) -> Dict[str, Any]:
        """
        Parse the LLM response into structured format.
        
        Args:
            response: Raw LLM response
            
        Returns:
            Dict with summary and bullet points
        """
        try:
            lines = response.strip().split('\n')
            summary = ""
            bullet_points = []
            
            current_section = None
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                if line.upper().startswith('SUMMARY:'):
                    summary = line[8:].strip()
                    current_section = "summary"
                elif line.upper().startswith('KEY POINTS:'):
                    current_section = "points"
                elif line.startswith('•') or line.startswith('-') or line.startswith('*'):
                    bullet_points.append(line[1:].strip())
                elif current_section == "summary" and not summary:
                    summary = line
                elif current_section == "points":
                    bullet_points.append(line)
            
            # Ensure we have content
            if not summary:
                summary = "Summary not available"
            
            if not bullet_points:
                bullet_points = ["Key points not available"]
            
            return {
                "summary": summary,
                "bullet_points": bullet_points
            }
            
        except Exception as e:
            logger.error("Failed to parse summary response", error=str(e))
            return {
                "summary": "Parsing failed",
                "bullet_points": ["Response parsing error"]
            }
    
    async def _save_summaries(self, summaries: List[Dict[str, Any]]):
        """
        Save summaries to the database.
        
        Args:
            summaries: List of summary dictionaries
        """
        db = SessionLocal()
        try:
            for i, summary_data in enumerate(summaries):
                summary = NewsSummary(
                    job_id=self.job_id,
                    article_id=summary_data["article_id"],
                    summary=summary_data["summary"],
                    bullet_points=summary_data["bullet_points"],
                    processing_time=summary_data["processing_time"],
                    created_at=datetime.utcnow()
                )
                db.add(summary)
                db.flush()  # Flush to get the ID before commit
                
                # Update the summary data with the database ID
                summary_data["id"] = summary.id
                summary_data["db_id"] = summary.id
                
                # Update Prometheus metrics
                SUMMARIES_GENERATED.inc()
            
            db.commit()
            logger.info("Summaries saved to database with IDs", count=len(summaries))
            
        except Exception as e:
            db.rollback()
            logger.error("Failed to save summaries", error=str(e))
            raise
        finally:
            db.close()