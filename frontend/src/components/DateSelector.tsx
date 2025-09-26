import React, { useState, useEffect } from 'react';
import { RefreshCw, Calendar, Settings, ChevronLeft, ChevronRight } from 'lucide-react';

interface DateSelectorProps {
  selectedDate: string;
  onDateChange: (date: string) => void;
  onSyncClick: () => void;
  onSettingsClick: () => void;
  isLoading: boolean;
}

export const DateSelector: React.FC<DateSelectorProps> = ({
  selectedDate,
  onDateChange,
  onSyncClick,
  onSettingsClick,
  isLoading
}) => {
  const [isToday, setIsToday] = useState(false);
  const [isEarliest, setIsEarliest] = useState(false);

  // Check if selected date is today
  useEffect(() => {
    try {
      const today = new Date();
      const year = today.getFullYear();
      const month = String(today.getMonth() + 1).padStart(2, '0');
      const day = String(today.getDate()).padStart(2, '0');
      const todayString = `${year}-${month}-${day}`;
      
      setIsToday(selectedDate === todayString);
      
      // You might want to set a reasonable earliest date based on your data
      // For now, let's assume we have data going back 30 days
      const thirtyDaysAgo = new Date();
      thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
      const earliestYear = thirtyDaysAgo.getFullYear();
      const earliestMonth = String(thirtyDaysAgo.getMonth() + 1).padStart(2, '0');
      const earliestDay = String(thirtyDaysAgo.getDate()).padStart(2, '0');
      const earliestDate = `${earliestYear}-${earliestMonth}-${earliestDay}`;
      
      setIsEarliest(selectedDate <= earliestDate);
    } catch (error) {
      console.error('Error in useEffect for date checking:', error);
      setIsToday(false);
      setIsEarliest(false);
    }
  }, [selectedDate]);

  const formatDateForInput = (dateString: string) => {
    try {
      // If it's already in YYYY-MM-DD format, return as is
      if (/^\d{4}-\d{2}-\d{2}$/.test(dateString)) {
        return dateString;
      }
      
      // Otherwise try to parse and format
      const dateParts = dateString.split('-');
      if (dateParts.length === 3) {
        const year = parseInt(dateParts[0], 10);
        const month = String(parseInt(dateParts[1], 10)).padStart(2, '0');
        const day = String(parseInt(dateParts[2], 10)).padStart(2, '0');
        return `${year}-${month}-${day}`;
      }
      
      // Fallback to current date
      const today = new Date();
      const year = today.getFullYear();
      const month = String(today.getMonth() + 1).padStart(2, '0');
      const day = String(today.getDate()).padStart(2, '0');
      return `${year}-${month}-${day}`;
    } catch (error) {
      console.error('Error formatting date for input:', error);
      // Return current date as fallback
      const today = new Date();
      const year = today.getFullYear();
      const month = String(today.getMonth() + 1).padStart(2, '0');
      const day = String(today.getDate()).padStart(2, '0');
      return `${year}-${month}-${day}`;
    }
  };

  const handleDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newDate = e.target.value;
    onDateChange(newDate);
  };

  const navigateDate = (direction: 'prev' | 'next') => {
    try {
      // Parse the current date more carefully
      const dateParts = selectedDate.split('-');
      if (dateParts.length !== 3) {
        console.error('Invalid date format:', selectedDate);
        return;
      }
      
      const year = parseInt(dateParts[0], 10);
      const month = parseInt(dateParts[1], 10) - 1; // Month is 0-indexed in Date constructor
      const day = parseInt(dateParts[2], 10);
      
      // Create date object with explicit values to avoid timezone issues
      const currentDate = new Date(year, month, day);
      
      // Check if the date is valid
      if (isNaN(currentDate.getTime())) {
        console.error('Invalid date created from:', selectedDate);
        return;
      }
      
      if (direction === 'prev') {
        currentDate.setDate(currentDate.getDate() - 1);
      } else {
        currentDate.setDate(currentDate.getDate() + 1);
      }
      
      // Format the new date back to YYYY-MM-DD
      const newYear = currentDate.getFullYear();
      const newMonth = String(currentDate.getMonth() + 1).padStart(2, '0');
      const newDay = String(currentDate.getDate()).padStart(2, '0');
      const newDateString = `${newYear}-${newMonth}-${newDay}`;
      
      onDateChange(newDateString);
    } catch (error) {
      console.error('Error navigating date:', error);
    }
  };

  const goToToday = () => {
    const today = new Date();
    const year = today.getFullYear();
    const month = String(today.getMonth() + 1).padStart(2, '0');
    const day = String(today.getDate()).padStart(2, '0');
    const todayString = `${year}-${month}-${day}`;
    onDateChange(todayString);
  };

  const formatDisplayDate = (dateString: string) => {
    try {
      // Parse the date string more safely
      const dateParts = dateString.split('-');
      if (dateParts.length !== 3) {
        return dateString; // Return original if parsing fails
      }
      
      const year = parseInt(dateParts[0], 10);
      const month = parseInt(dateParts[1], 10) - 1; // Month is 0-indexed
      const day = parseInt(dateParts[2], 10);
      
      const date = new Date(year, month, day);
      
      // Check if date is valid
      if (isNaN(date.getTime())) {
        return dateString; // Return original if invalid
      }
      
      const today = new Date();
      const yesterday = new Date(today);
      yesterday.setDate(yesterday.getDate() - 1);
      
      // Compare dates by creating date strings to avoid time component issues
      const dateStr = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
      const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
      const yesterdayStr = `${yesterday.getFullYear()}-${String(yesterday.getMonth() + 1).padStart(2, '0')}-${String(yesterday.getDate()).padStart(2, '0')}`;
      
      if (dateStr === todayStr) {
        return 'Today';
      } else if (dateStr === yesterdayStr) {
        return 'Yesterday';
      } else {
        return date.toLocaleDateString('en-US', { 
          weekday: 'short',
          month: 'short', 
          day: 'numeric',
          year: date.getFullYear() !== today.getFullYear() ? 'numeric' : undefined
        });
      }
    } catch (error) {
      console.error('Error formatting display date:', error);
      return dateString; // Return original string if anything fails
    }
  };

  return (
    <div className="flex items-center justify-between p-4 bg-white border-b border-gray-200">
      <div className="flex items-center space-x-4">
        {/* Enhanced Date Navigation */}
        <div className="flex items-center space-x-2 bg-gray-50 rounded-lg p-2">
          {/* Previous Day Button */}
          <button
            onClick={() => navigateDate('prev')}
            disabled={isEarliest || isLoading}
            className={`p-2 rounded-md transition-colors ${
              isEarliest || isLoading
                ? 'text-gray-400 cursor-not-allowed'
                : 'text-gray-600 hover:text-gray-800 hover:bg-white'
            }`}
            title="Previous day"
          >
            <ChevronLeft className="w-5 h-5" />
          </button>

          {/* Date Display and Picker */}
          <div className="relative group">
            <div className={`flex items-center space-x-2 px-3 py-2 bg-white border border-gray-200 rounded-md min-w-[180px] justify-center ${
              isLoading ? 'opacity-50' : ''
            }`}>
              {isLoading ? (
                <RefreshCw className="w-4 h-4 text-blue-500 animate-spin" />
              ) : (
                <Calendar className="w-4 h-4 text-gray-500" />
              )}
              <span className="font-medium text-gray-900">
                {formatDisplayDate(selectedDate)}
              </span>
            </div>
            
            {/* Hidden date input that shows on click */}
            <input
              type="date"
              value={formatDateForInput(selectedDate)}
              onChange={handleDateChange}
              max={new Date().toISOString().split('T')[0]}
              disabled={isLoading}
              className="absolute inset-0 opacity-0 cursor-pointer disabled:cursor-not-allowed"
              title="Click to select a date"
            />
          </div>

          {/* Next Day Button */}
          <button
            onClick={() => navigateDate('next')}
            disabled={isToday || isLoading}
            className={`p-2 rounded-md transition-colors ${
              isToday || isLoading
                ? 'text-gray-400 cursor-not-allowed'
                : 'text-gray-600 hover:text-gray-800 hover:bg-white'
            }`}
            title="Next day"
          >
            <ChevronRight className="w-5 h-5" />
          </button>
        </div>

        {/* Quick Today Button */}
        {!isToday && (
          <button
            onClick={goToToday}
            className="px-3 py-2 text-sm text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded-md transition-colors"
          >
            Today
          </button>
        )}
        
        {/* Sync Button */}
        <button
          onClick={onSyncClick}
          disabled={isLoading}
          className={`flex items-center space-x-2 px-4 py-2 rounded-md text-white font-medium transition-colors ${
            isLoading
              ? 'bg-gray-400 cursor-not-allowed'
              : 'bg-blue-600 hover:bg-blue-700'
          }`}
        >
          <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          <span>{isLoading ? 'Syncing...' : 'Sync News'}</span>
        </button>
      </div>

      <button
        onClick={onSettingsClick}
        className="flex items-center space-x-2 px-3 py-2 text-gray-600 hover:text-gray-800 hover:bg-gray-100 rounded-md transition-colors"
      >
        <Settings className="w-5 h-5" />
        <span>Settings</span>
      </button>
    </div>
  );
};