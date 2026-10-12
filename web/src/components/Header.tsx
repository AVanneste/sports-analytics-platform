import React, { useState } from 'react';
import { Settings, Trophy } from 'lucide-react';
import { TIME_ZONES } from '../time';

interface HeaderProps {
  sport: 'football' | 'tennis';
  setSport: (sport: 'football' | 'tennis') => void;
  lastUpdated?: string;
  timeZone: string;
  setTimeZone: (tz: string) => void;
}

export const Header: React.FC<HeaderProps> = ({ sport, setSport, lastUpdated, timeZone, setTimeZone }) => {
  const [showSettings, setShowSettings] = useState(false);
  return (
    <header className="border-b border-dark-700/80 bg-dark-800/80 backdrop-blur-md sticky top-0 z-50 shadow-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-emerald-500 via-teal-500 to-sky-500 flex items-center justify-center shadow-lg shadow-emerald-500/20">
            <Trophy className="w-5 h-5 text-dark-900 font-bold" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="font-extrabold text-base tracking-tight text-white">Belgian Odds Alerts</span>
            </div>
            <p className="text-[11px] text-slate-400 font-medium">Napoleon, Unibet & Bingoal vs Pinnacle · match models · scouting</p>
          </div>
        </div>

        {/* Sport Switcher */}
        <div className="flex items-center space-x-2">
          <div className="flex bg-dark-900/80 p-1 rounded-xl border border-dark-700">
            <button
              onClick={() => setSport('football')}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                sport === 'football' ? 'bg-emerald-500 text-dark-900 shadow-md' : 'text-slate-400 hover:text-white'
              }`}
            >
              <span>⚽</span>
              <span>Football</span>
            </button>
            <button
              onClick={() => setSport('tennis')}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                sport === 'tennis' ? 'bg-sky-500 text-dark-900 shadow-md' : 'text-slate-400 hover:text-white'
              }`}
            >
              <span>🎾</span>
              <span>Tennis</span>
            </button>
          </div>

          {/* Settings */}
          <div className="relative">
            <button
              onClick={() => setShowSettings((o) => !o)}
              title="Settings"
              className="p-2 rounded-lg border border-dark-700 bg-dark-900/80 text-slate-400 hover:text-white transition-all"
            >
              <Settings className="w-4 h-4" />
            </button>
            {showSettings && (
              <div className="absolute right-0 mt-2 w-64 bg-dark-800 border border-dark-700 rounded-xl p-3 shadow-xl space-y-2">
                <label className="block text-[11px] font-bold text-slate-400 uppercase tracking-wider">Time zone for kickoffs</label>
                <select
                  value={timeZone}
                  onChange={(e) => setTimeZone(e.target.value)}
                  className="w-full bg-dark-900 border border-dark-700 rounded-lg px-3 py-2 text-xs font-semibold text-slate-200 focus:outline-none focus:border-emerald-500"
                >
                  {TIME_ZONES.map((tz) => (
                    <option key={tz} value={tz}>
                      {tz}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
};
