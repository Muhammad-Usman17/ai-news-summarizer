"""
Simplified Multi-Agent News Processing System

This system creates specialized AI agents that collaborate using Groq for fast inference:
- SummarizerAgent: Creates initial summaries
- AnalystAgent: Analyzes implications and trends  
- CriticAgent: Reviews and improves the work
- CoordinatorAgent: Orchestrates the workflow

Each agent specializes in different aspects but they work together sequentially.
"""

import asyncio
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()

from app.services.groq_client import GroqClient
from app.models.news import NewsArticle, NewsSummary
from app.config.logging import get_logger
from app.services.redis_stream import RedisStreamService
from app.config.database import SessionLocal

logger = get_logger(__name__)


class SimpleMultiAgentProcessor:
    """
    Simplified multi-agent system that processes news through specialized agents.
    Each agent has a specific role and they work together in sequence.
    """
    
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.groq_client = GroqClient()
        self.redis_stream = RedisStreamService()
        
        # Agent system prompts
        self.agent_prompts = {
            "summarizer": """You are an expert news summarizer with deep knowledge of technology, business, and current events.

Your role:
- Create concise, accurate summaries of news articles
- Extract the most important information
- Identify key stakeholders and implications
- Focus on facts, not opinions
- Use clear, professional language

Format your response EXACTLY as:
HEADLINE: [One compelling headline]
SUMMARY: [2-3 sentences covering the main story]
KEY_POINTS:
• [Most important point]
• [Second important point] 
• [Third important point]

Be precise, factual, and engaging.""",

            "analyst": """You are a senior technology and business analyst with expertise in market trends, industry dynamics, and strategic implications.

Your role:
- Analyze the deeper meaning and implications of news
- Identify market impacts, competitive dynamics
- Assess short and long-term consequences
- Connect developments to broader trends
- Provide strategic insights for decision makers

Based on the summary provided, format your analysis EXACTLY as:
SIGNIFICANCE: [Why this matters - business/tech/market perspective]
IMPLICATIONS:
• [Business implication]
• [Technology implication]
• [Market/industry implication]
IMPACT_ASSESSMENT: [Short-term and long-term effects]
CONNECTIONS: [How this relates to other trends/developments]

Be insightful, strategic, and forward-looking.""",

            "critic": """You are a senior editorial reviewer and fact-checker with expertise in journalism standards and analytical rigor.

Your role:
- Review summaries and analyses for accuracy and completeness
- Identify gaps, inconsistencies, or areas for improvement
- Ensure clarity and professional presentation
- Verify logical reasoning and conclusions
- Suggest specific improvements

Review the provided summary and analysis, then format your review EXACTLY as:
QUALITY_ASSESSMENT: [Overall quality rating and brief evaluation]
STRENGTHS:
• [What works well]
• [Strong points to maintain]
IMPROVEMENT_AREAS:
• [Specific suggestions for enhancement]
• [Missing elements or weak points]
RECOMMENDATIONS: [Concrete steps to improve the work]

Be constructive, specific, and quality-focused.""",

            "coordinator": """You are a senior editorial coordinator responsible for producing final, polished news summaries and analyses.

Your role:
- Synthesize input from summarizer, analyst, and reviewer
- Create final, polished versions incorporating all feedback
- Ensure consistency and professional presentation
- Balance accuracy with readability
- Deliver publication-ready content

Based on all the previous agent inputs, create the final output formatted EXACTLY as:
=== FINAL_SUMMARY ===
HEADLINE: [Refined, compelling headline]
SUMMARY: [Polished 2-3 sentence summary]
KEY_POINTS:
• [Refined key point 1]
• [Refined key point 2] 
• [Refined key point 3]

=== ANALYSIS ===
SIGNIFICANCE: [Why this matters]
STRATEGIC_IMPLICATIONS:
• [Business impact]
• [Technology impact]
• [Market impact]
OUTLOOK: [What to watch for next]

Be authoritative, clear, and comprehensive."""
        }
    
    async def process_articles(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Process articles through the multi-agent collaboration system.
        
        Args:
            articles: List of article dictionaries
            
        Returns:
            Results from multi-agent processing
        """
        logger.info("Starting multi-agent news processing", 
                   job_id=self.job_id,
                   articles_count=len(articles))
        
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
            "total_count": len(articles),
            "job_id": self.job_id
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
        
        The workflow is:
        1. Summarizer creates initial summary
        2. Analyst provides deeper analysis
        3. Critic reviews and suggests improvements
        4. Coordinator creates final polished version
        
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
        
        # Track conversation history
        conversation_history = []
        
        try:
            # Step 1: Summarizer Agent
            logger.debug("Running summarizer agent", article_index=index+1)
            
            summarizer_input = f"""
Please process this news article:

TITLE: {title}
CONTENT: {content[:2500]}
URL: {url}
            """.strip()
            
            summarizer_response = await self.groq_client.chat(
                messages=[
                    {"role": "system", "content": self.agent_prompts["summarizer"]},
                    {"role": "user", "content": summarizer_input}
                ],
                model="llama-3.1-8b-instant",
                temperature=0.1
            )
            
            conversation_history.append(f"SUMMARIZER: {summarizer_response}")
            
            # Step 2: Analyst Agent
            logger.debug("Running analyst agent", article_index=index+1)
            
            analyst_input = f"""
Here is the news summary to analyze:

{summarizer_response}

Original article context:
TITLE: {title}
URL: {url}
            """.strip()
            
            analyst_response = await self.groq_client.chat(
                messages=[
                    {"role": "system", "content": self.agent_prompts["analyst"]},
                    {"role": "user", "content": analyst_input}
                ],
                model="llama-3.3-70b-versatile",  # Use more powerful model for analysis
                temperature=0.2
            )
            
            conversation_history.append(f"ANALYST: {analyst_response}")
            
            # Step 3: Critic Agent
            logger.debug("Running critic agent", article_index=index+1)
            
            critic_input = f"""
Review this news processing work:

SUMMARIZER OUTPUT:
{summarizer_response}

ANALYST OUTPUT:
{analyst_response}

Original article: {title}
            """.strip()
            
            critic_response = await self.groq_client.chat(
                messages=[
                    {"role": "system", "content": self.agent_prompts["critic"]},
                    {"role": "user", "content": critic_input}
                ],
                model="llama-3.1-8b-instant",
                temperature=0.1
            )
            
            conversation_history.append(f"CRITIC: {critic_response}")
            
            # Step 4: Coordinator Agent
            logger.debug("Running coordinator agent", article_index=index+1)
            
            coordinator_input = f"""
Create the final polished version incorporating all agent feedback:

SUMMARIZER OUTPUT:
{summarizer_response}

ANALYST OUTPUT:
{analyst_response}

CRITIC FEEDBACK:
{critic_response}

Original article: {title}
            """.strip()
            
            coordinator_response = await self.groq_client.chat(
                messages=[
                    {"role": "system", "content": self.agent_prompts["coordinator"]},
                    {"role": "user", "content": coordinator_input}
                ],
                model="llama-3.3-70b-versatile",  # Use powerful model for final synthesis
                temperature=0.1
            )
            
            conversation_history.append(f"COORDINATOR: {coordinator_response}")
            
            # Parse the final structured output
            parsed_result = self._parse_coordinator_output(coordinator_response)
            
            logger.info("Multi-agent processing completed for article", 
                       article_index=index+1)
            
            return {
                "article_index": index + 1,
                "article_title": title,
                "article_url": url,
                "summary": parsed_result.get("summary", "Summary not generated"),
                "headline": parsed_result.get("headline", title),
                "key_points": parsed_result.get("key_points", []),
                "analysis": parsed_result.get("analysis", "Analysis not generated"),
                "implications": parsed_result.get("implications", []),
                "outlook": parsed_result.get("outlook", "Outlook not generated"),
                "agent_conversation": conversation_history,
                "processing_time": 0.0  # Will be calculated at higher level
            }
            
        except Exception as e:
            logger.error("Multi-agent processing failed for article", 
                        article_index=index,
                        error=str(e))
            
            # Return basic fallback
            return {
                "article_index": index + 1,
                "article_title": title,
                "article_url": url,
                "summary": f"Multi-agent processing failed for: {title}",
                "headline": title,
                "key_points": ["Multi-agent processing unavailable"],
                "analysis": "Analysis generation failed",
                "implications": ["Impact assessment pending"],
                "outlook": "Further analysis needed",
                "agent_conversation": [f"Error: {str(e)}"],
                "processing_time": 0.0
            }
    
    def _parse_coordinator_output(self, content: str) -> Dict[str, Any]:
        """
        Parse structured output from the coordinator agent.
        
        Args:
            content: Raw agent output
            
        Returns:
            Parsed structured data
        """
        try:
            result = {
                "headline": "",
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
                if 'HEADLINE:' in line:
                    result["headline"] = line.split(':', 1)[1].strip()
                elif 'SUMMARY:' in line:
                    result["summary"] = line.split(':', 1)[1].strip()
                elif 'KEY_POINTS:' in line:
                    current_section = "key_points"
                elif 'SIGNIFICANCE:' in line:
                    result["analysis"] = line.split(':', 1)[1].strip()
                elif 'STRATEGIC_IMPLICATIONS:' in line:
                    current_section = "implications"
                elif 'OUTLOOK:' in line:
                    result["outlook"] = line.split(':', 1)[1].strip()
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
            logger.error("Failed to parse coordinator output", error=str(e))
            return {
                "headline": "Parsing failed",
                "summary": "Parsing failed",
                "key_points": ["Output parsing error"],
                "analysis": "Analysis parsing failed", 
                "implications": ["Impact assessment failed"],
                "outlook": "Outlook parsing failed"
            }


# For backwards compatibility, create an alias
MultiAgentNewsProcessor = SimpleMultiAgentProcessor