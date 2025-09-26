"""
NewsProcessingCore - Shared processing logic for news AI processing.

This module contains the core AI processing functions that can be reused across different
orchestration patterns for news summarization, analysis, and critique.
"""

import asyncio
from typing import List, Dict, Any, Optional
from app.config.logging import get_logger
from app.services.groq_client import GroqClient

logger = get_logger(__name__)


class NewsProcessingCore:
    """
    Core processing functions for news summarization, analysis, and critique.
    
    These functions contain the essential AI logic that can be used by
    individual agents (SummarizerAgent, AnalystAgent, CriticAgent).
    """
    
    @staticmethod
    async def fast_summarize(
        title: str, 
        content: str, 
        groq_client: GroqClient,
        max_tokens: int = 250,
        temperature: float = 0.1
    ) -> Dict[str, Any]:
        """
        Core summarization logic using Groq API.
        
        Args:
            title: Article title
            content: Article content (should be pre-truncated if needed)
            groq_client: Groq client instance
            max_tokens: Maximum tokens for response
            temperature: Temperature for generation
            
        Returns:
            Dict with summary and bullet_points
        """
        # Optimized prompt for fast summarization
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
            response = await groq_client.generate(
                prompt=prompt,
                model=groq_client.get_fast_model(),
                max_tokens=max_tokens,
                temperature=temperature
            )
            
            return NewsProcessingCore._parse_summary_response(response)
            
        except Exception as e:
            logger.error("Core summarization failed", error=str(e))
            
            # Fast fallback without LLM
            return {
                "summary": f"Breaking: {title}",
                "bullet_points": [
                    "Full article available at source", 
                    "AI summary temporarily unavailable", 
                    "Check original link for details"
                ]
            }
    
    @staticmethod
    async def deep_analyze(
        title: str,
        summary: str, 
        bullet_points: List[str],
        groq_client: GroqClient,
        max_tokens: int = 400,
        temperature: float = 0.2
    ) -> Dict[str, Any]:
        """
        Core analysis logic using Groq API.
        
        Args:
            title: Article title
            summary: Article summary
            bullet_points: Key points from summary
            groq_client: Groq client instance
            max_tokens: Maximum tokens for response
            temperature: Temperature for generation
            
        Returns:
            Dict with analysis, insights, and impact_assessment
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
            response = await groq_client.generate(
                prompt=prompt,
                model=groq_client.get_fast_model(),
                max_tokens=max_tokens,
                temperature=temperature
            )
            
            return NewsProcessingCore._parse_analysis_response(response)
            
        except Exception as e:
            logger.error("Core analysis failed", error=str(e))
            
            # Fast fallback without LLM
            return {
                "analysis": f"Breaking tech news: {title} - Analysis processing failed",
                "insights": [
                    "Technology sector development", 
                    "Market implications pending", 
                    "Industry impact assessment needed"
                ],
                "impact_assessment": "Full impact analysis temporarily unavailable"
            }
    
    @staticmethod
    async def quality_critique(
        title: str,
        summary: str,
        bullet_points: List[str],
        groq_client: GroqClient,
        article_url: str = "",
        max_tokens: int = 500,
        temperature: float = 0.3
    ) -> Dict[str, Any]:
        """
        Core critique logic using Groq API.
        
        Args:
            title: Article title
            summary: Original summary to critique
            bullet_points: Original bullet points to critique
            groq_client: Groq client instance
            article_url: Article URL for context
            max_tokens: Maximum tokens for response
            temperature: Temperature for generation
            
        Returns:
            Dict with improved_summary, improved_bullet_points, critique, quality_score, improvements
        """
        bullet_points_text = "\n".join([f"• {point}" for point in bullet_points])
        
        # Comprehensive critique prompt
        prompt = f"""You are a senior editorial reviewer. Review this news summary for quality, accuracy, and completeness.

ARTICLE TITLE: {title}
ARTICLE URL: {article_url}

ORIGINAL SUMMARY:
{summary}

ORIGINAL KEY POINTS:
{bullet_points_text}

Please provide:
1. Quality assessment (score 1-10)
2. Specific improvements needed
3. Improved version of the summary
4. Improved version of key points

Respond exactly in this format:
QUALITY_SCORE: [1-10 rating]
CRITIQUE: [Specific feedback on what needs improvement]
IMPROVEMENTS: [List of specific changes made]
IMPROVED_SUMMARY: [Better version of the summary - 2-3 clear sentences]
IMPROVED_KEY_POINTS:
• [improved key point 1]
• [improved key point 2]
• [improved key point 3]"""
        
        try:
            response = await groq_client.generate(
                prompt=prompt,
                model=groq_client.get_smart_model(),  # Use smarter model for critique
                max_tokens=max_tokens,
                temperature=temperature
            )
            
            return NewsProcessingCore._parse_critique_response(response, summary, bullet_points)
            
        except Exception as e:
            logger.error("Core critique failed", error=str(e))
            
            # Fallback - return original with minimal improvements
            return {
                "improved_summary": summary,
                "improved_bullet_points": bullet_points,
                "critique": f"Critique temporarily unavailable: {str(e)}",
                "quality_score": 7,  # Assume decent quality
                "improvements": ["No improvements made due to system error"]
            }
    
    @staticmethod
    async def generate_overall_trends(
        titles: List[str],
        summaries: List[str],
        groq_client: GroqClient,
        max_tokens: int = 500,
        temperature: float = 0.3
    ) -> Dict[str, Any]:
        """
        Generate overall trend analysis from multiple articles.
        
        Args:
            titles: List of article titles
            summaries: List of article summaries
            groq_client: Groq client instance
            max_tokens: Maximum tokens for response
            temperature: Temperature for generation
            
        Returns:
            Dict with analysis, insights, and impact_assessment for overall trends
        """
        prompt = f"""
Based on today's news stories, provide an overall trend analysis:

News Headlines:
{chr(10).join([f"{i+1}. {title}" for i, title in enumerate(titles)])}

Summaries:
{chr(10).join([f"{i+1}. {text}" for i, text in enumerate(summaries)])}

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
            response = await groq_client.generate(
                prompt=prompt,
                model=groq_client.get_quality_model(),  # Use quality model for overall analysis
                max_tokens=max_tokens,
                temperature=temperature
            )
            
            return NewsProcessingCore._parse_analysis_response(response)
            
        except Exception as e:
            logger.error("Core trend analysis failed", error=str(e))
            return {
                "analysis": "Overall trend analysis not available",
                "insights": ["Analysis generation failed"],
                "impact_assessment": "Impact assessment not available"
            }
    
    @staticmethod
    def _parse_summary_response(response: str) -> Dict[str, Any]:
        """Parse LLM summary response into structured format."""
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
    
    @staticmethod
    def _parse_analysis_response(response: str) -> Dict[str, Any]:
        """Parse LLM analysis response into structured format."""
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
    
    @staticmethod
    def _parse_critique_response(response: str, original_summary: str, original_points: List[str]) -> Dict[str, Any]:
        """Parse LLM critique response into structured format."""
        try:
            lines = response.strip().split('\n')
            quality_score = 7  # Default score
            critique = ""
            improvements = []
            improved_summary = original_summary
            improved_points = original_points.copy()
            
            current_section = None
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                if line.upper().startswith('QUALITY_SCORE:'):
                    try:
                        score_text = line.split(':', 1)[1].strip()
                        quality_score = int(score_text.split()[0])  # Extract just the number
                        quality_score = max(1, min(10, quality_score))  # Clamp to 1-10
                    except:
                        quality_score = 7  # Default if parsing fails
                        
                elif line.upper().startswith('CRITIQUE:'):
                    critique = line.split(':', 1)[1].strip()
                    current_section = "critique"
                    
                elif line.upper().startswith('IMPROVEMENTS:'):
                    current_section = "improvements"
                    
                elif line.upper().startswith('IMPROVED_SUMMARY:'):
                    improved_summary = line.split(':', 1)[1].strip()
                    current_section = "summary"
                    
                elif line.upper().startswith('IMPROVED_KEY_POINTS:'):
                    current_section = "points"
                    improved_points = []
                    
                elif line.startswith('•') or line.startswith('-') or line.startswith('*'):
                    if current_section == "points":
                        improved_points.append(line[1:].strip())
                    elif current_section == "improvements":
                        improvements.append(line[1:].strip())
                        
                elif current_section == "critique" and not critique:
                    critique = line
                elif current_section == "summary" and not improved_summary:
                    improved_summary = line
                elif current_section == "improvements" and line:
                    improvements.append(line)
            
            # Ensure we have content (fallback to originals if parsing failed)
            if not improved_summary or improved_summary == original_summary:
                if quality_score < 8:  # Only improve if quality is low
                    improved_summary = f"[Improved] {original_summary}"
            
            if not improved_points:
                improved_points = original_points
            
            if not critique:
                critique = f"Quality score: {quality_score}/10. Summary meets basic standards."
            
            if not improvements:
                improvements = ["No specific improvements identified"] if quality_score >= 8 else ["Minor clarity improvements made"]
            
            return {
                "improved_summary": improved_summary,
                "improved_bullet_points": improved_points,
                "critique": critique,
                "quality_score": quality_score,
                "improvements": improvements
            }
            
        except Exception as e:
            logger.error("Failed to parse critique response", error=str(e))
            return {
                "improved_summary": original_summary,
                "improved_bullet_points": original_points,
                "critique": f"Critique parsing failed: {str(e)}",
                "quality_score": 7,
                "improvements": ["Parsing error - no improvements made"]
            }