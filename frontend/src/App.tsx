import React, { useState, useEffect } from 'react';
import './App.css';
import { TimelineItem, OverallSummary } from './types';
import { newsAPI } from './api';
import TimelineItemComponent from './components/TimelineItem';
import { DateSelector } from './components/DateSelector';
import { SettingsModal } from './components/SettingsModal';
import { OverallSummaryComponent } from './components/OverallSummary';

const App: React.FC = () => {
  const [timelineItems, setTimelineItems] = useState<TimelineItem[]>([]);
  const [overallSummary, setOverallSummary] = useState<OverallSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [selectedDate, setSelectedDate] = useState<string>(new Date().toISOString().split('T')[0]);
  const [showSettings, setShowSettings] = useState(false);

  // Check backend health on mount
  useEffect(() => {
    checkHealth();
    loadNewsData();
  }, []);

  const checkHealth = async () => {
    try {
      await newsAPI.healthCheck();
      setIsConnected(true);
    } catch (error) {
      setIsConnected(false);
      console.error('Backend not available:', error);
    }
  };

  const loadNewsData = async () => {
    try {
      // Load news timeline data directly
      const timelineData = await newsAPI.getNewsTimeline(20);
      
      // Convert to TimelineItem format
      const items: TimelineItem[] = timelineData.items.map((item: any) => ({
        id: item.id,
        type: item.type as 'summary' | 'analysis' | 'article' | 'news_item',
        timestamp: item.timestamp,
        title: item.title,
        content: item.content,
        summary: item.summary,
        insights: item.insights,
        impact_assessment: item.impact_assessment,
        bullet_points: item.bullet_points,
        url: item.url,
        source: item.source,
        published_at: item.published_at,
        metadata: {
          source: item.source,
          bullet_points: item.bullet_points,
          url: item.url
        }
      }));
      
      setTimelineItems(items);
      
      // Set overall summary if available
      if ((timelineData as any).overall_summary) {
        setOverallSummary((timelineData as any).overall_summary);
      }
    } catch (error) {
      console.error('Error loading news data:', error);
    }
  };



  const handleSync = async () => {
    setLoading(true);
    try {
      // Sync with database to get latest data
      const syncResult = await newsAPI.syncData();
      console.log('Sync completed:', syncResult);
      
      // Reload timeline data to reflect any updates
      await loadNewsData();
      
      // Show success feedback
      console.log(`Synced data: ${syncResult.data_counts.articles} articles, ${syncResult.data_counts.summaries} summaries, ${syncResult.data_counts.analyses} analyses`);
      
    } catch (error) {
      console.error('Error syncing data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleDateChange = async (date: string) => {
    setSelectedDate(date);
    try {
      // Load news for specific date
      const dailyNews = await newsAPI.getDailyNews(date);
      
      // Convert to TimelineItem format
      const items: TimelineItem[] = dailyNews.items.map((item: any) => ({
        id: item.id,
        type: item.type as 'summary' | 'analysis' | 'article' | 'news_item',
        timestamp: item.timestamp,
        title: item.title,
        content: item.content,
        summary: item.summary,
        insights: item.insights,
        impact_assessment: item.impact_assessment,
        bullet_points: item.bullet_points,
        url: item.url,
        source: item.source,
        published_at: item.published_at,
        metadata: {
          source: item.source,
          bullet_points: item.bullet_points,
          url: item.url
        }
      }));
      
      setTimelineItems(items);
      
      // Set overall summary if available
      if ((dailyNews as any).overall_summary) {
        setOverallSummary((dailyNews as any).overall_summary);
      }
    } catch (error) {
      console.error('Error loading news for date:', error);
    }
  };

  const handleSettingsClick = () => {
    setShowSettings(true);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-4xl mx-auto px-4 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">📰 AI News Timeline</h1>
              <p className="text-gray-600 mt-1">Real-time AI-powered news summaries and analysis</p>
            </div>
            
            <div className="flex items-center space-x-2">
              <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}></div>
              <span className="text-sm text-gray-600">
                {isConnected ? 'Connected' : 'Disconnected'}
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Date Selector and Controls */}
      <div className="max-w-4xl mx-auto px-4 py-6">
        <DateSelector
          selectedDate={selectedDate}
          onDateChange={handleDateChange}
          onSyncClick={handleSync}
          onSettingsClick={handleSettingsClick}
          isLoading={loading}
        />



        {/* Overall Summary */}
        {overallSummary && (
          <OverallSummaryComponent 
            summary={overallSummary} 
            selectedDate={selectedDate}
          />
        )}

        {/* Timeline */}
        <div className="bg-white rounded-lg shadow-sm p-6">
          <h2 className="text-lg font-semibold mb-6">News Timeline</h2>
          
          {timelineItems.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-gray-500 mb-4">No news items yet</p>
              <p className="text-sm text-gray-400">
                Click "Settings" then "Start Traditional Workflow" to generate news summaries
              </p>
            </div>
          ) : (
            <div className="space-y-0">
              {timelineItems.map((item) => (
                <TimelineItemComponent key={item.id} item={item} />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Settings Modal */}
      <SettingsModal
        isOpen={showSettings}
        onClose={() => setShowSettings(false)}
      />
    </div>
  );
};

export default App;