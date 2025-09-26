import axios from 'axios';
import { 
  NewsJob, 
  NewsJobResult, 
  TimelineItem, 
  ProcessingStats,
  WorkflowHealthStatus,
  StaleJobSyncResult,
  HourlyProcessingStatus,
  NewsScheduleStatus,
  ScheduleConfig,
  ScheduleControlResult
} from './types';

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const newsAPI = {
  // MANUAL WORKFLOW TRIGGERS (No date selection - current date only)
  // Trigger manual news workflow for current date
  async triggerNewsWorkflow(): Promise<{ job_id: string; status: string; job_type: string; message: string; target_date: string }> {
    const response = await api.post('/news/run');
    return response.data;
  },

  // Historical functionality now handled by timeline API with optional date parameter

  // Get processing statistics
  async getProcessingStats(days: number = 30): Promise<ProcessingStats> {
    const response = await api.get(`/news/processing/stats?days=${days}`);
    return response.data;
  },

  // HOURLY PROCESSING CONTROL (LEGACY - Use schedule endpoints instead)
  // Start hourly automated processing
  async startHourlyProcessing(): Promise<{ status: string; message: string; schedule: string; next_run: string }> {
    const response = await api.post('/news/hourly/start');
    return response.data;
  },

  // Get hourly processing status
  async getHourlyProcessingStatus(): Promise<HourlyProcessingStatus> {
    const response = await api.get('/news/hourly/status');
    return response.data;
  },

  // SCHEDULE CONTROL (NEW - Configurable cron jobs)
  // Start news processing schedule
  async startNewsSchedule(config: ScheduleConfig): Promise<ScheduleControlResult> {
    const response = await api.post('/news/schedule/start', config);
    return response.data;
  },

  // Stop news processing schedule
  async stopNewsSchedule(): Promise<ScheduleControlResult> {
    const response = await api.post('/news/schedule/stop');
    return response.data;
  },

  // Get news processing schedule status
  async getNewsScheduleStatus(): Promise<NewsScheduleStatus> {
    const response = await api.get('/news/schedule/status');
    return response.data;
  },

  // WORKFLOW STATUS SYNC
  // Sync stale workflows
  async syncStaleWorkflows(maxAgeHours: number = 2): Promise<StaleJobSyncResult> {
    const response = await api.post(`/news/workflow/sync-stale?max_age_hours=${maxAgeHours}`);
    return response.data;
  },

  // Get workflow health status
  async getWorkflowHealth(): Promise<WorkflowHealthStatus> {
    const response = await api.get('/news/workflow/health');
    return response.data;
  },

  // Terminate a workflow
  async terminateWorkflow(jobId: string, reason: string = 'Manual termination'): Promise<{ success: boolean; job_id: string; message: string }> {
    const response = await api.post(`/news/workflow/terminate/${jobId}?reason=${encodeURIComponent(reason)}`);
    return response.data;
  },

  // EXISTING JOB MANAGEMENT
  // Get job status
  async getJobStatus(jobId: string): Promise<NewsJob> {
    const response = await api.get(`/news/jobs/${jobId}`);
    return response.data;
  },

  // Get job result
  async getJobResult(jobId: string): Promise<NewsJobResult> {
    const response = await api.get(`/news/jobs/${jobId}/result`);
    return response.data;
  },

  // List all jobs
  async listJobs(limit: number = 10, offset: number = 0): Promise<NewsJob[]> {
    const response = await api.get(`/news/jobs?limit=${limit}&offset=${offset}`);
    return response.data;
  },

  // SYSTEM HEALTH
  // Health check
  async healthCheck(): Promise<{ status: string; timestamp: string; service: string }> {
    const response = await api.get('/health');
    return response.data;
  },

  // Get metrics
  async getMetrics(): Promise<string> {
    const response = await api.get('/metrics');
    return response.data;
  },

  // TIMELINE AND DATA ACCESS
  // Get news timeline with optional date filtering
  async getNewsTimeline(limit: number = 20, offset: number = 0, date?: string): Promise<{
    items: any[];
    total: number;
    overall_summary?: any;
    date_filter?: string;
  }> {
    const params: any = { limit, offset };
    if (date) {
      params.date = date;
    }
    
    const response = await api.get('/news/timeline', { params });
    return response.data;
  },

  // Get news articles directly
  async getArticles(limit: number = 10, offset: number = 0, date?: string): Promise<any[]> {
    const response = await api.get('/news/articles', {
      params: { limit, offset, date }
    });
    return response.data;
  },

  // Get news summaries directly
  async getSummaries(limit: number = 10, offset: number = 0, date?: string): Promise<any[]> {
    const response = await api.get('/news/summaries', {
      params: { limit, offset, date }
    });
    return response.data;
  },

  // Get news analyses directly
  async getAnalyses(limit: number = 10, offset: number = 0, date?: string): Promise<any[]> {
    const response = await api.get('/news/analyses', {
      params: { limit, offset, date }
    });
    return response.data;
  },

  // DATA SYNC
  // Sync data with database
  async syncData(): Promise<{
    sync_timestamp: string;
    data_counts: any;
    latest_entries: any;
    message: string;
  }> {
    const response = await api.post('/news/sync-data');
    return response.data;
  },

  // LEGACY SUPPORT (DEPRECATED - Use historical endpoints instead)
  // Trigger news workflow with optional date (DEPRECATED)
  async triggerNewsWorkflowWithDate(date?: string): Promise<{ job_id: string; status: string; message: string; target_date: string }> {
    console.warn('triggerNewsWorkflowWithDate is deprecated. Use getHistoricalNews for older dates or triggerNewsWorkflow for current date.');
    return this.triggerNewsWorkflow();
  },

  // UTILITY FUNCTIONS
  // Convert job result to timeline items
  convertToTimelineItems(jobResult: NewsJobResult): TimelineItem[] {
    const items: TimelineItem[] = [];

    // Add summaries
    jobResult.summaries.forEach(summary => {
      items.push({
        id: `summary-${summary.id}`,
        type: 'summary',
        timestamp: summary.created_at,
        title: summary.article?.title || 'News Summary',
        content: summary.summary,
        bullet_points: summary.bullet_points,
        metadata: {
          source: summary.article?.source,
          sentiment: summary.sentiment,
        },
      });
    });

    // Add analyses
    jobResult.analyses.forEach(analysis => {
      items.push({
        id: `analysis-${analysis.id}`,
        type: 'analysis',
        timestamp: analysis.created_at,
        title: 'News Analysis',
        content: analysis.analysis,
        insights: analysis.insights,
        impact_assessment: analysis.impact_assessment,
        metadata: {
          tags: analysis.tags,
        },
      });
    });

    // Sort by timestamp (newest first)
    return items.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  },

  // Format date for API calls
  formatDateForAPI(date: Date): string {
    return date.toISOString().split('T')[0]; // Returns YYYY-MM-DD format
  },

  };

export default newsAPI;