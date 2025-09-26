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
  const [dateLoading, setDateLoading] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [selectedDate, setSelectedDate] = useState<string>(new Date().toISOString().split('T')[0]);
  const [showSettings, setShowSettings] = useState(false);
  const [hasDataForDate, setHasDataForDate] = useState(false);

  // Check backend health on mount
  useEffect(() => {
    const initializeApp = async () => {
      await checkHealth();
      await loadNewsData();
    };
    initializeApp();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Helper function to safely handle timestamps
  const safeTimestamp = (timestamp: string | undefined): string => {
    if (!timestamp) return new Date().toISOString();
    
    try {
      const date = new Date(timestamp);
      if (isNaN(date.getTime())) {
        console.warn('Invalid timestamp:', timestamp);
        return new Date().toISOString();
      }
      return timestamp;
    } catch (error) {
      console.warn('Error parsing timestamp:', timestamp, error);
      return new Date().toISOString();
    }
  };

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
    setDateLoading(true);
    try {
      // Load news timeline data for today (default behavior)
      const timelineData = await newsAPI.getNewsTimeline(20);
      
      // Convert to TimelineItem format
      const items: TimelineItem[] = timelineData.items.map((item: any) => ({
        id: item.id,
        type: item.type as 'summary' | 'analysis' | 'article' | 'news_item',
        timestamp: safeTimestamp(item.timestamp),
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
          key_points: item.bullet_points
        }
      }));
      
      setTimelineItems(items);
      setHasDataForDate(items.length > 0);
      
      // Set overall summary if available
      if (timelineData.overall_summary) {
        setOverallSummary(timelineData.overall_summary);
      }
    } catch (error) {
      console.error('Error loading news data:', error);
      setHasDataForDate(false);
    } finally {
      setDateLoading(false);
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
    // Convert ISO date to simple date string if needed
    let dateString = date;
    if (date.includes('T')) {
      // If it's an ISO date, extract just the date part
      dateString = date.split('T')[0];
    }
    
    setSelectedDate(dateString);
    setDateLoading(true);
    setHasDataForDate(false);
    
    try {
      // Use timeline API for all date requests - it handles both current and historical data
      const timelineData = await newsAPI.getNewsTimeline(50, 0, dateString);
      
      if (timelineData.items && timelineData.items.length > 0) {
        // Convert to TimelineItem format
        const items: TimelineItem[] = timelineData.items.map((item: any) => ({
          id: item.id,
          type: item.type as 'summary' | 'analysis' | 'article' | 'news_item',
          timestamp: safeTimestamp(item.timestamp),
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
            key_points: item.bullet_points
          }
        }));
        
        setTimelineItems(items);
        setHasDataForDate(true);
        
        // Set overall summary if available
        if (timelineData.overall_summary) {
          setOverallSummary(timelineData.overall_summary);
        } else {
          setOverallSummary(null);
        }
      } else {
        // No data found for this date
        setTimelineItems([]);
        setOverallSummary(null);
        setHasDataForDate(false);
      }
    } catch (error) {
      console.error('Error loading news for date:', dateString, error);
      setTimelineItems([]);
      setOverallSummary(null);
      setHasDataForDate(false);
    } finally {
      setDateLoading(false);
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
          isLoading={loading || dateLoading}
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
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-lg font-semibold">News Timeline</h2>
            {selectedDate !== new Date().toISOString().split('T')[0] && (
              <span className="text-sm text-gray-500">
                Showing data for {new Date(selectedDate).toLocaleDateString('en-US', { 
                  weekday: 'long',
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric'
                })}
              </span>
            )}
          </div>
          
          {dateLoading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
              <p className="text-gray-500">Loading news data...</p>
            </div>
          ) : timelineItems.length === 0 ? (
            <div className="text-center py-12">
              {selectedDate === new Date().toISOString().split('T')[0] ? (
                <>
                  <p className="text-gray-500 mb-4">No news items yet for today</p>
                  <p className="text-sm text-gray-400">
                    Click "Settings" then "Start Traditional Workflow" to generate news summaries
                  </p>
                </>
              ) : hasDataForDate ? (
                <>
                  <p className="text-gray-500 mb-2">No data found for this date</p>
                  <p className="text-sm text-gray-400">
                    Try selecting a different date or running a workflow for this date
                  </p>
                </>
              ) : (
                <>
                  <p className="text-gray-500 mb-2">No processed news available for {new Date(selectedDate).toLocaleDateString()}</p>
                  <p className="text-sm text-gray-400 mb-4">
                    This date may not have been processed yet, or no news was available
                  </p>
                  <button
                    onClick={() => setSelectedDate(new Date().toISOString().split('T')[0])}
                    className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors text-sm"
                  >
                    Go to Today
                  </button>
                </>
              )}
            </div>
          ) : (
            <div className="space-y-0">
              {timelineItems.map((item) => (
                <TimelineItemComponent key={item.id} item={item} />
              ))}
              
              {timelineItems.length > 0 && (
                <div className="text-center py-6 border-t border-gray-100">
                  <p className="text-sm text-gray-400">
                    Showing {timelineItems.length} news items
                  </p>
                </div>
              )}
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