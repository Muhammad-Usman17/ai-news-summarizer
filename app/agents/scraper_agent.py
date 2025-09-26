import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict, Any, Optional
import asyncio
from urllib.parse import urljoin, urlparse
from prometheus_client import Counter
import urllib3

from app.config.settings import get_settings
from app.config.logging import get_logger, LogContext
from app.config.database import SessionLocal
from app.models.news import NewsArticle
from app.services.redis_stream import RedisStreamService

# Disable SSL warnings for problematic feeds
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
            target_date: Deprecated - scraper now fetches latest news regardless of date
        
        Returns:
            Dict containing scraped articles
        """
        with LogContext(job_id=self.job_id, agent="ScraperAgent"):
            logger.info("Starting latest news scraping")
            
            # Send status update
            await self.redis_stream.publish_update(
                job_id=self.job_id,
                status="scraping_started",
                message="Starting latest news article scraping"
            )
            
            all_articles = []
            
            for feed_url in self.rss_feeds:
                feed_url = feed_url.strip()
                try:
                    logger.info("Scraping feed for latest news", feed_url=feed_url)
                    articles = await self._scrape_feed(feed_url)
                    all_articles.extend(articles)
                    
                except Exception as e:
                    logger.error("Failed to scrape feed", feed_url=feed_url, error=str(e))
                    continue
            
            # Remove duplicates
            unique_articles = await self._remove_duplicates(all_articles)
            logger.info("Duplicate removal completed", 
                       original_count=len(all_articles), 
                       unique_count=len(unique_articles))
            
            # Increase limit to top 10 unique articles (was 5)
            top_articles = unique_articles[:10]
            
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
    
    async def _scrape_feed(self, feed_url: str) -> List[Dict[str, Any]]:
        """
        Scrape latest articles from a single RSS feed.
        
        Args:
            feed_url: RSS feed URL
            
        Returns:
            List of article dictionaries
        """
        articles = []
        
        try:
            # Configure SSL handling for RSS parsing
            logger.info("Attempting to parse RSS feed", feed_url=feed_url)
            
            # Try multiple approaches for feed parsing (prioritize working methods)
            feed = None
            parsing_methods = [
                # Method 1: Using requests with SSL handling (most reliable)
                lambda: self._parse_feed_with_requests(feed_url),
                # Method 2: Standard parsing with user agent
                lambda: feedparser.parse(feed_url, agent="Mozilla/5.0 (compatible; NewsBot/1.0)"),
                # Method 3: Standard parsing
                lambda: feedparser.parse(feed_url),
            ]
            
            for i, method in enumerate(parsing_methods, 1):
                try:
                    logger.info(f"Trying parsing method {i}", feed_url=feed_url)
                    feed = method()
                    if feed and hasattr(feed, 'entries') and feed.entries:
                        logger.info(f"Parsing method {i} successful", feed_url=feed_url, entries_count=len(feed.entries))
                        break
                    else:
                        logger.warning(f"Parsing method {i} returned empty feed", feed_url=feed_url)
                except Exception as method_error:
                    logger.warning(f"Parsing method {i} failed", feed_url=feed_url, error=str(method_error))
                    continue
            
            if not feed:
                logger.error("All parsing methods failed", feed_url=feed_url)
                return []
            
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
            
            # Track processing statistics - increased from 10 to 20 articles per feed
            total_entries = len(feed.entries[:20])  # Process first 20 entries per feed
            processed_count = 0
            
            for i, entry in enumerate(feed.entries[:20]):  # Increased limit per feed
                try:
                    processed_count += 1
                    logger.info("Processing article", feed_url=feed_url, 
                               article_num=processed_count, 
                               title=entry.get('title', 'No title')[:100])
                    
                    article = await self._extract_article_content(entry, source_name)
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
            
            # Log processing statistics
            logger.info("Feed processing completed", 
                       source=source_name,
                       total_entries=total_entries,
                       processed=processed_count,
                       extracted=len(articles))
                    
        except Exception as e:
            logger.error("Failed to parse RSS feed", feed_url=feed_url, error=str(e))
            raise
        
        return articles
    
    async def _extract_article_content(self, entry, source_name: str) -> Dict[str, Any]:
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
        
        # Enhanced published date parsing with multiple fallbacks
        published_at = None
        
        # Strategy 1: Try RSS feed date fields
        date_fields = ['published_parsed', 'updated_parsed', 'created_parsed']
        for field_name in date_fields:
            if hasattr(entry, field_name):
                field_value = getattr(entry, field_name)
                if field_value:
                    try:
                        published_at = datetime(*field_value[:6])
                        logger.debug(f"Date found in RSS {field_name}", 
                                   title=title[:50], 
                                   date=published_at.isoformat())
                        break
                    except Exception as e:
                        logger.debug(f"Failed to parse {field_name}", error=str(e))
                        continue
        
        # Strategy 2: Try to extract date from article page if RSS date failed
        if not published_at:
            page_date = await self._extract_date_from_page(url)
            if page_date:
                published_at = page_date
                logger.debug("Date extracted from article page", 
                           title=title[:50], 
                           date=published_at.isoformat())
        
        # Strategy 3: Parse date from URL if available
        if not published_at:
            url_date = self._extract_date_from_url(url)
            if url_date:
                published_at = url_date
                logger.debug("Date extracted from URL", 
                           title=title[:50], 
                           date=published_at.isoformat())
        
        # Strategy 4: Use current time as final fallback
        if not published_at:
            published_at = datetime.utcnow()
            logger.debug("Using current time as fallback date", 
                       title=title[:50], 
                       date=published_at.isoformat())
        
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
    
    async def _extract_date_from_page(self, url: str) -> Optional[datetime]:
        """
        Try to extract publication date from article HTML page.
        
        Args:
            url: Article URL
            
        Returns:
            Parsed datetime or None if not found
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; NewsBot/1.0)'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Strategy 1: JSON-LD structured data
            json_ld_scripts = soup.find_all('script', type='application/ld+json')
            for script in json_ld_scripts:
                try:
                    import json
                    data = json.loads(script.string)
                    if isinstance(data, list):
                        data = data[0]
                    
                    # Look for datePublished or dateCreated
                    for date_field in ['datePublished', 'dateCreated', 'dateModified']:
                        if date_field in data:
                            date_str = data[date_field]
                            parsed_date = self._parse_date_string(date_str)
                            if parsed_date:
                                logger.debug(f"Date found in JSON-LD {date_field}", date=parsed_date.isoformat())
                                return parsed_date
                except Exception as e:
                    logger.debug("Failed to parse JSON-LD", error=str(e))
                    continue
            
            # Strategy 2: Meta tags
            meta_selectors = [
                'meta[property="article:published_time"]',
                'meta[name="publishdate"]', 
                'meta[name="date"]',
                'meta[name="publish-date"]',
                'meta[property="og:published_time"]',
                'meta[name="article:published_time"]'
            ]
            
            for selector in meta_selectors:
                meta_tag = soup.select_one(selector)
                if meta_tag:
                    content = meta_tag.get('content')
                    if content:
                        parsed_date = self._parse_date_string(content)
                        if parsed_date:
                            logger.debug(f"Date found in meta tag {selector}", date=parsed_date.isoformat())
                            return parsed_date
            
            # Strategy 3: Time elements with datetime attribute
            time_elements = soup.find_all('time', attrs={'datetime': True})
            for time_elem in time_elements:
                datetime_attr = time_elem.get('datetime')
                if datetime_attr:
                    parsed_date = self._parse_date_string(datetime_attr)
                    if parsed_date:
                        logger.debug("Date found in time element", date=parsed_date.isoformat())
                        return parsed_date
            
            # Strategy 4: Common date classes/patterns in text
            date_selectors = [
                '.date', '.publish-date', '.published', '.article-date',
                '.post-date', '.entry-date', '.timestamp'
            ]
            
            for selector in date_selectors:
                date_elem = soup.select_one(selector)
                if date_elem:
                    date_text = date_elem.get_text(strip=True)
                    parsed_date = self._parse_date_string(date_text)
                    if parsed_date:
                        logger.debug(f"Date found in element {selector}", date=parsed_date.isoformat())
                        return parsed_date
            
            logger.debug("No date found in article page", url=url[:100])
            return None
            
        except Exception as e:
            logger.debug("Failed to extract date from page", url=url[:100], error=str(e))
            return None
    
    def _extract_date_from_url(self, url: str) -> Optional[datetime]:
        """
        Try to extract date from URL pattern.
        
        Args:
            url: Article URL
            
        Returns:
            Parsed datetime or None if not found
        """
        import re
        
        try:
            # Common URL date patterns
            patterns = [
                r'/(\d{4})/(\d{1,2})/(\d{1,2})/',  # /2025/09/24/
                r'/(\d{4})-(\d{1,2})-(\d{1,2})/',  # /2025-09-24/
                r'_(\d{4})(\d{2})(\d{2})_',        # _20250924_
                r'-(\d{4})(\d{2})(\d{2})-',        # -20250924-
            ]
            
            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    year, month, day = match.groups()
                    try:
                        parsed_date = datetime(int(year), int(month), int(day))
                        logger.debug("Date extracted from URL pattern", 
                                   pattern=pattern, 
                                   date=parsed_date.isoformat())
                        return parsed_date
                    except ValueError:
                        continue
            
            logger.debug("No date pattern found in URL", url=url[:100])
            return None
            
        except Exception as e:
            logger.debug("Failed to extract date from URL", url=url[:100], error=str(e))
            return None
    
    def _parse_date_string(self, date_str: str) -> Optional[datetime]:
        """
        Parse various date string formats.
        
        Args:
            date_str: Date string to parse
            
        Returns:
            Parsed datetime or None if parsing failed
        """
        if not date_str or not isinstance(date_str, str):
            return None
        
        # Clean the date string
        date_str = date_str.strip()
        
        # Common date formats to try
        formats = [
            '%Y-%m-%dT%H:%M:%SZ',           # 2025-09-24T10:30:00Z
            '%Y-%m-%dT%H:%M:%S%z',          # 2025-09-24T10:30:00+00:00
            '%Y-%m-%dT%H:%M:%S',            # 2025-09-24T10:30:00
            '%Y-%m-%d %H:%M:%S',            # 2025-09-24 10:30:00
            '%Y-%m-%d',                     # 2025-09-24
            '%d %B %Y',                     # 24 September 2025
            '%B %d, %Y',                    # September 24, 2025
            '%d %b %Y',                     # 24 Sep 2025
            '%b %d, %Y',                    # Sep 24, 2025
        ]
        
        for fmt in formats:
            try:
                parsed_date = datetime.strptime(date_str, fmt)
                return parsed_date
            except ValueError:
                continue
        
        # Try with dateutil as fallback (more flexible parsing)
        try:
            from dateutil import parser
            parsed_date = parser.parse(date_str)
            return parsed_date
        except ImportError:
            logger.debug("dateutil not available, skipping flexible parsing")
        except Exception:
            pass
        
        logger.debug("Failed to parse date string", date_str=date_str[:50])
        return None
    
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
    
    def _parse_feed_with_requests(self, feed_url: str):
        """
        Parse RSS feed using requests with SSL verification disabled as fallback.
        
        Args:
            feed_url: RSS feed URL
            
        Returns:
            Parsed feed object or None if failed
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; NewsBot/1.0; +http://example.com/bot)',
                'Accept': 'application/rss+xml, application/xml, text/xml'
            }
            
            # Make request with SSL verification disabled
            response = requests.get(
                feed_url, 
                headers=headers,
                verify=False,  # Disable SSL verification
                timeout=10
            )
            response.raise_for_status()
            
            # Parse the content with feedparser
            return feedparser.parse(response.content)
            
        except Exception as e:
            logger.error("Failed to parse feed with requests method", feed_url=feed_url, error=str(e))
            return None
    
    async def _save_articles(self, articles: List[Dict[str, Any]]):
        """
        Save articles to the database and update them with their database IDs.
        
        Args:
            articles: List of article dictionaries (modified in-place with IDs)
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
            
            for i, article_data in enumerate(articles):
                # Explicitly generate UUID for the article
                article_id = uuid.uuid4()
                
                article = NewsArticle(
                    id=article_id,  # Explicitly set the ID
                    job_id=job_uuid,  # Use the UUID, not the string
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