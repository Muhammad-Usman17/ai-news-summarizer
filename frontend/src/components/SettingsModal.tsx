import React, { useState, useEffect } from 'react';
import { X, Play, RotateCw, Activity, AlertCircle, CheckCircle, Clock, Settings } from 'lucide-react';
import { newsAPI } from '../api';
import { NewsJob, NewsScheduleStatus, ScheduleConfig } from '../types';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({ isOpen, onClose }) => {
  const [jobs, setJobs] = useState<NewsJob[]>([]);
  const [healthStatus, setHealthStatus] = useState<any>(null);
  const [scheduleStatus, setScheduleStatus] = useState<NewsScheduleStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [scheduleLoading, setScheduleLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Schedule form state
  const [scheduleConfig, setScheduleConfig] = useState<ScheduleConfig>({
    schedule_type: 'hourly',
    hours: 1,
    daily_time: 9,
    custom_cron: '0 */1 * * *'
  });
  useEffect(() => {
    if (isOpen) {
      fetchData();
    }
  }, [isOpen]);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [jobsData, health, schedule] = await Promise.all([
        newsAPI.listJobs(10),
        newsAPI.healthCheck(),
        newsAPI.getNewsScheduleStatus()
      ]);
      setJobs(jobsData);
      setHealthStatus(health);
      setScheduleStatus(schedule);
      
      // Update form with current schedule config
      if (schedule?.schedule) {
        setScheduleConfig({
          schedule_type: schedule.schedule.schedule_type as 'hourly' | 'daily' | 'custom',
          hours: schedule.schedule.hours,
          daily_time: schedule.schedule.daily_time,
          custom_cron: schedule.schedule.custom_cron
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch data');
    } finally {
      setLoading(false);
    }
  };

  const handleTriggerWorkflow = async () => {
    setLoading(true);
    setError(null);
    try {
      await newsAPI.triggerNewsWorkflow();
      // Refresh jobs after triggering
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to trigger workflow');
    } finally {
      setLoading(false);
    }
  };

  const handleStartSchedule = async () => {
    setScheduleLoading(true);
    setError(null);
    try {
      await newsAPI.startNewsSchedule(scheduleConfig);
      await fetchData(); // Refresh to get updated status
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start schedule');
    } finally {
      setScheduleLoading(false);
    }
  };

  const handleStopSchedule = async () => {
    setScheduleLoading(true);
    setError(null);
    try {
      await newsAPI.stopNewsSchedule();
      await fetchData(); // Refresh to get updated status
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to stop schedule');
    } finally {
      setScheduleLoading(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'text-green-600';
      case 'failed': return 'text-red-600';
      case 'started': return 'text-blue-600';
      default: return 'text-gray-600';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed': return <CheckCircle className="w-4 h-4 text-green-600" />;
      case 'failed': return <AlertCircle className="w-4 h-4 text-red-600" />;
      case 'started': return <RotateCw className="w-4 h-4 text-blue-600 animate-spin" />;
      default: return <Activity className="w-4 h-4 text-gray-600" />;
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full mx-4 max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200">
          <h2 className="text-2xl font-bold text-gray-900">Settings & Job Management</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        <div className="p-6 overflow-y-auto max-h-[80vh]">
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-md p-4 mb-6">
              <div className="flex items-center">
                <AlertCircle className="w-5 h-5 text-red-400 mr-2" />
                <span className="text-red-700">{error}</span>
              </div>
            </div>
          )}

          {/* Health Status */}
          <div className="mb-8">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">System Health</h3>
            {healthStatus ? (
              <div className="bg-green-50 border border-green-200 rounded-md p-4">
                <div className="flex items-center">
                  <CheckCircle className="w-5 h-5 text-green-500 mr-2" />
                  <span className="text-green-800 font-medium">Service: {healthStatus.service}</span>
                </div>
                <p className="text-green-700 mt-1">Status: {healthStatus.status}</p>
                <p className="text-green-700">Last Check: {new Date(healthStatus.timestamp).toLocaleString()}</p>
              </div>
            ) : (
              <div className="bg-gray-50 border border-gray-200 rounded-md p-4">
                <span className="text-gray-600">Loading health status...</span>
              </div>
            )}
          </div>

          {/* Workflow Controls */}
          <div className="mb-8">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Manual Workflow Controls</h3>
            
            <div className="mb-4 p-4 bg-blue-50 border border-blue-200 rounded-md">
              <p className="text-sm text-blue-800">
                📝 <strong>Manual On-Demand Workflows</strong> - Process current date only
              </p>
              <p className="text-xs text-blue-600 mt-1">
                For historical dates, use the date selector in the main interface to view already processed news from the database.
              </p>
            </div>
            
            <div className="flex justify-center">
              <button
                onClick={handleTriggerWorkflow}
                disabled={loading}
                className="flex items-center justify-center space-x-2 px-6 py-3 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 transition-colors"
              >
                <Play className="w-4 h-4" />
                <span>Start News Workflow</span>
              </button>
            </div>
          </div>

          {/* Schedule Configuration */}
          <div className="mb-8">
            <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
              <Clock className="w-5 h-5 mr-2" />
              Automated Schedule Configuration
            </h3>
            
            {scheduleStatus && (
              <div className={`mb-4 p-4 border rounded-md ${
                scheduleStatus.schedule.enabled 
                  ? 'bg-green-50 border-green-200' 
                  : 'bg-gray-50 border-gray-200'
              }`}>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">
                      Status: {scheduleStatus.schedule.enabled ? 'Enabled' : 'Disabled'}
                    </p>
                    {scheduleStatus.schedule.enabled && (
                      <p className="text-xs text-gray-600 mt-1">
                        Current: {scheduleStatus.schedule.schedule_type} 
                        {scheduleStatus.schedule.schedule_type === 'hourly' && ` (every ${scheduleStatus.schedule.hours}h)`}
                        {scheduleStatus.schedule.schedule_type === 'daily' && ` (at ${scheduleStatus.schedule.daily_time}:00)`}
                        {scheduleStatus.schedule.schedule_type === 'custom' && ` (${scheduleStatus.schedule.custom_cron})`}
                      </p>
                    )}
                  </div>
                  <button
                    onClick={scheduleStatus.schedule.enabled ? handleStopSchedule : handleStartSchedule}
                    disabled={scheduleLoading}
                    className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
                      scheduleStatus.schedule.enabled
                        ? 'bg-red-100 text-red-700 hover:bg-red-200'
                        : 'bg-green-100 text-green-700 hover:bg-green-200'
                    }`}
                  >
                    {scheduleLoading ? 'Updating...' : scheduleStatus.schedule.enabled ? 'Stop' : 'Start'}
                  </button>
                </div>
              </div>
            )}

            <div className="space-y-4">
              {/* Schedule Type Selection */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Schedule Type</label>
                <select
                  value={scheduleConfig.schedule_type}
                  onChange={(e) => setScheduleConfig({
                    ...scheduleConfig, 
                    schedule_type: e.target.value as 'hourly' | 'daily' | 'custom'
                  })}
                  className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="hourly">Hourly</option>
                  <option value="daily">Daily</option>
                  <option value="custom">Custom Cron</option>
                </select>
              </div>

              {/* Hourly Configuration */}
              {scheduleConfig.schedule_type === 'hourly' && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">Every X Hours</label>
                  <input
                    type="number"
                    min="1"
                    max="24"
                    value={scheduleConfig.hours}
                    onChange={(e) => setScheduleConfig({
                      ...scheduleConfig, 
                      hours: parseInt(e.target.value) || 1
                    })}
                    className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                  />
                  <p className="text-xs text-gray-500 mt-1">Run every {scheduleConfig.hours} hours</p>
                </div>
              )}

              {/* Daily Configuration */}
              {scheduleConfig.schedule_type === 'daily' && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">Hour of Day (24h format)</label>
                  <input
                    type="number"
                    min="0"
                    max="23"
                    value={scheduleConfig.daily_time}
                    onChange={(e) => setScheduleConfig({
                      ...scheduleConfig, 
                      daily_time: parseInt(e.target.value) || 9
                    })}
                    className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                  />
                  <p className="text-xs text-gray-500 mt-1">Run daily at {scheduleConfig.daily_time}:00</p>
                </div>
              )}

              {/* Custom Cron Configuration */}
              {scheduleConfig.schedule_type === 'custom' && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">Cron Expression</label>
                  <input
                    type="text"
                    value={scheduleConfig.custom_cron}
                    onChange={(e) => setScheduleConfig({
                      ...scheduleConfig, 
                      custom_cron: e.target.value
                    })}
                    className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                    placeholder="0 */1 * * *"
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    5-part format: minute hour day month day_of_week<br/>
                    Example: "0 */2 * * *" = every 2 hours
                  </p>
                </div>
              )}

              {/* Update Schedule Button */}
              <div className="flex justify-center">
                <button
                  onClick={handleStartSchedule}
                  disabled={scheduleLoading}
                  className="flex items-center justify-center space-x-2 px-6 py-3 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 transition-colors"
                >
                  <Settings className="w-4 h-4" />
                  <span>{scheduleLoading ? 'Updating...' : 'Update Schedule'}</span>
                </button>
              </div>
            </div>
          </div>

          {/* Recent Jobs */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900">Recent Jobs</h3>
              <button
                onClick={fetchData}
                disabled={loading}
                className="flex items-center space-x-1 px-3 py-1 text-sm text-gray-600 hover:text-gray-800 border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
              >
                <RotateCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                <span>Refresh</span>
              </button>
            </div>

            {jobs.length > 0 ? (
              <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Job ID
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Status
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Created
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Completed
                        </th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {jobs.map((job) => (
                        <tr key={job.job_id} className="hover:bg-gray-50">
                          <td className="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-900">
                            {job.job_id.slice(0, 8)}...
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap">
                            <div className="flex items-center space-x-2">
                              {getStatusIcon(job.status)}
                              <span className={`text-sm font-medium ${getStatusColor(job.status)}`}>
                                {job.status}
                              </span>
                            </div>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                            {new Date(job.created_at).toLocaleString()}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                            {job.completed_at ? new Date(job.completed_at).toLocaleString() : '-'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <div className="text-center py-8 text-gray-500">
                No jobs found
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};