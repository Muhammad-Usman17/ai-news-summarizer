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
from app.models.news import NewsAnalysis
from app.services.redis_stream import RedisStreamService
from app.services.groq_client import GroqClient

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
                    overall_analysis = await self._generate_overall_analysis(summaries, analyses)
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
        Analyze a single summary using Groq for fast insights.
        
        Args:
            summary: Summary dictionary
            
        Returns:
            Dict containing analysis, insights, and impact assessment
        """
        article_title = summary.get("article_title", "")
        summary_text = summary.get("summary", "")
        bullet_points = summary.get("bullet_points", [])
        
        # Use fast Groq analysis
        return await self._direct_groq_analyze(article_title, summary_text, bullet_points)
    
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
                
                # Use the actual database ID from the summary
                summary_id = summary.get("id") or summary.get("db_id") or (index + 1)
                
                # Prepare analysis data
                analysis_data = {
                    "summary_id": summary_id,
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
    
    async def _direct_groq_analyze(self, title: str, summary: str, bullet_points: List[str]) -> Dict[str, Any]:
        """
        Fast analysis method using Groq API.
        
        Args:
            title: Article title
            summary: Article summary
            bullet_points: Key points
            
        Returns:
            Dict containing analysis components
        """
        bullet_text = "\n".join([f"• {point}" for point in bullet_points])
        
        prompt = f"""Analyze this tech news quickly:

Title: {title}
Summary: {summary}
Key Points:
{bullet_text}

Provide concise analysis in exactly this format:
ANALYSIS: [Why this matters - 1-2 sentences]

INSIGHTS:
• [Business implication]
• [Technology implication] 
• [Market implication]

IMPACT: [Short and long-term effects - 1-2 sentences]"""
        
        try:
            response = await self.groq_client.generate(
                prompt=prompt,
                model=self.groq_client.get_fast_model(),  # Use fastest model
                max_tokens=400,  # Reduced for faster processing
                temperature=0.2  # Lower temperature for consistent analysis
            )
            
            # Parse the response
            return self._parse_analysis_response(response)
            
        except Exception as e:
            logger.error("Groq analysis failed", error=str(e))
            
            # Fast fallback without LLM
            return {
                "analysis": f"Breaking tech news: {title} - Analysis processing failed",
                "insights": ["Technology sector development", "Market implications pending", "Industry impact assessment needed"],
                "impact_assessment": "Full impact analysis temporarily unavailable"
            }
    
    async def _generate_overall_analysis(self, summaries: List[Dict[str, Any]], analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate an overall trend analysis from all summaries.
        
        Args:
            summaries: List of summary dictionaries
            analyses: List of individual analyses
            
        Returns:
            Dict containing overall analysis
        """
        # Prepare combined context
        titles = [s.get("article_title", "") for s in summaries]
        summary_texts = [s.get("summary", "") for s in summaries]
        
        prompt = f"""
        Based on today's news stories, provide an overall trend analysis:
        
        News Headlines:
        {chr(10).join([f"{i+1}. {title}" for i, title in enumerate(titles)])}
        
        Summaries:
        {chr(10).join([f"{i+1}. {text}" for i, text in enumerate(summary_texts)])}
        
        Please provide:
        1. Overall Analysis: What are the main themes and trends?
        2. Key Insights: What patterns or connections do you see?
        3. Impact Assessment: What could these developments mean collectively?
        
        Format your response as:
        ANALYSIS: [overall analysis]
        
        INSIGHTS:
        • [trend insight 1]
        • [trend insight 2]
        • [trend insight 3]
        
        IMPACT: [collective impact assessment]
        """
        
        try:
            # Use Groq for fast overall analysis
            response = await self.groq_client.generate(
                prompt=prompt,
                model=self.groq_client.get_quality_model(),  # Use quality model for overall analysis
                max_tokens=500,
                temperature=0.3
            )
            
            # Parse and format the response
            result = self._parse_analysis_response(response)
            
            # Mark this as overall analysis
            result.update({
                "summary_id": 0,  # Special ID for overall analysis
                "processing_time": 0.0,
                "article_title": "Overall Trend Analysis",
                "article_url": ""
            })
            
            return result
            
        except Exception as e:
            logger.error("Failed to generate overall analysis", error=str(e))
            return {
                "summary_id": 0,
                "analysis": "Overall trend analysis not available",
                "insights": ["Analysis generation failed"],
                "impact_assessment": "Impact assessment not available",
                "processing_time": 0.0,
                "article_title": "Overall Trend Analysis",
                "article_url": ""
            }
    
    def _parse_analysis_response(self, response: str) -> Dict[str, Any]:
        """
        Parse the LLM response into structured analysis format.
        
        Args:
            response: Raw LLM response
            
        Returns:
            Dict with analysis, insights, and impact assessment
        """
        try:
            lines = response.strip().split('\n')
            analysis = ""
            insights = []
            impact_assessment = ""
            
            current_section = None
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                if line.upper().startswith('ANALYSIS:'):
                    analysis = line[9:].strip()
                    current_section = "analysis"
                elif line.upper().startswith('INSIGHTS:'):
                    current_section = "insights"
                elif line.upper().startswith('IMPACT:'):
                    impact_assessment = line[7:].strip()
                    current_section = "impact"
                elif line.startswith('•') or line.startswith('-') or line.startswith('*'):
                    if current_section == "insights":
                        insights.append(line[1:].strip())
                elif current_section == "analysis" and not analysis:
                    analysis = line
                elif current_section == "impact" and not impact_assessment:
                    impact_assessment = line
            
            # Ensure we have content
            if not analysis:
                analysis = "Analysis not available"
            
            if not insights:
                insights = ["Insights not available"]
                
            if not impact_assessment:
                impact_assessment = "Impact assessment not available"
            
            return {
                "analysis": analysis,
                "insights": insights,
                "impact_assessment": impact_assessment
            }
            
        except Exception as e:
            logger.error("Failed to parse analysis response", error=str(e))
            return {
                "analysis": "Parsing failed",
                "insights": ["Response parsing error"],
                "impact_assessment": "Impact assessment parsing failed"
            }
    
    async def _save_analyses(self, analyses: List[Dict[str, Any]]):
        """
        Save analyses to the database.
        
        Args:
            analyses: List of analysis dictionaries
        """
        db = SessionLocal()
        try:
            for analysis_data in analyses:
                analysis = NewsAnalysis(
                    job_id=self.job_id,
                    summary_ids=[analysis_data["summary_id"]],  # Store as a list to match the model
                    analysis=analysis_data["analysis"],
                    insights=analysis_data["insights"],
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