import React, { useState, useRef, useEffect, useMemo } from 'react';
import { Calendar, ChevronLeft, ChevronRight, X, Check } from 'lucide-react';

interface CalendarDateRangePickerProps {
  startDate: string; // 'YYYY-MM-DD'
  endDate: string;   // 'YYYY-MM-DD'
  onChange: (start: string, end: string) => void;
  mode?: 'upcoming' | 'ledger';
  label?: string;
}

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

const DAYS_OF_WEEK = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'];

function formatDisplayDate(dStr: string): string {
  if (!dStr) return '';
  const parts = dStr.split('-');
  if (parts.length !== 3) return dStr;
  const year = parts[0];
  const monthIdx = parseInt(parts[1], 10) - 1;
  const day = parseInt(parts[2], 10);
  const mName = MONTH_NAMES[monthIdx]?.slice(0, 3) || parts[1];
  return `${mName} ${day}, ${year}`;
}

function toDateString(year: number, month: number, day: number): string {
  const mStr = String(month + 1).padStart(2, '0');
  const dStr = String(day).padStart(2, '0');
  return `${year}-${mStr}-${dStr}`;
}

export const CalendarDateRangePicker: React.FC<CalendarDateRangePickerProps> = ({
  startDate,
  endDate,
  onChange,
  mode = 'upcoming',
  label = 'Calendar Date Range',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [hoverDate, setHoverDate] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Determine initial view month and year
  const initialDate = useMemo(() => {
    if (startDate) {
      const parts = startDate.split('-');
      return new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, 1);
    }
    return new Date();
  }, [startDate]);

  const [viewYear, setViewYear] = useState(initialDate.getFullYear());
  const [viewMonth, setViewMonth] = useState(initialDate.getMonth());

  // Close when clicking outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  // Navigate months
  const handlePrevMonth = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (viewMonth === 0) {
      setViewMonth(11);
      setViewYear((y) => y - 1);
    } else {
      setViewMonth((m) => m - 1);
    }
  };

  const handleNextMonth = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (viewMonth === 11) {
      setViewMonth(0);
      setViewYear((y) => y + 1);
    } else {
      setViewMonth((m) => m + 1);
    }
  };

  // Calendar days computation
  const daysInMonth = useMemo(() => {
    return new Date(viewYear, viewMonth + 1, 0).getDate();
  }, [viewYear, viewMonth]);

  const firstDayOfWeek = useMemo(() => {
    // getDay returns 0 for Sunday. We want Monday=0, Sunday=6
    const day = new Date(viewYear, viewMonth, 1).getDay();
    return day === 0 ? 6 : day - 1;
  }, [viewYear, viewMonth]);

  // Handle Day Click
  const handleDayClick = (day: number) => {
    const clickedDateStr = toDateString(viewYear, viewMonth, day);

    if (!startDate || (startDate && endDate)) {
      // Start a fresh range
      onChange(clickedDateStr, '');
    } else if (startDate && !endDate) {
      if (clickedDateStr < startDate) {
        // Clicked before start date -> make this the new start
        onChange(clickedDateStr, '');
      } else {
        // Complete the range
        onChange(startDate, clickedDateStr);
        setIsOpen(false);
      }
    }
  };

  // Presets
  const applyPreset = (presetKey: string) => {
    const today = new Date();
    const todayStr = toDateString(today.getFullYear(), today.getMonth(), today.getDate());

    const addDays = (d: Date, n: number) => {
      const res = new Date(d);
      res.setDate(res.getDate() + n);
      return toDateString(res.getFullYear(), res.getMonth(), res.getDate());
    };

    switch (presetKey) {
      case 'all':
        onChange('', '');
        break;
      case 'today':
        onChange(todayStr, todayStr);
        break;
      case 'next7':
        onChange(todayStr, addDays(today, 7));
        break;
      case 'next14':
        onChange(todayStr, addDays(today, 14));
        break;
      case 'next30':
        onChange(todayStr, addDays(today, 30));
        break;
      case 'last7':
        onChange(addDays(today, -7), todayStr);
        break;
      case 'last30':
        onChange(addDays(today, -30), todayStr);
        break;
      case 'last90':
        onChange(addDays(today, -90), todayStr);
        break;
      case 'this_month': {
        const startMonth = toDateString(today.getFullYear(), today.getMonth(), 1);
        const endMonth = toDateString(today.getFullYear(), today.getMonth(), new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate());
        onChange(startMonth, endMonth);
        break;
      }
      default:
        break;
    }
    setIsOpen(false);
  };

  const hasActiveRange = Boolean(startDate || endDate);

  const displayLabel = useMemo(() => {
    if (startDate && endDate) {
      if (startDate === endDate) return formatDisplayDate(startDate);
      return `${formatDisplayDate(startDate)} — ${formatDisplayDate(endDate)}`;
    }
    if (startDate) return `From ${formatDisplayDate(startDate)}`;
    if (endDate) return `Until ${formatDisplayDate(endDate)}`;
    return 'All Dates (Calendar)';
  }, [startDate, endDate]);

  return (
    <div className="relative" ref={containerRef}>
      {label && (
        <label className="block text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-1 flex items-center justify-between">
          <span>📅 {label}</span>
          {hasActiveRange && (
            <span className="text-[10px] text-emerald-400 font-mono font-normal">Active</span>
          )}
        </label>
      )}

      {/* Trigger Button */}
      <div className="relative flex items-center">
        <button
          type="button"
          onClick={() => setIsOpen(!isOpen)}
          className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-semibold transition-all border ${
            hasActiveRange
              ? 'bg-emerald-500/10 border-emerald-500/40 text-emerald-300 shadow-sm'
              : 'bg-dark-900 border-dark-700 text-slate-300 hover:border-slate-600 hover:text-white'
          }`}
        >
          <div className="flex items-center space-x-2 truncate">
            <Calendar className={`w-3.5 h-3.5 flex-shrink-0 ${hasActiveRange ? 'text-emerald-400' : 'text-slate-400'}`} />
            <span className="truncate">{displayLabel}</span>
          </div>

          <div className="flex items-center space-x-1 flex-shrink-0 ml-1">
            {hasActiveRange && (
              <span
                role="button"
                tabIndex={0}
                onClick={(e) => {
                  e.stopPropagation();
                  onChange('', '');
                }}
                className="p-0.5 rounded hover:bg-dark-800 text-slate-400 hover:text-white"
                title="Clear date filter"
              >
                <X className="w-3 h-3" />
              </span>
            )}
          </div>
        </button>
      </div>

      {/* Calendar Dropdown Popover */}
      {isOpen && (
        <div className="absolute left-0 top-full mt-1 z-50 w-72 sm:w-80 bg-dark-900 border border-dark-700 rounded-2xl shadow-2xl p-4 space-y-3 animate-in fade-in zoom-in-95 duration-150">
          {/* Quick Presets Bar */}
          <div className="flex flex-wrap gap-1 pb-2 border-b border-dark-800">
            {mode === 'upcoming' ? (
              <>
                <button
                  onClick={() => applyPreset('all')}
                  className={`px-2 py-1 rounded text-[10px] font-bold border transition-colors ${
                    !hasActiveRange ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40' : 'bg-dark-800 text-slate-400 border-dark-700 hover:text-white'
                  }`}
                >
                  All Dates
                </button>
                <button
                  onClick={() => applyPreset('today')}
                  className="px-2 py-1 rounded text-[10px] font-bold bg-dark-800 text-slate-300 border border-dark-700 hover:bg-dark-700 hover:text-white"
                >
                  Today
                </button>
                <button
                  onClick={() => applyPreset('next7')}
                  className="px-2 py-1 rounded text-[10px] font-bold bg-dark-800 text-slate-300 border border-dark-700 hover:bg-dark-700 hover:text-white"
                >
                  Next 7 Days
                </button>
                <button
                  onClick={() => applyPreset('next14')}
                  className="px-2 py-1 rounded text-[10px] font-bold bg-dark-800 text-slate-300 border border-dark-700 hover:bg-dark-700 hover:text-white"
                >
                  Next 14 Days
                </button>
                <button
                  onClick={() => applyPreset('next30')}
                  className="px-2 py-1 rounded text-[10px] font-bold bg-dark-800 text-slate-300 border border-dark-700 hover:bg-dark-700 hover:text-white"
                >
                  Next 30 Days
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={() => applyPreset('all')}
                  className={`px-2 py-1 rounded text-[10px] font-bold border transition-colors ${
                    !hasActiveRange ? 'bg-sky-500/20 text-sky-300 border-sky-500/40' : 'bg-dark-800 text-slate-400 border-dark-700 hover:text-white'
                  }`}
                >
                  All Time
                </button>
                <button
                  onClick={() => applyPreset('last7')}
                  className="px-2 py-1 rounded text-[10px] font-bold bg-dark-800 text-slate-300 border border-dark-700 hover:bg-dark-700 hover:text-white"
                >
                  Last 7 Days
                </button>
                <button
                  onClick={() => applyPreset('last30')}
                  className="px-2 py-1 rounded text-[10px] font-bold bg-dark-800 text-slate-300 border border-dark-700 hover:bg-dark-700 hover:text-white"
                >
                  Last 30 Days
                </button>
                <button
                  onClick={() => applyPreset('this_month')}
                  className="px-2 py-1 rounded text-[10px] font-bold bg-dark-800 text-slate-300 border border-dark-700 hover:bg-dark-700 hover:text-white"
                >
                  This Month
                </button>
                <button
                  onClick={() => applyPreset('last90')}
                  className="px-2 py-1 rounded text-[10px] font-bold bg-dark-800 text-slate-300 border border-dark-700 hover:bg-dark-700 hover:text-white"
                >
                  Last 90 Days
                </button>
              </>
            )}
          </div>

          {/* Month & Year Navigation */}
          <div className="flex items-center justify-between px-1">
            <button
              onClick={handlePrevMonth}
              className="p-1 rounded-lg hover:bg-dark-800 text-slate-400 hover:text-white transition-colors"
              title="Previous Month"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>

            <div className="text-xs font-bold text-white font-mono">
              {MONTH_NAMES[viewMonth]} {viewYear}
            </div>

            <button
              onClick={handleNextMonth}
              className="p-1 rounded-lg hover:bg-dark-800 text-slate-400 hover:text-white transition-colors"
              title="Next Month"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          {/* Day of week headers */}
          <div className="grid grid-cols-7 gap-1 text-center">
            {DAYS_OF_WEEK.map((d) => (
              <div key={d} className="text-[10px] font-bold text-slate-500 uppercase">
                {d}
              </div>
            ))}
          </div>

          {/* Days Grid */}
          <div className="grid grid-cols-7 gap-1">
            {/* Blank offset tiles for first day */}
            {Array.from({ length: firstDayOfWeek }).map((_, i) => (
              <div key={`blank-${i}`} className="h-7" />
            ))}

            {/* Day tiles */}
            {Array.from({ length: daysInMonth }).map((_, i) => {
              const day = i + 1;
              const dateStr = toDateString(viewYear, viewMonth, day);

              const isStart = startDate === dateStr;
              const isEnd = endDate === dateStr;
              const isSelected = isStart || isEnd;

              const activeEnd = endDate || (startDate && !endDate ? hoverDate : null);
              const isInRange = Boolean(
                startDate &&
                activeEnd &&
                dateStr > startDate &&
                dateStr < activeEnd
              );

              return (
                <button
                  key={day}
                  type="button"
                  onClick={() => handleDayClick(day)}
                  onMouseEnter={() => {
                    if (startDate && !endDate) {
                      setHoverDate(dateStr);
                    }
                  }}
                  onMouseLeave={() => setHoverDate(null)}
                  className={`h-7 w-full text-xs font-semibold rounded-lg flex items-center justify-center transition-all ${
                    isSelected
                      ? 'bg-emerald-500 text-white font-bold shadow-md shadow-emerald-900/40 scale-105'
                      : isInRange
                      ? 'bg-emerald-500/20 text-emerald-200 rounded-none'
                      : 'text-slate-300 hover:bg-dark-800 hover:text-white'
                  }`}
                >
                  {day}
                </button>
              );
            })}
          </div>

          {/* Footer status & Actions */}
          <div className="pt-2 border-t border-dark-800 flex items-center justify-between text-xs">
            <div className="text-[11px] text-slate-400 truncate max-w-[170px]">
              {startDate && !endDate && (
                <span className="text-amber-400 font-medium animate-pulse">Pick end date...</span>
              )}
              {startDate && endDate && (
                <span className="text-emerald-400 font-mono text-[10px]">{startDate} to {endDate}</span>
              )}
              {!startDate && !endDate && (
                <span className="text-slate-500 text-[10px]">Click any date to start</span>
              )}
            </div>

            <div className="flex items-center space-x-1.5">
              {hasActiveRange && (
                <button
                  type="button"
                  onClick={() => {
                    onChange('', '');
                    setIsOpen(false);
                  }}
                  className="px-2 py-1 text-[10px] font-bold text-slate-400 hover:text-white rounded hover:bg-dark-800"
                >
                  Reset
                </button>
              )}
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="px-2.5 py-1 text-[10px] font-bold bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg flex items-center space-x-1 shadow-sm"
              >
                <Check className="w-3 h-3" />
                <span>Done</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

