from datetime import datetime
from typing import List, Optional
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Float, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from pydantic import BaseModel

Base = declarative_base()


class NewsJob(Base):
    __tablename__ = "news_jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, unique=True, index=True)
    status = Column(String, default="started")
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Relationships
    articles = relationship("NewsArticle", back_populates="job")
    summaries = relationship("NewsSummary", back_populates="job")
    analysis = relationship("NewsAnalysis", back_populates="job")


class NewsArticle(Base):
    __tablename__ = "news_articles"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, ForeignKey("news_jobs.job_id"), index=True)
    title = Column(String, index=True)
    url = Column(String)
    content = Column(Text)
    source = Column(String)
    published_at = Column(DateTime, nullable=True)
    scraped_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    job = relationship("NewsJob", back_populates="articles")
    summaries = relationship("NewsSummary", back_populates="article")


class NewsSummary(Base):
    __tablename__ = "news_summaries"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, ForeignKey("news_jobs.job_id"), index=True)
    article_id = Column(Integer, ForeignKey("news_articles.id"))
    summary = Column(Text)
    bullet_points = Column(JSON)
    processing_time = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    job = relationship("NewsJob", back_populates="summaries")
    article = relationship("NewsArticle", back_populates="summaries")


class NewsAnalysis(Base):
    __tablename__ = "news_analysis"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, ForeignKey('news_jobs.job_id'), nullable=False)
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
    id: int
    job_id: str
    status: str
    created_at: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]
    
    class Config:
        from_attributes = True


class NewsArticleResponse(BaseModel):
    id: int
    job_id: str
    title: str
    url: str
    content: str
    source: str
    published_at: Optional[datetime]
    scraped_at: datetime
    
    class Config:
        from_attributes = True


class NewsSummaryResponse(BaseModel):
    id: int
    job_id: str
    article_id: int
    summary: str
    bullet_points: List[str]
    processing_time: float
    created_at: datetime
    
    class Config:
        from_attributes = True


class NewsAnalysisResponse(BaseModel):
    id: int
    job_id: str
    summary_id: int
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