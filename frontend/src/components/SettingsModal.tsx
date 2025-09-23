import React, { useState, useEffect } from 'react';
import { X, Play, RotateCw, Users, Activity, AlertCircle, CheckCircle } from 'lucide-react';
import { newsAPI } from '../api';
import { NewsJob } from '../types';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({ isOpen, onClose }) => {
  const [jobs, setJobs] = useState<NewsJob[]>([]);
  const [healthStatus, setHealthStatus] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState<string>(new Date().toISOString().split('T')[0]);

  useEffect(() => {
    if (isOpen) {
      fetchData();
    }
  }, [isOpen]);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [jobsData, health] = await Promise.all([
        newsAPI.listJobs(10),
        newsAPI.healthCheck()
      ]);
      setJobs(jobsData);
      setHealthStatus(health);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch data');
    } finally {
      setLoading(false);
    }
  };

  const handleTriggerWorkflow = async (isMultiAgent: boolean = false) => {
    setLoading(true);
    setError(null);
    try {
      if (isMultiAgent) {
        await newsAPI.triggerMultiAgentWorkflow(selectedDate);
      } else {
        await newsAPI.triggerNewsWorkflowWithDate(selectedDate);
      }
      // Refresh jobs after triggering
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to trigger workflow');
    } finally {
      setLoading(false);
    }
  };

  const handleDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newDate = e.target.value;
    // Prevent selecting future dates
    const today = new Date().toISOString().split('T')[0];
    if (newDate > today) {
      setError('Cannot select future dates for news scraping');
      return;
    }
    setError(null);
    setSelectedDate(newDate);
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
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Workflow Controls</h3>
            
            {/* Date Selection */}
            <div className="mb-4">
              <label htmlFor="workflow-date" className="block text-sm font-medium text-gray-700 mb-2">
                Select Date for News Scraping:
              </label>
              <input
                id="workflow-date"
                type="date"
                value={selectedDate}
                onChange={handleDateChange}
                max={new Date().toISOString().split('T')[0]}
                className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
              <p className="text-xs text-gray-500 mt-1">
                Choose a date to scrape historical news. Current date is selected by default.
              </p>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <button
                onClick={() => handleTriggerWorkflow(false)}
                disabled={loading}
                className="flex items-center justify-center space-x-2 px-4 py-3 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 transition-colors"
              >
                <Play className="w-4 h-4" />
                <span>Start Traditional Workflow</span>
              </button>
              
              <button
                onClick={() => handleTriggerWorkflow(true)}
                disabled={loading}
                className="flex items-center justify-center space-x-2 px-4 py-3 bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:bg-gray-400 transition-colors"
              >
                <Users className="w-4 h-4" />
                <span>Start Multi-Agent Workflow</span>
              </button>
            </div>
            
            {selectedDate !== new Date().toISOString().split('T')[0] && (
              <div className="mt-2 p-2 bg-yellow-50 border border-yellow-200 rounded-md">
                <p className="text-sm text-yellow-800">
                  📅 Historical date selected: {new Date(selectedDate).toLocaleDateString()}
                </p>
              </div>
            )}
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