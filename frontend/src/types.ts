export interface NewsArticle {
  id: string; // Changed to string for UUID support
  title: string;
  url: string;
  published_at: string;
  source: string;
  content?: string;
  created_at: string;
  scraped_at: string;
}

export interface NewsSummary {
  id: string; // Changed to string for UUID support
  article_id: string; // Changed to string for UUID support
  summary: string;
  bullet_points: string[]; // Updated field name
  quality_score?: number; // Added quality score
  processing_time?: number; // Added processing time
  sentiment?: 'positive' | 'negative' | 'neutral'; // Made optional
  created_at: string;
  article?: NewsArticle;
}

export interface NewsAnalysis {
  id: string; // Changed to string for UUID support
  analysis: string;
  insights: string[];
  impact_assessment?: string; // Added impact assessment
  processing_time?: number; // Added processing time
  summary_ids?: string[]; // Changed from summary_id to summary_ids array
  tags?: string[]; // Made optional
  created_at: string;
  summaries?: NewsSummary[]; // Changed from summary to summaries array
}

export interface NewsJob {
  id: string; // Changed to string for UUID support (database primary key)
  job_id: string; // This remains the UUID job identifier
  job_type: 'manual' | 'hourly'; // Removed multi_agent type
  workflow_run_id?: string; // Added workflow run ID
  processed_date?: string; // Added processed date
  status: 'started' | 'completed' | 'failed' | 'terminated'; // Added terminated status
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
  scraped_at?: string;
  created_at?: string;
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
  job_type?: string; // Added job type
  message: string;
  target_date?: string; // Added target date
  stream_url?: string;
  processing_mode?: string;
  agents?: string[];
}

export interface NewsJobResponse {
  job_id: string;
  status: string;
  job_type?: string; // Added job type
  message: string;
  target_date?: string; // Added target date
  stream_url?: string;
  processing_mode?: string;
  agents?: string[];
}

// Historical functionality now handled by timeline API with date filtering

export interface NewsAvailabilityCheck {
  date: string;
  available: boolean;
  status: string;
  job_id?: string;
  job_type?: string;
  articles_count?: number;
  processed_date?: string;
  created_at?: string;
  completed_at?: string;
  error_message?: string;
  message?: string;
}

export interface RecentNewsResponse {
  days: number;
  count: number;
  news_summaries: RecentNewsSummary[];
}

export interface RecentNewsSummary {
  job_id: string;
  job_type: string;
  processed_date?: string;
  status: string;
  articles_count: number;
  created_at: string;
  completed_at?: string;
}

export interface ProcessingStats {
  statistics: {
    date_range: {
      start: string;
      end: string;
      days: number;
    };
    total_jobs: number;
    completed_jobs: number;
    failed_jobs: number;
    in_progress_jobs: number;
    total_articles: number;
    job_types: {
      hourly: number;
      manual: number;
    };
    daily_breakdown: Array<{
      date: string;
      articles: number;
      jobs: number;
    }>;
  };
  insights: {
    success_rate: number;
    avg_articles_per_job: number;
    most_active_job_type: string;
  };
}

// Workflow status sync interfaces
export interface WorkflowHealthStatus {
  timestamp: string;
  health: {
    overall_health: 'healthy' | 'degraded' | 'unhealthy' | 'unknown';
    total_jobs: number;
    job_status_breakdown: {
      completed: number;
      failed: number;
      started: number;
    };
    success_rate: number;
    recent_activity_24h: {
      total_jobs: number;
      completed_jobs: number;
      success_rate: number;
    };
    alerts: string[];
  };
}

export interface StaleJobSyncResult {
  success: boolean;
  sync_results: {
    total_stale_jobs: number;
    synced_jobs: number;
    failed_syncs: number;
    job_details: Array<{
      job_id: string;
      status: string;
      age_hours: number;
    }>;
  };
}

export interface HourlyProcessingStatus {
  hourly_processing_active: boolean;
  recent_hourly_jobs: number;
  last_hourly_run?: {
    job_id: string;
    status: string;
    created_at: string;
    completed_at?: string;
  };
  next_scheduled_run: string;
}

// Schedule configuration interfaces
export interface NewsScheduleStatus {
  timestamp: string;
  schedule: {
    enabled: boolean;
    schedule_type: 'hourly' | 'daily' | 'custom';
    hours: number;
    daily_time: number;
    custom_cron: string;
    next_run: string;
    current_schedule: any;
  };
}

export interface ScheduleConfig {
  schedule_type: 'hourly' | 'daily' | 'custom';
  hours?: number;        // For hourly: 1-24
  daily_time?: number;   // For daily: 0-23 (hour of day)
  custom_cron?: string;  // For custom: 5-part cron expression
}

export interface ScheduleControlResult {
  status: 'started' | 'stopped';
  message: string;
  schedule_type?: string;
  configuration?: {
    hours?: number;
    daily_time?: number;
    custom_cron?: string;
  };
}