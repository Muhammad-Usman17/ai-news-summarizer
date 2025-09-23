import React from 'react';
import { TimelineItem } from '../types';
import { formatDistanceToNow } from 'date-fns';
import { ExternalLink, Clock, Target, List, Lightbulb } from 'lucide-react';

interface TimelineItemProps {
  item: TimelineItem;
}

const TimelineItemComponent: React.FC<TimelineItemProps> = ({ item }) => {
  const getIcon = () => {
    switch (item.type) {
      case 'news_item':
        return '📰';
      case 'summary':
        return '📰';
      case 'analysis':
        return '🔍';
      default:
        return '📄';
    }
  };

  const getBorderColor = () => {
    switch (item.type) {
      case 'news_item':
        return 'border-blue-400';
      case 'summary':
        return 'border-blue-400';
      case 'analysis':
        return 'border-green-400';
      default:
        return 'border-gray-400';
    }
  };

  const handleSourceClick = () => {
    if (item.url) {
      window.open(item.url, '_blank', 'noopener,noreferrer');
    }
  };



  return (
    <div className={`border-l-4 ${getBorderColor()} pl-6 pb-8 relative`}>
      {/* Timeline dot */}
      <div className="absolute -left-2 top-2 w-4 h-4 bg-white border-2 border-current rounded-full flex items-center justify-center text-xs">
        {getIcon()}
      </div>

      {/* Content Card */}
      <div className="bg-white rounded-lg shadow-lg hover:shadow-xl transition-shadow duration-200 overflow-hidden">
        {/* Header with Title and Timestamp */}
        <div className="p-6 pb-4">
          <div className="flex items-start justify-between mb-3">
            <h3 
              onClick={handleSourceClick}
              className={`text-xl font-bold text-gray-800 line-clamp-2 flex-1 ${
                item.url ? 'cursor-pointer hover:text-blue-600 transition-colors' : ''
              }`}
            >
              {item.title}
            </h3>
            
            {item.url && (
              <button
                onClick={handleSourceClick}
                className="ml-3 p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-all"
                title="Open source"
              >
                <ExternalLink className="w-5 h-5" />
              </button>
            )}
          </div>

          {/* Timestamp and Source */}
          <div className="flex items-center justify-between text-sm text-gray-500">
            <div className="flex items-center space-x-4">
              {item.source && (
                <span className="bg-gray-100 text-gray-700 px-3 py-1 rounded-full font-medium">
                  📡 {item.source}
                </span>
              )}
              
              <div className="flex items-center space-x-1">
                <Clock className="w-4 h-4" />
                <span>
                  {formatDistanceToNow(
                    new Date(item.published_at || item.timestamp), 
                    { addSuffix: true }
                  )}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Summary */}
        {item.summary && (
          <div className="px-6 pb-4">
            <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center">
              📄 Summary
            </h4>
            <p className="text-gray-700 leading-relaxed">{item.summary}</p>
          </div>
        )}

        {/* Key Points */}
        {item.bullet_points && item.bullet_points.length > 0 && (
          <div className="px-6 pb-4">
            <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center">
              <List className="w-4 h-4 mr-1" />
              Key Points
            </h4>
            <ul className="space-y-2">
              {item.bullet_points.map((point, index) => (
                <li key={index} className="flex items-start space-x-2">
                  <span className="w-2 h-2 bg-blue-500 rounded-full mt-2 flex-shrink-0"></span>
                  <span className="text-sm text-gray-700">{point}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Insights */}
        {item.insights && item.insights.length > 0 && (
          <div className="px-6 pb-4">
            <h4 className="text-sm font-semibold text-blue-700 mb-3 flex items-center">
              <Lightbulb className="w-4 h-4 mr-1" />
              Insights
            </h4>
            <div className="space-y-2">
              {item.insights.map((insight, index) => (
                <div key={index} className="bg-blue-50 border-l-4 border-blue-400 p-3 rounded-r">
                  <p className="text-sm text-blue-800">{insight}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Impact Assessment */}
        {item.impact_assessment && (
          <div className="px-6 pb-6">
            <h4 className="text-sm font-semibold text-green-700 mb-3 flex items-center">
              <Target className="w-4 h-4 mr-1" />
              Impact Assessment
            </h4>
            <div className="bg-green-50 border border-green-200 rounded-lg p-4">
              <p className="text-sm text-green-800 leading-relaxed">{item.impact_assessment}</p>
            </div>
          </div>
        )}

        {/* Footer with additional metadata */}
        {item.published_at && (
          <div className="bg-gray-50 px-6 py-3 border-t">
            <p className="text-xs text-gray-500">
              Published: {new Date(item.published_at).toLocaleDateString('en-US', {
                year: 'numeric',
                month: 'long', 
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
              })}
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default TimelineItemComponent;