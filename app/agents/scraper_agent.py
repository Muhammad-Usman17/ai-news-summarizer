import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict, Any
import asyncio
from urllib.parse import urljoin, urlparse
from prometheus_client import Counter

from app.config.settings import get_settings
from app.config.logging import get_logger, LogContext
from app.config.database import SessionLocal
from app.models.news import NewsArticle
from app.services.redis_stream import RedisStreamService

logger = get_logger(__name__)
settings = get_settings()

# Prometheus Metrics
ARTICLES_SCRAPED = Counter('news_articles_scraped_total', 'Total articles scraped', ['source'])


class ScraperAgent:
    """Agent responsible for scraping news articles from RSS feeds."""
    
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.redis_stream = RedisStreamService()
        self.rss_feeds = settings.rss_feeds.split(",")
        
    async def run(self, target_date: str = None) -> Dict[str, Any]:
        """
        Execute the scraper agent.
        
        Args:
            target_date: Target date for scraping in YYYY-MM-DD format
        
        Returns:
            Dict containing scraped articles
        """
        # Store target_date for use in article processing
        self._target_date = target_date
        
        with LogContext(job_id=self.job_id, agent="ScraperAgent"):
            date_msg = f" for {target_date}" if target_date else ""
            logger.info("Starting news scraping", target_date=target_date)
            
            # Send status update
            await self.redis_stream.publish_update(
                job_id=self.job_id,
                status="scraping_started",
                message=f"Starting news article scraping{date_msg}"
            )
            
            all_articles = []
            
            for feed_url in self.rss_feeds:
                feed_url = feed_url.strip()
                try:
                    logger.info("Scraping feed", feed_url=feed_url, target_date=target_date)
                    articles = await self._scrape_feed(feed_url, target_date)
                    all_articles.extend(articles)
                    
                except Exception as e:
                    logger.error("Failed to scrape feed", feed_url=feed_url, error=str(e))
                    continue
            
            # Remove duplicates
            unique_articles = await self._remove_duplicates(all_articles)
            logger.info("Duplicate removal completed", 
                       original_count=len(all_articles), 
                       unique_count=len(unique_articles))
            
            # Limit to top 5 unique articles
            top_articles = unique_articles[:5]
            
            # Save articles to database
            await self._save_articles(top_articles)
            
            # Send completion update
            await self.redis_stream.publish_update(
                job_id=self.job_id,
                status="scraping_completed",
                message=f"Scraping completed. Found {len(top_articles)} articles",
                data={"articles_count": len(top_articles)}
            )
            
            logger.info("News scraping completed", articles_count=len(top_articles))
            
            return {
                "articles": top_articles,
                "total_scraped": len(all_articles),
                "selected_count": len(top_articles)
            }
    
    async def _scrape_feed(self, feed_url: str, target_date: str = None) -> List[Dict[str, Any]]:
        """
        Scrape articles from a single RSS feed.
        
        Args:
            feed_url: RSS feed URL
            target_date: Target date for filtering articles (YYYY-MM-DD format)
            
        Returns:
            List of article dictionaries
        """
        articles = []
        
        try:
            # Configure headers and SSL handling for RSS parsing
            import ssl
            import certifi
            
            # Create SSL context that doesn't verify certificates (for problematic feeds)
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            # Parse RSS feed with better error handling
            feed = feedparser.parse(feed_url, agent="NewsBot/1.0")
            
            if feed.bozo:
                logger.warning("Feed parsing had issues", feed_url=feed_url, 
                             error=str(getattr(feed, 'bozo_exception', 'Unknown')))
                # Continue processing even with bozo flag - many feeds still work
            
            # Check if feed has entries
            if not hasattr(feed, 'entries') or not feed.entries:
                logger.warning("No entries found in feed", feed_url=feed_url, 
                             feed_keys=list(feed.keys()) if hasattr(feed, 'keys') else [])
                return articles
                
            logger.info("Feed parsed successfully", feed_url=feed_url, 
                       entries_count=len(feed.entries), 
                       feed_title=feed.feed.get('title', 'Unknown'))
            
            # Extract source name from feed
            source_name = feed.feed.get('title', urlparse(feed_url).netloc)
            
            # Track filtering statistics
            total_entries = len(feed.entries[:10])  # We only process first 10 entries
            filtered_by_date = 0
            processed_count = 0
            
            for i, entry in enumerate(feed.entries[:10]):  # Limit per feed
                try:
                    # Filter by date if target_date is provided
                    if target_date and not self._is_article_from_target_date(entry, target_date):
                        filtered_by_date += 1
                        logger.debug("Filtered out by date", 
                                   title=entry.get('title', 'No title')[:50],
                                   target_date=target_date)
                        continue
                    
                    processed_count += 1
                    logger.info("Processing article", feed_url=feed_url, 
                               article_num=processed_count, 
                               title=entry.get('title', 'No title')[:100])
                    
                    article = await self._extract_article_content(entry, source_name, target_date)
                    if article:
                        articles.append(article)
                        logger.info("Article extracted successfully", 
                                   title=article.get('title', '')[:100])
                    else:
                        logger.warning("Article extraction returned None", 
                                     entry_title=entry.get('title', 'No title')[:50])
                        
                except Exception as e:
                    logger.error("Failed to extract article", 
                               entry_url=entry.get('link'), error=str(e))
                    continue
            
            # Log filtering statistics
            if target_date:
                logger.info("Feed processing completed with date filtering", 
                           source=source_name,
                           total_entries=total_entries,
                           filtered_by_date=filtered_by_date, 
                           processed=processed_count,
                           extracted=len(articles),
                           target_date=target_date)
                    
        except Exception as e:
            logger.error("Failed to parse RSS feed", feed_url=feed_url, error=str(e))
            raise
        
        return articles
    
    def _is_article_from_target_date(self, entry, target_date: str) -> bool:
        """
        Check if an RSS entry is from the exact target date.
        
        Args:
            entry: RSS feed entry
            target_date: Target date in YYYY-MM-DD format
            
        Returns:
            True if article is published exactly on the target date
        """
        try:
            from datetime import datetime, date
            
            target_date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
            
            # Parse published date from entry
            published_at = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                try:
                    published_at = datetime(*entry.published_parsed[:6]).date()
                except Exception as e:
                    logger.debug("Failed to parse published_parsed date", error=str(e))
            
            # Try alternative date fields if published_parsed failed
            if not published_at:
                for date_field in ['updated_parsed', 'created_parsed']:
                    if hasattr(entry, date_field) and getattr(entry, date_field):
                        try:
                            published_at = datetime(*getattr(entry, date_field)[:6]).date()
                            break
                        except Exception as e:
                            logger.debug(f"Failed to parse {date_field} date", error=str(e))
            
            # If we still don't have a published date, reject the article for strict date filtering
            if not published_at:
                logger.debug("No published date found for article - rejecting for date filtering",
                           title=entry.get('title', 'No title')[:50],
                           target_date=target_date)
                return False
            
            # Only include articles from the exact target date
            is_match = published_at == target_date_obj
            
            if not is_match:
                logger.debug("Article date mismatch", 
                           article_date=str(published_at),
                           target_date=target_date,
                           title=entry.get('title', 'No title')[:50])
            
            return is_match
            
        except Exception as e:
            logger.warning("Error checking article date", error=str(e))
            # If we can't parse dates, include the article
            return True
    
    async def _extract_article_content(self, entry, source_name: str, target_date: str = None) -> Dict[str, Any]:
        """
        Extract full content from an RSS entry.
        
        Args:
            entry: RSS feed entry
            source_name: Name of the news source
            
        Returns:
            Article dictionary with full content
        """
        title = entry.get('title', '').strip()
        url = entry.get('link', '').strip()
        
        if not title or not url:
            logger.warning("Missing title or URL", title=bool(title), url=bool(url))
            return None
        
        # Get summary from RSS - try multiple fields
        summary = (entry.get('summary', '') or 
                  entry.get('description', '') or 
                  entry.get('content', [{}])[0].get('value', '') if entry.get('content') else '')
        
        # Clean up HTML tags from summary if present
        if summary:
            from bs4 import BeautifulSoup
            summary = BeautifulSoup(summary, 'html.parser').get_text(strip=True)
        
        # For tech news, ensure we have some content to work with
        if not summary or len(summary.strip()) < 50:
            logger.warning("Summary too short or missing", 
                         title=title[:100], summary_length=len(summary) if summary else 0)
            # Still create article but mark it
            summary = f"Content available at: {url}"
        
        # Try to get full content by scraping the article page
        full_content = await self._scrape_article_page(url)
        
        # Use full content if available and substantial, otherwise fall back to summary
        content = full_content if full_content and len(full_content) > 200 else summary
        
        # Parse published date with fallback logic
        published_at = None
        
        # First, try to get from RSS feed
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            try:
                published_at = datetime(*entry.published_parsed[:6])
            except:
                pass
        
        # If no RSS date and we have a target_date, use target_date as fallback
        if not published_at and hasattr(self, '_target_date') and self._target_date:
            try:
                # Use target_date as the published date for historical scraping
                target_datetime = datetime.strptime(self._target_date, "%Y-%m-%d")
                published_at = target_datetime
            except:
                pass
        
        # If still no date, use current time (for real-time scraping)
        if not published_at:
            published_at = datetime.utcnow()
        
        return {
            "title": title,
            "url": url,
            "content": content,
            "source": source_name,
            "published_at": published_at,
            "summary": summary
        }
    
    async def _scrape_article_page(self, url: str) -> str:
        """
        Scrape the full content from an article page.
        
        Args:
            url: Article URL
            
        Returns:
            Full article content or empty string if failed
        """
        try:
            # Add timeout and headers
            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; NewsBot/1.0)'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove unwanted elements
            for element in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
                element.decompose()
            
            # Try different content selectors
            content_selectors = [
                'article',
                '[role="main"]',
                '.content',
                '.article-content',
                '.post-content',
                '.entry-content',
                'main',
                '.story-body'
            ]
            
            content = ""
            for selector in content_selectors:
                elements = soup.select(selector)
                if elements:
                    # Get text from the first matching element
                    content = elements[0].get_text(strip=True, separator=' ')
                    if len(content) > 200:  # Ensure we got substantial content
                        break
            
            # If no content found with selectors, try to get all paragraph text
            if not content or len(content) < 200:
                paragraphs = soup.find_all('p')
                content = ' '.join([p.get_text(strip=True) for p in paragraphs])
            
            # Clean up the content
            content = ' '.join(content.split())  # Normalize whitespace
            
            return content[:5000]  # Limit content length
            
        except Exception as e:
            logger.warning("Failed to scrape article content", url=url, error=str(e))
            return ""
    
    async def _remove_duplicates(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Remove duplicate articles based on URL and title similarity.
        
        Args:
            articles: List of article dictionaries
            
        Returns:
            List of unique articles
        """
        if not articles:
            return articles
        
        unique_articles = []
        seen_urls = set()
        seen_titles = set()
        
        for article in articles:
            url = article.get("url", "").strip().lower()
            title = article.get("title", "").strip().lower()
            
            # Skip if URL already seen
            if url in seen_urls:
                logger.info("Skipping duplicate URL", url=url[:100])
                continue
            
            # Check for title similarity (simple approach - exact match after normalization)
            title_normalized = self._normalize_title(title)
            if title_normalized in seen_titles:
                logger.info("Skipping similar title", title=title[:100])
                continue
            
            # Check against existing articles in database for this job
            if await self._is_duplicate_in_db(url, title):
                logger.info("Skipping existing article in database", title=title[:100])
                continue
            
            # Article is unique
            unique_articles.append(article)
            seen_urls.add(url)
            seen_titles.add(title_normalized)
        
        return unique_articles
    
    def _normalize_title(self, title: str) -> str:
        """Normalize title for duplicate detection."""
        import re
        # Remove special characters, extra spaces, and convert to lowercase
        normalized = re.sub(r'[^\w\s]', '', title.lower())
        normalized = ' '.join(normalized.split())  # Remove extra whitespace
        return normalized[:100]  # Limit length for comparison
    
    async def _is_duplicate_in_db(self, url: str, title: str) -> bool:
        """
        Check if article already exists in database.
        
        Args:
            url: Article URL
            title: Article title
            
        Returns:
            True if duplicate exists
        """
        try:
            db = SessionLocal()
            existing = db.query(NewsArticle).filter(
                (NewsArticle.url == url) | 
                (NewsArticle.title.ilike(f"%{title[:50]}%"))
            ).first()
            db.close()
            return existing is not None
        except Exception as e:
            logger.warning("Error checking database for duplicates", error=str(e))
            return False
    
    async def _save_articles(self, articles: List[Dict[str, Any]]):
        """
        Save articles to the database and update them with their database IDs.
        
        Args:
            articles: List of article dictionaries (modified in-place with IDs)
        """
        db = SessionLocal()
        try:
            for i, article_data in enumerate(articles):
                article = NewsArticle(
                    job_id=self.job_id,
                    title=article_data["title"],
                    url=article_data["url"],
                    content=article_data["content"],
                    source=article_data["source"],
                    published_at=article_data.get("published_at"),
                    scraped_at=datetime.utcnow()
                )
                db.add(article)
                db.flush()  # Flush to get the ID before commit
                
                # Update the article dictionary with the database ID
                article_data["id"] = article.id
                article_data["db_id"] = article.id  # Alternative key for clarity
                
                # Update Prometheus metrics
                ARTICLES_SCRAPED.labels(source=article_data["source"]).inc()
            
            db.commit()
            logger.info("Articles saved to database with IDs", count=len(articles))
            
        except Exception as e:
            db.rollback()
            logger.error("Failed to save articles", error=str(e))
            raise
        finally:
            db.close()