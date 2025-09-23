import axios from 'axios';
import { NewsJob, NewsJobResult, TimelineItem } from './types';

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const newsAPI = {
  // Trigger news workflow
  async triggerNewsWorkflow(): Promise<{ job_id: string; status: string; message: string }> {
    const response = await api.post('/news/run');
    return response.data;
  },

  // Trigger multi-agent workflow
  async triggerMultiAgentWorkflow(date?: string): Promise<{ job_id: string; status: string; message: string; target_date: string }> {
    const response = await api.post('/news/multi-agent', {}, {
      params: date ? { target_date: date } : {}
    });
    return response.data;
  },

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

  // Get daily news for a specific date using new timeline endpoint
  async getDailyNews(date: string): Promise<{
    date: string;
    items: any[];
    overall_summary?: any;
    total: number;
    date_filter: string;
  }> {
    const response = await api.get('/news/timeline', {
      params: {
        date: date,
        limit: 50
      }
    });
    return {
      date,
      items: response.data.items,
      overall_summary: response.data.overall_summary,
      total: response.data.total,
      date_filter: response.data.date_filter
    };
  },

  // Get news timeline (all recent news)
  async getNewsTimeline(limit: number = 20, offset: number = 0): Promise<{
    items: any[];
    total: number;
  }> {
    const response = await api.get('/news/timeline', {
      params: { limit, offset }
    });
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

  // Trigger news workflow with optional date
  async triggerNewsWorkflowWithDate(date?: string): Promise<{ job_id: string; status: string; message: string; target_date: string }> {
    const response = await api.post('/news/run', {}, {
      params: date ? { target_date: date } : {}
    });
    return response.data;
  },

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
        metadata: {
          source: summary.article?.source,
          sentiment: summary.sentiment,
          key_points: summary.key_points,
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
        metadata: {
          tags: analysis.tags,
        },
      });
    });

    // Sort by timestamp (newest first)
    return items.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  },
};