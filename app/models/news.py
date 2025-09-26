from datetime import datetime, date
from typing import List, Optional
import uuid
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Float, ForeignKey, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from pydantic import BaseModel

Base = declarative_base()


class NewsJob(Base):
    __tablename__ = "news_jobs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True, nullable=False)
    job_id = Column(String, unique=True, index=True)  # Keep for backward compatibility and external references
    job_type = Column(String(50), nullable=False, default="manual")  # 'hourly', 'manual', 'multi_agent'
    workflow_run_id = Column(String, nullable=True)  # Temporal workflow run ID
    status = Column(String, default="started")
    processed_date = Column(Date, nullable=True)  # Date for which news was processed
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Relationships
    articles = relationship("NewsArticle", back_populates="job", cascade="all, delete-orphan")
    summaries = relationship("NewsSummary", back_populates="job", cascade="all, delete-orphan")
    analysis = relationship("NewsAnalysis", back_populates="job", cascade="all, delete-orphan")


class NewsArticle(Base):
    __tablename__ = "news_articles"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True, nullable=False)
    job_id = Column(UUID(as_uuid=True), ForeignKey("news_jobs.id", ondelete="CASCADE"), index=True, nullable=False)
    title = Column(String, index=True)
    url = Column(String)
    content = Column(Text)
    source = Column(String)
    published_at = Column(DateTime, nullable=True)
    scraped_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    job = relationship("NewsJob", back_populates="articles")
    summaries = relationship("NewsSummary", back_populates="article", cascade="all, delete-orphan")


class NewsSummary(Base):
    __tablename__ = "news_summaries"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True, nullable=False)
    job_id = Column(UUID(as_uuid=True), ForeignKey("news_jobs.id", ondelete="CASCADE"), index=True, nullable=False)
    article_id = Column(UUID(as_uuid=True), ForeignKey("news_articles.id", ondelete="CASCADE"), nullable=False)
    summary = Column(Text)
    bullet_points = Column(JSON)
    processing_time = Column(Float)
    quality_score = Column(Integer, nullable=True)  # 1-10 quality rating from critic
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    job = relationship("NewsJob", back_populates="summaries")
    article = relationship("NewsArticle", back_populates="summaries")


class NewsAnalysis(Base):
    __tablename__ = "news_analysis"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True, nullable=False)
    job_id = Column(UUID(as_uuid=True), ForeignKey('news_jobs.id', ondelete="CASCADE"), nullable=False, index=True)
    summary_ids = Column(JSON)  # List of summary IDs that were analyzed
    analysis = Column(Text)
    insights = Column(JSON)
    impact_assessment = Column(Text)
    processing_time = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    job = relationship("NewsJob", back_populates="analysis")


# Pydantic Models for API
class NewsJobResponse(BaseModel):
    id: str  # UUID as string
    job_id: str
    job_type: str
    workflow_run_id: Optional[str]
    status: str
    processed_date: Optional[date]
    created_at: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]
    
    class Config:
        from_attributes = True


class NewsArticleResponse(BaseModel):
    id: str  # UUID as string
    job_id: str  # UUID as string
    title: str
    url: str
    content: str
    source: str
    published_at: Optional[datetime]
    scraped_at: datetime
    
    class Config:
        from_attributes = True


class NewsSummaryResponse(BaseModel):
    id: str  # UUID as string
    job_id: str  # UUID as string
    article_id: str  # UUID as string
    summary: str
    bullet_points: List[str]
    processing_time: float
    quality_score: Optional[int]
    created_at: datetime
    
    class Config:
        from_attributes = True


class NewsAnalysisResponse(BaseModel):
    id: str  # UUID as string
    job_id: str  # UUID as string
    summary_ids: List[str]  # List of UUID strings
    analysis: str
    insights: List[str]
    impact_assessment: str
    processing_time: float
    created_at: datetime
    
    class Config:
        from_attributes = True


class NewsStreamUpdate(BaseModel):
    job_id: str
    status: str
    message: str
    timestamp: datetime
    data: Optional[dict] = None


class NewsJobResult(BaseModel):
    job_id: str
    status: str
    articles_count: int
    summaries: List[NewsSummaryResponse]
    analyses: List[NewsAnalysisResponse]
    processing_time: float
    created_at: datetime
    completed_at: Optional[datetime]


class NewsJobSummary(BaseModel):
    """Summary model for listing jobs without full details"""
    id: str
    job_id: str
    job_type: str
    status: str
    processed_date: Optional[date]
    articles_count: int
    created_at: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]


class AppConfig(Base):
    """Application configuration storage table"""
    __tablename__ = "app_config"
    
    key = Column(String, primary_key=True, index=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)