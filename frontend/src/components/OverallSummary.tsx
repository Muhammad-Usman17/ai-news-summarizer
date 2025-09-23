import React from 'react';
import { OverallSummary } from '../types';
import { TrendingUp, Hash, Target, Calendar } from 'lucide-react';

interface OverallSummaryProps {
  summary: OverallSummary;
  selectedDate?: string;
}

export const OverallSummaryComponent: React.FC<OverallSummaryProps> = ({ 
  summary, 
  selectedDate 
}) => {
  const formatDate = (dateString?: string) => {
    if (!dateString) return 'Today';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { 
      weekday: 'long', 
      year: 'numeric', 
      month: 'long', 
      day: 'numeric' 
    });
  };

  return (
    <div className="bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-lg p-6 mb-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-2">
          <TrendingUp className="w-6 h-6 text-blue-600" />
          <h2 className="text-xl font-bold text-gray-800">News Overview</h2>
        </div>
        
        <div className="flex items-center space-x-2 text-sm text-gray-600">
          <Calendar className="w-4 h-4" />
          <span>{formatDate(selectedDate)}</span>
          <span className="bg-blue-100 text-blue-800 px-2 py-1 rounded-full text-xs font-medium">
            {summary.news_count} articles
          </span>
        </div>
      </div>

      {/* Main Summary */}
      <div className="mb-4">
        <p className="text-gray-700 leading-relaxed">
          {summary.summary}
        </p>
      </div>

      {/* Key Themes and Impact in a Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Key Themes */}
        {summary.key_themes && summary.key_themes.length > 0 && (
          <div>
            <div className="flex items-center space-x-2 mb-3">
              <Hash className="w-4 h-4 text-indigo-600" />
              <h3 className="font-semibold text-gray-800">Key Themes</h3>
            </div>
            <ul className="space-y-2">
              {summary.key_themes.map((theme, index) => (
                <li key={index} className="flex items-start space-x-2">
                  <span className="w-2 h-2 bg-indigo-400 rounded-full mt-2 flex-shrink-0"></span>
                  <span className="text-sm text-gray-700">{theme}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Impact Overview */}
        {summary.impact_overview && (
          <div>
            <div className="flex items-center space-x-2 mb-3">
              <Target className="w-4 h-4 text-green-600" />
              <h3 className="font-semibold text-gray-800">Impact Overview</h3>
            </div>
            <div className="bg-white rounded-md p-3 border border-green-200">
              <p className="text-sm text-gray-700 leading-relaxed">
                {summary.impact_overview}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default OverallSummaryComponent;