"""
Multi-Agent News Processing System using AutoGen + Groq

This system creates specialized AI agents that collaborate:
- SummarizerAgent: Creates initial summaries
- AnalystAgent: Analyzes implications and trends  
- CriticAgent: Reviews and improves the work
- CoordinatorAgent: Orchestrates the workflow

Each agent has expertise and they collaborate through AutoGen's conversation system.
"""

import asyncio
import json
from typing import List, Dict, Any, Optional
from datetime import datetime

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.messages import TextMessage

from app.agents.simple_multi_agent import SimpleMultiAgentProcessor
from app.config.logging import get_logger, LogContext
from app.config.database import SessionLocal
from app.models.news import NewsSummary, NewsAnalysis
from app.services.redis_stream import RedisStreamService
from app.services.groq_autogen_client import GroqAutogenClient

logger = get_logger(__name__)


class MultiAgentNewsProcessor(SimpleMultiAgentProcessor):
    """
    Orchestrates multiple AI agents to process news articles collaboratively.
    """
    
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.redis_stream = RedisStreamService()
        
        # Initialize Groq client for all agents
        self.llm_client = GroqAutogenClient(model="llama-3.1-8b-instant")
        
        # Create specialized agents
        self.summarizer_agent = self._create_summarizer_agent()
        self.analyst_agent = self._create_analyst_agent() 
        self.critic_agent = self._create_critic_agent()
        self.coordinator_agent = self._create_coordinator_agent()
        
    def _create_summarizer_agent(self) -> AssistantAgent:
        """Create an agent specialized in news summarization."""
        return AssistantAgent(
            name="Newssummarizer",
            model_client=self.llm_client,
            system_message="""You are an expert news summarizer with deep knowledge of technology, business, and current events.

Your role:
- Create concise, accurate summaries of news articles
- Extract the most important information
- Identify key stakeholders and implications
- Focus on facts, not opinions
- Use clear, professional language

Format your summaries as:
HEADLINE: [One compelling headline]
SUMMARY: [2-3 sentences covering the main story]
KEY POINTS:
• [Most important point]
• [Second important point] 
• [Third important point]

Be precise, factual, and engaging."""
        )
    
    def _create_analyst_agent(self) -> AssistantAgent:
        """Create an agent specialized in news analysis."""
        return AssistantAgent(
            name="NewsAnalyst", 
            model_client=self.llm_client,
            system_message="""You are a senior technology and business analyst with expertise in market trends, industry dynamics, and strategic implications.

Your role:
- Analyze the deeper meaning and implications of news
- Identify market impacts, competitive dynamics
- Assess short and long-term consequences
- Connect developments to broader trends
- Provide strategic insights for decision makers

Format your analysis as:
SIGNIFICANCE: [Why this matters - business/tech/market perspective]
IMPLICATIONS:
• [Business implication]
• [Technology implication]
• [Market/industry implication]
IMPACT ASSESSMENT: [Short-term and long-term effects]
CONNECTIONS: [How this relates to other trends/developments]

Be insightful, strategic, and forward-looking."""
        )
    
    def _create_critic_agent(self) -> AssistantAgent:
        """Create an agent specialized in quality review and improvement."""
        return AssistantAgent(
            name="QualityReviewer",
            model_client=self.llm_client,
            system_message="""You are a senior editorial reviewer and fact-checker with expertise in journalism standards and analytical rigor.

Your role:
- Review summaries and analyses for accuracy and completeness
- Identify gaps, inconsistencies, or areas for improvement
- Ensure clarity and professional presentation
- Verify logical reasoning and conclusions
- Suggest specific improvements

Format your review as:
QUALITY ASSESSMENT: [Overall quality rating and brief evaluation]
STRENGTHS:
• [What works well]
• [Strong points to maintain]
IMPROVEMENT AREAS:
• [Specific suggestions for enhancement]
• [Missing elements or weak points]
FINAL RECOMMENDATIONS: [Concrete steps to improve the work]

Be constructive, specific, and quality-focused."""
        )
    
    def _create_coordinator_agent(self) -> AssistantAgent:
        """Create an agent to coordinate and synthesize the work."""
        return AssistantAgent(
            name="WorkflowCoordinator",
            model_client=self.llm_client,
            system_message="""You are a senior editorial coordinator responsible for producing final, polished news summaries and analyses.

Your role:
- Synthesize input from summarizer, analyst, and reviewer
- Create final, polished versions incorporating all feedback
- Ensure consistency and professional presentation
- Balance accuracy with readability
- Deliver publication-ready content

Format final output as:
=== FINAL NEWS SUMMARY ===
HEADLINE: [Refined, compelling headline]
SUMMARY: [Polished 2-3 sentence summary]
KEY POINTS:
• [Refined key point 1]
• [Refined key point 2] 
• [Refined key point 3]

=== ANALYSIS ===
SIGNIFICANCE: [Why this matters]
STRATEGIC IMPLICATIONS:
• [Business impact]
• [Technology impact]
• [Market impact]
OUTLOOK: [What to watch for next]

Be authoritative, clear, and comprehensive."""
        )
    
    async def process_articles(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Process articles through the multi-agent collaboration system.
        
        Args:
            articles: List of article dictionaries
            
        Returns:
            Results from multi-agent processing
        """
        with LogContext(job_id=self.job_id, agent="MultiAgentProcessor"):
            logger.info("Starting multi-agent news processing", articles_count=len(articles))
            
            await self.redis_stream.publish_update(
                job_id=self.job_id,
                status="multi_agent_started",
                message=f"Starting collaborative processing of {len(articles)} articles"
            )
            
            all_results = []
            
            # Process articles with controlled concurrency
            semaphore = asyncio.Semaphore(2)  # Process 2 articles concurrently
            
            tasks = [
                self._process_single_article_with_semaphore(semaphore, i, article)
                for i, article in enumerate(articles)
            ]
            
            # Wait for all articles to be processed
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Filter successful results
            for i, result in enumerate(results):
                if isinstance(result, dict):
                    all_results.append(result)
                else:
                    logger.error("Article processing failed", 
                               article_index=i, 
                               error=str(result))
            
            # Save results to database
            await self._save_multi_agent_results(all_results)
            
            await self.redis_stream.publish_update(
                job_id=self.job_id,
                status="multi_agent_completed",
                message=f"Multi-agent processing completed. Processed {len(all_results)}/{len(articles)} articles"
            )
            
            logger.info("Multi-agent processing completed", 
                       success_count=len(all_results),
                       total_count=len(articles))
            
            return {
                "results": all_results,
                "success_count": len(all_results),
                "total_count": len(articles)
            }
    
    async def _process_single_article_with_semaphore(
        self, 
        semaphore: asyncio.Semaphore, 
        index: int, 
        article: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process a single article with concurrency control."""
        async with semaphore:
            try:
                return await asyncio.wait_for(
                    self._process_single_article(index, article),
                    timeout=120.0  # 2 minute timeout per article
                )
            except asyncio.TimeoutError:
                logger.warning("Article processing timed out", article_index=index)
                raise Exception(f"Processing timeout for article {index}")
            except Exception as e:
                logger.error("Article processing failed", article_index=index, error=str(e))
                raise e
    
    async def _process_single_article(self, index: int, article: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single article through the multi-agent workflow.
        
        Args:
            index: Article index
            article: Article dictionary
            
        Returns:
            Processed results from all agents
        """
        title = article.get("title", "")
        content = article.get("content", "")
        url = article.get("url", "")
        
        logger.info("Processing article with multi-agent system", 
                   article_index=index+1,
                   title=title[:100])
        
        try:
            # Create the group chat for this article
            team = RoundRobinGroupChat(
                participants=[
                    self.summarizer_agent,
                    self.analyst_agent, 
                    self.critic_agent,
                    self.coordinator_agent
                ],
                max_turns=8  # Each agent responds twice (4 agents * 2 turns each)
            )
            
            # Initial message with article content
            initial_message = f"""
Please process this news article through our collaborative workflow:

TITLE: {title}

CONTENT: {content[:3000]}  # Limit content for processing

URL: {url}

NewsumMarizer: Please start by creating an initial summary.
NewsAnalyst: Then provide your analysis.
QualityReviewer: Review the work and suggest improvements.  
WorkflowCoordinator: Finally, create the polished final version.
            """.strip()
            
            # Run the conversation
            result = await team.run(
                task=TextMessage(content=initial_message, source="user")
            )
            
            # Extract the final result from the coordinator
            final_message = result.messages[-1].content if result.messages else "No result generated"
            
            # Parse the structured output
            parsed_result = self._parse_agent_output(final_message)
            
            return {
                "article_index": index + 1,  # Keep for logging/display purposes
                "article_id": article.get("id") or article.get("db_id"),  # Use actual database ID
                "article_title": title,
                "article_url": url,
                "summary": parsed_result.get("summary", "Summary not generated"),
                "key_points": parsed_result.get("key_points", []),
                "analysis": parsed_result.get("analysis", "Analysis not generated"),
                "implications": parsed_result.get("implications", []),
                "outlook": parsed_result.get("outlook", "Outlook not generated"),
                "agent_conversation": [msg.content for msg in result.messages[-4:]]  # Last 4 messages
            }
            
        except Exception as e:
            logger.error("Multi-agent processing failed for article", 
                        article_index=index,
                        error=str(e))
            
            # Fallback to basic processing
            return {
                "article_index": index + 1,  # Keep for logging/display purposes
                "article_id": article.get("id") or article.get("db_id"),  # Use actual database ID
                "article_title": title,
                "article_url": url,
                "summary": f"Processing failed: {title}",
                "key_points": ["Multi-agent processing unavailable"],
                "analysis": "Analysis generation failed",
                "implications": ["Impact assessment pending"],
                "outlook": "Further analysis needed",
                "agent_conversation": [f"Error: {str(e)}"]
            }
    
    def _parse_agent_output(self, content: str) -> Dict[str, Any]:
        """
        Parse structured output from the coordinator agent.
        
        Args:
            content: Raw agent output
            
        Returns:
            Parsed structured data
        """
        try:
            result = {
                "summary": "",
                "key_points": [],
                "analysis": "",
                "implications": [],
                "outlook": ""
            }
            
            lines = content.split('\n')
            current_section = None
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                # Identify sections
                if 'SUMMARY:' in line.upper():
                    result["summary"] = line.split(':', 1)[1].strip()
                    current_section = "summary"
                elif 'KEY POINTS:' in line.upper():
                    current_section = "key_points"
                elif 'SIGNIFICANCE:' in line.upper():
                    result["analysis"] = line.split(':', 1)[1].strip()
                    current_section = "analysis"
                elif 'STRATEGIC IMPLICATIONS:' in line.upper():
                    current_section = "implications"
                elif 'OUTLOOK:' in line.upper():
                    result["outlook"] = line.split(':', 1)[1].strip()
                    current_section = "outlook"
                elif line.startswith('•') or line.startswith('-'):
                    # Extract bullet points
                    point = line[1:].strip()
                    if current_section == "key_points":
                        result["key_points"].append(point)
                    elif current_section == "implications":
                        result["implications"].append(point)
            
            # Ensure we have at least basic content
            if not result["summary"]:
                result["summary"] = "Summary extraction failed"
            if not result["key_points"]:
                result["key_points"] = ["Key points not available"]
            if not result["analysis"]:
                result["analysis"] = "Analysis not available"
                
            return result
            
        except Exception as e:
            logger.error("Failed to parse agent output", error=str(e))
            return {
                "summary": "Parsing failed",
                "key_points": ["Output parsing error"],
                "analysis": "Analysis parsing failed", 
                "implications": ["Impact assessment failed"],
                "outlook": "Outlook parsing failed"
            }
    
    async def _save_multi_agent_results(self, results: List[Dict[str, Any]]):
        """
        Save multi-agent processing results to database.
        
        Args:
            results: List of processing results
        """
        db = SessionLocal()
        try:
            for result in results:
                # Save summary
                summary = NewsSummary(
                    job_id=self.job_id,
                    article_id=result["article_id"],  # Use actual database ID instead of array index
                    summary=result["summary"],
                    bullet_points=result["key_points"],
                    processing_time=0.0,  # Will be calculated at workflow level
                    created_at=datetime.utcnow()
                )
                db.add(summary)
                db.flush()  # Flush to get the summary ID
                
                # Save analysis
                analysis = NewsAnalysis(
                    job_id=self.job_id,
                    summary_ids=[summary.id],  # Use the actual summary ID from the saved summary
                    analysis=result["analysis"],
                    insights=result["implications"],
                    impact_assessment=result["outlook"],
                    processing_time=0.0,
                    created_at=datetime.utcnow()
                )
                db.add(analysis)
            
            db.commit()
            logger.info("Multi-agent results saved to database", count=len(results))
            
        except Exception as e:
            db.rollback()
            logger.error("Failed to save multi-agent results", error=str(e))
            raise
        finally:
            db.close()