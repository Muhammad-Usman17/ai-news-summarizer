export interface NewsArticle {
  id: number;
  title: string;
  url: string;
  published_at: string;
  source: string;
  content?: string;
  created_at: string;
}

export interface NewsSummary {
  id: number;
  article_id: number;
  summary: string;
  key_points: string[];
  sentiment: 'positive' | 'negative' | 'neutral';
  created_at: string;
  article?: NewsArticle;
}

export interface NewsAnalysis {
  id: number;
  summary_id: number;
  analysis: string;
  insights: string[];
  tags: string[];
  created_at: string;
  summary?: NewsSummary;
}

export interface NewsJob {
  id: number;
  job_id: string;
  status: 'started' | 'completed' | 'failed';
  created_at: string;
  completed_at?: string;
  error_message?: string;
}

export interface NewsJobResult {
  job_id: string;
  status: string;
  articles_count: number;
  summaries: NewsSummary[];
  analyses: NewsAnalysis[];
  processing_time: number;
  created_at: string;
  completed_at?: string;
}

export interface TimelineItem {
  id: string;
  type: 'article' | 'summary' | 'analysis' | 'news_item';
  timestamp: string;
  title: string;
  content?: string;
  summary?: string;
  insights?: string[];
  impact_assessment?: string;
  bullet_points?: string[];
  url?: string;
  source?: string;
  published_at?: string;
  metadata?: {
    source?: string;
    sentiment?: string;
    tags?: string[];
    key_points?: string[];
  };
}

export interface OverallSummary {
  summary: string;
  key_themes: string[];
  impact_overview: string;
  news_count: number;
}

export interface NewsJobResponse {
  job_id: string;
  status: string;
  message: string;
  stream_url?: string;
  processing_mode?: string;
  agents?: string[];
}

export interface DailyNews {
  date: string;
  articles: NewsArticle[];
  summaries: NewsSummary[];
  analyses: NewsAnalysis[];
}